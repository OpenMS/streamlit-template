---
name: contribute
description: Use when someone wants to contribute to an OpenMS web app (FLASHApp, OpenDDA, UmetaFlow, OpenDIAKiosk, TOPPView-Lite or the template), when a contributor's computer needs Git, a GitHub SSH key, forks and clones set up, or when a contributor asks where a change belongs and in which order to open the pull requests.
---

# Set up a contributor

The person in front of you wants to contribute to an OpenMS web app. This skill
takes them from a computer that may not even have Git to three working clones
(the app, the template it is built on, and openms-insight) and tells you, the
agent, how to open their pull requests in the right order.

You are usually reached by the one-line prompt on an app's front page
("Want to contribute?"), which names the app and its repository. The skill may
have been read from a URL, before anything is cloned: do not assume a
repository on disk.

## How to work

- **Ask before anything that changes their account or their computer**:
  installing software, writing Git's global config, creating a key, starring,
  forking. One short question each, with the command you will run. Reading
  (versions, existing keys, `git config --get`) needs no question.
- **Never ask for a password, token or private key, and never print or copy a
  private key.** Only the public key (`*.pub`) is ever shown or uploaded. If a
  step needs a login, the person does it in their browser or in a command they
  run themselves (`gh auth login`).
- **Skip what is already done.** Every step starts with a check; a step whose
  check passes is reported in a word ("Git 2.45 found") and left alone.
- Keep each message short and in plain words. At the end, give one summary
  (below), not a log of every command.

## Where you run

The prompt is usually pasted into the Claude desktop app, sometimes into
Claude Code in a terminal. Find out which of these you are in before the first
step:

- **You can run commands on their computer** (the desktop app's Code tab, or
  Claude Code): run the checks and, after a yes, the steps yourself. The
  desktop app runs on macOS and Windows; on Windows your commands run in Git
  Bash, so the paths below in `~/...` form work there too.
- **You cannot run commands** (a chat without access to their computer): say
  once that the desktop app's Code tab can do the steps for them, and offer
  that. If they stay in the chat, give one command at a time, say where to
  paste it (Terminal on macOS, PowerShell on Windows), and wait for what it
  printed before the next one.

Your shell is not interactive: a command that waits for typed input (a
passphrase, `yes/no`, a menu) hangs. So:

- Run SSH checks with `-o BatchMode=yes`, so they fail instead of waiting.
- Steps where the person types something secret or answers a prompt
  (`ssh-keygen` with a passphrase, `ssh-add`, `gh auth login`) are run **by the
  person**, in their own Terminal or PowerShell window. Give them the exact
  command, tell them what it will ask, and continue when they say it is done.
  In Claude Code in a terminal they can instead type the command after `!`.
- Long-running commands (`streamlit run`) go in the background, or the person
  starts them.

## 1. Which app

Take the app from the prompt. If none was named, ask, offering these:

| App | Repository |
|---|---|
| FLASHApp (top-down proteomics) | `OpenMS/FLASHApp` |
| OpenDDA (quantitative DDA proteomics) | `OpenMS/quantms-web` |
| UmetaFlow (untargeted metabolomics) | `OpenMS/umetaflow` |
| OpenDIAKiosk (DIA proteomics) | `OpenMS/OpenDIAKiosk` |
| TOPPView-Lite (mzML viewer) | `t0mdavid-m/TOPPView-Lite` |
| Only the framework | `OpenMS/streamlit-template` |

The **triplet** is always:

1. the app (`<owner>/<app-repo>`),
2. the template every app is built from: `OpenMS/streamlit-template`,
3. the visualization library the apps use: `t0mdavid-m/OpenMS-Insight` (Python
   package `openms-insight`).

When the app *is* the template, the triplet has two repositories. Find each
repository's default branch instead of assuming `main` (FLASHApp develops on
`develop`): `gh repo view <owner>/<repo> --json defaultBranchRef -q .defaultBranchRef.name`,
or after cloning `git remote show upstream | sed -n 's/.*HEAD branch: //p'`.

## 2. Git

Check: `git --version`.

Missing → ask, then install:

- Windows: `winget install --id Git.Git -e` (Git for Windows also brings Git
  Bash and `ssh`). If you cannot run commands before Git is there, the person
  runs this in PowerShell. Claude and any open terminal need a restart
  afterwards to find it.
- macOS: `xcode-select --install` (or `brew install git` when Homebrew is there).
- Debian/Ubuntu: `sudo apt-get install -y git`; Fedora: `sudo dnf install -y git`.

Then the identity Git writes into commits:
`git config --global --get user.name` and `--get user.email`. If either is
empty, ask for the name and the email they want on their commits, and mention
that GitHub's private address (`<id>+<login>@users.noreply.github.com`, shown
at https://github.com/settings/emails) keeps their own email out of public
history. Write them with `git config --global user.name "…"` /
`user.email "…"` only after they answered.

Optional but useful: the GitHub CLI (`gh --version`; install with
`winget install --id GitHub.cli`, `brew install gh`, or the packages at
https://cli.github.com). With it, forking, starring and adding the key are one
command each; without it, every step below has a browser link instead.

## 3. A GitHub account and an SSH key

They need a GitHub account (https://github.com/signup). Ask for their GitHub
login; you need it for the fork URLs.

Check for a key: `ls ~/.ssh/id_ed25519.pub ~/.ssh/id_ecdsa.pub ~/.ssh/id_rsa.pub`
(Windows PowerShell: `ls $HOME\.ssh\*.pub`). Then check whether GitHub already
accepts it: `ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -T git@github.com`
answers "Hi <login>! You've successfully authenticated" when it does (the exit
code is 1 even then; read the text). `accept-new` records GitHub's host key on
the first connection without a prompt; compare it once
(`ssh-keygen -lf ~/.ssh/known_hosts -F github.com`) with the fingerprints GitHub
publishes at
https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints,
and stop if they differ.

No key → the person creates it in their own Terminal or PowerShell (it asks
for a passphrase, which they type there, never to you; a passphrase is
recommended):
`ssh-keygen -t ed25519 -C "<their commit email>" -f ~/.ssh/id_ed25519`
(PowerShell: `-f $HOME\.ssh\id_ed25519`). Then the key goes into the
system's key store, so that your commands, which cannot type the passphrase,
can use it:

- macOS: the person runs `ssh-add --apple-use-keychain ~/.ssh/id_ed25519`, and
  you add to `~/.ssh/config` (after asking):
  ```
  Host github.com
    AddKeysToAgent yes
    UseKeychain yes
    IdentityFile ~/.ssh/id_ed25519
  ```
- Windows: the person starts the `ssh-agent` service once, in an
  administrator PowerShell
  (`Get-Service ssh-agent | Set-Service -StartupType Automatic; Start-Service ssh-agent`),
  then runs `ssh-add $HOME\.ssh\id_ed25519`. Git for Windows brings its own
  `ssh`, which does not see that service, so point Git at the Windows one:
  `git config --global core.sshCommand "C:/Windows/System32/OpenSSH/ssh.exe"`.
  That setting changes only what Git runs, so on Windows run every `ssh`
  check below with that executable too
  (`C:/Windows/System32/OpenSSH/ssh.exe -o BatchMode=yes -T git@github.com`).
- Linux: `eval "$(ssh-agent -s)" && ssh-add ~/.ssh/id_ed25519` in their
  terminal; a desktop session usually runs an agent already.

Key not yet on GitHub → show the content of the `.pub` file (the public key
only), open https://github.com/settings/ssh/new and let them paste it. With
`gh` already signed in (`gh auth status`), `gh ssh-key add ~/.ssh/id_ed25519.pub --title "<computer name>"`
does the same; signing in (`gh auth login`) is a step the person runs. Run the
`ssh -o BatchMode=yes -T git@github.com` check again until it greets them by
login.

A network that blocks port 22 makes `ssh -T` time out: GitHub serves SSH on
port 443 too (`ssh -T -p 443 git@ssh.github.com`); if that works, add to
`~/.ssh/config`:

```
Host github.com
  Hostname ssh.github.com
  Port 443
  User git
```

## 4. Star and fork

Ask once: "Would you like to star the three repositories? It helps the
projects be found." Star only on a yes: `gh repo star <owner>/<repo>`, or the
Star button on each repository page.

Fork each repository of the triplet that they do not have yet
(`gh repo view <login>/<repo>` fails when there is no fork):
`gh repo fork <owner>/<repo> --clone=false`, or open
`https://github.com/<owner>/<repo>/fork` and click **Create fork**. A fork
that already exists is reused; never delete or recreate one.

## 5. Clone

Ask where the code should live. In the desktop app's Code tab, suggest the
folder the session was opened in; otherwise suggest `~/openms-webapps`. Clone each fork
over SSH into that folder, side by side, and point `upstream` at the original:

```bash
mkdir -p ~/openms-webapps && cd ~/openms-webapps
git clone git@github.com:<login>/<app-repo>.git
git -C <app-repo> remote add upstream https://github.com/<owner>/<app-repo>.git
git clone git@github.com:<login>/streamlit-template.git
git -C streamlit-template remote add upstream https://github.com/OpenMS/streamlit-template.git
git clone git@github.com:<login>/OpenMS-Insight.git
git -C OpenMS-Insight remote add upstream https://github.com/t0mdavid-m/OpenMS-Insight.git
```

In the app's clone also add the template, which is how template changes reach
the app: `git -C <app-repo> remote add template https://github.com/OpenMS/streamlit-template.git`.
Then `git fetch --all` in each clone. A folder that is already a clone of the
right repository is kept: add the missing remotes, do not clone again.

## 6. Run it once

The apps need Python 3.11. In the app's clone:

```bash
python3.11 -m venv .venv && . .venv/bin/activate   # macOS/Linux
# Git Bash on Windows: . .venv/Scripts/activate
# PowerShell on Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt && pip install pytest fakeredis
python -m pytest test_gui.py tests/ -q
streamlit run app.py      # in the background; it serves http://localhost:8501
```

To work on openms-insight together with the app, install the clone into the
app's venv in place of the PyPI release. Its frontend has to be built once
first, which needs Node.js (https://nodejs.org):

```bash
cd ../OpenMS-Insight/js-component && npm install && npm run build && cd ..
mkdir -p openms_insight/js-component && cp -r js-component/dist openms_insight/js-component/
pip install -e ".[dev]"
```

The contributing guide of openms-insight
(https://github.com/t0mdavid-m/OpenMS-Insight/blob/main/CONTRIBUTING.md)
explains the hot-reload setup for frontend work. The
template runs the same way as an app (`streamlit run app.py` in its clone).
Running TOPP tools locally needs OpenMS installed (https://openms.de); pages
that only show results work without it. Say so if a test or page fails for
that reason, rather than trying to install OpenMS unasked.

## 7. Where a change goes, and the order of the pull requests

Decide per change, before writing code:

| The change is… | It goes to |
|---|---|
| shared by the apps: the workflow framework (`src/workflow/`), `src/common/`, upload and import, layout manager, Docker, k8s, CI, desktop build, `.claude/` | **the template** |
| a visualization, a plot or table component, interaction between components, statistics computed for a view | **openms-insight** |
| the app's own science: its workflow, its tools' settings, its result pages and presets | **the app** |

A file the app lists under `sync.app_owned` in its `app.yaml` is the app's;
every other file in an app comes from the template, and changing it in the app
alone is lost or conflicts at the next template sync.

Open the pull requests in this order, each on its own branch in the fork
(`git switch -c <short-topic>` from the upstream default branch):

1. **Template first.** A PR to `OpenMS/streamlit-template` with the shared part.
2. **openms-insight next.** A PR to `t0mdavid-m/OpenMS-Insight` with the
   visualization or statistics part.
3. **The app last.** A PR to the app that uses the two. Until they are merged
   it may bring the template branch in by merging it (`git fetch template` or
   from the fork) and may require the openms-insight branch in its
   `requirements.txt`; say so in the PR. Once the template PR is merged, the
   app takes it by merging the template's default branch, never by copying
   files. An app release needs the openms-insight change in a version
   published on PyPI.

Each PR links the ones it depends on ("Needs OpenMS/streamlit-template#123").
A change that touches only one of the three is a single PR there.

Every PR:

- describes what it changes for the people using the app, in plain words;
- carries **screenshots or a short video of every visible change** (light and
  dark theme where it matters), attached to the PR description;
- comes with tests for the logic it adds, and passes the repository's checks
  locally first: `python -m pytest test_gui.py tests/` and pylint as in the
  repository's `CLAUDE.md` for the template and apps, `pytest` and `ruff check .`
  for openms-insight;
- keeps to one change; unrelated fixes get their own PR;
- contains no passwords, tokens, keys, password hashes or personal data, and
  no details of a deployment's infrastructure (server names, internal
  addresses, credentials of a cluster or registry), in code, commits, PR text,
  logs or screenshots. These repositories are public. A deployment's own
  values belong in its secrets, never in the repository.

Push to the fork (`git push -u origin <branch>`) and open the PR against the
upstream repository: `gh pr create --repo <owner>/<repo> --fill`, or the
"Compare & pull request" link GitHub prints after the push. The template's and
the apps' `CLAUDE.md` and `.claude/skills/` describe the framework in depth;
read them in the clone before changing code there.

## 8. Finish

End with one short summary:

- what was found and what was set up (Git, key, forks, clones and their folder),
- the commands to start the app and run its tests,
- the PR order in one sentence,
- anything they still have to do themselves (a key to paste, a fork to click).

Then ask what they would like to work on.
