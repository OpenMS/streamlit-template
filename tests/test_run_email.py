"""run_email: the e-mail a user asks for on the Run page (Streamlit-free)."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.workflow import run_email  # noqa: E402


class FakeSMTP:
    sent = []

    def __init__(self, host, port, timeout=None, **_):
        self.host, self.port = host, port
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, context=None):
        self.calls.append("starttls")

    def login(self, user, password):
        self.calls.append(("login", user))

    def send_message(self, msg):
        FakeSMTP.sent.append((self, msg))


@pytest.fixture
def smtp(monkeypatch):
    FakeSMTP.sent = []
    monkeypatch.setenv("SMTP_HOST", "mail.example.org")
    monkeypatch.setenv("SMTP_FROM", "noreply@example.org")
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.delenv("SMTP_TLS", raising=False)
    monkeypatch.delenv("SMTP_PORT", raising=False)
    monkeypatch.setattr(run_email.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(run_email.smtplib, "SMTP_SSL", FakeSMTP)
    return FakeSMTP


def test_enabled_needs_host_and_sender(monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.setenv("SMTP_FROM", "a@b.org")
    assert not run_email.enabled()
    monkeypatch.setenv("SMTP_HOST", "mail")
    assert run_email.enabled()


@pytest.mark.parametrize("address,ok", [
    ("a@b.org", True), (" a.b+c@d.example.org ", True),
    ("", False), ("a@b", False), ("a b@c.org", False), ("a@@b.org", False),
])
def test_valid_address(address, ok):
    assert run_email.valid_address(address) is ok


def test_request_is_kept_outside_logs(tmp_path):
    run_email.request(tmp_path, "a@b.org", "https://app/?workspace=x")
    assert run_email.requested(tmp_path) == "a@b.org"
    assert (tmp_path / run_email.FILE_NAME).exists()
    assert not (tmp_path / "logs").exists()
    with pytest.raises(ValueError):
        run_email.request(tmp_path, "nope", "")


def test_finished_run_sends_once_and_deletes_address(tmp_path, smtp):
    run_email.request(tmp_path / "topp-workflow", "a@b.org", "https://app/run?workspace=x")
    assert run_email.notify(tmp_path / "topp-workflow", "finished", app_name="OpenMS App")
    (server, msg), = smtp.sent
    assert server.host == "mail.example.org" and server.port == 587
    assert server.calls == ["starttls"]
    assert msg["To"] == "a@b.org" and msg["From"] == "noreply@example.org"
    assert msg["Subject"] == "OpenMS App: topp-workflow finished"
    assert "https://app/run?workspace=x" in msg.get_content()
    assert run_email.requested(tmp_path / "topp-workflow") == ""
    assert not run_email.notify(tmp_path / "topp-workflow", "finished", app_name="X")
    assert len(smtp.sent) == 1


def test_failed_run_says_so(tmp_path, smtp):
    run_email.request(tmp_path, "a@b.org", "")
    assert run_email.notify(tmp_path, "error", workflow="Run", app_name="App")
    assert smtp.sent[0][1]["Subject"] == "App: Run failed"


def test_cancelled_run_sends_nothing(tmp_path, smtp):
    run_email.request(tmp_path, "a@b.org", "")
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "minimal.log").write_text("ERROR\nWORKFLOW CANCELLED\n")
    assert not run_email.notify(tmp_path, "error", app_name="App")
    assert smtp.sent == []
    assert run_email.requested(tmp_path) == ""


def test_without_mail_server_nothing_is_sent_but_address_is_deleted(tmp_path, smtp, monkeypatch):
    monkeypatch.delenv("SMTP_HOST")
    run_email.request(tmp_path, "a@b.org", "")
    assert not run_email.notify(tmp_path, "finished", app_name="App")
    assert smtp.sent == [] and run_email.requested(tmp_path) == ""


def test_ssl_and_login(tmp_path, smtp, monkeypatch):
    monkeypatch.setenv("SMTP_TLS", "ssl")
    monkeypatch.setenv("SMTP_USER", "u")
    monkeypatch.setenv("SMTP_PASSWORD", "p")
    run_email.request(tmp_path, "a@b.org", "")
    assert run_email.notify(tmp_path, "finished", app_name="App")
    server = smtp.sent[0][0]
    assert server.port == 465 and server.calls == [("login", "u")]


def test_send_failure_never_raises(tmp_path, smtp, monkeypatch):
    def boom(msg):
        raise OSError("connection refused")
    monkeypatch.setattr(run_email, "_send", boom)
    run_email.request(tmp_path, "a@b.org", "")
    assert run_email.notify(tmp_path, "finished", app_name="App") is False


def test_execute_workflow_mails_the_outcome(tmp_path, monkeypatch):
    """tasks.execute_workflow calls notify for a finished and a failed run."""
    import importlib
    tasks = importlib.import_module("src.workflow.tasks")
    # Other test modules purge src.workflow.* from sys.modules; patch the
    # module _send_email imports now, not the one imported at the top.
    current = importlib.import_module("src.workflow.run_email")
    calls = []
    monkeypatch.setattr(current, "notify", lambda wd, outcome, *a, **k: calls.append(outcome))
    tasks._send_email(tmp_path, "finished")
    monkeypatch.setattr(current, "notify", lambda *a, **k: (_ for _ in ()).throw(RuntimeError()))
    tasks._send_email(tmp_path, "error")  # never raises
    assert calls == ["finished"]
    assert json.dumps(calls)
