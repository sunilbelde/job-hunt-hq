#!/bin/sh
# Stops the launchd service and removes it so it no longer starts at boot.
# Stored output files, logs and .env are left in place.
# Usage: scripts/uninstall_service.sh
set -eu

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  echo "Usage: $0"
  exit 0
fi

label=local.job-hunt-hq
plist="${LAUNCHD_DIR:-/Library/LaunchDaemons}/$label.plist"

sudo launchctl bootout "system/$label" >/dev/null 2>&1 || true
sudo rm -f "$plist"
echo "OK: service stopped and removed. Output files and logs were kept."
echo "If you published the API docs on your tailnet, also run: tailscale serve --https=8444 off"
