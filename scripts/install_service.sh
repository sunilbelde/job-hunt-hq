#!/bin/sh
# Installs (or reinstalls) the service as a launchd daemon that starts at boot,
# restarts on crash and listens on 127.0.0.1: the four public endpoints Funnel publishes
# on PORT (default 8080), and the full API, its docs and the resume viewer on DOCS_PORT
# (default 8081), the local listener reached only from this Mac. Run as your own
# user; it uses sudo only for the launchd steps. Safe to run again after `git pull`.
# Usage: [PORT=8080] [DOCS_PORT=8081] scripts/install_service.sh
set -eu

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  echo "Usage: $0    (see README: Running on the Mac mini)"
  exit 0
fi

repo=$(cd "$(dirname "$0")/.." && pwd)
label=local.job-hunt-hq
port=${PORT:-8080}
docs_port=${DOCS_PORT:-8081}
launchd_dir=${LAUNCHD_DIR:-/Library/LaunchDaemons}
plist_dst="$launchd_dir/$label.plist"
log_dir="$HOME/Library/Logs/job-hunt-hq"
cache_dir="$HOME/Library/Caches/job-hunt-hq/tectonic"
venv_py="$repo/.venv/bin/python"

die() { echo "ERROR: $*" >&2; exit 1; }
step() { echo "==> $*"; }

[ "$(id -u)" != 0 ] || die "run as your normal user, not root (the script calls sudo itself)"

step "Checking prerequisites"
case "$docs_port" in
  off) die "DOCS_PORT=off is no longer supported: the local listener is required for job status, application edits and the resume viewer" ;;
  ''|*[!0-9]*) die "DOCS_PORT must be a port number, got '$docs_port'" ;;
  "$port") die "DOCS_PORT ($docs_port) must differ from PORT ($port)" ;;
esac
command -v python3.12 >/dev/null 2>&1 || die "python3.12 not found. Install it: brew install python@3.12"
command -v tectonic >/dev/null 2>&1 || die "tectonic not found. Install it: brew install tectonic"
# Resume tailoring needs the Claude Code CLI and a credential; without them the service still runs,
# but resumes that need scoring fail, so these are warnings at the end rather than errors here.
claude_bin=$(command -v claude 2>/dev/null || true)
# The viewer's Fill form button runs Herdr; without it only that button fails.
herdr_bin=$(command -v herdr 2>/dev/null || true)
if grep -Eq '^[[:space:]]*(CLAUDE_CODE_OAUTH_TOKEN|ANTHROPIC_API_KEY)[[:space:]]*=[[:space:]]*[^[:space:]#]' "$repo/.env" 2>/dev/null; then
  has_credential=yes
else
  has_credential=no
fi
[ -f "$repo/.env" ] || die ".env not found. Create it: cp .env.example .env, fill it in, then chmod 600 .env"
mode=$(stat -f %Lp "$repo/.env")
[ $((0$mode & 077)) -eq 0 ] || die ".env is readable by other users (mode $mode). Fix it: chmod 600 .env"

step "Setting up the Python environment"
if ! "$venv_py" -c 'import sys; sys.exit(sys.version_info[:2] != (3, 12))' >/dev/null 2>&1; then
  rm -rf "$repo/.venv"
  python3.12 -m venv "$repo/.venv"
fi
"$venv_py" -m pip install -q -r "$repo/requirements.txt"

step "Validating configuration"
# Settings errors never contain input values, so the message is safe to show.
if ! err=$(cd "$repo" && "$venv_py" -c 'from app.main import create_app; create_app()' 2>&1); then
  printf '%s\n' "$err" | grep -vE '^\s*(File |Traceback|\^)' | tail -n 8 >&2
  die "configuration is invalid; fix .env and run again"
fi

step "Warming the TeX package cache (first run downloads packages)"
mkdir -p "$cache_dir"
(cd "$repo" && TECTONIC_CACHE_DIR="$cache_dir" "$venv_py" -c \
  'from app.rendering import render_pdf; assert render_pdf().startswith(b"%PDF")') \
  || die "test render failed; run the command above by hand to see tectonic's output"

step "Writing launchd and logging configuration"
mkdir -p "$log_dir"
"$venv_py" "$repo/deploy/render_template.py" "$repo/deploy/logging.json.template" \
  "$repo/deploy/logging.json" LOG_DIR="$log_dir"
tmp_plist=$(mktemp); trap 'rm -f "$tmp_plist"' EXIT
"$venv_py" "$repo/deploy/render_template.py" "$repo/deploy/local.job-hunt-hq.plist.template" \
  "$tmp_plist" REPO="$repo" USER="$(id -un)" HOME="$HOME" PORT="$port" DOCS_PORT="$docs_port" \
  CLAUDE_BIN="${claude_bin:-claude}" HERDR_BIN="${herdr_bin:-herdr}"
plutil -lint "$tmp_plist" >/dev/null || die "generated plist is invalid"
: > "$log_dir/launchd.log"

step "Loading the launchd job (sudo)"
sudo install -m 644 -o root -g wheel "$tmp_plist" "$plist_dst"
sudo launchctl bootout "system/$label" >/dev/null 2>&1 || true
tries=0
until sudo launchctl bootstrap system "$plist_dst"; do
  tries=$((tries + 1))
  [ $tries -lt 5 ] || die "launchctl bootstrap failed"
  sleep 1  # bootout finishes asynchronously
done

step "Waiting for the service"
i=0
until curl -fsS "http://127.0.0.1:$port/health" >/dev/null 2>&1; do
  i=$((i + 1))
  [ $i -lt 30 ] || die "service did not answer /health within 30s; see $log_dir/launchd.log and service.log"
  sleep 1
done
# The public port is the one Funnel publishes: it must never serve the API docs or the resume viewer.
for path in /docs /viewer; do
  code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port$path" || true)
  [ "$code" = 404 ] || die "http://127.0.0.1:$port$path answered $code, want 404: the public port must not serve API docs or the viewer"
done
# Nor anything but its four endpoints: these are served on the local listener only.
for path in /healthz /resume/00000000-0000-0000-0000-000000000000/status; do
  code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port$path" || true)
  [ "$code" = 404 ] || die "http://127.0.0.1:$port$path answered $code, want 404: the public port serves only its four endpoints"
done
for path in /docs /viewer; do
  code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$docs_port$path" || true)
  [ "$code" = 200 ] || die "docs listener did not answer http://127.0.0.1:$docs_port$path (got $code); see $log_dir/launchd.log"
done
echo "OK: service is running on http://127.0.0.1:$port (logs: $log_dir)"

if ! command -v tailscale >/dev/null 2>&1; then
  echo "WARNING: tailscale not installed; the service is only reachable from this Mac." >&2
elif ! tailscale serve status 2>/dev/null | grep -q "127.0.0.1:$port"; then
  echo "WARNING: tailscale serve is not proxying to port $port." >&2
  echo "         Run: tailscale serve --bg --https=443 http://127.0.0.1:$port" >&2
fi

echo "API docs on this Mac: http://127.0.0.1:$docs_port/docs"
echo "Resume viewer on this Mac: http://127.0.0.1:$docs_port/viewer"
# The local listener is for this Mac only: any Tailscale mapping to it is a leftover to remove.
if command -v tailscale >/dev/null 2>&1; then
  rc=0
  docs_url=$(tailscale serve status --json 2>/dev/null | "$venv_py" "$repo/deploy/tailscale_docs.py" "$docs_port") || rc=$?
  case "$docs_url" in https://*:*) https_port=${docs_url##*:} ;; *) https_port=443 ;; esac
  case $rc in
    0) echo "WARNING: tailscale serve publishes the local listener at $docs_url: the API docs and resume viewer are reachable from your tailnet." >&2
       echo "         Run: tailscale serve --https=$https_port off" >&2 ;;
    3) echo "WARNING: Funnel publishes the local listener at $docs_url: the API docs and resume viewer are public." >&2
       echo "         Run: tailscale funnel --https=$https_port off" >&2
       echo "         then: tailscale serve --https=$https_port off" >&2 ;;
  esac
fi

# Resume tailoring: the CLI, a credential, and one minimal live call to see the credential works.
if [ -z "$claude_bin" ]; then
  echo "WARNING: Claude Code CLI not found; resumes that need tailoring will fail." >&2
  echo "         Install Claude Code (https://code.claude.com/docs/en/setup), then run this script again." >&2
elif [ "$has_credential" = no ]; then
  echo "WARNING: .env sets no Claude credential; resumes that need tailoring will fail." >&2
  echo "         Run claude setup-token and add CLAUDE_CODE_OAUTH_TOKEN=<token> to .env as one line," >&2
  echo "         or set ANTHROPIC_API_KEY. Then run this script again." >&2
else
  rc=0
  tailoring=$(cd "$repo" && CLAUDE_BIN="$claude_bin" "$venv_py" -m app.tailoring --check --live 2>/dev/null) || rc=$?
  if [ $rc -eq 0 ]; then
    echo "OK: tailoring $tailoring"
  else
    echo "WARNING: tailoring check: ${tailoring:-did not run}" >&2
  fi
fi
