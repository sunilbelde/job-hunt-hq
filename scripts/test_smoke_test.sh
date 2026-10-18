#!/bin/sh
# Tests scripts/smoke_test.sh with a stubbed curl (no network).
here=$(cd "$(dirname "$0")" && pwd)
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
fail=0

# Stub curl: status codes come from STUB_APP / STUB_RESUME; DELETE and /resume calls are logged to STUB_LOG.
cat > "$tmp/curl" <<'STUB'
#!/bin/sh
case "$*" in
  *"-X DELETE"*) echo "DELETE $*" >> "$STUB_LOG" ;;
  *"/application"*) printf '{"ok":true,"application_id":"3f2b9c1e-8d4a-4c6e-9b1f-2a7d5e8c0b13"}\n%s' "$STUB_APP" ;;
  *"/resume"*) echo "$*" | tr "\n" " " >> "$STUB_LOG"; echo >> "$STUB_LOG"
    printf '{"ok":true,"application_id":"3f2b9c1e-8d4a-4c6e-9b1f-2a7d5e8c0b13","saved_path":"%s"}\n%s' "$STUB_SAVED" "$STUB_RESUME" ;;
esac
STUB
chmod +x "$tmp/curl"

id=3f2b9c1e-8d4a-4c6e-9b1f-2a7d5e8c0b13
saved="$tmp/out/Smoke Test Co/$id/SUNIL BELDE.pdf"

# run <app status> <resume status> [file content | "none"]
run() {
  rm -rf "$tmp/out" "$tmp/log"; : > "$tmp/log"
  if [ "${3:-%PDF-1.5}" != none ]; then
    mkdir -p "$(dirname "$saved")" && printf '%s' "${3:-%PDF-1.5}" > "$saved"
  fi
  PATH="$tmp:$PATH" API_KEY=k STUB_APP=$1 STUB_RESUME=$2 STUB_SAVED=$saved STUB_LOG=$tmp/log \
    sh "$here/smoke_test.sh" http://x >/dev/null 2>&1
}
deleted() { grep -q "DELETE.*http://x/application/$id" "$tmp/log"; }
sent_as_string() { grep -q "/resume .*-d {\"application_id\":\"$id\"}" "$tmp/log"; }
ok() { echo "ok $1"; }
bad() { echo "FAIL $1"; fail=1; }

run 201 201 && deleted && [ ! -e "$tmp/out/Smoke Test Co" ] && ok "success cleans up what it created" || bad "success"
run 201 201 && sent_as_string && ok "resume body sends the ID as a string" || bad "id as string"
run 200 201 && ! deleted && [ -f "$saved" ] && ok "existing application kept" || bad "existing kept"
run 401 201; [ $? -ne 0 ] && ! deleted && ok "application401" || bad "application401"
run 201 404; [ $? -ne 0 ] && deleted && ok "resume404 still cleans up" || bad "resume404"
run 200 401; [ $? -ne 0 ] && ! deleted && ok "resume401" || bad "resume401"
run 201 201 none; [ $? -ne 0 ] && deleted && ok "missing file" || bad "missing file"
run 201 201 '{"not":"pdf"}'; [ $? -ne 0 ] && ok "notpdf" || bad "notpdf"
env -u API_KEY PATH="$tmp:$PATH" sh "$here/smoke_test.sh" http://x >/dev/null 2>&1 && bad "nokey" || ok "nokey"
exit $fail
