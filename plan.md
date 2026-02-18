# Plan: Add Cookie-Based Captcha Bypass

## Goal
When a user solves the captcha, set a browser cookie (`captcha_passed=true`) that expires after 1 day. On subsequent visits, check for this cookie and skip the captcha if it exists.

## Approach
Use `streamlit_js_eval` (already declared as a dependency in `requirements.txt`) to read/write browser cookies via JavaScript. No new dependencies needed.

### Key consideration: async behavior
`streamlit_js_eval` is a Streamlit component — it returns `None` (or `0`) on the first render, then returns the actual JS result on rerun. The cookie check must handle this:
- `None`/`0` → JS hasn't executed yet, don't decide yet (fall through to captcha)
- `"true"` → cookie found, skip captcha
- Any other string → no valid cookie, show captcha

---

## Changes

### File 1: `src/common/captcha_.py`

**Change 1a — Add import (line 1 area)**

Add `from streamlit_js_eval import streamlit_js_eval` to the imports section.

**Change 1b — Add cookie expiry constant (after line 185)**

Add:
```python
CAPTCHA_COOKIE_MAX_AGE = 86400  # 1 day in seconds
```

**Change 1c — Cookie check at start of `captcha_control()` (lines 206–207)**

Before the existing `if "controllo" not in st.session_state ...` check, insert a cookie check block:

```python
def captcha_control():
    # ... (docstring unchanged) ...

    # Check if user already passed captcha via browser cookie
    cookie_val = streamlit_js_eval(
        js_expressions=(
            "document.cookie.split('; ')"
            ".find(c => c.startsWith('captcha_passed='))"
            "?.split('=')[1] || ''"
        ),
        key="captcha_cookie_check",
    )
    # cookie_val is None on first render (JS hasn't executed yet),
    # then the actual string value on rerun
    if cookie_val == "true":
        st.session_state["controllo"] = True
        return

    # existing code continues: if "controllo" not in st.session_state or ...
```

This will:
- On first render: `cookie_val` is `None` → falls through to the existing captcha logic
- On rerun (JS has executed): `cookie_val` is `"true"` → sets `controllo=True` and returns, skipping captcha entirely
- If cookie doesn't exist: `cookie_val` is `""` → falls through to captcha

**Change 1d — Set cookie after successful captcha verification (line 257 area)**

After `st.session_state["controllo"] = True` and before `st.rerun()`, set the cookie:

```python
if st.session_state["Captcha"].lower() == capta2_text.lower().strip():
    del st.session_state["Captcha"]
    if "captcha_input" in st.session_state:
        del st.session_state["captcha_input"]
    col1.empty()
    st.session_state["controllo"] = True
    # Set browser cookie to remember captcha was passed
    streamlit_js_eval(
        js_expressions=f"document.cookie = 'captcha_passed=true; max-age={CAPTCHA_COOKIE_MAX_AGE}; path=/; SameSite=Strict'",
        key="captcha_cookie_set",
    )
    st.rerun()
```

---

## Summary of touched files

| File | What changes |
|------|-------------|
| `src/common/captcha_.py` | Add import, add constant, add cookie check at top of `captcha_control()`, set cookie on successful verification |

No other files need changes. No new dependencies.

## Testing notes
- The cookie check adds one extra Streamlit rerun on the very first page load (JS executes, returns value, triggers rerun). This is imperceptible to users.
- The cookie is scoped to `path=/` so it works across all pages of the app.
- `SameSite=Strict` prevents the cookie from being sent in cross-site requests.
- The cookie is only checked in online mode — in local mode, `controllo` is already set to `True` in `common.py:485` before `captcha_control()` is called, so the function returns immediately at the existing check on line 206.
