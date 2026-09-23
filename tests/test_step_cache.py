"""
Unit tests for the TOPP step cache (src/workflow/StepCache.py) and its
integration into CommandExecutor.run_topp().

Covers: key construction/reuse, the filename-only input identity policy
(never reads file content), dependency chaining between steps, corruption /
missing-output handling, and the step-cache-enabled toggle in params.json.

See docs/step-cache.md / docs/topp-cache-handoff.ko.md for the full design.
"""
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

# Mock streamlit/pyopenms the same way test_topp_flag_parameters.py does, so
# this file can run without those heavy deps installed.
mock_streamlit = MagicMock()
mock_streamlit.session_state = {}

_original_streamlit = sys.modules.get("streamlit")
_original_pyopenms = sys.modules.get("pyopenms")
sys.modules["streamlit"] = mock_streamlit
if _original_pyopenms is None:
    sys.modules["pyopenms"] = MagicMock()

from src.workflow.ParameterManager import ParameterManager
from src.workflow.CommandExecutor import CommandExecutor
from src.workflow.StepCache import StepCache
from src.workflow.progress import read_progress, failures

# Restore the original modules so other test files import the real ones. The
# classes imported above keep their module-level `st`/`poms` bound to the
# mocks, which is what we want here too. Also pop the cached src.workflow.*
# modules so that *other* test files (which do their own mocking, e.g.
# test_topp_flag_parameters.py) re-import fresh instead of inheriting a
# module already bound to this file's mock objects (or, after restoration,
# to the real streamlit).
if _original_streamlit is not None:
    sys.modules["streamlit"] = _original_streamlit
else:
    sys.modules.pop("streamlit", None)
if _original_pyopenms is None:
    sys.modules.pop("pyopenms", None)

for _key in list(sys.modules.keys()):
    if _key.startswith("src.workflow"):
        sys.modules.pop(_key, None)


@pytest.fixture(autouse=True)
def reset_session_state():
    mock_streamlit.session_state = {}
    yield
    mock_streamlit.session_state = {}


@pytest.fixture
def fake_tool(tmp_path):
    """A fake 'tool' executable that never gets invoked by these tests
    (run_command is mocked), used only so _executable_identity() has a real
    file to hash instead of silently failing."""
    tool_path = tmp_path / "FakeTool"
    tool_path.write_bytes(b"#!/bin/sh\necho fake tool\n")
    tool_path.chmod(0o755)
    return str(tool_path)


def make_executor(workflow_dir: Path, params_json: dict = None) -> CommandExecutor:
    pm = ParameterManager(workflow_dir)
    with open(pm.params_file, "w", encoding="utf-8") as f:
        json.dump(dict(params_json or {}, max_threads=1), f)
    return CommandExecutor(workflow_dir, MagicMock(), pm)


# ============================== StepCache core ==============================


class TestConditionHash:
    def test_same_condition_same_hash(self, tmp_path):
        cache = StepCache(tmp_path)
        digest1, _ = cache.condition_hash(
            tool="Comet",
            input_paths=["a.mzML"],
            output_paths=["a.idXML"],
            effective_params={"x": 1},
            threads=4,
        )
        digest2, _ = cache.condition_hash(
            tool="Comet",
            input_paths=["a.mzML"],
            output_paths=["a.idXML"],
            effective_params={"x": 1},
            threads=4,
        )
        assert digest1 == digest2

    def test_param_change_changes_hash(self, tmp_path):
        cache = StepCache(tmp_path)
        digest1, _ = cache.condition_hash(
            "Comet", ["a.mzML"], ["a.idXML"], {"x": 1}, 4
        )
        digest2, _ = cache.condition_hash(
            "Comet", ["a.mzML"], ["a.idXML"], {"x": 2}, 4
        )
        assert digest1 != digest2

    def test_threads_change_changes_hash(self, tmp_path):
        cache = StepCache(tmp_path)
        digest1, _ = cache.condition_hash(
            "Comet", ["a.mzML"], ["a.idXML"], {"x": 1}, 4
        )
        digest2, _ = cache.condition_hash(
            "Comet", ["a.mzML"], ["a.idXML"], {"x": 1}, 8
        )
        assert digest1 != digest2

    def test_input_basename_only_ignores_directory(self, tmp_path):
        """Same basename in a different folder -> identical input identity."""
        cache = StepCache(tmp_path)
        digest1, _ = cache.condition_hash(
            "Comet", ["/data/run1/sample.mzML"], ["a.idXML"], {}, 1
        )
        digest2, _ = cache.condition_hash(
            "Comet", ["/data/run2/sample.mzML"], ["a.idXML"], {}, 1
        )
        assert digest1 == digest2

    def test_different_basename_changes_hash(self, tmp_path):
        cache = StepCache(tmp_path)
        digest1, _ = cache.condition_hash(
            "Comet", ["sample1.mzML"], ["a.idXML"], {}, 1
        )
        digest2, _ = cache.condition_hash(
            "Comet", ["sample2.mzML"], ["a.idXML"], {}, 1
        )
        assert digest1 != digest2

    def test_upstream_key_propagates(self, tmp_path):
        cache = StepCache(tmp_path)
        digest1, _ = cache.condition_hash(
            "Percolator", ["a.idXML"], ["a.perc.idXML"], {}, 1,
            upstream_keys=["hash-A"],
        )
        digest2, _ = cache.condition_hash(
            "Percolator", ["a.idXML"], ["a.perc.idXML"], {}, 1,
            upstream_keys=["hash-B"],
        )
        assert digest1 != digest2

    def test_condition_hash_never_reads_input_file_content(self, tmp_path):
        """Key construction must not touch the input files at all -- only
        their basenames -- even when they exist and are readable."""
        big_input = tmp_path / "huge.mzML"
        big_input.write_bytes(b"x" * 1024)

        real_open = open

        def guarded_open(*a, **k):
            if str(big_input) in str(a):
                pytest.fail("condition_hash must not open any file")
            return real_open(*a, **k)

        with patch("builtins.open", side_effect=guarded_open):
            cache = StepCache(tmp_path)
            cache.condition_hash(
                "NonexistentTool12345", [str(big_input)], ["out.idXML"], {}, 1
            )


class TestCacheHitMiss:
    def test_miss_when_no_manifest(self, tmp_path):
        cache = StepCache(tmp_path)
        assert cache.try_restore("Comet", "deadbeef", [str(tmp_path / "out.idXML")]) is False

    def test_publish_then_restore_roundtrip(self, tmp_path):
        cache = StepCache(tmp_path)
        out_file = tmp_path / "out.idXML"
        out_file.write_text("original content")

        digest, condition = cache.condition_hash(
            "Comet", ["in.mzML"], [str(out_file)], {}, 1
        )
        assert cache.publish("Comet", digest, condition, [str(out_file)]) is True

        # Simulate the output being removed/reset, then restored from cache.
        out_file.unlink()
        assert cache.try_restore("Comet", digest, [str(out_file)]) is True
        assert out_file.read_text() == "original content"

    def test_publish_fails_if_declared_output_missing(self, tmp_path):
        cache = StepCache(tmp_path)
        missing_output = tmp_path / "missing.idXML"
        digest, condition = cache.condition_hash(
            "Comet", ["in.mzML"], [str(missing_output)], {}, 1
        )
        assert cache.publish("Comet", digest, condition, [str(missing_output)]) is False
        # Nothing should have been written to the cache dir for this digest.
        assert not cache._manifest_path("Comet", digest).exists()

    def test_restore_fails_if_cached_file_corrupted(self, tmp_path):
        cache = StepCache(tmp_path)
        out_file = tmp_path / "out.idXML"
        out_file.write_text("original content")
        digest, condition = cache.condition_hash(
            "Comet", ["in.mzML"], [str(out_file)], {}, 1
        )
        cache.publish("Comet", digest, condition, [str(out_file)])

        # Corrupt the cached copy directly.
        step_dir = cache._step_dir("Comet", digest)
        (step_dir / "0").write_text("corrupted!!")

        out_file.unlink()
        assert cache.try_restore("Comet", digest, [str(out_file)]) is False
        assert not out_file.exists()

    def test_restore_fails_if_cached_file_missing(self, tmp_path):
        cache = StepCache(tmp_path)
        out_file = tmp_path / "out.idXML"
        out_file.write_text("original content")
        digest, condition = cache.condition_hash(
            "Comet", ["in.mzML"], [str(out_file)], {}, 1
        )
        cache.publish("Comet", digest, condition, [str(out_file)])

        step_dir = cache._step_dir("Comet", digest)
        (step_dir / "0").unlink()

        out_file.unlink()
        assert cache.try_restore("Comet", digest, [str(out_file)]) is False

    def test_restore_fails_on_output_count_mismatch(self, tmp_path):
        cache = StepCache(tmp_path)
        out_file = tmp_path / "out.idXML"
        out_file.write_text("content")
        digest, condition = cache.condition_hash(
            "Comet", ["in.mzML"], [str(out_file)], {}, 1
        )
        cache.publish("Comet", digest, condition, [str(out_file)])

        # Ask for restore expecting two outputs instead of one.
        assert cache.try_restore(
            "Comet", digest, [str(out_file), str(tmp_path / "extra.idXML")]
        ) is False


class TestProducerChaining:
    def test_upstream_key_for_unknown_input_is_none(self, tmp_path):
        cache = StepCache(tmp_path)
        assert cache.upstream_key_for("never_seen.mzML") is None

    def test_register_and_lookup_by_basename(self, tmp_path):
        cache = StepCache(tmp_path)
        cache.register_producer("/some/dir/comet_out.idXML", "hash-123")
        assert cache.upstream_key_for("/other/dir/comet_out.idXML") == "hash-123"

    def test_producers_persist_across_instances(self, tmp_path):
        """A fresh StepCache() (as created by a new worker process) can still
        resolve producers registered by a previous instance, since the
        mapping is persisted to disk under workflow_dir/cache/producers.json."""
        cache1 = StepCache(tmp_path)
        cache1.register_producer("comet_out.idXML", "hash-abc")

        cache2 = StepCache(tmp_path)
        assert cache2.upstream_key_for("comet_out.idXML") == "hash-abc"


# ========================= CommandExecutor integration ======================


class TestRunToppCaching:
    def test_second_identical_run_is_a_cache_hit_and_skips_execution(self, tmp_path):
        executor = make_executor(tmp_path)
        out_file = tmp_path / "out.idXML"

        def fake_run_command(cmd, task=None):
            Path(out_file).write_text("computed")
            return True

        executor.run_command = MagicMock(side_effect=fake_run_command)

        io = {"in": [str(tmp_path / "in.mzML")], "out": [str(out_file)]}
        assert executor.run_topp("FeatureFinderMetabo", io) is True
        assert executor.run_command.call_count == 1

        out_file.unlink()  # simulate a fresh results/ dir on rerun
        assert executor.run_topp("FeatureFinderMetabo", io) is True
        # No second execution -- served from cache.
        assert executor.run_command.call_count == 1
        assert out_file.read_text() == "computed"

    def test_param_change_forces_recompute(self, tmp_path):
        executor = make_executor(tmp_path, params_json={"FeatureFinderMetabo": {"opt": "1"}})
        out_file = tmp_path / "out.idXML"
        executor.run_command = MagicMock(
            side_effect=lambda cmd, task=None: (Path(out_file).write_text("v1"), True)[1]
        )
        io = {"in": [str(tmp_path / "in.mzML")], "out": [str(out_file)]}
        executor.run_topp("FeatureFinderMetabo", io)
        assert executor.run_command.call_count == 1

        # Change the persisted parameter -> merged_params differs -> MISS.
        pm_params = executor.parameter_manager.get_parameters_from_json()
        pm_params["FeatureFinderMetabo"]["opt"] = "2"
        with open(executor.parameter_manager.params_file, "w", encoding="utf-8") as f:
            json.dump(pm_params, f)

        out_file.unlink()
        executor.run_topp("FeatureFinderMetabo", io)
        assert executor.run_command.call_count == 2


# Exercise the real subprocess/progress path on Windows as well as Linux.
# Only the executable is replaced; TOPP command construction, caching,
# threading, exit codes and stdout/stderr handling all run normally.
FAKE_TOPP = """
import sys, time
from pathlib import Path
args = sys.argv[1:]
name = args[args.index('-in') + 1]
if 'slow' in name:
    time.sleep(0.15)
if 'bad' in name:
    print('Error: bad input', file=sys.stderr)
    sys.exit(3)
Path(args[args.index('-out') + 1]).write_text(name)
"""


@pytest.fixture
def integrated_executor(tmp_path, monkeypatch):
    executor = make_executor(tmp_path)
    executor._max_threads = 2
    executor.pid_dir.mkdir()
    monkeypatch.setattr(StepCache, '_executable_identity',
                        staticmethod(lambda tool: {'tool': tool, 'sha256': 'fake-v1'}))
    original = executor.run_command

    def run(cmd, task=None):
        return original([sys.executable, '-c', FAKE_TOPP, *cmd[1:]], task=task)

    executor.run_command = MagicMock(side_effect=run)
    return executor


def test_mixed_hits_failures_keep_original_indices_and_cache_only_successes(
    tmp_path, integrated_executor,
):
    executor = integrated_executor
    outputs = [str(tmp_path / f'{i}.out') for i in range(4)]
    # Two initial files get the same one-thread allocation as the later batch.
    assert executor.run_topp('Fake', {'in': ['hit-a', 'hit-b'], 'out': outputs[:2]}) is True
    executor.run_command.reset_mock()
    io = {'in': ['hit-a', 'slow-good', 'hit-b', 'bad'],
          'out': [outputs[0], outputs[2], outputs[1], outputs[3]]}
    assert executor.run_topp('Fake', io) is False
    assert executor.run_command.call_count == 2
    state = read_progress(tmp_path)
    step = state['steps'][-1]
    assert [f['status'] for f in step['files']] == ['done', 'done', 'done', 'failed']
    assert step['ended'] is not None
    assert failures(state)[0]['context'] == 'While running Fake on file 4 of 4 (bad)'
    assert failures(state)[0]['returncode'] == 3
    assert 'Error: bad input' in failures(state)[0]['output']
    # The slow success finished after the failure: results must not be paired
    # with cache metadata in completion order. Only the failure runs next time.
    executor.run_command.reset_mock()
    assert executor.run_topp('Fake', io) is False
    assert executor.run_command.call_count == 1
    assert executor.run_command.call_args.kwargs['task'][1] == 3


def test_all_hits_record_completed_step(tmp_path, integrated_executor):
    executor = integrated_executor
    io = {'in': ['a', 'b'], 'out': [str(tmp_path / 'a.out'), str(tmp_path / 'b.out')]}
    assert executor.run_topp('Fake', io) is True
    executor.run_command.reset_mock()
    for path in io['out']:
        Path(path).unlink()
    assert executor.run_topp('Fake', io) is True
    executor.run_command.assert_not_called()
    step = read_progress(tmp_path)['steps'][-1]
    assert [f['status'] for f in step['files']] == ['done', 'done']
    assert step['ended'] is not None
    assert all(Path(p).exists() for p in io['out'])


def test_public_batch_api_keeps_boolean_and_exception_tracking(tmp_path, integrated_executor):
    executor = integrated_executor
    executor.run_command = MagicMock(side_effect=[True, RuntimeError('cannot start')])
    step = executor.progress.start_step('Fake', ['a', 'b'])
    assert executor.run_multiple_commands([['Fake'], ['Fake']], step=step) is False
    assert failures(read_progress(tmp_path))[0]['context'].endswith('file 2 of 2 (b)')
    assert executor.run_multiple_commands([]) is True


@pytest.mark.parametrize('operation', ['try_restore', 'publish'])
def test_cache_io_failure_does_not_fail_tool(tmp_path, integrated_executor, monkeypatch, operation):
    executor = integrated_executor
    monkeypatch.setattr(executor.step_cache, operation, MagicMock(side_effect=OSError('disk error')))
    assert executor.run_topp('Fake', {'in': ['a'], 'out': [str(tmp_path / 'a.out')]}) is True
    assert read_progress(tmp_path)['steps'][-1]['files'][0]['status'] == 'done'
    assert any('WARNING' in call.args[0] for call in executor.logger.log.call_args_list)
    assert executor._step_cache_failed is True
    executor.step_cache.condition_hash = MagicMock(side_effect=AssertionError('stale cache used'))
    assert executor.run_topp('Next', {'in': ['a.out'], 'out': [str(tmp_path / 'next.out')]}) is True
    executor.step_cache.condition_hash.assert_not_called()


def test_cache_disabled_preserves_progress_and_never_consults_cache(tmp_path, integrated_executor):
    executor = integrated_executor
    executor.parameter_manager.params_file.write_text(json.dumps({'step-cache-enabled': False}))
    executor.step_cache = MagicMock()
    io = {'in': ['a'], 'out': [str(tmp_path / 'a.out')]}
    assert executor.run_topp('Fake', io) is True
    assert executor.run_topp('Fake', io) is True
    assert executor.run_command.call_count == 2
    assert executor.step_cache.mock_calls == []
    assert len(read_progress(tmp_path)['steps']) == 2


def test_hash_tracks_duplicate_cli_parameters_not_dict_overlay(tmp_path, integrated_executor):
    executor = integrated_executor
    pm = executor.parameter_manager
    io = {'in': ['a'], 'out': [str(tmp_path / 'a.out')]}
    pm.params_file.write_text(json.dumps({'Fake': {'x': 1}}))
    assert executor.run_topp('Fake', io, custom_params={'x': 9}) is True
    pm.params_file.write_text(json.dumps({'Fake': {'x': 2}}))
    assert executor.run_topp('Fake', io, custom_params={'x': 9}) is True
    assert executor.run_command.call_count == 2
    cmd = executor.run_command.call_args.args[0]
    assert cmd[cmd.index('-x'):cmd.index('-threads')] == ['-x', '2', '-x', '9']


def test_removed_parameters_do_not_invalidate_cache(tmp_path, integrated_executor, monkeypatch):
    executor = integrated_executor
    pm = executor.parameter_manager
    monkeypatch.setattr(pm, 'known_topp_params', lambda tool: {'kept'})
    io = {'in': ['a'], 'out': [str(tmp_path / 'a.out')]}
    pm.params_file.write_text(json.dumps({'Fake': {'kept': 1, 'removed': 1}}))
    assert executor.run_topp('Fake', io) is True
    pm.params_file.write_text(json.dumps({'Fake': {'kept': 1, 'removed': 2}}))
    assert executor.run_topp('Fake', io) is True
    assert executor.run_command.call_count == 1
    assert '-removed' not in executor.run_command.call_args.args[0]


def test_singleton_input_does_not_reset_sample_index(tmp_path, integrated_executor):
    executor = integrated_executor
    outputs = [str(tmp_path / 'a.out'), str(tmp_path / 'b.out')]
    assert executor.run_topp('Fake', {'database': ['shared.fasta'], 'in': ['a', 'b'], 'out': outputs})
    assert [Path(p).read_text() for p in outputs] == ['a', 'b']


def test_instance_name_uses_real_executable_identity(tmp_path):
    cache = StepCache(tmp_path)
    with patch.object(cache, '_executable_identity', return_value={'sha256': 'v1'}) as identity:
        first, condition = cache.condition_hash('instance', ['a'], ['b'], {}, 1, executable='RealTool')
        identity.assert_called_once_with('RealTool')
        assert condition['tool'] == 'instance'
    with patch.object(cache, '_executable_identity', return_value={'sha256': 'v2'}):
        second, _ = cache.condition_hash('instance', ['a'], ['b'], {}, 1, executable='RealTool')
    assert first != second


def test_output_directory_and_io_roles_affect_key(tmp_path, integrated_executor):
    executor = integrated_executor
    cache = executor.step_cache
    first, _ = cache.condition_hash('Fake', ['a'], ['one/out'], {}, 1)
    second, _ = cache.condition_hash('Fake', ['a'], ['two/out'], {}, 1)
    assert first != second
    output = str(tmp_path / 'a.out')
    assert executor.run_topp('Fake', {'in': ['a'], 'aux': ['b'], 'out': [output]})
    assert executor.run_topp('Fake', {'in': ['a'], 'other': ['b'], 'out': [output]})
    assert executor.run_command.call_count == 2


def test_absolute_tool_path_stays_under_cache_root(tmp_path):
    cache = StepCache(tmp_path / 'workflow')
    tool = str(tmp_path / 'bin' / 'tool')
    assert cache._step_dir(tool, 'digest').is_relative_to(cache.cache_root)


def test_instance_integration_and_binary_change(tmp_path, integrated_executor, monkeypatch):
    executor = integrated_executor
    io = {'in': ['a'], 'out': [str(tmp_path / 'a.out')]}
    identity = MagicMock(return_value={'sha256': 'v1'})
    monkeypatch.setattr(executor.step_cache, '_executable_identity', identity)
    assert executor.run_topp('RealTool', io, tool_instance_name='instance') is True
    assert executor.run_topp('RealTool', io, tool_instance_name='instance') is True
    assert executor.run_command.call_count == 1
    identity.assert_called_with('RealTool')
    identity.return_value = {'sha256': 'v2'}
    assert executor.run_topp('RealTool', io, tool_instance_name='instance') is True
    assert executor.run_command.call_count == 2
    assert read_progress(tmp_path)['steps'][-1]['tool'] == 'RealTool (instance)'


def test_one_remaining_batch_command_exception_is_false(tmp_path, integrated_executor):
    executor = integrated_executor
    executor._max_threads = 1
    io = {'in': ['a'], 'out': [str(tmp_path / 'a.out')]}
    assert executor.run_topp('Fake', io) is True
    executor.run_command = MagicMock(side_effect=OSError('missing tool'))
    io = {'in': ['a', 'b'], 'out': [str(tmp_path / 'a.out'), str(tmp_path / 'b.out')]}
    assert executor.run_topp('Fake', io) is False
    executor.run_command.assert_called_once()
    step = read_progress(tmp_path)['steps'][-1]
    assert [f['status'] for f in step['files']] == ['done', 'failed']
    assert step['ended'] is not None


@pytest.mark.parametrize('manifest', [[], {'outputs': 'bad'},
                                      {'condition_hash': 'digest', 'outputs': [{}]}])
def test_malformed_manifest_is_a_miss(tmp_path, manifest):
    cache = StepCache(tmp_path)
    path = cache._manifest_path('Fake', 'digest')
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(manifest))
    assert cache.try_restore('Fake', 'digest', [str(tmp_path / 'out')]) is False


class TestRunToppCachingAdditional:
    def test_step_cache_disabled_always_executes(self, tmp_path):
        executor = make_executor(tmp_path, params_json={"step-cache-enabled": False})
        out_file = tmp_path / "out.idXML"
        executor.run_command = MagicMock(
            side_effect=lambda cmd, task=None: (Path(out_file).write_text("x"), True)[1]
        )
        io = {"in": [str(tmp_path / "in.mzML")], "out": [str(out_file)]}
        executor.run_topp("FeatureFinderMetabo", io)
        executor.run_topp("FeatureFinderMetabo", io)
        assert executor.run_command.call_count == 2

    def test_failed_run_is_not_cached(self, tmp_path):
        executor = make_executor(tmp_path)
        out_file = tmp_path / "out.idXML"
        executor.run_command = MagicMock(return_value=False)  # tool fails, no output written

        io = {"in": [str(tmp_path / "in.mzML")], "out": [str(out_file)]}
        assert executor.run_topp("FeatureFinderMetabo", io) is False
        assert executor.run_command.call_count == 1

        # Retry should attempt execution again -- nothing was published.
        assert executor.run_topp("FeatureFinderMetabo", io) is False
        assert executor.run_command.call_count == 2

    def test_dependent_step_recomputes_when_upstream_changes(self, tmp_path):
        """Comet output feeds Percolator. Changing Comet's params must
        change Comet's key AND, transitively, Percolator's key -- even
        though Percolator's own params and the file's basename are
        unchanged -- because Percolator's key chains to Comet's."""
        executor = make_executor(tmp_path, params_json={"Comet": {"x": "1"}})
        comet_out = tmp_path / "comet_out.idXML"
        perc_out = tmp_path / "perc_out.idXML"

        executor.run_command = MagicMock(
            side_effect=lambda cmd, task=None: (Path(cmd[cmd.index("-out") + 1]).write_text("v"), True)[1]
        )

        mz = tmp_path / "in.mzML"
        executor.run_topp("Comet", {"in": [str(mz)], "out": [str(comet_out)]})
        executor.run_topp("Percolator", {"in": [str(comet_out)], "out": [str(perc_out)]})
        assert executor.run_command.call_count == 2

        # Re-run both with no changes at all -- both should be cache hits.
        comet_out.unlink()
        perc_out.unlink()
        executor.run_topp("Comet", {"in": [str(mz)], "out": [str(comet_out)]})
        executor.run_topp("Percolator", {"in": [str(comet_out)], "out": [str(perc_out)]})
        assert executor.run_command.call_count == 2  # no new executions

        # Now change Comet's params. Comet must recompute, and Percolator
        # -- unchanged itself, but chained to Comet's new key -- must also
        # recompute (its own inputs' upstream_key changed).
        pm_params = executor.parameter_manager.get_parameters_from_json()
        pm_params["Comet"]["x"] = "2"
        with open(executor.parameter_manager.params_file, "w", encoding="utf-8") as f:
            json.dump(pm_params, f)

        comet_out.unlink()
        perc_out.unlink()
        executor.run_topp("Comet", {"in": [str(mz)], "out": [str(comet_out)]})
        executor.run_topp("Percolator", {"in": [str(comet_out)], "out": [str(perc_out)]})
        assert executor.run_command.call_count == 4

    def test_multi_sample_run_returns_per_sample_hit_and_miss(self, tmp_path):
        """One sample already cached, one new -- only the new one executes,
        and the overall call still reports success."""
        executor = make_executor(tmp_path)
        out1 = tmp_path / "s1.idXML"
        out2 = tmp_path / "s2.idXML"

        executor.run_command = MagicMock(
            side_effect=lambda cmd, task=None: (Path(cmd[cmd.index("-out") + 1]).write_text("v"), True)[1]
        )
        io_first_only = {
            "in": [str(tmp_path / "s1.mzML")],
            "out": [str(out1)],
        }
        assert executor.run_topp("FeatureFinderMetabo", io_first_only) is True
        assert executor.run_command.call_count == 1

        out1.unlink()
        io_both = {
            "in": [str(tmp_path / "s1.mzML"), str(tmp_path / "s2.mzML")],
            "out": [str(out1), str(out2)],
        }
        assert executor.run_topp("FeatureFinderMetabo", io_both) is True
        # s1 was a cache hit, s2 required one new execution.
        assert executor.run_command.call_count == 2
        assert out1.exists() and out2.exists()

    def test_no_output_keys_bypasses_cache_without_error(self, tmp_path):
        """A tool invocation with no key starting with 'out' (unusual, but
        must not crash) always executes."""
        executor = make_executor(tmp_path)
        executor.run_command = MagicMock(return_value=True)
        io = {"in": [str(tmp_path / "in.mzML")]}
        assert executor.run_topp("SomeTool", io) is True
        assert executor.run_command.call_count == 1
        executor.run_topp("SomeTool", io)
        assert executor.run_command.call_count == 2
