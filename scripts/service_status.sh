#!/bin/sh
# Reports whether the launchd job is loaded, its pid, a health check, the size
# of the launchd log and whether the Mac is set never to sleep.
# Usage: scripts/service_status.sh
set -u

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  echo "Usage: $0"
  exit 0
fi

label=local.job-hunt-hq
port=${PORT:-8080}
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
