#!/bin/sh
# Tests scripts/smoke_test.sh with a stubbed curl (no network).
here=$(cd "$(dirname "$0")" && pwd)
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
fail=0

# Stub curl: status codes come from STUB_POST / STUB_GET; downloaded body from STUB_BODY.
cat > "$tmp/curl" <<'STUB'
#!/bin/sh
case "$*" in
  *"-X POST"*) printf '{"url":"https://signed.example/f.json"}\n%s' "$STUB_POST" ;;
  *) out=""; while [ $# -gt 0 ]; do [ "$1" = "-o" ] && out=$2; shift; done
     [ -n "$out" ] && printf '%s' "$STUB_BODY" > "$out"; printf '%s' "$STUB_GET" ;;
esac
STUB
chmod +x "$tmp/curl"

run() { PATH="$tmp:$PATH" API_KEY=k STUB_POST=$1 STUB_GET=$2 STUB_BODY=${3:-%PDF-1.5} sh "$here/smoke_test.sh" http://x >/dev/null 2>&1; }

run 201 200 && echo "ok success" || { echo "FAIL success"; fail=1; }
run 401 200 && { echo "FAIL post401"; fail=1; } || echo "ok post401"
run 201 200 '{"not":"pdf"}' && { echo "FAIL notpdf"; fail=1; } || echo "ok notpdf"
run 201 403 && { echo "FAIL get403"; fail=1; } || echo "ok get403"
env -u API_KEY PATH="$tmp:$PATH" sh "$here/smoke_test.sh" http://x >/dev/null 2>&1 && { echo "FAIL nokey"; fail=1; } || echo "ok nokey"
exit $fail
