#!/bin/sh
# Installs (or reinstalls) the service as a launchd daemon that starts at boot,
# restarts on crash and listens on 127.0.0.1. Run as your own user; it uses sudo
# only for the launchd steps. Safe to run again after `git pull`.
# Usage: scripts/install_service.sh
set -eu

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  echo "Usage: $0    (see README: Running on the Mac mini)"
  exit 0
fi

repo=$(cd "$(dirname "$0")/.." && pwd)
label=local.job-hunt-hq
port=${PORT:-8080}
launchd_dir=${LAUNCHD_DIR:-/Library/LaunchDaemons}
plist_dst="$launchd_dir/$label.plist"
log_dir="$HOME/Library/Logs/job-hunt-hq"
cache_dir="$HOME/Library/Caches/job-hunt-hq/tectonic"
venv_py="$repo/.venv/bin/python"

die() { echo "ERROR: $*" >&2; exit 1; }
step() { echo "==> $*"; }

[ "$(id -u)" != 0 ] || die "run as your normal user, not root (the script calls sudo itself)"

step "Checking prerequisites"
command -v python3.12 >/dev/null 2>&1 || die "python3.12 not found. Install it: brew install python@3.12"
command -v tectonic >/dev/null 2>&1 || die "tectonic not found. Install it: brew install tectonic"
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
  "$tmp_plist" REPO="$repo" USER="$(id -un)" HOME="$HOME" PORT="$port"
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
echo "OK: service is running on http://127.0.0.1:$port (logs: $log_dir)"

if ! command -v tailscale >/dev/null 2>&1; then
  echo "WARNING: tailscale not installed; the service is only reachable from this Mac." >&2
elif ! tailscale serve status 2>/dev/null | grep -q "127.0.0.1:$port"; then
  echo "WARNING: tailscale serve is not proxying to port $port." >&2
  echo "         Run: tailscale serve --bg --https=443 http://127.0.0.1:$port" >&2
fi
