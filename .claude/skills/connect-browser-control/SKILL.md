---
name: connect-browser-control
description: Use when a session needs to drive a browser rather than merely open one - taking screenshots of a page, clicking through it, or reading its DOM - and control is not yet known to work.
---

# Connect browser control

Ends in one of two states, and the caller branches on which:

- **control, confirmed** — a browser you have driven, which loaded a page this
  machine served. The user's app opens in it.
- **no control** — page checks run in the headless browser, the app opens in
  their default browser, and rounds put their eyes on one named thing at a time.

**Neither state is ever explained to the user.** Both are this framework's
plumbing, and a limitation explained is plumbing talk however carefully the noun
is chosen. *"The browser reachable from this session lives on another machine,
so I can't look at your finished pages myself"* was a real turn, and it is
retired. It obeyed every rule this skill had — cost stated once, in their terms,
the extension unnamed — and it still told a mass spectrometrist about the
deployment topology of their coding assistant. What a user can act on is a
question about their page. Nothing above is one.

**Consider only the browser you are attached to.** Where it runs is a fact about
the deployment, not a fault in it: Claude Code is routinely a shell on one
machine and a browser on another, and the user picked neither. There is no
better browser to go looking for, and no machine to suggest they move to. Where
it runs may route your next command; it is never a finding, and it never reaches
the user. What decides whether you drive it is one thing only: whether it can
load a page you serve.

**Chromium only, but that is a wide family.** Claude Code registers its native
messaging host for Chrome, Edge, Chromium, Brave, Arc, Opera and Vivaldi — check
the machine rather than assuming, since the list is the installer's and can
grow:

```
Windows:  HKCU:\Software\**\NativeMessagingHosts\com.anthropic.claude_code_browser_extension
macOS:    ~/Library/Application Support/*/NativeMessagingHosts/
Linux:    ~/.config/*/NativeMessagingHosts/
```

**There is no Firefox extension and there will not be one from here.** The host
manifest declares a `chrome-extension://` origin, which Firefox cannot load, and
no `Mozilla` registration is written. An earlier version of this rule said the
host was registered "for Chrome, Edge and Chromium alone"; that was wrong, and
it would have had you skip a Brave or Vivaldi install that works.

**With control, open the app by driving to it.** Navigate the browser you
already hold; it is the user's own window, so the app arrives in front of them
and you are looking at their pixels rather than a second rendering of the same
page. That matters: otherwise a design round discusses two renderings, and a
header truncated in one sits fine in the other.

**With control, never launch anything to do it.** `start <url>`, `open <url>`
and `xdg-open <url>` all open the *default* browser, which is how a user who had
just installed the extension in Chrome was shown their app in Firefox. Naming a
local executable instead does not fix it — the browser you drive need not be on
this filesystem at all, so the path you found here can name a browser nobody is
sitting at. Navigating the browser under control has neither failure: there is
no default to resolve and no path to be wrong about.

**With no control, open their default and say nothing about why.** Nothing is
being protected now, so `start` / `open` / `xdg-open` is exactly right: they get
their app in a window. You simply cannot see it, so never imply you can.

Say only *"it's open at <url>"*. **That URL is always `localhost:<port>`** —
whatever address you had to use to reach the app yourself is machinery, and
theirs resolves from where they are sitting.

## Find a Chromium browser

**Only when nothing is attached.** A browser already under control needs no
path from you; this search exists to wake a shut local one so the extension in
it can answer.

Any browser from the family above. Windows keeps them under `Program Files`;
elsewhere try the executable name on `PATH`. Edge ships with Windows, so on a
Windows machine the answer is almost always yes.

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

**An empty probe is a step, not the answer.** Control is worth real effort —
it is what puts the app in the user's own window instead of a second rendering
of it — so the next move after an empty probe is a command, never another
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
finished pages myself."* After they decline, it is not named again, and
nothing takes its place: the run simply proceeds without it.

**Check that it started; `start` on Windows does not.** A measured run
issued `cmd /c start "" "<path>"`, saw its own `launched` echo, probed,
and moved on — and no browser had opened. `start` hands off and returns
whether or not anything ran. Both forms above were verified to leave a
process behind; after either, confirm the process exists before probing.

The same applies later: **opening a page starts a browser** — but only a
Chromium one is driveable. Opening the app with no control opens their
*default*, which may be Firefox, and re-probing after that finds nothing
because there is nothing there to find. So a page opening is worth a re-probe
only when what opened was the local browser you launched yourself; the install
has its own re-probe, and this rule does not govern it.

**Confirm by driving, not by probing.** A probe that returns is not proof:
navigate to any ordinary web page and take one screenshot. Not
`about:blank` — the screenshot tool refuses browser-internal URLs with
*"Can't interact with browser-internal or unparseable URLs"*, so a blank
tab fails the check while control is in fact working.

**Then confirm it can reach *this* machine, with a page you serve.** A browser
that answers is not the same as a browser that can load what you are serving,
and the difference is invisible: a run drove a browser successfully for an
entire build, pointed it at `localhost:8577`, and read **a different Streamlit
app** on that port — reporting its pages back as this run's. Most likely an
earlier build of the user's own, still running over there. The cause never
mattered; only that the pixels belonged to different software. Nothing in the
tab context distinguishes them — it reads `"New Tab" chrome://newtab/` either
way. Only a page you serve can:

```
write  <tmp>/<random-token>.txt containing that token
serve  python -m http.server <port> --bind 0.0.0.0 --directory <tmp>
drive  browser -> http://<candidate>/<token>.txt
read   the page

token back    ->  it can reach you. Use it, and say nothing.
anything else ->  next candidate, then stop.
```

Candidates, in order: `127.0.0.1:<port>`, then each routable interface this host
has. A random token on a random port is why binding every interface is safe here
— and necessary, or every candidate but loopback fails for the wrong reason.

**A browser that fails every candidate is never driven.** Not for the smoke run,
not for a design round, not once. It renders *some* app on that port
convincingly, and a screenshot of the wrong app is worse than no screenshot: it
is a finding about different software, delivered to your user as one about
theirs.

**Ask the extension where that browser is to route the fix, never to report
it.** It says whether the browser is local, and that answer picks between two
different repairs. It is not a finding, and it does not reach the user:

- **not local** — an ordinary deployment: a shell in WSL, a container or an SSH
     host, with the browser on the desktop that owns it. Nothing is misconfigured
     and there is no second browser to switch to. The app binds every interface
     (`streamlit run` with no `--server.address`), so the only open question is
     which address that host routes to — which the candidate walk above already
     answers.
- **local, marker still fails** — the extension is answering for a browser
     that is not signed in as you. The probe's own error names the
     requirement: logged into claude.ai under the same account as Claude
     Code. Open claude.ai in their browser, ask for the sign-in, re-probe and
     re-marker.

Either way: **once**. Then stop asking.

**"Nothing to fix from here" is not an ending — and neither is silence.** A run
said exactly that and moved on, leaving the user holding nothing. Without
control the run still opens their app in their default browser and still gets
their eyes on it: one named thing, at the moment it matters, in the words of the
page — *"the header on the left column — does that read right to you?"* That is
what a design round sounds like anyway, which is the point. Nothing about the
run changes shape, so nothing about it needs announcing.

**What never happens is the preamble.** No sentence in preflight saying you will
be asking them to look, no reason offered, no tour of which browser checks what.
Stating the cost *once, early* was itself a rule here, and it was wrong: it
guaranteed a turn whose only content was the framework describing itself to
someone who had asked for an app. Successive reviews rewrote that sentence.
This one deleted it.

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

**Four roads lead to no control, and they arrive at the same place.** They
declined the install; the schema never loaded; every candidate address failed
the marker; the machine has no browser from the family at all. Each road carries
at most one repair — the launch, the install, the sign-in — and once that is
spent the road is done and no outcome is worse than the others. Carry on and say
nothing: their app still opens in their default browser, and the rounds still
ask them to look.
