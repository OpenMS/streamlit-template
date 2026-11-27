"""E-mail the user when a queued run ends.

Online, a run can take hours, and the user closes the tab. While a run is
going the Run page offers to send one e-mail when it ends; the address and the
link back to the workspace are kept in ``<workflow_dir>/notify-email.json``
(not in ``logs/``, which a start clears) and the file is deleted when the
message is sent, so the address is never stored longer than the run.

Streamlit-free: :func:`notify` runs in the worker (``tasks.execute_workflow``).

The mail server is deployment configuration, read from the environment only,
never from the repository: ``SMTP_HOST`` (feature off without it),
``SMTP_FROM`` (sender, required too), ``SMTP_PORT`` (default 587),
``SMTP_USER`` and ``SMTP_PASSWORD`` (optional, put them in a Kubernetes
secret), ``SMTP_TLS`` (``starttls`` default, ``ssl`` or ``none``).
"""

from __future__ import annotations

import json
import os
import re
import smtplib
import ssl
import uuid
from email.message import EmailMessage
from pathlib import Path

FILE_NAME = "notify-email.json"

#: Deliberately plain: one @, no spaces, a dot in the domain.
_ADDRESS = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

#: tasks / classify_log_outcome outcome -> words after the workflow's name
_WORDS = {"finished": "finished", "error": "failed"}


def enabled() -> bool:
    """True when the deployment configured a mail server."""
    return bool(os.environ.get("SMTP_HOST") and os.environ.get("SMTP_FROM"))


def valid_address(address: str) -> bool:
    """A plausible e-mail address (the mail server has the final word)."""
    return bool(address) and len(address) <= 254 and bool(_ADDRESS.match(address.strip()))


def _path(workflow_dir) -> Path:
    return Path(workflow_dir) / FILE_NAME


def request(workflow_dir, address: str, link: str = "") -> None:
    """Remember to e-mail ``address`` when the current run ends."""
    address = address.strip()
    if not valid_address(address):
        raise ValueError(f"Not an e-mail address: {address!r}")
    path = _path(workflow_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps({"address": address, "link": link}), encoding="utf-8")
    os.replace(tmp, path)


def requested(workflow_dir) -> str:
    """The address an e-mail will go to, or ''."""
    try:
        data = json.loads(_path(workflow_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    return data.get("address", "") if isinstance(data, dict) else ""


def forget(workflow_dir) -> None:
    """Drop the request: no e-mail is sent (Stop, or the user changed their mind)."""
    try:
        _path(workflow_dir).unlink()
    except FileNotFoundError:
        pass


def _message(sender: str, address: str, workflow: str, outcome: str, link: str,
             app_name: str) -> EmailMessage:
    words = _WORDS.get(outcome, "failed")
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = address
    msg["Subject"] = f"{app_name}: {workflow} {words}"
    lines = [f"Your {app_name} run of {workflow} {words}."]
    if link:
        lines += ["", "Open your workspace to see " + (
            "the results:" if outcome == "finished" else "what went wrong:"), link]
    lines += ["", "You get this e-mail once, because you asked for it on the Run page. "
              "Your address has been deleted."]
    msg.set_content("\n".join(lines))
    return msg


def _send(msg: EmailMessage) -> None:
    host = os.environ["SMTP_HOST"]
    mode = os.environ.get("SMTP_TLS", "starttls").lower()
    port = int(os.environ.get("SMTP_PORT") or (465 if mode == "ssl" else 587))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")
    context = ssl.create_default_context()
    if mode == "ssl":
        server = smtplib.SMTP_SSL(host, port, timeout=30, context=context)
    else:
        server = smtplib.SMTP(host, port, timeout=30)
    with server:
        if mode == "starttls":
            server.starttls(context=context)
        if user:
            server.login(user, password or "")
        server.send_message(msg)


def notify(workflow_dir, outcome: str, workflow: str = "", app_name: str = "") -> bool:
    """Send the requested e-mail for a run that ended with ``outcome``.

    ``outcome`` is ``"finished"`` or ``"error"``; a cancelled run (the log
    says so) sends nothing. The request is deleted either way, so a later run
    never mails an address given for this one. Returns True if a message was
    sent; never raises.
    """
    path = _path(workflow_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    forget(workflow_dir)
    if not enabled() or not isinstance(data, dict):
        return False
    address = str(data.get("address", ""))
    if not valid_address(address):
        return False
    try:
        from src.workflow._log_status import classify_log_outcome
        log = Path(workflow_dir, "logs", "minimal.log")
        if log.exists() and classify_log_outcome(
                log.read_text(encoding="utf-8", errors="replace")) == "cancelled":
            return False
    except OSError:
        pass
    if not app_name:
        try:
            from src.workflow.settings_io import load_settings
            app_name = load_settings().get("app-name", "") or "OpenMS"
        except Exception:  # pylint: disable=broad-except
            app_name = "OpenMS"
    workflow = workflow or Path(workflow_dir).name
    try:
        _send(_message(os.environ["SMTP_FROM"], address, workflow, outcome,
                       str(data.get("link", "")), app_name))
    except (OSError, smtplib.SMTPException, ValueError):
        return False
    return True
