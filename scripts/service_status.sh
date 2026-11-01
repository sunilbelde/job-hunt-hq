#!/bin/sh
# Reports whether the launchd job is loaded, its pid, a health check, the docs
# listener, whether resume tailoring is ready, the size of the launchd log and
# whether the Mac is set never to sleep.
# Usage: scripts/service_status.sh
set -u

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  echo "Usage: $0"
  exit 0
fi

repo=$(cd "$(dirname "$0")/.." && pwd)
label=local.job-hunt-hq
port=${PORT:-8080}
plist="${LAUNCHD_DIR:-/Library/LaunchDaemons}/$label.plist"
log_dir="$HOME/Library/Logs/job-hunt-hq"
status=0

if info=$(launchctl print "system/$label" 2>/dev/null); then
  state=$(printf '%s\n' "$info" | awk -F' = ' '/^\tstate = /{print $2; exit}')
  pid=$(printf '%s\n' "$info" | awk -F' = ' '/^\tpid = /{print $2; exit}')
  echo "launchd:   loaded (state: ${state:-unknown}, pid: ${pid:-none})"
else
  echo "launchd:   not loaded"
  status=1
fi

if curl -fsS --max-time 5 "http://127.0.0.1:$port/health" >/dev/null 2>&1; then
  echo "health:    ok (http://127.0.0.1:$port/health)"
else
  echo "health:    FAILING (http://127.0.0.1:$port/health)"
  status=1
fi

# The docs port is whatever the installed job was given, so this matches what is running.
if [ -f "$plist" ]; then
  docs_port=$(sed -n '/<string>--docs-port<\/string>/{n;s/.*<string>\([0-9]*\)<\/string>.*/\1/p;}' "$plist")
  if [ -z "$docs_port" ]; then
    # Installed with the retired DOCS_PORT=off: no job status, edits or viewer anywhere.
    echo "docs:      not configured; reinstall (scripts/install_service.sh)"
    status=1
  elif [ "$(curl -s --max-time 5 -o /dev/null -w '%{http_code}' "http://127.0.0.1:$docs_port/docs")" = 200 ]; then
    echo "docs:      ok (http://127.0.0.1:$docs_port/docs, local only)"
  else
    echo "docs:      FAILING (http://127.0.0.1:$docs_port/docs)"
    status=1
  fi
  # The local listener is for this Mac only: any Tailscale mapping to it is a leftover to remove.
  if [ -n "$docs_port" ] && command -v tailscale >/dev/null 2>&1; then
    docs_url=$(tailscale serve status --json 2>/dev/null | "$repo/.venv/bin/python" "$repo/deploy/tailscale_docs.py" "$docs_port")
    rc=$?
    case "$docs_url" in https://*:*) https_port=${docs_url##*:} ;; *) https_port=443 ;; esac
    case $rc in
      0) echo "tailnet:   WARNING: tailscale serve publishes the local listener at $docs_url; run: tailscale serve --https=$https_port off" ;;
      3) echo "tailnet:   WARNING: Funnel publishes the local listener at $docs_url: the API docs are public; run: tailscale funnel --https=$https_port off, then tailscale serve --https=$https_port off" ;;
    esac
  fi
fi

# Offline check of what tailoring needs: the CLI the installed job uses, its version and the credential
# kind in .env. It makes no model call, so it costs nothing; the install script does the live check.
if [ -x "$repo/.venv/bin/python" ]; then
  claude_bin=$( [ -f "$plist" ] && plutil -extract EnvironmentVariables.CLAUDE_BIN raw "$plist" 2>/dev/null)
  if tailoring=$(cd "$repo" && CLAUDE_BIN="${claude_bin:-claude}" "$repo/.venv/bin/python" -m app.tailoring --check 2>/dev/null); then
    echo "tailoring: $tailoring"
  else
    echo "tailoring: ${tailoring:-FAILING (the check did not run)}"
    status=1
  fi
fi

if [ -f "$log_dir/launchd.log" ]; then
  echo "logs:      $log_dir (launchd.log $(wc -c < "$log_dir/launchd.log" | tr -d ' ') bytes)"
fi

sleep_value=$(pmset -g 2>/dev/null | awk '$1 == "sleep" {print $2; exit}')
if [ -n "$sleep_value" ] && [ "$sleep_value" != 0 ]; then
  echo "power:     system sleep is ${sleep_value} min; run: sudo pmset -a sleep 0 disksleep 0"
else
  echo "power:     system sleep disabled"
fi
exit $status
