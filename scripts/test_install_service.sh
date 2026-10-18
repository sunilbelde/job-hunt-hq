#!/bin/sh
# Tests install_service.sh, uninstall_service.sh and service_status.sh against a
# throwaway copy of the repo with stubbed sudo, launchctl, curl, tectonic, tailscale
# and pmset. Nothing touches launchd or needs root.
here=$(cd "$(dirname "$0")" && pwd)
src=$(cd "$here/.." && pwd)
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
fail=0
check() { if eval "$2"; then echo "ok $1"; else echo "FAIL $1"; fail=1; fi; }

bin="$tmp/bin"; mkdir -p "$bin"
calls="$tmp/calls.log"

stub() { printf '#!/bin/sh\n%s\n' "$2" > "$bin/$1"; chmod +x "$bin/$1"; }
stub python3.12 'exit 0'
stub tectonic 'exit 0'
stub tailscale 'echo "https://mac-mini.ts.net (tailnet only) |-- / proxy http://127.0.0.1:8080"'
stub pmset 'printf " sleep                0\n"'
stub curl 'echo "curl $*" >> "$CALLS"; exit ${STUB_CURL_RC:-0}'
stub launchctl 'echo "launchctl $*" >> "$CALLS"; [ "${STUB_LOADED:-0}" = 1 ] || exit 113; printf "system/local.job-hunt-hq = {\n\tstate = running\n\tpid = 4242\n}\n"'
# sudo records its arguments; `install` copies the plist where the test can read it.
stub sudo 'echo "sudo $*" >> "$CALLS"
if [ "$1" = install ]; then for a; do prev2=$prev1; prev1=$a; done; cp "$prev2" "$TESTDIR/installed.plist"; fi
exit 0'

make_repo() {
  repo="$tmp/repo with space"; rm -rf "$repo"; mkdir -p "$repo/.venv/bin"
  cp -R "$src/scripts" "$src/deploy" "$repo/"
  rm -f "$repo/deploy/logging.json"
  touch "$repo/requirements.txt"
  printf 'API_KEY=k\n' > "$repo/.env"; chmod 600 "$repo/.env"
  # Fake venv python: real python only for the template renderer.
  cat > "$repo/.venv/bin/python" <<'PY'
#!/bin/sh
case "$1" in *render_template.py) exec /usr/bin/python3 "$@" ;; esac
case "$*" in *create_app*) [ "${STUB_CONFIG_RC:-0}" = 0 ] || { echo "1 validation error for Settings"; echo "link_signing_secret"; exit 1; } ;; esac
exit 0
PY
  chmod +x "$repo/.venv/bin/python"
  home="$tmp/home"; rm -rf "$home"; mkdir -p "$home"
  : > "$calls"; rm -f "$tmp/installed.plist"
}

run() {  # run <script> [VAR=value ...]
  script=$1; shift
  env PATH="$bin:/usr/bin:/bin:/usr/sbin:/sbin" HOME="$home" CALLS="$calls" TESTDIR="$tmp" "$@" \
    sh "$repo/scripts/$script" > "$tmp/out" 2>&1
}

# --- install ---
make_repo
run install_service.sh; rc=$?
check "install happy path exits 0" '[ $rc -eq 0 ]'
check "install boots out before bootstrapping" \
  'grep -n "launchctl bootout system/local.job-hunt-hq" "$calls" | cut -d: -f1 > "$tmp/a"; grep -n "launchctl bootstrap system" "$calls" | cut -d: -f1 > "$tmp/b"; [ -s "$tmp/a" ] && [ -s "$tmp/b" ] && [ "$(cat "$tmp/a")" -lt "$(cat "$tmp/b")" ]'
check "installed plist is valid and uses the repo path" \
  'plutil -lint "$tmp/installed.plist" >/dev/null && [ "$(plutil -extract WorkingDirectory raw "$tmp/installed.plist")" = "$repo" ]'
check "installed plist runs as the current user" \
  '[ "$(plutil -extract UserName raw "$tmp/installed.plist")" = "$(id -un)" ]'
check "installed plist keeps API docs off" \
  '[ "$(plutil -extract EnvironmentVariables.API_DOCS_ENABLED raw "$tmp/installed.plist")" = false ]'
check "logging config written with home log dir" \
  'grep -q "$home/Library/Logs/job-hunt-hq/service.log" "$repo/deploy/logging.json"'
check "no tailscale warning when serve is configured" '! grep -q "WARNING" "$tmp/out"'

run install_service.sh; rc=$?
check "reinstall exits 0" '[ $rc -eq 0 ]'

make_repo; chmod 644 "$repo/.env"
run install_service.sh; rc=$?
check "world-readable .env refused" '[ $rc -ne 0 ] && grep -q "chmod 600" "$tmp/out"'
check "world-readable .env installs nothing" '! grep -q "^sudo" "$calls"'

make_repo; rm "$repo/.env"
run install_service.sh; rc=$?
check "missing .env refused" '[ $rc -ne 0 ] && ! grep -q "^sudo" "$calls"'

make_repo; mv "$bin/tectonic" "$tmp/tectonic.off"
run install_service.sh; rc=$?
mv "$tmp/tectonic.off" "$bin/tectonic"
check "missing tectonic refused" '[ $rc -ne 0 ] && grep -q "brew install tectonic" "$tmp/out" && ! grep -q "^sudo" "$calls"'

make_repo
run install_service.sh STUB_CONFIG_RC=1; rc=$?
check "invalid config refused and named" '[ $rc -ne 0 ] && grep -q "link_signing_secret" "$tmp/out" && ! grep -q "^sudo" "$calls"'

make_repo
run install_service.sh STUB_CURL_RC=7; rc=$?
check "install fails when health never answers" '[ $rc -ne 0 ] && grep -q "did not answer" "$tmp/out"'

# --- uninstall ---
make_repo
data="$home/Library/Application Support/job-hunt-hq/outputs/2026-01-01"; mkdir -p "$data"; echo pdf > "$data/f.pdf"
run uninstall_service.sh; rc=$?
check "uninstall exits 0" '[ $rc -eq 0 ]'
check "uninstall boots out and removes plist" \
  'grep -q "sudo launchctl bootout system/local.job-hunt-hq" "$calls" && grep -q "sudo rm -f /Library/LaunchDaemons/local.job-hunt-hq.plist" "$calls"'
check "uninstall keeps output files" '[ -f "$data/f.pdf" ]'

# --- status ---
make_repo
run service_status.sh STUB_LOADED=0 STUB_CURL_RC=7; rc=$?
check "status reports not loaded" '[ $rc -ne 0 ] && grep -q "not loaded" "$tmp/out" && grep -q "FAILING" "$tmp/out"'
run service_status.sh STUB_LOADED=1; rc=$?
check "status reports running pid and health" '[ $rc -eq 0 ] && grep -q "pid: 4242" "$tmp/out" && grep -q "health:    ok" "$tmp/out"'

exit $fail
