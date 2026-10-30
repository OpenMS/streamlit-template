## 💻 Create a window executable of a Streamlit App with embeddable Python

To create an executable for Streamlit app on Windows, we'll use an embeddable version of Python.</br>
Here's a step-by-step guide:

### Prerequisites

You need a **system Python installation** (the regular Python installer from python.org) of the same version as the embeddable Python you'll download. This is required because the embeddable Python lacks development headers (`Python.h`) needed to compile native extensions.

Install Python 3.11.9 from https://www.python.org/downloads/ if you don't have it already.

### Download and Extract Python Embeddable Version

1. Download a suitable Python embeddable version. For example, let's download Python 3.11.9:

   ```bash
   # use curl command or manually download
   curl -O https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip
   ```

2. Extract the downloaded zip file:

   ```bash
   mkdir python-3.11.9

   unzip python-3.11.9-embed-amd64.zip -d python-3.11.9

   rm python-3.11.9-embed-amd64.zip
   ```

### Configure Python Environment

1. Uncomment 'import site' in the `._pth` file:

   ```bash
   # Uncomment to run site.main() automatically
   # Remove hash from python-3.11.9/python311._pth file
   import site

   # Or use command
   sed -i '/^\s*#\s*import\s\+site/s/^#//' python-3.11.9/python311._pth
   ```

### Install Required Packages

Install all required packages from `requirements.txt` using the **system Python** with `--target` to install into the embeddable Python's site-packages:

```bash
# Use system Python (which has development headers) to compile packages,
# installing into the embeddable Python's site-packages directory.
# The embeddable Python lacks Python.h headers needed for native extensions.
python -m pip install -r requirements.txt --target python-3.11.9/Lib/site-packages --upgrade --no-warn-script-location
```

> **Important**: Do NOT use `./python-3.11.9/python -m pip install ...` directly. The embeddable Python lacks the development headers required to compile native extensions (e.g., `Python.h`), which will cause builds to fail with errors like:
> ```
> fatal error C1083: Cannot open include file: 'Python.h': No such file or directory
> ```

### Test the app

```batch
.\python-3.11.9\python -m streamlit run app.py local
```

### Create one executable folder

1. Create a folder for your Streamlit app:

   ```bash
   mkdir ../streamlit_exe
   ```

2. Copy environment and app files:

   ```bash
   # move Python environment folder
   mv  python-3.11.9 ../streamlit_exe

   # copy streamlit app files
   cp -r src utils content docs .streamlit assets example-data ../streamlit_exe
   cp app.py settings.json default-parameters.json ../streamlit_exe
   ```

3. Remove the server address from the bundled config to use `localhost` (default) instead of `0.0.0.0`, which doesn't work as a connect address on Windows:

   ```powershell
   (Get-Content streamlit_exe/.streamlit/config.toml) -notmatch '^address' | Set-Content streamlit_exe/.streamlit/config.toml
   ```

This folder is the payload that the Electron shell packages into an installer, as described below.

## Build the installer in GitHub Actions

The workflow [Build desktop app](https://github.com/OpenMS/streamlit-template/blob/main/.github/workflows/build-desktop-app.yaml) runs all of these steps, adds the OpenMS TOPP tools listed in `TOPP_TOOLS`, and builds `<APP_NAME>-Setup.exe`. On a release, the installer is attached to the release. The Docker images download it from the latest release and offer it on the Quickstart and Installation pages.
</br>

## Electron desktop app (per-user installer)

The Windows build produces `<APP_NAME>-Setup.exe`, which packages the folder above (embedded Python, pyOpenMS, TOPP tools, `share/OpenMS`) in the Electron shell from `electron/`. The older MSI installer is no longer built.

- It installs per user to `%LOCALAPPDATA%\Programs\<APP_NAME>` and needs no admin rights.
- The app opens in its own window. The shell starts Streamlit on a free loopback port and stops it, together with any running TOPP tools, when the window closes.
- Workspaces live in `%APPDATA%\<APP_NAME>\workspaces`. The shell passes that location to the app in `LOCAL_WORKSPACES_DIR`, which takes precedence over `workspaces_dir` from `settings.json` in local mode.
- On start, it checks the latest release of `github-user`/`repository-name` from `settings.json` and links to the release page when a newer version exists. It never downloads anything by itself.
- Streamlit's output is written to `%APPDATA%\<APP_NAME>\logs\streamlit.log`.

The shell sets up the environment for the TOPP tools: the install folder and every `share\OpenMS\THIRDPARTY\*` folder go on `PATH`, and `OPENMS_DATA_PATH` points to `share\OpenMS`. CI installs the result silently and checks pyOpenMS, every tool in `TOPP_TOOLS`, and the app page before uploading it.

CI then runs `electron/scripts/e2e.js` against the installed app: it drives the app window with Playwright, opens every page in the navigation and fails on any Python exception shown there. An app adds its own steps, such as running a workflow and checking its results page, as scenario modules passed with `--scenario <file.js>`; each module exports `async (t) => {...}` and gets helpers such as `t.open(page)`, `t.clickTab`, `t.clickButton`, `t.choose(label, option)`, `t.waitForText` and `t.waitForComponent(selector)`. Locally, `node scripts/e2e.js` (run in `electron/`) without `--exe` runs the shell from the checkout (on Linux under `xvfb-run`).

The window allows Chromium's software WebGL renderer, so WebGL plots also draw without a usable GPU (remote desktop, virtual machines).

To try the shell from a checkout, run `npm install` and then `npm start` in `electron/`. It runs `app.py` from the repository with the `python` on your `PATH`. Set `OPENMS_APP_PAYLOAD` to use a built payload folder instead.

## macOS and Linux

The same workflow also wraps the app in the same Electron shell as `<APP_NAME>-macOS-arm64.dmg` (Apple Silicon only) and as `<APP_NAME>-Linux-x86_64.AppImage` plus `<APP_NAME>-Linux-amd64.deb`. It reads `APP_NAME`, `TOPP_TOOLS` and `OPENMS_VERSION` like the Windows build.

- `electron/scripts/stage-python.sh` takes CPython from [python-build-standalone](https://github.com/astral-sh/python-build-standalone) (there is no embeddable Python for macOS and Linux), installs `requirements.txt` into it and compiles the bytecode, because the signed app and the AppImage are read-only.
- `electron/scripts/stage-openms.sh` takes the TOPP tools from the official OpenMS release: the arm64 `.pkg` on macOS, the `.deb` on Linux, whose system libraries (Qt, Xerces, ...) it copies into the bundle. The tools stay in `openms/bin` next to `openms/lib` and find their libraries through a relative rpath; the shell puts `openms/bin` on `PATH`.
- Workspaces and the log live in `~/Library/Application Support/<APP_NAME>` on macOS and in `~/.config/<APP_NAME>` on Linux.

CI runs the same smoke and end-to-end tests as on Windows, on macOS from the mounted dmg and on Linux against both the AppImage and the deb.

### Signing for macOS

macOS only opens downloaded apps that are signed with a Developer ID certificate and notarized by Apple. The workflow does both when these repository or organization secrets exist, and builds an unsigned app otherwise:

| Secret | Content |
|---|---|
| `MACOS_CERTIFICATE` | The "Developer ID Application" certificate with its private key, as a base64-encoded `.p12` |
| `MACOS_CERTIFICATE_PASSWORD` | The `.p12` password |
| `APPLE_API_KEY` | Contents of an App Store Connect API key (`.p8`, Team key with the Developer role) |
| `APPLE_API_KEY_ID` | The key's ID |
| `APPLE_API_ISSUER` | The issuer ID shown above the key list |

Instead of the three `APPLE_API_*` secrets, notarization also works with an Apple ID: `APPLE_ID` (the developer account's email), `APPLE_APP_SPECIFIC_PASSWORD` (created at account.apple.com under Sign-In and Security → App-Specific Passwords) and `APPLE_TEAM_ID` (the 10-character team ID from developer.apple.com → Membership details).

The `.p12` can be made without a Mac:

```bash
openssl genrsa -out devid.key 2048
openssl req -new -key devid.key -out devid.csr -subj "/emailAddress=<Apple ID>/CN=<name>/C=<country>"
# developer.apple.com: Certificates -> + -> Developer ID Application (G2 Sub-CA), upload devid.csr
openssl x509 -inform DER -in developerID_application.cer -out devid.pem
openssl pkcs12 -export -legacy -inkey devid.key -in devid.pem -name "Developer ID Application" -out cert.p12
base64 -w0 cert.p12   # -> MACOS_CERTIFICATE
```

`-legacy` keeps the `.p12` readable by the macOS keychain. The entitlements the bundled Python and TOPP tools need under the hardened runtime are in `electron/build/entitlements.mac.plist`.
