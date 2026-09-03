---
name: connect-browser-control
description: Use when a session needs to drive a browser rather than merely open one - taking screenshots of a page, clicking through it, or reading its DOM - and control is not yet known to work.
---

# Connect browser control

Ends in one of two states, and the caller branches on which:

- **control, confirmed** — a browser this machine can serve, which you have
  driven. Say nothing further about it.
- **no control** — the cost is stated once in the user's terms, and page checks
  run in the local headless browser instead.

**Chromium only.** Chrome, Edge, Brave, Chromium. There is no Firefox
extension and there will not be one from here: the native messaging host Claude
Code registers declares a `chrome-extension://` origin, which Firefox cannot
load, and it is registered for Chrome, Edge and Chromium alone.

**Open the app in the browser you drive.** When control is confirmed, that is
where the user's app opens too — otherwise a design round discusses two
renderings, and a header truncated in one sits fine in the other. Say only
*"it's open at <url>"*; which browser, and why, is not their problem. With no
control, open their default and never imply you can see it.

## Find a Chromium browser

Chrome, Edge, Brave, Chromium. Windows keeps them under `Program Files`; elsewhere try the executable
name on `PATH`. Edge ships with Windows, so on a Windows machine the
answer is almost always yes.

## Connect control, by using it

Its tools are deferred MCP
tools, so they do not appear until asked for:

```
ToolSearch  select:mcp__claude-in-chrome__tabs_context_mcp,
                      mcp__claude-in-chrome__navigate,
                      mcp__claude-in-chrome__computer
mcp__claude-in-chrome__tabs_context_mcp   {"createIfEmpty": true}
```

`createIfEmpty` opens a **tab in a running browser**. It does not launch a
closed one, and the extension is what answers the probe — so with the
browser shut, control is unavailable and the probe rightly says so.

**Preflight ends with the browser under control** — every design round
and the whole usability gate depend on it. An empty probe is a step in a
sequence, not the answer, and the next step is a command, not another
probe:

```
no schema?    ->  control does not exist in this session at all. There is
                     no probe to run and launching a browser will not create
                     one; go straight to the offer below.
probe empty?  ->  launch the browser found above, wait ~5s, probe again
                     PowerShell:  Start-Process '<path found above>'
                     POSIX shell: "<path found above>" >/dev/null 2>&1 &
still empty?  ->  the extension is missing from that browser.
```

**Two failure shapes, and they are not the same.** A schema that loads
and answers *"not connected"* means control exists and the browser is
shut or the extension missing from it — fixable here. `ToolSearch`
returning **no schema** means this session has no browser control to
connect to at all: there is no probe to run, launching a browser cannot
create one, and a session started afterwards is what picks the tools up.

**Take them to the install; do not offer to mention it later.** You cannot
finish this yourself — the extension comes from the store, in their
browser, under their claude.ai account, and the click and the sign-in are
theirs. Everything up to that is yours. Open `https://claude.ai/chrome`
the same way you open any page (see the table above), say the one thing to
click, and then:

```
schema, not connected  ->  carry on with capture while they install;
                              re-probe before the first design round
no schema at all       ->  wait. Then: "one click to add it, then start
                              me again -- nothing's been decided yet, so
                              there's nothing to lose." A restart is theirs
                              to do; you cannot restart yourself.
```

*"Happy to point you at the setup for next time"* is the failure. It was a
real turn, and it converts a one-click fix available right now into
homework. So is raising it later — *"I'd have to ask you to set that up"*,
landing mid-decision, which is the thing this step exists to prevent. Ask
here, once. If they decline, it is settled for the run and never raised
again.

**Everything installs before the first question — the asking, at least.**
In the connected-but-shut case their clicking overlaps your capture work,
and that is fine: what may not drift later is the moment you ask.

**Name the extension only to act on it.** Naming it to explain a
limitation is plumbing talk — *"your Chrome extension isn't connected, so
I can't check the pages"* tells a mass spectrometrist about this
framework's wiring and gives them nothing to do. Naming it inside a
request is different, because it comes with an action and a reason:
*"one click to add the Claude browser extension and I can check the
finished pages myself."* After they decline, it is not named again — the
cost is stated in their terms and the reason is dropped.

**Check that it started; `start` on Windows does not.** A measured run
issued `cmd /c start "" "<path>"`, saw its own `launched` echo, probed,
and moved on — and no browser had opened. `start` hands off and returns
whether or not anything ran. Both forms above were verified to leave a
process behind; after either, confirm the process exists before probing.

The same applies later: **opening a page starts a browser** — but only a
Chromium one is driveable. `xdg-open` / `start <url>` opens their
*default*, which may be Firefox, and re-probing after that finds nothing
because there is nothing there to find. So if you open the app before
control is established, re-probe only when what opened was the browser
you found above.

**Confirm by driving, not by probing.** A probe that returns is not proof:
navigate to any ordinary web page and take one screenshot. Not
`about:blank` — the screenshot tool refuses browser-internal URLs with
*"Can't interact with browser-internal or unparseable URLs"*, so a blank
tab fails the check while control is in fact working.

**Then confirm it is *your* browser, with a page you serve.** A browser
answering is not the same as the browser on this machine answering, and
the difference is invisible: a run drove a browser successfully for an
entire build, pointed it at `localhost:8577`, and read **a different
Streamlit app** on that port — reporting its pages back as if they were
the user's. Nothing in the tab context distinguishes them; it reads
`"New Tab" chrome://newtab/` either way. Only a page you serve can:

```
write  <tmp>/<random-token>.txt containing that token
serve  python -m http.server <port> --bind 127.0.0.1 --directory <tmp>
drive  browser -> http://127.0.0.1:<port>/<token>.txt
read   the page

token back  ->  it is this machine's browser. Say nothing; use it.
anything else -> a browser answered, but not yours.
```

**A browser that fails the marker is never driven.** Not for the smoke
run, not for a design round, not once. It renders other people's pages
convincingly, and a screenshot of the wrong app is worse than no
screenshot — it is a finding about someone else's software delivered to
your user as theirs.

**Ask the extension where that browser is before guessing why.** It
reports whether the browser is local, and the two causes take different
fixes:

- **not local** — the browser is on another machine. A shell inside WSL, a
     container or an SSH host with the browser on the desktop that owns it is
     the ordinary case, and there is no second browser to switch to. Do not
     stop here: the app binds every interface (`streamlit run` with no
     `--server.address`), so the question is only which address that host can
     route to. Try one it can reach and re-marker.
- **local, marker still fails** — the extension is answering for a browser
     that is not signed in as you. The probe's own error names the
     requirement: logged into claude.ai under the same account as Claude
     Code. Open claude.ai in their browser, ask for the sign-in, re-probe and
     re-marker.

Either way: **once**. Then stop asking.

**"Nothing to fix from here" is not an ending.** A run said exactly that
and moved on. If the checks have to run in the local headless browser, the
user hears the cost once, in their terms — *"I'll ask you to glance at a
page or two near the end"* — and, where the browser is on another machine,
the one thing that would change it: running this where their browser is.
Never a tour of which browser is checking what.

If control is real and it is theirs, nothing more is said about it. Announcing control *before*
driving anything is how a session ends up claiming a capability it has not
established, or disclaiming one it has.

**The setup summary claims nothing you have not done.** A run ended
preflight with *"Everything's set up ... and I can open pages in your
Chrome and check them myself"*, and had to retract the second half later:
*"Correct — I can't."* Opening and checking are the two rows of the table
above and they have different requirements, so a sentence joining them is
half true at best. Until you have driven a page, the summary says what was
installed and nothing about checking.

Only if the machine has **no** Chromium browser at all does the run go
without: say what it costs *them* — *"I won't be able to check the
finished pages myself, so I'll ask you to look"*, never *"your Chrome
extension isn't connected"* — and carry on. Opening pages still works; see
the table above.
