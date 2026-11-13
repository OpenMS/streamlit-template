"""Tell the user when a run ends while they look at another tab.

Streamlit-free: these functions return the HTML that the Run page draws with
``st.html(..., unsafe_allow_javascript=True)``, which runs in the page itself
(not in an iframe), so it can use the browser's Notification API and change
the tab title.

- :func:`ask_html` is a small "Notify me when it ends" button, drawn while a
  run is going. The browser asks for permission only on a click of the user
  (Firefox and Safari ignore a request without one), so it is an HTML button,
  not a Streamlit one, whose click reaches the server first. It hides itself
  when the browser has no notifications or the user has answered already.
- :func:`notice_html` is drawn once when a run this session watched has
  ended. While the tab is hidden it puts the outcome in front of the tab
  title until the tab is shown again, and sends a notification when the user
  allowed them. A tab in view changes nothing: the page says it already.
"""

from __future__ import annotations

import json

#: classify_log_outcome() result -> (title mark, words after the run's name)
OUTCOMES = {
    "finished": ("✓", "finished"),
    "cancelled": ("■", "was cancelled"),
    "error": ("✗", "failed"),
}

ASK_ID = "openms-run-notify"


def _js(value) -> str:
    """A JSON literal safe inside a <script> element."""
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def ask_html(label: str = "Notify me when it ends") -> str:
    """The button that asks the browser for permission to notify."""
    return (
        f'<button id="{ASK_ID}" type="button" style="display:none;'
        "cursor:pointer;border:1px solid rgba(128,128,128,.4);border-radius:.5rem;"
        "padding:.25rem .75rem;background:transparent;color:inherit;font:inherit;"
        f'font-size:.875rem">🔔 {label}</button>'
        "<script>(function(){"
        f"var b=document.getElementById({_js(ASK_ID)});"
        "if(!b||!('Notification' in window)||Notification.permission!=='default')return;"
        "b.style.display='inline-block';"
        "b.onclick=function(){Notification.requestPermission().then(function(p){"
        "if(p!=='default')b.style.display='none';});};"
        "})();</script>"
    )


def notice_html(outcome: str, name: str = "The workflow") -> str:
    """Script for the end of a run: tab title mark and notification."""
    mark, words = OUTCOMES.get(outcome, OUTCOMES["error"])
    text = f"{name} {words}."
    return (
        "<script>(function(){"
        "var d=document;if(!d.hidden)return;"
        f"var mark={_js(mark + ' ')},text={_js(text)};"
        "if(d.title.indexOf(mark)!==0)d.title=mark+d.title;"
        "d.addEventListener('visibilitychange',function f(){"
        "if(d.hidden)return;"
        "if(d.title.indexOf(mark)===0)d.title=d.title.slice(mark.length);"
        "d.removeEventListener('visibilitychange',f);});"
        "if('Notification' in window&&Notification.permission==='granted'){"
        "try{var n=new Notification(text,{tag:'openms-run'});"
        "n.onclick=function(){window.focus();n.close();};}catch(e){}}"
        "})();</script>"
    )
