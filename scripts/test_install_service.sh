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
stub claude 'exit 0'
# `serve status --json` answers with STUB_SERVE_JSON (default set in run()).
stub tailscale 'case "$*" in
  *--json*) printf "%s" "$STUB_SERVE_JSON" ;;
  *) echo "https://mac-mini.ts.net (Funnel on) |-- / proxy http://127.0.0.1:8080" ;;
esac'
# The API funnelled on 443 and the docs listener tailnet-only on 8444.
serve_json='{"Web":{"mac-mini.ts.net:443":{"Handlers":{"/":{"Proxy":"http://127.0.0.1:8080"}}},"mac-mini.ts.net:8444":{"Handlers":{"/":{"Proxy":"http://127.0.0.1:8081"}}}},"AllowFunnel":{"mac-mini.ts.net:443":true}}'
stub pmset 'printf " sleep                0\n"'
# /docs and /viewer status codes: STUB_PUBLIC_DOCS / STUB_PUBLIC_VIEWER on the public port 8080,
# STUB_DOCS / STUB_VIEWER on any other port.
stub curl 'echo "curl $*" >> "$CALLS"
case "$*" in
  *:8080/docs*) printf "%s" "${STUB_PUBLIC_DOCS:-404}" ;;
  *:8080/viewer*) printf "%s" "${STUB_PUBLIC_VIEWER:-404}" ;;
  */docs*) printf "%s" "${STUB_DOCS:-200}" ;;
  */viewer*) printf "%s" "${STUB_VIEWER:-200}" ;;
esac
exit ${STUB_CURL_RC:-0}'
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
  printf 'API_KEY=k\nCLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-secret-token\n' > "$repo/.env"; chmod 600 "$repo/.env"
  # Fake venv python: real python only for the template renderer.
  cat > "$repo/.venv/bin/python" <<'PY'
#!/bin/sh
case "$1" in *render_template.py|*tailscale_docs.py) exec /usr/bin/python3 "$@" ;; esac
case "$*" in *create_app*) [ "${STUB_CONFIG_RC:-0}" = 0 ] || { echo "1 validation error for Settings"; echo "link_signing_secret"; exit 1; } ;; esac
# app.tailoring --check answers with STUB_TAILORING and exits with STUB_TAILORING_RC.
case "$*" in *app.tailoring*) echo "python $* CLAUDE_BIN=$CLAUDE_BIN" >> "$CALLS"; echo "${STUB_TAILORING:-ready (subscription token, claude-opus-5-5, Claude Code 2.1.303)}"; exit ${STUB_TAILORING_RC:-0} ;; esac
exit 0
PY
  chmod +x "$repo/.venv/bin/python"
  home="$tmp/home"; rm -rf "$home"; mkdir -p "$home"
  : > "$calls"; rm -f "$tmp/installed.plist"
}

run() {  # run <script> [VAR=value ...]
  script=$1; shift
  env PATH="$bin:/usr/bin:/bin:/usr/sbin:/sbin" HOME="$home" CALLS="$calls" TESTDIR="$tmp" STUB_SERVE_JSON="$serve_json" "$@" \
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
check "installed plist runs the launcher with the docs port" \
  'plutil -extract ProgramArguments json -o - "$tmp/installed.plist" | grep -q "\"-m\",\"app.serve\",.*\"--docs-port\",\"8081\""'
check "install checks /docs on both ports" \
  'grep -q "127.0.0.1:8080/docs" "$calls" && grep -q "127.0.0.1:8081/docs" "$calls"'
check "install prints the docs URLs" \
  'grep -q "http://127.0.0.1:8081/docs" "$tmp/out" && grep -q "https://mac-mini.ts.net:8444/docs" "$tmp/out"'
check "install checks /viewer on both ports" \
  'grep -q "127.0.0.1:8080/viewer" "$calls" && grep -q "127.0.0.1:8081/viewer" "$calls"'
check "install prints the viewer URLs" \
  'grep -q "http://127.0.0.1:8081/viewer" "$tmp/out" && grep -q "https://mac-mini.ts.net:8444/viewer" "$tmp/out"'
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

# --- resume tailoring prerequisites ---
make_repo
run install_service.sh; rc=$?
check "installed plist names the Claude CLI found" \
  '[ "$(plutil -extract EnvironmentVariables.CLAUDE_BIN raw "$tmp/installed.plist")" = "$bin/claude" ]'
check "install runs the live tailoring check" \
  'grep -q "app.tailoring --check --live" "$calls" && grep -q "OK: tailoring ready (subscription token" "$tmp/out"'
check "install never prints the credential" '! grep -q "secret-token" "$tmp/out"'

make_repo; mv "$bin/claude" "$tmp/claude.off"
run install_service.sh; rc=$?
mv "$tmp/claude.off" "$bin/claude"
check "missing Claude CLI warns while the install completes" \
  '[ $rc -eq 0 ] && grep -q "WARNING: Claude Code CLI not found" "$tmp/out" && [ "$(plutil -extract EnvironmentVariables.CLAUDE_BIN raw "$tmp/installed.plist")" = claude ]'

make_repo; printf 'API_KEY=k\nCLAUDE_CODE_OAUTH_TOKEN=\nANTHROPIC_API_KEY=  # later\n' > "$repo/.env"; chmod 600 "$repo/.env"
run install_service.sh; rc=$?
check "no credential warns and names both ways to set one" \
  '[ $rc -eq 0 ] && grep -q "WARNING: .env sets no Claude credential" "$tmp/out" && grep -q "claude setup-token" "$tmp/out" && grep -q "ANTHROPIC_API_KEY" "$tmp/out" && ! grep -q "app.tailoring" "$calls"'

make_repo
run install_service.sh STUB_TAILORING="FAILING (credential rejected): paste the token from \`claude setup-token\` as one line" STUB_TAILORING_RC=1; rc=$?
check "rejected credential warns while the install completes" \
  '[ $rc -eq 0 ] && grep -q "WARNING: tailoring check: FAILING (credential rejected)" "$tmp/out" && grep -q "as one line" "$tmp/out"'

# --- docs listener ---
make_repo
run install_service.sh DOCS_PORT=9090; rc=$?
check "DOCS_PORT is rendered into the plist" \
  '[ $rc -eq 0 ] && plutil -extract ProgramArguments json -o - "$tmp/installed.plist" | grep -q "\"--docs-port\",\"9090\"" && grep -q "127.0.0.1:9090/docs" "$calls"'

make_repo
run install_service.sh DOCS_PORT=off; rc=$?
check "DOCS_PORT=off installs without a docs listener" \
  '[ $rc -eq 0 ] && plutil -lint "$tmp/installed.plist" >/dev/null && ! grep -q "docs-port" "$tmp/installed.plist" && ! grep -q "API docs on" "$tmp/out"'
check "DOCS_PORT=off keeps API docs off" \
  '[ "$(plutil -extract EnvironmentVariables.API_DOCS_ENABLED raw "$tmp/installed.plist")" = false ]'

make_repo
run install_service.sh DOCS_PORT=8080; rc=$?
check "docs port equal to the service port refused" '[ $rc -ne 0 ] && grep -q "must differ" "$tmp/out" && ! grep -q "^sudo" "$calls"'

make_repo
run install_service.sh DOCS_PORT=abc; rc=$?
check "non-numeric docs port refused" '[ $rc -ne 0 ] && grep -q "DOCS_PORT" "$tmp/out" && ! grep -q "^sudo" "$calls"'

make_repo
run install_service.sh STUB_PUBLIC_DOCS=200; rc=$?
check "install fails when the public port serves docs" '[ $rc -ne 0 ] && grep -q "must not serve API docs" "$tmp/out"'

make_repo
run install_service.sh STUB_PUBLIC_VIEWER=200; rc=$?
check "install fails when the public port serves the viewer" '[ $rc -ne 0 ] && grep -q "must not serve API docs or the viewer" "$tmp/out"'

make_repo
run install_service.sh STUB_VIEWER=404; rc=$?
check "install fails when the docs listener does not serve the viewer" '[ $rc -ne 0 ] && grep -q "did not answer http://127.0.0.1:8081/viewer" "$tmp/out"'

make_repo
run install_service.sh STUB_DOCS=000; rc=$?
check "install fails when the docs listener does not answer" '[ $rc -ne 0 ] && grep -q "docs listener did not answer" "$tmp/out"'

make_repo
run install_service.sh STUB_SERVE_JSON='{"Web":{"mac-mini.ts.net:443":{"Handlers":{"/":{"Proxy":"http://127.0.0.1:8080"}}}},"AllowFunnel":{"mac-mini.ts.net:443":true}}'; rc=$?
check "missing docs mapping warns with the serve command" \
  '[ $rc -eq 0 ] && grep -q "WARNING: tailscale serve is not proxying the docs port 8081" "$tmp/out" && grep -q "tailscale serve --bg --https=8444 http://127.0.0.1:8081" "$tmp/out"'

make_repo
run install_service.sh STUB_SERVE_JSON='{"Web":{"mac-mini.ts.net:8443":{"Handlers":{"/":{"Proxy":"http://127.0.0.1:8081"}}}},"AllowFunnel":{"mac-mini.ts.net:8443":true}}'; rc=$?
check "funnelled docs mapping warns that docs are public" \
  'grep -q "Funnel publishes the docs listener at https://mac-mini.ts.net:8443" "$tmp/out" && grep -q "tailscale funnel --https=8443 off" "$tmp/out"'

# --- uninstall ---
make_repo
data="$home/Library/Application Support/job-hunt-hq/outputs/2026-01-01"; mkdir -p "$data"; echo pdf > "$data/f.pdf"
run uninstall_service.sh; rc=$?
check "uninstall exits 0" '[ $rc -eq 0 ]'
check "uninstall boots out and removes plist" \
  'grep -q "sudo launchctl bootout system/local.job-hunt-hq" "$calls" && grep -q "sudo rm -f /Library/LaunchDaemons/local.job-hunt-hq.plist" "$calls"'
check "uninstall keeps output files" '[ -f "$data/f.pdf" ]'
check "uninstall reminds to remove the docs mapping" 'grep -q "tailscale serve --https=8444 off" "$tmp/out"'

# --- status ---
make_repo
run install_service.sh; mkdir -p "$tmp/ld"; cp "$tmp/installed.plist" "$tmp/ld/local.job-hunt-hq.plist"
run service_status.sh STUB_LOADED=0 STUB_CURL_RC=7; rc=$?
check "status reports not loaded" '[ $rc -ne 0 ] && grep -q "not loaded" "$tmp/out" && grep -q "FAILING" "$tmp/out"'
run service_status.sh STUB_LOADED=1; rc=$?
check "status reports running pid and health" '[ $rc -eq 0 ] && grep -q "pid: 4242" "$tmp/out" && grep -q "health:    ok" "$tmp/out"'
run service_status.sh STUB_LOADED=1 LAUNCHD_DIR="$tmp/ld"; rc=$?
check "status reports the docs listener" \
  '[ $rc -eq 0 ] && grep -q "docs:      ok (http://127.0.0.1:8081/docs)" "$tmp/out" && grep -q "tailnet:   https://mac-mini.ts.net:8444/docs" "$tmp/out"'
run service_status.sh STUB_LOADED=1 LAUNCHD_DIR="$tmp/ld" STUB_DOCS=000; rc=$?
check "status fails when the docs listener is down" '[ $rc -ne 0 ] && grep -q "docs:      FAILING" "$tmp/out"'
run service_status.sh STUB_LOADED=1 LAUNCHD_DIR="$tmp/ld" STUB_SERVE_JSON='{"Web":{"mac-mini.ts.net:8443":{"Handlers":{"/":{"Proxy":"127.0.0.1:8081"}}}},"AllowFunnel":{"mac-mini.ts.net:8443":true}}'
check "status warns when Funnel publishes the docs" 'grep -q "WARNING: Funnel publishes the docs listener" "$tmp/out"'
make_repo
run install_service.sh DOCS_PORT=off; cp "$tmp/installed.plist" "$tmp/ld/local.job-hunt-hq.plist"
run service_status.sh STUB_LOADED=1 LAUNCHD_DIR="$tmp/ld"; rc=$?
check "status reports docs off" '[ $rc -eq 0 ] && grep -q "docs:      off" "$tmp/out"'

make_repo
run install_service.sh; cp "$tmp/installed.plist" "$tmp/ld/local.job-hunt-hq.plist"; : > "$calls"
run service_status.sh STUB_LOADED=1 LAUNCHD_DIR="$tmp/ld"; rc=$?
check "status reports tailoring ready" \
  '[ $rc -eq 0 ] && grep -q "tailoring: ready (subscription token, claude-opus-5-5, Claude Code 2.1.303)" "$tmp/out"'
check "status checks offline with the CLI the job uses" \
  'grep -q "app.tailoring --check CLAUDE_BIN=$bin/claude" "$calls" && ! grep -q -- "--live" "$calls"'
check "status never prints the credential" '! grep -q "secret-token" "$tmp/out"'
run service_status.sh STUB_LOADED=1 LAUNCHD_DIR="$tmp/ld" STUB_TAILORING="not configured: set CLAUDE_CODE_OAUTH_TOKEN (from \`claude setup-token\`) or ANTHROPIC_API_KEY in .env" STUB_TAILORING_RC=1; rc=$?
check "status reports tailoring not configured" '[ $rc -ne 0 ] && grep -q "tailoring: not configured" "$tmp/out"'
run service_status.sh STUB_LOADED=1 LAUNCHD_DIR="$tmp/ld" STUB_TAILORING="FAILING: Claude Code CLI not found (claude)" STUB_TAILORING_RC=1; rc=$?
check "status reports tailoring failing" '[ $rc -ne 0 ] && grep -q "tailoring: FAILING: Claude Code CLI not found" "$tmp/out"'

exit $fail
