import time
import os
import shutil
import subprocess
import threading
from pathlib import Path
from .Logger import Logger
from .ParameterManager import ParameterManager, bool_param_paths_from_param_xml_ini
from .settings_io import load_settings, detect_cpu_quota, resolve_thread_setting, local_thread_default
from .vendor_files import vendor_format
from .progress import RunProgress, read_progress, failure_context, OUTPUT_TAIL
from collections import deque
from .StepCache import StepCache
import sys
import importlib.util
import json
import streamlit as st

class CommandExecutor:
    """
    Manages the execution of external shell commands such as OpenMS TOPP tools within a Streamlit application.

    This class provides a structured approach to executing shell commands, capturing
    their output, and handling errors. It is designed to facilitate running both single
    commands and batches of commands in parallel, leveraging Python's subprocess module
    for execution.
    """
    # Methods for running commands and logging
    def __init__(self, workflow_dir: Path, logger: Logger, parameter_manager: ParameterManager):
        self.workflow_dir = Path(workflow_dir)
        self.pid_dir = Path(workflow_dir, "pids")
        self.logger = logger
        self.parameter_manager = parameter_manager
        # Memoised thread budget, resolved lazily by _get_max_threads().
        self._max_threads = None
        # Per-file progress of run_topp() calls, read by the Run page
        self.progress = RunProgress(Path(workflow_dir))
        self.step_cache = StepCache(self.workflow_dir)
        self._step_cache_failed = False

    def _get_max_threads(self) -> int:
        """
        Get max threads for current deployment mode.

        Settings are read from settings.json on disk, not from
        st.session_state: inside the RQ work horse there is no
        ScriptRunContext, so st.session_state is an empty mock, the online
        branch was unreachable and the hardcoded local default silently won
        instead of max_threads.online.

        In local mode the workspace params.json may override the configured
        value - that is what the "Threads" widget writes, and it is only
        rendered in local mode. Online the worker is shared and sized by its
        pod spec, so user supplied params.json is ignored.

        Online the container's own cgroup CPU quota wins over
        max_threads.online where one exists. The rq-worker runs at
        requests.cpu == limits.cpu, so its pod spec IS its allocation, and the
        memory-tier components size that per deployment - a 4 cpu worker and a
        20 cpu worker cannot both be described by one number in settings.json,
        and the number that was there described neither. max_threads.online
        remains the fallback for every deployment where no quota is readable:
        bare metal, docker-compose without a cpu limit, a dev box.

        ``"auto"`` (the template default for both keys; ``null`` and ``-1``
        mean the same) is every usable CPU but one, see
        settings_io.default_thread_count(). A number pins the budget.

        The trade-off, deliberately taken: an operator can no longer
        under-subscribe a container that declares more CPU than it wants used.
        For a Guaranteed pod that is the right call, because the declaration
        and the allocation are the same thing.

        The result is memoised for the lifetime of this executor: run_topp()
        consults it twice, once for its own thread split and once more inside
        run_multiple_commands(), and the two must agree.

        Returns:
            int: Maximum number of threads to use for parallel processing (minimum 1).
        """
        if self._max_threads is not None:
            return self._max_threads

        settings = load_settings()
        max_threads_config = settings.get("max_threads", {})

        if settings.get("online_deployment", False):
            quota = detect_cpu_quota()
            if quota is not None:
                value = quota
            else:
                value = resolve_thread_setting(max_threads_config.get("online", "auto"))
        else:
            default = local_thread_default(settings)
            params = self.parameter_manager.get_parameters_from_json()
            value = params.get("max_threads", default)

        try:
            value = int(value)
        except (TypeError, ValueError):
            # params.json is user supplied - the parameter import uploader
            # writes it verbatim - so a non numeric thread budget degrades to
            # serial execution instead of taking the whole run down.
            self.logger.log(f"Invalid max_threads value {value!r}, falling back to 1.", 1)
            value = 1

        self._max_threads = max(1, value)
        return self._max_threads

    def run_multiple_commands(
        self, commands: list[list[str]], step: int = None
    ) -> bool:
        """Run a batch, retaining upstream's aggregate boolean contract."""
        return all(self._run_multiple_command_results(commands, step=step))

    def _run_multiple_command_results(
        self, commands: list[list[str]], step: int = None,
        file_indices: list[int] = None,
    ) -> list[bool]:
        """
        Executes multiple shell commands concurrently in separate threads.

        This method leverages threading to run each command in parallel, improving
        efficiency for batch command execution. The number of concurrent commands
        is limited by the max_threads setting, which is distributed between
        parallel command execution and per-tool thread allocation.

        Args:
            commands (list[str]): A list where each element is a list representing
                                        a command and its arguments.
            step (int, optional): The progress step these commands belong to
                (from RunProgress.start_step()); command i is its file i.
            file_indices: Original file indices when cache hits were removed.

        Returns:
            list[bool]: Per-command success, in the same order as ``commands``.
                Returning per-command results (rather than an aggregate bool)
                lets run_topp() match each result back to its step-cache
                metadata and publish only the commands that actually ran and
                succeeded.
        """
        # Get thread settings and calculate distribution
        max_threads = self._get_max_threads()
        num_commands = len(commands)
        parallel_commands = min(num_commands, max_threads)

        # Log the start of command execution
        self.logger.log(f"Running {num_commands} commands (max {parallel_commands} parallel, {max_threads} total threads)...", 1)
        start_time = time.time()

        results: list[bool] = [False] * num_commands
        if file_indices is None:
            file_indices = list(range(num_commands))
        lock = threading.Lock()
        semaphore = threading.Semaphore(parallel_commands)

        def run_and_track(index, cmd):
            with semaphore:
                try:
                    if step is None:
                        success = self.run_command(cmd)
                    else:
                        success = self.run_command(cmd, task=(step, file_indices[index]))
                except Exception as e:
                    # e.g. the tool is not installed. A thread that dies here
                    # would add no result, and the step would count as passed.
                    self.logger.log(f"ERROR: {cmd[0]}: {e}", 0)
                    success = False
                    if step is not None:
                        task = (step, file_indices[index])
                        self.progress.file_finished(*task, ok=False, returncode=-1, output=[str(e)])
                        self._log_failure_context(task, -1)
                with lock:
                    results[index] = success

        # Initialize a list to keep track of threads
        threads = []

        # Start a new thread for each command, tracking its position so
        # results stay aligned with the caller's command order.
        for index, cmd in enumerate(commands):
            thread = threading.Thread(target=run_and_track, args=(index, cmd))
            thread.start()
            threads.append(thread)

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Calculate and log the total execution time
        end_time = time.time()
        self.logger.log(f"Total time to run {num_commands} commands: {end_time - start_time:.2f} seconds", 1)

        return results

    def run_command(self, command: list[str], task: tuple = None, cwd=None) -> bool:
        """
        Executes a specified shell command and logs its execution details.

        Args:
            command (list[str]): The shell command to execute, provided as a list of strings.
            task (tuple, optional): (step, index) of this command in the run
                progress (see run_topp()). Its start, end and, on failure, exit
                code and output are recorded there, and a failure is logged
                with its context ("While running X on file 2 of 3 (a.mzML)").
            cwd (str | Path, optional): Working directory of the command, for
                programs that read files next to their executable. Defaults to
                the app's working directory.

        Raises:
            Exception: If the command execution results in any errors.
        """
        # Ensure all command parts are strings
        command = [str(c) for c in command]

        # Log the execution start
        if cwd is not None:
            self.logger.log(f"Working directory: {cwd}", 1)
        self.logger.log(f"Running command:\n"+' '.join(command)+"\nWaiting for command to finish...", 1)   
        start_time = time.time()
        if task is not None:
            self.progress.file_started(*task)

        # Execute the command with real-time output capture
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # Line buffered
                universal_newlines=True,
                cwd=cwd,
            )
        except OSError as e:
            # e.g. the tool is not installed: record it, then fail as before
            if task is not None:
                self.progress.file_finished(*task, ok=False, returncode=-1, output=[str(e)])
                self._log_failure_context(task, -1)
            raise
        child_pid = process.pid
        
        # Record the PID to keep track of running processes associated with this workspace/workflow
        # User can close the Streamlit app and return to a running workflow later
        pid_file_path = self.pid_dir / str(child_pid)
        pid_file_path.touch()

        # Buffer for stderr - will only be written to minimal log if process fails
        stderr_buffer: list[str] = []
        # Last lines of stdout, kept for the run progress of a failed file
        stdout_tail: deque = deque(maxlen=OUTPUT_TAIL)

        # Real-time output capture
        self._stream_output(process, stderr_buffer, stdout_tail)

        # Wait for process completion
        process.wait()

        # Cleanup PID file
        pid_file_path.unlink()

        end_time = time.time()
        execution_time = end_time - start_time

        # Log completion
        self.logger.log(f"Process finished:\n"+' '.join(command)+f"\nTotal time to run command: {execution_time:.2f} seconds", 1)

        ok = process.returncode == 0
        if task is not None:
            self.progress.file_finished(
                *task,
                ok=ok,
                returncode=process.returncode,
                output=list(stdout_tail) + stderr_buffer,
            )

        # Check for errors
        if not ok:
            # Write buffered stderr to minimal log only on failure
            for line in stderr_buffer:
                self.logger.log(f"STDERR: {line}", 0)
            self.logger.log(f"ERROR: Command failed with exit code {process.returncode}: {command[0]}", 0)
            if task is not None:
                self._log_failure_context(task, process.returncode)
            return False
        return True

    def _log_failure_context(self, task: tuple, returncode: int) -> None:
        """Log which tool failed on which file, e.g. 'While running X on file 2 of 3 (a.mzML)'."""
        if task[0] < 0:  # the step could not be recorded
            return
        state = read_progress(self.progress.workflow_dir)
        try:
            step = state["steps"][task[0]]
        except (TypeError, KeyError, IndexError):
            return
        self.logger.log(f"ERROR: {failure_context(step, task[1])} (exit code {returncode})", 0)

    @staticmethod
    def _command_labels(input_output: dict, n_processes: int) -> list[str]:
        """A name per command for the run progress: its input file, as a rule.

        Taken from the first input-like key ("in", "in_...") whose list holds
        one entry per command, else the first such list; a collected list of
        files becomes "<n> files".
        """
        keys = list(input_output.keys())
        candidates = [k for k in keys if k.lower().startswith("in")] + keys
        key = next(
            (k for k in candidates if len(input_output[k]) == n_processes),
            candidates[0] if candidates else None,
        )
        labels = []
        for i in range(n_processes):
            if key is None:
                labels.append("")
                continue
            values = input_output[key]
            value = values[i] if len(values) > i else values[0]
            if isinstance(value, list):
                labels.append(Path(value[0]).name if len(value) == 1 else f"{len(value)} files")
            else:
                labels.append(Path(str(value)).name)
        return labels

    def _stream_output(
        self,
        process: subprocess.Popen,
        stderr_buffer: list[str],
        stdout_tail: deque = None,
    ) -> None:
        """
        Streams stdout and stderr from a running process in real-time to the logger.
        This method runs in the workflow process, not the GUI thread, so it's safe to block.

        Stderr is buffered and only logged to the detailed log (level 2) during execution.
        The caller is responsible for writing buffered stderr to minimal log if the process fails.

        Args:
            process: The subprocess.Popen object to stream from
            stderr_buffer: A list to accumulate stderr lines for conditional logging
        """
        def read_stdout():
            """Read stdout in real-time"""
            try:
                for line in iter(process.stdout.readline, ''):
                    if line:
                        self.logger.log(line.rstrip(), 2)
                        if stdout_tail is not None:
                            stdout_tail.append(line.rstrip())
                    if process.poll() is not None:
                        break
            except Exception as e:
                self.logger.log(f"Error reading stdout: {e}", 2)
            finally:
                process.stdout.close()

        def read_stderr():
            """Read stderr in real-time, buffering for conditional minimal log output"""
            try:
                for line in iter(process.stderr.readline, ''):
                    if line:
                        stderr_line = line.rstrip()
                        stderr_buffer.append(stderr_line)
                        # Log to detailed log only during execution
                        self.logger.log(f"STDERR: {stderr_line}", 2)
                    if process.poll() is not None:
                        break
            except Exception as e:
                self.logger.log(f"Error reading stderr: {e}", 2)
            finally:
                process.stderr.close()

        # Start threads to read stdout and stderr simultaneously
        stdout_thread = threading.Thread(target=read_stdout, daemon=True)
        stderr_thread = threading.Thread(target=read_stderr, daemon=True)

        stdout_thread.start()
        stderr_thread.start()

        # Wait for both threads to complete
        stdout_thread.join()
        stderr_thread.join()

    def run_topp(self, tool: str, input_output: dict, custom_params: dict = {}, tool_instance_name: str = None) -> bool:
        """
        Constructs and executes commands for the specified tool OpenMS TOPP tool based on the given
        input and output configurations. Ensures that all input/output file lists
        are of the same length, or single strings, to maintain consistency in command
        execution.
        In many tools, a single input file is processed to produce a single output file.
        When dealing with lists of input or output files, the convention is that
        files are paired based on their order. For instance, the n-th input file is
        assumed to correspond to the n-th output file, maintaining a structured
        relationship between input and output data.
        Supports executing commands either as single or multiple processes
        based on the input size.

        Args:
            tool (str): The executable name or path of the tool.
            input_output (dict): A dictionary specifying the input/output parameter names (as key) and their corresponding file paths (as value).
            custom_params (dict): A dictionary of custom parameters to pass to the tool.
            tool_instance_name (str, optional): A unique instance name for this tool
                invocation, used for parameter lookup when multiple instances of the
                same tool exist. If not provided, defaults to the tool name.

        Returns:
            bool: True if all commands succeeded, False if any failed.

        Raises:
            ValueError: If the lengths of input/output file lists are inconsistent,
                        except for single string inputs.
        """
        # Use tool_instance_name for parameter lookup, fall back to tool name
        params_key = tool_instance_name if tool_instance_name else tool
        # check input: any input lists must be same length, other items can be a single string
        # e.g. input_mzML : [list of n mzML files], output_featureXML : [list of n featureXML files], input_database : database.tsv
        io_lengths = [len(v) for v in input_output.values() if len(v) > 1]

        if len(set(io_lengths)) > 1:
            raise ValueError(f"ERROR in {tool} input/output.\nFile list lengths must be 1 and/or the same. They are {io_lengths}.")

        if len(io_lengths) == 0:  # all inputs/outputs are length == 1
            n_processes = 1
        else:
            n_processes = max(io_lengths)

        # Calculate threads per command based on max_threads setting
        max_threads = self._get_max_threads()
        parallel_commands = min(n_processes, max_threads)
        threads_per_command = max(1, max_threads // parallel_commands)

        # Load merged parameters (_defaults + user overrides) for this tool instance
        merged_params = self.parameter_manager.get_merged_params(params_key)

        # A stored parameter the installed tool does not have (saved before an
        # upgrade that removed or renamed it) makes the tool refuse the whole
        # run: "Parameters passed to '<tool>' are invalid", exit code 6. Leave
        # it out and say so. Only when the tool's .ini is there to tell.
        known_params = self.parameter_manager.known_topp_params(tool)
        if isinstance(known_params, set):
            unknown = sorted(k for k in merged_params if k not in known_params)
            for k in unknown:
                del merged_params[k]
            if unknown:
                self.logger.log(
                    f"WARNING: {tool} has no parameter {', '.join(unknown)}; "
                    "the stored value is not passed on. Check the parameters "
                    "of this tool on the configuration page.",
                    0,
                )

        # Load flag parameter names: params.json takes priority (survives session restart),
        # session_state is the live fallback during the current session.
        params_json = self.parameter_manager.get_parameters_from_json()
        flag_map = params_json.get("_flag_params", {})
        flag_list = flag_map.get(params_key)
        if flag_list is None:
            flag_list = st.session_state.get("_topp_flag_params", {}).get(params_key, [])
        flag_params: set = set(flag_list)
        step_cache_enabled = params_json.get("step-cache-enabled", True) and not self._step_cache_failed

        # Commands that still need to run (cache misses), and their aligned
        # step-cache metadata (or None for entries not eligible for caching).
        pending_commands = []
        pending_meta = []
        pending_indices = []
        cached_indices = []

        # Construct a command for each process, checking the step cache first
        for i in range(n_processes):
            command = [tool]
            input_paths: list = []
            output_paths: list = []
            cache_io = []
            # Add input/output files
            for k in input_output.keys():
                # add key as parameter name
                command += [f"-{k}"]
                # get value from input_output dictionary
                value = input_output[k]
                # when multiple input/output files exist (e.g., multiple mzMLs and featureXMLs), but only one additional input file (e.g., one input database file)
                idx = 0 if len(value) == 1 else i
                entry = value[idx]
                # when the entry is a list of collected files to be passed as one [["sample1", "sample2"]]
                if isinstance(entry, list):
                    command += entry
                    file_names = entry
                # standard case, files was a list of strings, take the file name at index
                else:
                    command += [entry]
                    file_names = [entry]
                # Convention used throughout this codebase: TOPP output keys
                # are named "out", "out_cxml", "out_msstats", etc.; every
                # other key ("in", "ids", "id", ...) is an input.
                if k.startswith("out"):
                    output_paths.extend(file_names)
                else:
                    input_paths.extend(file_names)
                cache_io.append((k, [str(p) if k.startswith("out") else Path(p).name
                                     for p in file_names]))
            params_start = len(command)
            # Add merged TOPP tool parameters (_defaults + user overrides)
            for k, v in merged_params.items():
                if k in flag_params:
                    # CLI flag: include "-k" only when truthy, omit when false
                    if isinstance(v, str):
                        is_enabled = v.lower() == "true"
                    else:
                        is_enabled = bool(v)
                    if is_enabled:
                        command += [f"-{k}"]
                    continue
                # Regular parameter: skip empty/None/empty-list, append value otherwise
                if v == "" or v is None or (isinstance(v, list) and not v):
                    continue
                command += [f"-{k}"]
                if isinstance(v, str) and "\n" in v:
                    command += v.split("\n")
                elif isinstance(v, list):
                    command += [str(x) for x in v]
                elif isinstance(v, bool):
                    # OpenMS reads a boolean as "true"/"false", not "True"
                    command += [str(v).lower()]
                else:
                    command += [str(v)]
            # Add custom parameters
            for k, v in custom_params.items():
                if k in flag_params:
                    if isinstance(v, str):
                        is_enabled = v.lower() == "true"
                    else:
                        is_enabled = bool(v)
                    if is_enabled:
                        command += [f"-{k}"]
                    continue
                if v == "" or v is None or (isinstance(v, list) and not v):
                    continue
                command += [f"-{k}"]
                if isinstance(v, list):
                    command += [str(x) for x in v]
                elif isinstance(v, bool):
                    command += [str(v).lower()]
                else:
                    command += [str(v)]
            # Add threads parameter for TOPP tools
            command += ["-threads", str(threads_per_command)]

            if step_cache_enabled and output_paths:
                meta, restored = self._lookup_step_cache(
                    tool, params_key, input_paths, output_paths,
                    {
                        "io": cache_io,
                        # Thread count affects scheduling but is intentionally
                        # excluded from cache identity. This lets a per-file
                        # result survive when the batch size changes.
                        "argv": [str(v) for v in command[params_start:-2]],
                    },
                    threads_per_command,
                )
                if restored:
                    self.logger.log(
                        f"Cache HIT for {params_key} ({meta['digest'][:12]}): reused "
                        f"{len(output_paths)} output(s), skipped computation", 1
                    )
                    cached_indices.append(i)
                    continue
                pending_meta.append(meta)
            else:
                if step_cache_enabled and not output_paths:
                    self.logger.log(
                        f"Cache bypass for {params_key}: no declared output files detected", 2
                    )
                pending_meta.append(None)

            pending_commands.append(command)
            pending_indices.append(i)

        # Record the call for the Run page: one entry per command (input file)
        step = self.progress.start_step(
            tool if params_key == tool else f"{tool} ({params_key})",
            self._command_labels(input_output, n_processes),
            threads=threads_per_command,
            parallel=parallel_commands,
        )
        try:
            for index in cached_indices:
                self.progress.file_finished(step, index, ok=True)
            if not pending_commands:
                return True
            # Preserve upstream's single-command exception behavior. A batch
            # remains a batch even if all but one file were cache hits.
            if n_processes == 1:
                successes = [self.run_command(pending_commands[0], task=(step, pending_indices[0]))]
            else:
                successes = self._run_multiple_command_results(
                    pending_commands, step=step, file_indices=pending_indices,
                )
            for success, meta in zip(successes, pending_meta):
                if success and meta is not None:
                    self._publish_step_cache(params_key, meta)
            return all(successes)
        finally:
            self.progress.end_step(step)

    def _lookup_step_cache(self, tool, params_key, inputs, outputs, params, threads):
        """Cache failures are warnings; the original tool can still run."""
        if self._step_cache_failed:
            return None, False
        try:
            upstream_keys = {self.step_cache.upstream_key_for(p) for p in inputs}
            upstream_keys.discard(None)
            digest, condition = self.step_cache.condition_hash(
                tool=params_key, executable=tool, input_paths=inputs,
                output_paths=outputs, effective_params=params, threads=threads,
                upstream_keys=upstream_keys,
            )
            meta = {"digest": digest, "condition": condition, "output_paths": outputs}
            if self.step_cache.try_restore(params_key, digest, outputs):
                for path in outputs:
                    self.step_cache.register_producer(path, digest)
                return meta, True
            self.logger.log(f"Cache MISS for {params_key} ({digest[:12]})", 1)
            return meta, False
        except (OSError, ValueError, KeyError, TypeError) as exc:
            # A missing producer update could make downstream reuse stale
            # results. Bypass caching for this executor after an I/O failure.
            self._step_cache_failed = True
            self.logger.log(f"WARNING: Step cache bypass for {params_key}: {exc}", 1)
            return None, False

    def _publish_step_cache(self, params_key, meta):
        if self._step_cache_failed:
            return
        try:
            if self.step_cache.publish(
                params_key, meta["digest"], meta["condition"], meta["output_paths"]
            ):
                for path in meta["output_paths"]:
                    self.step_cache.register_producer(path, meta["digest"])
            else:
                self._step_cache_failed = True
                self.logger.log(f"WARNING: Step cache disabled: incomplete outputs for {params_key}", 1)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self._step_cache_failed = True
            self.logger.log(f"WARNING: Could not publish step cache for {params_key}: {exc}", 1)

    def stop(self) -> None:
        """
        Terminates all processes initiated by this executor by killing them based on stored PIDs.
        """
        self.logger.log("Stopping all running processes...")
        pids = [Path(f).stem for f in self.pid_dir.iterdir()]
        
        for pid in pids:
            try:
                os.kill(int(pid), 9)
            except OSError as e:
                self.logger.log(f"Failed to kill process {pid}: {e}")
        
        shutil.rmtree(self.pid_dir, ignore_errors=True)
        self.logger.log("Workflow stopped.")

    def run_python(self, script_file: str, input_output: dict = {}) -> bool:
        """
        Executes a specified Python script with dynamic input and output parameters,
        optionally logging the execution process. The method identifies and loads
        parameter defaults from the script, updates them with any user-specified
        parameters and file paths, and then executes the script via a subprocess
        call.

        This method facilitates the integration of standalone Python scripts into
        a larger application or workflow, allowing for the execution of these scripts
        with varying inputs and outputs without modifying the scripts themselves.

        Args:
            script_file (str):  The name or path of the Python script to be executed.
                                If the path is omitted, the method looks for the script in 'src/python-tools/'.
                                The '.py' extension is appended if not present.
            input_output (dict, optional): A dictionary specifying the input/output parameter names (as key) and their corresponding file paths (as value). Defaults to {}.

        Returns:
            bool: True if the script ran and exited 0, False otherwise. Same
                contract as run_topp(), so execution() can gate on it. This used
                to discard run_command()'s result and return None, which made
                every `if not self.executor.run_python(...)` guard dead code and
                left a failed Python tool indistinguishable from a successful one.
        """
        # Check if script file exists (can be specified without path and extension)
        # default location: src/python-tools/script_file
        if not script_file.endswith(".py"):
            script_file += ".py"
        path = Path(script_file)
        if not path.exists():
            path = Path("src", "python-tools", script_file)
            if not path.exists():
                # Bail out here: falling through to spec_from_file_location on a
                # path that does not exist raises out of the workflow instead of
                # reporting a failed step.
                self.logger.log(f"ERROR: Script file not found: {script_file}", 0)
                return False

        # load DEFAULTS
        if path.parent not in sys.path:
            sys.path.append(str(path.parent))
        spec = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        defaults = getattr(module, "DEFAULTS", None)
        if defaults is None:
            self.logger.log(f"WARNING: No DEFAULTS found in {path.name}")
            # run command without params
            return self.run_command([sys.executable, str(path)])
        elif isinstance(defaults, list):
            defaults = {entry["key"]: entry["value"] for entry in defaults}
            # load paramters from JSON file
            params = {k: v for k, v in self.parameter_manager.get_parameters_from_json().items() if path.name in k}
            # update defaults
            for k, v in params.items():
                defaults[k.replace(f"{path.name}:", "")] = v
            for k, v in input_output.items():
                defaults[k] = v
            # save parameters to temporary JSON file
            tmp_params_file = Path(self.pid_dir.parent, f"{path.stem}.json")
            with open(tmp_params_file, "w", encoding="utf-8") as f:
                json.dump(defaults, f, indent=4)
            # run command
            success = self.run_command(
                [sys.executable, str(path), str(tmp_params_file)]
            )
            # remove tmp params file
            tmp_params_file.unlink()
            return success

        # DEFAULTS exists but is not the documented list of parameter dicts, so
        # nothing ran. Reporting that as success would put the workflow's
        # WORKFLOW FINISHED marker on a step which never executed.
        self.logger.log(
            f"ERROR: DEFAULTS in {path.name} is a {type(defaults).__name__}, "
            "expected a list of parameter dicts. Script not run.",
            0,
        )
        return False

    def convert_to_mzml(self, files: list[str], out_dir: str = None) -> list[str]:
        """
        Returns an mzML path for every input file, converting vendor files first.

        mzML files are returned unchanged. Thermo ``.raw`` files are converted
        with the TOPP tool FileConverter (ThermoRawFileParser; on Linux and
        macOS it needs mono). Bruker timsTOF ``.d`` folders are converted with
        ``src/python-tools/bruker_to_mzml.py``. A conversion is done once: the
        mzML is kept in ``out_dir`` (default ``<workflow_dir>/converted-mzML``)
        and reused while it is newer than its input.

        Args:
            files (list[str]): Input files, e.g. ``self.params["mzML-files"]``.
            out_dir (str, optional): Where converted mzML files are kept.

        Returns:
            list[str]: mzML paths in input order, or None if a conversion failed
                (the reason is in the workflow log).
        """
        out_dir = Path(out_dir) if out_dir else Path(self.pid_dir.parent, "converted-mzML")
        mzmls = []
        for f in files:
            kind = vendor_format(f)
            if kind is None:
                mzmls.append(str(f))
                continue
            out = Path(out_dir, f"{Path(f).stem}.mzML")
            if out.exists() and out.stat().st_mtime >= Path(f).stat().st_mtime:
                self.logger.log(f"Using converted {out.name} for {Path(f).name}.")
                mzmls.append(str(out))
                continue
            out_dir.mkdir(parents=True, exist_ok=True)
            # Written under a temporary name so a cancelled or failed
            # conversion never leaves a truncated mzML that would be reused.
            tmp = Path(out_dir, f"{out.stem}.part.mzML")
            tmp.unlink(missing_ok=True)
            self.logger.log(f"Converting {Path(f).name} to mzML...")
            if kind == "raw":
                ok = self.run_topp("FileConverter", {"in": [str(f)], "out": [str(tmp)]})
            else:
                ok = self.run_python("bruker_to_mzml", {"in": str(f), "out": str(tmp)})
            if not ok or not tmp.exists():
                tmp.unlink(missing_ok=True)
                self.logger.log(f"ERROR: Could not convert {Path(f).name} to mzML.", 0)
                return None
            os.replace(tmp, out)
            mzmls.append(str(out))
        return mzmls
