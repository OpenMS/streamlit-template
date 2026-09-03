"""Usability gate for a Streamlit results page.

AppTest executes no JavaScript, so it cannot see OpenMS-Insight components at
all -- a page built entirely from them passes every AppTest assertion while
rendering nothing. This drives a real browser instead.

Hard assertions catch breakage; the screenshot it saves is for a human or model
to critique against the dashboard style contract.

Usage:
  python gate.py --url http://localhost:8510/identification_results \
      --expect-components 2 --screenshot shot.png
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from playwright.sync_api import sync_playwright

VIEWPORT = {"width": 1280, "height": 800}


class Gate:
    def __init__(self):
        self.checks: list[tuple[str, bool, str]] = []

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.checks.append((name, bool(ok), detail))
        mark = "ok  " if ok else "FAIL"
        print(f"  [{mark}] {name}" + (f"  -- {detail}" if detail else ""))
        return bool(ok)

    def warn(self, name: str, detail: str = "") -> None:
        self.checks.append((name, True, "WARN: " + detail))
        print(f"  [warn] {name}" + (f"  -- {detail}" if detail else ""))

    @property
    def failed(self) -> int:
        return sum(1 for _, ok, _ in self.checks if not ok)


def settle(page, seconds: float = 2.0, expect_frames: int = 0,
           timeout: float = 90.0) -> None:
    """Wait for Streamlit to stop running, not for a fixed number of seconds.

    A fixed sleep samples a half-rendered page: Streamlit streams output while
    the script is still executing, and OpenMS-Insight preprocesses large tables
    in a subprocess before its component ever mounts. Poll the app's own running
    indicator, then wait for the components to actually appear.
    """
    time.sleep(seconds)
    deadline = time.time() + timeout
    last, stable_since = -1, None
    while time.time() < deadline:
        running = page.query_selector("[data-testid='stStatusWidget']")
        frames = len(page.query_selector_all("iframe"))
        if frames != last:
            last, stable_since = frames, time.time()
        if running is None and frames >= expect_frames:
            break
        # Waiting for a frame COUNT alone is wrong: --expect-components is the
        # TOTAL panel count including native fallbacks, so a page with two
        # iframes plus a show_fig() panel waits for a third iframe that never
        # arrives, and burns the whole timeout. Measured on the one corpus app
        # with a fallback panel: 96.5s first paint, every run, for twenty runs,
        # read as a slow page rather than as this bug. So also stop once the app
        # is idle and the iframe count has stopped changing.
        if running is None and stable_since and time.time() - stable_since >= 3.0:
            break
        time.sleep(1.0)
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass


def component_frames(page):
    """Iframes holding custom components, with their rendered size."""
    frames = []
    for el in page.query_selector_all("iframe"):
        try:
            box = el.bounding_box() or {}
            frames.append((el, box.get("width", 0), box.get("height", 0)))
        except Exception:
            continue
    return frames


# A panel is not always an Insight component. When no Insight component fits a
# role, build-insight-dashboard prescribes falling back to pyopenms-viz through
# show_fig(), which renders a native Streamlit chart rather than an iframe.
# Counting iframes alone marks that dashboard down for following the guidance.
NATIVE_PANEL_SELECTORS = (
    "[data-testid='stPlotlyChart']",
    "[data-testid='stVegaLiteChart']",
    "[data-testid='stArrowVegaLiteChart']",
    "[data-testid='stPyplotChart']",
)


def native_panels(page):
    """Non-iframe chart panels (fallback panels), with their rendered size."""
    panels = []
    for selector in NATIVE_PANEL_SELECTORS:
        for el in page.query_selector_all(selector):
            try:
                box = el.bounding_box() or {}
                panels.append((el, box.get("width", 0), box.get("height", 0)))
            except Exception:
                continue
    return panels


def stuck_panels(frames):
    """Panels that mounted but never finished loading their data.

    This is the failure mode the rest of the gate is blind to: the iframe has
    real size, the console is clean and nothing throws, so every other check
    passes while the user looks at the word "Loading" forever. It happens when a
    panel filters on a link identifier that no panel has set and no
    filter_defaults value covers.

    Only called after settle(), so a loading indicator here has outlived the
    app's own running indicator and is not merely late.
    """
    stuck = []
    for el, _, _ in frames:
        try:
            frame = el.content_frame()
            if frame is None:
                continue
            text = (frame.inner_text("body") or "").strip()
        except Exception:
            continue
        if not text:
            stuck.append("a panel renders no text at all")
            continue
        # A real panel carries axis labels, headers or rows. A stuck one has a
        # placeholder and nothing else, so bound this on total length as well as
        # on the word, or a table with a "Loading" column header trips it.
        if len(text) < 200 and any(
            marker in text.lower() for marker in ("loading", "no data", "waiting")
        ):
            stuck.append(f"a panel shows only: {text.splitlines()[0][:60]!r}")
    return stuck


def design_notes(page, frames, native, viewport_height):
    """Observations for the final design round, phrased for a user.

    The gate's second job. Its findings feed the last design round in
    build-insight-dashboard, where a user reads them -- so these are sentences
    about the page, not log lines about assertions.
    """
    notes = []

    below = [f for f in frames + native
             if (f[0].bounding_box() or {}).get("y", 0) + f[2] > viewport_height]
    if below:
        notes.append(
            f"{len(below)} panel(s) sit below the fold at {viewport_height}px -- "
            "a first-time visitor has to scroll to learn they exist"
        )

    if not page.query_selector("[data-testid='stMetric']"):
        notes.append(
            "no summary strip: the page opens with no headline numbers, so the "
            "size of the result is only inferable from a table"
        )

    # Crowding, measured. This note used to fire on `len(cols) > 6`, the ceiling
    # tick 002 disproved: a six-column table truncated 'Matched i...' while the
    # count check stayed silent. `truncated_headers` fails on a header that has
    # already overflowed; the useful *note* is the one that has not overflowed
    # yet but has no room left, because that is the table a longer value or one
    # more column will break.
    for el, _, _ in frames:
        try:
            frame = el.content_frame()
            if frame is None:
                continue
            tight = frame.evaluate(
                """() => {
                    const sel = '.tabulator-col-title, .tabulator-col .tabulator-title';
                    let worst = null;
                    for (const n of document.querySelectorAll(sel)) {
                        const slack = n.clientWidth - n.scrollWidth;
                        if (slack < 0) continue;          // already truncated
                        if (worst === null || slack < worst.slack) {
                            worst = {slack, text: (n.textContent || '').trim().slice(0, 40)};
                        }
                    }
                    return worst;
                }"""
            )
        except Exception:
            continue
        # 8px is roughly one character at Tabulator's default header font, so
        # the note means "one more character and this truncates" rather than an
        # aesthetic judgement. It is a threshold on the measured property, not a
        # proxy for it -- which is the distinction the column-count rule failed.
        if tight and tight["slack"] <= 8:
            notes.append(
                f"the header {tight['text']!r} has {tight['slack']}px of slack "
                "left -- a longer value, or one more column, truncates it"
            )

    return notes


def truncated_headers(frames):
    """Table column headers whose text does not fit the column it sits in.

    Column count was a proxy for this and the proxy was wrong: a table with
    exactly six columns rendered 'Matched i...' while a >6 check stayed silent
    and the gate reported a full pass. Measure the property actually cared about
    -- rendered text wider than the box holding it -- instead of guessing at a
    ceiling that produces it.

    Tabulator sets the title element's scrollWidth beyond its clientWidth when it
    ellipsises, so this is exact rather than an estimate.
    """
    truncated = []
    for el, _, _ in frames:
        try:
            frame = el.content_frame()
            if frame is None:
                continue
            found = frame.evaluate(
                """() => {
                    const out = [];
                    const sel = '.tabulator-col-title, .tabulator-col .tabulator-title';
                    for (const n of document.querySelectorAll(sel)) {
                        if (n.scrollWidth > n.clientWidth + 1) {
                            out.push((n.textContent || '').trim().slice(0, 40));
                        }
                    }
                    return out;
                }"""
            )
        except Exception:
            continue
        truncated.extend(h for h in found if h)
    return truncated


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--expect-components", type=int, default=1)
    ap.add_argument("--screenshot", default="usability.png")
    ap.add_argument("--first-paint-budget", type=float, default=5.0)
    ap.add_argument("--no-interaction", action="store_true")
    ap.add_argument(
        "--nav",
        default=None,
        help="Sidebar link to click after loading --url. Navigating like a user "
        "avoids Streamlit resolving /_stcore relative to a sub-page path, which "
        "produces two spurious 404s when a page URL is opened directly.",
    )
    ap.add_argument(
        "--ignore-console",
        action="append",
        default=[],
        help="Substring of a known-benign console error to ignore. Every use "
        "should be justified in the skill or the app's notes.",
    )
    ap.add_argument("--capture-height", type=int, default=2400)
    args = ap.parse_args()

    gate = Gate()
    console_errors: list[str] = []
    page_errors: list[str] = []
    failed_requests: list[str] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport=VIEWPORT)
        page.on(
            "console",
            lambda m: console_errors.append(m.text) if m.type == "error" else None,
        )
        page.on("pageerror", lambda e: page_errors.append(str(e)))
        # "Failed to load resource" in the console never says which resource;
        # record the URL and status so a 404 is actionable.
        page.on(
            "response",
            lambda r: failed_requests.append(f"{r.status} {r.url}")
            if r.status >= 400
            else None,
        )

        print(f"\nUSABILITY GATE  {args.url}  @{VIEWPORT['width']}x{VIEWPORT['height']}\n")

        t0 = time.time()
        page.goto(args.url, wait_until="domcontentloaded", timeout=60000)
        if args.nav:
            settle(page, 2.0)
            link = page.get_by_role("link", name=args.nav).first
            link.click(timeout=20000)
        settle(page, 3.0, expect_frames=args.expect_components)
        first_paint = time.time() - t0

        console_errors[:] = [
            e for e in console_errors
            if not any(pat in e for pat in args.ignore_console)
        ]
        page_errors[:] = [
            e for e in page_errors
            if not any(pat in e for pat in args.ignore_console)
        ]
        failed_requests[:] = [
            r for r in failed_requests
            if not any(pat in r for pat in args.ignore_console)
        ]

        body = page.inner_text("body")

        gate.check(
            "page boots without a Python traceback",
            "Traceback (most recent call last)" not in body,
            body.split("Traceback")[-1][:160].strip() if "Traceback" in body else "",
        )
        gate.check(
            "no Streamlit exception block",
            page.query_selector("[data-testid='stException']") is None,
        )
        gate.check("no uncaught JS page errors", not page_errors, "; ".join(page_errors[:2]))
        gate.check(
            "browser console clean",
            not console_errors,
            f"{len(console_errors)} error(s): " + "; ".join(console_errors[:2]),
        )

        frames = component_frames(page)
        rendered = [f for f in frames if f[1] > 50 and f[2] > 50]
        native = [p for p in native_panels(page) if p[1] > 50 and p[2] > 50]
        total = len(rendered) + len(native)
        gate.check(
            f"{args.expect_components} panel(s) rendered with real size",
            total >= args.expect_components,
            f"found {len(rendered)} Insight component(s) + {len(native)} "
            f"fallback panel(s), of {len(frames)} iframes",
        )
        # Machine-readable, so a harness never has to scrape the prose above.
        # Renaming a check's wording must not silently zero someone's metric.
        print(f"PANELS insight={len(rendered)} fallback={len(native)} total={total}")

        # A panel that mounted but never loaded passes every check above.
        stuck = stuck_panels(rendered)
        gate.check(
            "no panel is stuck loading",
            not stuck,
            "; ".join(stuck[:2]),
        )

        # An unreadable column header is a defect a user sees immediately and no
        # other assertion sees at all -- the same shape of blind spot as the
        # stuck panel above.
        clipped = truncated_headers(rendered)
        gate.check(
            "no table header is truncated",
            not clipped,
            "clipped: " + ", ".join(repr(h) for h in clipped[:3]) if clipped else "",
        )

        # Empty state, not a blank page.
        gate.check("page is not blank", len(body.strip()) > 40, f"{len(body.strip())} chars")

        # Horizontal overflow: the body must never scroll sideways.
        overflow = page.evaluate(
            "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )
        gate.check("no horizontal scrollbar", overflow <= 2, f"overflow {overflow}px")

        if first_paint <= args.first_paint_budget:
            gate.check(f"first paint within {args.first_paint_budget}s", True,
                       f"{first_paint:.1f}s")
        else:
            gate.warn("first paint over budget", f"{first_paint:.1f}s")

        # Cross-component linking: click a row, assert a linked panel changes.
        if not args.no_interaction and rendered:
            before = page.screenshot(full_page=False)
            clicked = False
            for el, _, _ in rendered:
                frame = el.content_frame()
                if not frame:
                    continue
                row = frame.query_selector(".tabulator-row")
                if row:
                    try:
                        row.click(timeout=5000)
                        clicked = True
                        break
                    except Exception:
                        continue
            if clicked:
                settle(page, 2.5)
                after = page.screenshot(full_page=False)
                gate.check(
                    "clicking a table row changes a linked panel",
                    before != after,
                    "page identical after click" if before == after else "",
                )
            else:
                gate.warn("no clickable table row found", "linking not exercised")

        # The gate's second output: not pass/fail, but material for the final
        # design round. Printed before the screenshot so the two arrive together.
        notes = design_notes(page, rendered, native, VIEWPORT["height"])
        if notes:
            print("\n  design notes -- material for the final round:")
            for note in notes:
                print(f"   -  {note}")

        # full_page is useless here: Streamlit scrolls its main container, not
        # the document, so a full-page shot captures only the first viewport.
        # Grow the viewport instead so panels below the fold are in the critique.
        page.set_viewport_size({"width": VIEWPORT["width"], "height": args.capture_height})
        settle(page, 2.0)
        page.screenshot(path=args.screenshot)
        page.set_viewport_size(VIEWPORT)
        print(f"\n  [img ] screenshot -> {args.screenshot}")

        browser.close()

    print(f"\n{'PASS' if gate.failed == 0 else 'FAIL'}: "
          f"{len(gate.checks) - gate.failed}/{len(gate.checks)} checks\n")
    if console_errors:
        print("console errors:")
        for e in console_errors[:8]:
            print("   ", e[:200])
    if failed_requests:
        print("failed requests:")
        for r in failed_requests[:8]:
            print("   ", r[:200])
    return 1 if gate.failed else 0


if __name__ == "__main__":
    sys.exit(main())
