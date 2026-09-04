---
name: connect-browser-control
description: Use when a session needs to drive a browser rather than merely open one - taking screenshots of a page, clicking through it, or reading its DOM - and control is not yet known to work.
---

# Connect browser control

Ends in one of two states, and the caller branches on which:

- **control, confirmed** — a browser you have driven, which loaded a page this
  machine served on loopback. The user's app opens in it.
- **no control, declined** — you asked, and they said no. Page checks fall to the
  gate's headless browser, the app opens in their default browser, and rounds put
  their eyes on one named thing at a time.

**There is no third ending, and a run never settles for the headless browser on
its own judgement.** The only thing that puts a run there is a user who was asked
and said no. Every road that does not reach confirmed control reaches the ask,
and preflight does not move past it.

## What this stage says out loud

Decide from the probe and the marker, then produce the matching row. **This
table is the whole of what setup volunteers.** Every other sentence this skill
puts in front of a user is prescribed by name where it belongs — the *"carry on
without it?"* follow-up, the one line on a decline, *"it's open at `<url>`"*,
and the request to reopen a browser whose device has gone. Nothing outside those
is spoken, and none of this governs what you say when asked directly.

| what you found | what they read |
|---|---|
| it answers, and the marker comes back | *(nothing)* |
| it answers, the marker fails, and a Chromium browser is on this machine | the click, in that browser |
| it answers *"not connected"* | the click, in the browser already there |
| no schema at all | the click, and the restart |
| no Chromium browser on this machine at all | the request to install one |
| they have already said no | *(nothing further — the decline had its one line, and it is settled)* |

**Silence is earned by confirmed control, or by a decline. Nothing else earns
it.** An earlier table had three silent rows and a run walked one of them: the
probe answered, the marker failed, it said nothing and carried on — while a
Chromium browser sat installed and extension-free at `/usr/bin/google-chrome`,
one click from working. The user asked twice what was happening before anything
surfaced. That row asserted no repair existed instead of going to look for one.
Rows two and four here exist because the repair did.

**What is never said is the topology.** *"The browser reachable from this session
lives on another machine, so I can't look at your finished pages myself — I'll
check them in a local headless browser"* was a real turn, and it is retired. It
obeyed every rule this skill then had — cost stated once, in their terms, the
extension unnamed — and it still told a mass spectrometrist about the deployment
of their coding assistant and the inventory of browsers behind it. Each row above
is a click, a restart, or an install: something to do. None of them is an
explanation.

**Where the browser runs is never a finding.** Claude Code is routinely a shell
on one machine and a browser on another, and the user picked neither. Where it
runs may route your next command; it never reaches the user, and there is no
machine to suggest they move to. What decides whether you drive it is one thing
only: whether it can load a page you serve on loopback.

**Attached is not theirs.** The extension answering proves a browser exists
somewhere you can reach — not that it can reach *you*. A run drove one for an
entire preflight, screenshotting pages the user could not see, and learned the
difference only when they said so. The marker separates those two: a browser
that answers, from a browser that loads what this host serves.

**What the marker cannot separate is presence.** It says the pair works; it
cannot say a human is in front of that window, and nothing available can. `switch_browser` claims to — *"sends a connection
request to every Chrome browser with the extension installed and waits for the
user to click Connect"* — and it was measured: it **excludes the browser you are
already attached to**. With one browser connected it returns *"No other browsers
available to switch to"* in under six seconds. With two, and the user sitting at
the attached one, it timed out at ~124 seconds three times running while that
user watched their own Chrome and reported *"Nothing appears.."*. There was
nothing to click. **Do not reach for it to confirm the browser you already
hold** — it is structurally incapable of prompting that one.

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
already hold; it is the window that just proved it can load what you serve, and
no other window has proved anything. That matters: otherwise a design round
discusses two renderings of the same page, and a header truncated in one sits
fine in the other.

**With control, never launch anything to do it.** `start <url>`, `open <url>`
and `xdg-open <url>` all open the *default* browser, which is how a user who had
just installed the extension in Chrome was shown their app in Firefox. Naming a
local executable instead does not fix it — the browser you drive need not be on
this filesystem at all, so the path you found here can name a browser nobody is
sitting at. Navigating the browser under control has neither failure: there is
no default to resolve and no path to be wrong about.

**Before you point it at the app, check the port is yours.** The app runs on
this host and you started it, so confirm from the shell that the port is held by
the process this run launched — not by a stale build of theirs, not by anything
else. A port you did not verify is a page you cannot vouch for. If it is not
yours, take another port and relaunch rather than navigating at it.

**Once they have declined, open their default and say nothing about why.**
Nothing is being protected now, so `start` / `open` / `xdg-open` is exactly
right: they get their app in a window. You simply cannot see it, so never imply
you can.

Say only *"it's open at <url>"*. **That URL is always `localhost:<port>`** —
whatever address you had to use to reach the app yourself is machinery, and
theirs resolves from where they are sitting.

## Find a Chromium browser

**Whenever control is not confirmed.** Not only when the probe came back empty —
also when it answered for a browser that failed the marker, which is the case
that most needs the search, and the case an earlier gate excluded. Something
being attached is not a reason to stop looking: a browser on this machine that
the extension is not in is one click from being the one you drive.

Any browser from the family above. Windows keeps them under `Program Files`;
elsewhere try the executable name on `PATH`. Edge ships with Windows, so on a
Windows machine the answer is almost always yes.

What you find decides which row of the table you are on: a browser here means
the click; nothing here means the request to install one.

## Connect control, by using it

Its tools are deferred MCP
tools, so they do not appear until asked for:

```
ToolSearch  select:mcp__claude-in-chrome__tabs_context_mcp,
                      mcp__claude-in-chrome__navigate,
                      mcp__claude-in-chrome__computer,
                      mcp__claude-in-chrome__get_page_text,
                      mcp__claude-in-chrome__list_connected_browsers,
                      mcp__claude-in-chrome__select_browser
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
                     one -- but still search, because the store page has to
                     open somewhere and the last row of the ask cannot be
                     chosen without knowing. Then go to the ask.
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

## Read the browser list, never show it

`list_connected_browsers` returns every browser on the account —
`deviceId`, `name`, `osPlatform`, `connectedAt`, `isLocal`. Read it to route
yourself. **It does not reach the user.** Its own description mandates an
`AskUserQuestion` listing every browser with its `deviceId` in the label, and
that turn is the topology this skill retired — a mass spectrometrist reading
UUIDs and operating-system names to fix a coding assistant. The mandate lives in
that description alone; `select_browser` carries none of it, and says only
*"select a specific Chrome browser by deviceId... without broadcasting a pairing
request."* So a run may read the list and act on it without ever rendering it.

**Only `deviceId` is stable. The names are positional.** The same device was
`"Browser 2"` in one listing and `"Browser 1"` in the next, and the list
renumbers as membership changes. Two orderings fit every listing measured and
neither could be separated from the other, so do not infer one. Select by
`deviceId`, and never carry a name from one listing to the next.

**Nothing in the list says which browser you are attached to.** There is no such
field, and `tabs_context_mcp` does not carry one either — a run that reported
*"the session was attached to the wrong one"* had inferred it by elimination
from a list holding exactly one non-local device, and could not have with two.
You do not need it: the marker tells you whether the browser you hold can reach
you, and that is the whole question.

## Confirm by driving, not by probing

A probe that returns is not proof: navigate to any ordinary web page and take
one screenshot. Not `about:blank` — the screenshot tool refuses browser-internal
URLs with *"Can't interact with browser-internal or unparseable URLs"*, so a
blank tab fails the check while control is in fact working.

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
write  <tmp>/<token>.txt containing that token
serve  python -m http.server <random port> --bind 127.0.0.1 --directory <tmp>
check  curl the URL from this shell first -- the token must come back
drive  browser -> http://127.0.0.1:<port>/<token>.txt
read   get_page_text, and match the token exactly

token back    ->  it can reach you. Use it, and say nothing.
anything else ->  it cannot. Go to the ask.
```

**The token is at least ten characters, after trimming.** Nine fails. This was
bisected on a live server, same tab, same `Content-type: text/plain`, varying
only the body: `abcdefghij` passes, `abcdefghi` fails, and padding the nine with
newlines or spaces still fails — the threshold applies to the trimmed text. A
trailing newline is free. A run lost its marker to a nine-character token and
diagnosed the extractor instead.

**Write the bind out.** `python -m http.server` defaults to `0.0.0.0`, so
dropping the flag does not narrow the bind, it widens it — and the wide bind is
the one command the auto-mode classifier refuses, denied on two of four trials
here and on every trial elsewhere. `--bind 127.0.0.1` is the only bind that can
be assumed available on any host.

**Loopback is the only candidate.** There is no walk. A routable interface has
never once returned a token in any recorded run, the classifier's treatment of
named routable addresses differs by host, and a browser that needs a routable
hop to reach you is not the local one. WSL forwards localhost by default and
`docker -p` publishes to it, so the ordinary deployments still pass here.

**Curl before you drive, or you cannot read the answer.** A dead server and an
unreachable browser produce the same browser-side error. A run picked a port
that was already in use, its server died with `Address already in use`, and it
navigated at the corpse and read the error page as a marker failure — four
wasted calls chasing a browser that was fine. The `curl` separates them: it
passes, and every later browser failure is evidence about the browser.

**Pick the port at random and mean it.** Three separate builds all used 8791,
which is how one of them collided.

**Never read the token from the URL or the tab title.** Tab context echoes back
the URL you *requested* — token and all — even when the navigation totally
failed, so a token seen there is your own input read back as proof. Titles are
worse: a `text/plain` page has none, and the title is stale for a beat after
navigating. The token has to come out of the page body.

**A candidate you cannot test is a candidate that failed.** A sandbox that
blocks the navigation has not left you an open question — it has left you
without the evidence, which lands in the same place as evidence against. A run
treated that gap as a third state, reported *"I can't yet trust it"*, promised
itself a retest later, and drove nothing in the meantime. There are two verdicts
here and no others.

**A browser that fails the marker is never driven.** Not for the smoke run, not
for a design round, not once. It renders *some* app on that port convincingly,
and a screenshot of the wrong app is worse than no screenshot: it is a finding
about different software, delivered to your user as one about theirs.

## When it breaks later

Control is confirmed once, at preflight, and then used. There is no re-check
between rounds — but the confirmation can stop being true, and **it stops
silently in the success direction**, which is why the recovery below exists.

A user closed their browser mid-session. Their device left
`list_connected_browsers` on its own, the session was **silently re-attached to
a browser on another machine**, and `navigate` went on returning *"Navigated to
`<url>`"* — success, every call — while rendering somewhere nobody was sitting.
No error surfaced. Only serving a page and failing to read it back revealed it.

**Two things are not evidence, and both look like it.** `pgrep` counted three
live Chrome processes after that device had already left the list, so a running
browser is not a connected device. And a successful `navigate` return says the
call was accepted, not that anything you recognise is on screen.

**When a page comes back wrong, re-enumerate — do not re-probe.**
`tabs_context_mcp` answers for whatever you are attached to now and will look
perfectly healthy on the wrong browser. `list_connected_browsers` is what shows
the device is gone. A run re-probed twice after its user acted, saw the same
healthy answer both times, and missed a browser that had appeared five calls
earlier.

**The repair is one action and it is theirs: reopen the browser.** Measured —
the device returns to the list on its own with a fresh `connectedAt`, with no
reinstall, no sign-in and nothing else asked of them. Then `select_browser` by
`deviceId`, and marker it again before you show them anything.

**`tabGroupId` is per-attachment, not per-device.** Reattaching to the *same*
device yields a new group, so a change tells you only that something moved,
never what. If you have one recorded, unchanged means you are still on the
attachment you verified; changed means re-marker. It never means reselect.

## The ask

**Take them to it; do not offer to mention it later.** You cannot finish this
yourself — the extension comes from the store, in their browser, under their
claude.ai account, and the click and the sign-in are theirs. Everything up to
that is yours. Open `https://claude.ai/chrome` the same way you open any page,
say the one thing to click, and scale the request to the row you are on:

```
marker failed, browser here  ->  launch it, take them to the store page:
                                    "one click to add the Claude browser
                                    extension and I can check the finished
                                    pages myself."
schema, not connected        ->  the same click, in the browser already there.
no schema at all             ->  the click, then: "one click to add it, then
                                    start me again -- nothing's been decided
                                    yet, so there's nothing to lose."
no Chromium browser at all   ->  ask them to install one -- Chrome, Edge,
                                    Brave, any of the family -- once, plainly,
                                    and as something they may say no to.
```

**Preflight stops here until they answer.** The notebook question does not go
out first, and neither does anything else that moves the run forward; this is
the one place a run waits. Asking and pressing on regardless is how a run
reaches the headless browser without a decline, which is the thing that must not
happen.

**Only an explicit no is a decline.** Read the list before reading their words:
whatever they reply, re-enumerate, re-select and re-marker once, and if control
now answers, use it and say nothing further. Their click may have created a
device that was not there when you asked — one appeared nineteen minutes into a
preflight, and the run that only re-probed did not see it for five more calls.
If control still does not answer and they have not plainly declined — they said
*"done"*, or *"later"*, or answered with their notebook path — ask once, short:
*"carry on without it?"* That is the only follow-up, and their answer to it
settles the run either way.

**Then it is settled and it is never raised again.** Not at the first design
round, not at the gate, not when a page would have been easier to check.
*"Happy to point you at the setup for next time"* is the failure — it converts a
one-click fix available right now into homework. So is raising it later — *"I'd
have to ask you to set that up"*, landing mid-decision, which is the thing this
step exists to prevent.

**Name the extension only to act on it.** Naming it to explain a limitation is
plumbing talk — *"your Chrome extension isn't connected, so I can't check the
pages"* tells a mass spectrometrist about this framework's wiring and gives them
nothing to do. Naming it inside a request is different, because it comes with an
action and a reason. After they decline, it is not named again.

**On the decline, one line, and it is about them.** *"I'll ask you to look at a
page or two as we go."* That is the whole of it: what they will be asked to do.
Not what you cannot see, not what the headless browser does instead, not why.
The run then behaves exactly as that line promised — rounds put one named thing
in front of them, in the words of the page: *"the header on the left column —
does that read right to you?"*

**Check that it started; `start` on Windows does not.** A measured run
issued `cmd /c start "" "<path>"`, saw its own `launched` echo, probed,
and moved on — and no browser had opened. `start` hands off and returns
whether or not anything ran. Both launch forms above were verified to leave a
process behind; after either, confirm the process exists before probing — and
remember a live process is not a connected device, so the probe still decides.

The same applies later: **opening a page starts a browser** — but only a
Chromium one is driveable. Opening the app after a decline opens their
*default*, which may be Firefox, and re-probing after that finds nothing
because there is nothing there to find. So a page opening is worth a re-probe
only when what opened was a Chromium browser; the ask has its own re-check, and
this rule does not govern it.

**Often the default and the one you launched are the same window.** Edge ships
as the default on Windows, so `start <url>` there opens the browser you already
launched and probed — one window, not two. Look at what the default actually
resolves to rather than assuming a page you opened landed somewhere else: if it
is Chromium, that page just started something worth probing again.

## What is said, and what is not

**No preamble, ever.** Nothing said *ahead of the ask* about what you will need
from them later, no reason offered, no tour of which browser checks what.
Stating the cost *once, early* was itself a rule here, and it was wrong: it
guaranteed a turn whose only content was the framework describing itself to
someone who had asked for an app. **A preamble is speech before they have
chosen**, which is what makes two sentences here not preamble at all: the ask,
which is a request for a click that the table licenses, and the one line after a
decline, which follows their own answer and tells them what they just chose.

**If control is real, nothing is said about it at all.** Announcing control
*before* driving anything is how a session ends up claiming a capability it has
not established, or disclaiming one it has.

**The setup summary claims nothing you have not done.** A run ended preflight
with *"Everything's set up ... and I can open pages in your Chrome and check
them myself"*, and had to retract the second half later: *"Correct — I can't."*
Opening and checking have different requirements, so a sentence joining them is
half true at best. Until you have driven a page and seen your own marker come
back, the summary says what was installed and nothing about checking.

**Asked directly, answer fully.** *"What about driving Chrome?"* is a question
about the machinery from someone who wants the machinery, and every rule above
governs what you *volunteer*, not what you answer. Say what was probed, what was
served, what came back, what it means and what would change it — plainly, and
without hedging. What a direct question does not license is the third state: a
run answered one with *"I can't yet trust it, I'll retest later"*, which was
neither verdict and left the user holding a browser nobody had decided about.
