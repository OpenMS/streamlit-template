#!/usr/bin/env bash
# Daily usability sweep of the OpenMS web apps.
#
# For every app in apps.json: shallow-clone its default branch, install its
# requirements into a cached venv, start it with Streamlit, and let check.mjs
# walk every page in a fresh workspace and in the app's demo workspace.
# Apps with a live deployment are also checked at their public URL.
#
# usage: usability-checks/run.sh [OUT_DIR] [APP ...]
# env:   WORK_DIR (default /tmp/usability-checks), VENV_DIR (default /tmp/venvs),
#        SKIP_LIVE=1, SKIP_LOCAL=1
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
STAMP="$(date -u +%Y-%m-%d_%H%M)"
OUT="${1:-/mnt/project-files/usability-checks/$STAMP}"
shift || true
WORK="${WORK_DIR:-/tmp/usability-checks}"
VENVS="${VENV_DIR:-/tmp/venvs}"
mkdir -p "$OUT" "$WORK/src" "$VENVS"
OUT="$(cd "$OUT" && pwd)"

APPS=("$@")
if [ ${#APPS[@]} -eq 0 ]; then
  mapfile -t APPS < <(python3 -c "import json;print('\n'.join(json.load(open('$HERE/apps.json'))))")
fi

cfg() { python3 -c "import json,sys;v=json.load(open('$HERE/apps.json'))['$1'].get('$2');print('' if v is None else ('1' if v is True else v))"; }

port=8601
for app in "${APPS[@]}"; do
  repo="$(cfg "$app" repo)"; demo="$(cfg "$app" demo)"; live="$(cfg "$app" live)"; exwf="$(cfg "$app" exampleWorkflow)"
  appout="$OUT/$app"; mkdir -p "$appout"
  log="$appout/setup.log"
  echo "=== $app"

  if [ -z "${SKIP_LOCAL:-}" ]; then
    src="$WORK/src/$app"
    rm -rf "$src"
    if ! git clone -q --depth 1 "https://github.com/$repo.git" "$src" >>"$log" 2>&1; then
      echo '{"app":"'"$app"'","setupError":"git clone failed","pages":[],"scenarios":[],"failed":1}' >"$appout/results.json"
      continue
    fi
    git -C "$src" log -1 --format='%H %cs %s' >"$appout/commit.txt"
    venv="$VENVS/$app"
    [ -x "$venv/bin/python" ] || uv venv -q -p 3.11 "$venv" >>"$log" 2>&1
    if ! UV_HTTP_TIMEOUT=600 VIRTUAL_ENV="$venv" uv pip install -q -r "$src/requirements.txt" >>"$log" 2>&1; then
      echo '{"app":"'"$app"'","setupError":"installing requirements.txt failed (see setup.log)","pages":[],"scenarios":[],"failed":1}' >"$appout/results.json"
      continue
    fi

    # Workspaces live in ../workspaces-<repository-name>; names carry the app
    # because quantms-web and the template share a repository-name.
    wsroot="$WORK/src/workspaces-$(python3 -c "import json;print(json.load(open('$src/settings.json'))['repository-name'])")"
    fresh="ux-fresh-$app"; wsargs=(--workspace "$fresh")
    rm -rf "$wsroot/$fresh"
    if [ -n "$demo" ] && [ -d "$src/example-data/workspaces/$demo" ]; then
      rm -rf "$wsroot/ux-demo-$app"; mkdir -p "$wsroot"
      cp -r "$src/example-data/workspaces/$demo" "$wsroot/ux-demo-$app"
      wsargs+=(--workspace "ux-demo-$app")
    fi

    (cd "$src" && exec "$venv/bin/streamlit" run app.py --server.headless true --server.port "$port" \
      --browser.gatherUsageStats false >"$appout/streamlit.log" 2>&1) &
    spid=$!
    up=""
    for _ in $(seq 1 90); do
      curl -sf "http://localhost:$port/_stcore/health" >/dev/null && { up=1; break; }
      kill -0 $spid 2>/dev/null || break
      sleep 2
    done
    if [ -n "$up" ]; then
      extra=(); [ -n "$exwf" ] && extra+=(--example-workflow)
      node "$HERE/check.mjs" --app "$app" --url "http://localhost:$port" --out "$appout" "${wsargs[@]}" "${extra[@]}"
    else
      echo '{"app":"'"$app"'","setupError":"streamlit did not start (see streamlit.log)","pages":[],"scenarios":[],"failed":1}' >"$appout/results.json"
    fi
    pkill -P $spid 2>/dev/null; kill $spid 2>/dev/null; wait $spid 2>/dev/null
    port=$((port + 1))
  fi

  if [ -n "$live" ] && [ -z "${SKIP_LIVE:-}" ]; then
    liveout="$OUT/$app-live"; mkdir -p "$liveout"
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 30 "$live/")"
    if [ "$code" = "000" ]; then
      detail="$(curl -sS -o /dev/null --max-time 30 "$live/" 2>&1 | head -1 | tr -d '"\\')"
      echo '{"app":"'"$app"' (live)","url":"'"$live"'","unreachable":true,"detail":"'"$detail"'","pages":[],"scenarios":[],"failed":0}' >"$liveout/results.json"
    else
      node "$HERE/check.mjs" --app "$app (live)" --url "$live" --out "$liveout" --live
    fi
  fi
done

python3 "$HERE/report.py" "$OUT"
