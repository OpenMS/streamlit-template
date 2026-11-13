"""A methods section for a run, to copy into a publication.

Written from the processing report (``processing_report.build_report``): the
app and OpenMS version, then every tool call that finished, in order, with
the parameters that differ from the tool's defaults, and the references. It is
a draft to edit, not the final text: it names what was run, not why.

An app words its own tools in the optional ``methods`` block of settings.json::

    "methods": {
        "reference": "How to cite the app itself.",
        "tools": {
            "CometAdapter": {"text": "Spectra were searched with Comet",
                             "reference": "Eng JK, et al. ..."}
        }
    }

``text`` replaces "<Tool> was run" in the tool's sentence, and ``reference``
is cited after it. Parameters are named as in ``parameter-names.json``.
Streamlit-free.
"""

from collections import Counter
from typing import Any, Callable, Dict, List, Optional

from .parameter_names import display_name

OPENMS_REFERENCE = (
    "Pfeuffer J, Bielow C, Wein S, et al. OpenMS 3 enables reproducible analysis of "
    "large-scale mass spectrometry data. Nat Methods. 2024;21(3):365-367. "
    "doi:10.1038/s41592-024-02197-7"
)

WEBAPPS_REFERENCE = (
    "Müller TD, et al. OpenMS WebApps: Building User-Friendly "
    "Solutions for MS Analysis. J Proteome Res. 2025. doi:10.1021/acs.jproteome.4c00872"
)

# How the steps after the first are introduced, in turn
_THEN = ("Then", "Next", "After that")
# Input files named in the text up to this many; above it only their number
_NAMED_FILES = 6


def _split_tool(tool: str, program: str) -> Optional[str]:
    """The ``tool_instance_name`` of a step labelled "Tool (instance)", or None."""
    if tool.startswith(f"{program} (") and tool.endswith(")"):
        return tool[len(program) + 2:-1]
    return None


def _param_name(program: str, key: str, instance: Optional[str], names: Callable) -> str:
    entry = names(program, key, instance)
    return entry["name"] if entry and entry.get("name") else key


def _join(items: List[str]) -> str:
    if len(items) <= 2:
        return " and ".join(items)
    return ", ".join(items[:-1]) + f" and {items[-1]}"


def _files_phrase(inputs: List[dict]) -> str:
    n = len(inputs)
    if n == 1:
        return f"The input file {inputs[0]['name']} was"
    if n <= _NAMED_FILES:
        return f"The {n} input files ({_join([i['name'] for i in inputs])}) were"
    return f"The {n} input files were"


class _References:
    """References numbered in the order the text cites them."""

    def __init__(self):
        self.items: List[str] = []

    def cite(self, text: str) -> str:
        if text not in self.items:
            self.items.append(text)
        return f"[{self.items.index(text) + 1}]"


def methods_text(
    report: dict,
    settings: Optional[dict] = None,
    names: Callable[..., Optional[dict]] = display_name,
) -> str:
    """The methods section of a run as plain text, or "" when no tool finished.

    One paragraph, then "References" and the numbered references: text that
    pastes into a manuscript as it is.

    Args:
        report: ``build_report`` / ``report_for`` of the run.
        settings: settings.json, for its ``methods`` block (optional).
        names: ``display_name``-like lookup of a parameter's name.
    """
    steps = [s for s in report.get("steps") or [] if s.get("status") == "done"]
    if not steps:
        return ""
    # A settings block of another shape (a typo in settings.json) is ignored, never an error
    wording = (settings or {}).get("methods") if isinstance(settings, dict) else None
    wording = wording if isinstance(wording, dict) else {}
    tool_wording = wording.get("tools") if isinstance(wording.get("tools"), dict) else {}
    refs = _References()

    # Steps that took several input files at once (feature linking, protein inference)
    # and how many of them each call of the step took at most
    together: Dict[int, int] = {}
    for item in report.get("inputs") or []:
        for call in item.get("calls") or []:
            if call.get("with"):
                together[call["step"]] = max(together.get(call["step"], 0), call["with"] + 1)

    app = report.get("app") or {}
    app_name = " ".join(x for x in (app.get("name"), app.get("version")) if x)
    topp_versions = Counter(s["version"] for s in steps if s.get("kind") == "topp" and s.get("version"))
    openms = topp_versions.most_common(1)[0][0] if topp_versions else (
        (report.get("environment") or {}).get("pyopenms", ""))

    inputs = report.get("inputs") or []
    opening = _files_phrase(inputs) if inputs else "The data were"
    text = f"{opening} processed with {app_name or 'an OpenMS web app'}"
    if isinstance(wording.get("reference"), str) and wording["reference"]:
        text += f" {refs.cite(wording['reference'])}"
    text += (f", a web application built on the OpenMS WebApps framework {refs.cite(WEBAPPS_REFERENCE)}"
             f" that runs the tools of OpenMS{f' {openms}' if openms else ''} {refs.cite(OPENMS_REFERENCE)}.")
    sentences = [text]

    for index, step in enumerate(steps):
        program = step.get("program") or step.get("tool", "")
        instance = _split_tool(step.get("tool", ""), program)
        own = tool_wording.get(instance or "") or tool_wording.get(program) or {}
        own = own if isinstance(own, dict) else {}
        if isinstance(own.get("text"), str) and own["text"]:
            subject = own["text"]
        elif step.get("kind") == "python":
            subject = f"the Python script {program} was run"
        else:
            subject = f"{program} was run"
        version = step.get("version") or ""
        if step.get("kind") == "topp" and version and version != openms:
            subject += f" (version {version})"
        if isinstance(own.get("reference"), str) and own["reference"]:
            subject += f" {refs.cite(own['reference'])}"
        if index == 0:
            lead = "First, " if len(steps) > 1 else ""
        else:
            lead = "Finally, " if index == len(steps) - 1 and len(steps) > 2 else f"{_THEN[(index - 1) % len(_THEN)]}, "
        if not lead:
            subject = subject[0].upper() + subject[1:]
        elif own.get("text") or step.get("kind") == "python":
            # An ordinary first word ("Spectra were ..."), not a tool's name
            subject = subject[0].lower() + subject[1:]
        sentence = lead + subject
        if len(inputs) > 1:
            group = together.get(step["number"], 0)
            if not group:
                sentence += " on each file"
            elif group >= len(inputs):
                sentence += " on all files together"
            else:
                sentence += f" on groups of up to {group} files together"
        params = step.get("params") or {}
        if params:
            parts = [f"{_param_name(program, k, instance, names)} set to {v}" for k, v in params.items()]
            sentence += f", with {_join(parts)}"
        elif step.get("recorded") and step.get("kind") == "topp":
            sentence += ", with default parameters"
        sentences.append(sentence + ".")

    lines = [" ".join(sentences), "", "References"]
    lines += [f"{n}. {ref}" for n, ref in enumerate(refs.items, start=1)]
    return "\n".join(lines) + "\n"
