#!/bin/sh
# Tests scripts/smoke_test.sh with a stubbed curl (no network).
here=$(cd "$(dirname "$0")" && pwd)
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
fail=0

# Stub curl: http://x is the public base URL, http://d the docs listener. Status codes come from
# STUB_DOCS (public docs and viewer) / STUB_DOCS_LISTENER / STUB_VIEWER_LISTENER / STUB_APP / STUB_PATCH / STUB_RESUME /
# STUB_LETTER / STUB_STATUS, the schema from STUB_SCHEMA, match.status from STUB_MATCH and saved_path from STUB_NAME; POST /application, PATCH,
# DELETE, /resume, its status reads and /cover-letter calls are logged to STUB_LOG. STUB_LETTER_FILE makes /cover-letter
# write a file. The resume job reads `running` for the first STUB_RUNNING polls, then STUB_JOB (default done).
cat > "$tmp/curl" <<'STUB'
#!/bin/sh
case "$*" in
  *"http://d/docs"*) printf '%s' "$STUB_DOCS_LISTENER" ;;
  *"http://d/viewer"*) printf '%s' "${STUB_VIEWER_LISTENER:-$STUB_DOCS_LISTENER}" ;;
  *"http://d/openapi.json"*) printf '%s\n%s' "$STUB_SCHEMA" "$STUB_DOCS_LISTENER" ;;
  *"/docs"*|*"/openapi.json"*) printf '%s' "$STUB_DOCS" ;;
  *"/viewer"*) printf '%s' "${STUB_VIEWER:-$STUB_DOCS}" ;;
  *"-X DELETE"*) echo "DELETE $*" >> "$STUB_LOG" ;;
  *"-X PATCH"*) echo "PATCH $*" >> "$STUB_LOG"; printf '%s' "${STUB_PATCH:-200}" ;;
  *"/cover-letter"*) echo "LETTER $*" | tr "\n" " " >> "$STUB_LOG"; echo >> "$STUB_LOG"
    [ -n "${STUB_LETTER_FILE:-}" ] && printf '%%PDF' > "$(dirname "$STUB_SAVED")/SUNIL BELDE - Cover Letter.pdf"
    printf '{"ok":false,"message":"no posting text"}\n%s' "${STUB_LETTER:-422}" ;;
  *"/resume/"*"/status"*) echo "STATUS $*" | tr "\n" " " >> "$STUB_LOG"; echo >> "$STUB_LOG"
    job=${STUB_JOB:-done}; [ "$(grep -c '^STATUS' "$STUB_LOG")" -le "${STUB_RUNNING:-0}" ] && job=running
    printf '{"ok":true,"application_id":"3f2b9c1e-8d4a-4c6e-9b1f-2a7d5e8c0b13","status":"%s","saved_path":"%s","match":{"status":"%s"},"error":"Resume generation failed"}\n%s' \
      "$job" "${STUB_NAME:-SUNIL BELDE.pdf}" "${STUB_MATCH:-no_job_description}" "${STUB_STATUS:-200}" ;;
  *"/application"*) echo "CREATE $*" >> "$STUB_LOG"
    printf '{"ok":true,"application_id":"3f2b9c1e-8d4a-4c6e-9b1f-2a7d5e8c0b13"}\n%s' "$STUB_APP" ;;
  *"/resume"*) echo "$*" | tr "\n" " " >> "$STUB_LOG"; echo >> "$STUB_LOG"
    printf '{"ok":true,"application_id":"3f2b9c1e-8d4a-4c6e-9b1f-2a7d5e8c0b13","status":"running","started_at":"t"}\n%s' \
      "$STUB_RESUME" ;;
esac
STUB
chmod +x "$tmp/curl"

id=3f2b9c1e-8d4a-4c6e-9b1f-2a7d5e8c0b13
saved="$tmp/out/Smoke Test Co/$id/SUNIL BELDE.pdf"
thirteen='{"paths":{"/healthz":{"get":{}},"/health":{"get":{}},"/application":{"post":{}},"/application/{application_id}":{"patch":{},"delete":{},"get":{}},"/resume":{"post":{}},"/cover-letter":{"post":{}},"/applications":{"get":{}},"/application/{application_id}/resume.pdf":{"get":{}},"/application/{application_id}/cover-letter.pdf":{"get":{}},"/resume/base.pdf":{"get":{}},"/cover-letter/base.pdf":{"get":{}}}}'
fifteen='{"paths":{"/healthz":{"get":{}},"/health":{"get":{}},"/application":{"post":{}},"/application/{application_id}":{"patch":{},"delete":{},"get":{}},"/resume":{"post":{}},"/resume/{application_id}/status":{"get":{}},"/cover-letter":{"post":{}},"/cover-letter/{application_id}/status":{"get":{}},"/applications":{"get":{}},"/application/{application_id}/resume.pdf":{"get":{}},"/application/{application_id}/cover-letter.pdf":{"get":{}},"/resume/base.pdf":{"get":{}},"/cover-letter/base.pdf":{"get":{}}}}'
seventeen="$(printf '%s' "$fifteen" | sed 's/}}$/,"\/viewer\/application\/{application_id}":{"patch":{},"delete":{}}}}/')"

# run <app status> <resume status> [file content | "none"]
# Call with prefixed variables inside ( ): sh keeps VAR=x assignments made before a function call.
run() {
  rm -rf "$tmp/out" "$tmp/log"; : > "$tmp/log"
  if [ "${3:-%PDF-1.5}" != none ]; then
    mkdir -p "$(dirname "$saved")" && printf '%s' "${3:-%PDF-1.5}" > "$saved"
  fi
  PATH="$tmp:$PATH" API_KEY=k STUB_DOCS=${STUB_DOCS:-404} STUB_DOCS_LISTENER=${STUB_DOCS_LISTENER:-200} \
  STUB_SCHEMA=${STUB_SCHEMA:-$seventeen} DOCS_URL=${DOCS_URL:-http://d} OUTPUT_DIR=${OUTPUT_DIR:-$tmp/out} STUB_APP=$1 STUB_RESUME=$2 STUB_SAVED=$saved STUB_LOG=$tmp/log \
    POLL_SECONDS=0 JOB_TIMEOUT=${JOB_TIMEOUT:-3} sh "$here/smoke_test.sh" http://x >/dev/null 2>&1
}
created_any() { grep -q "^CREATE" "$tmp/log"; }
deleted() { grep -q "DELETE.*http://x/application/$id" "$tmp/log"; }
sent_as_string() { grep -q "/resume .*-d {\"application_id\":\"$id\"}" "$tmp/log"; }
patched() { grep -q "PATCH .*http://x/application/$id .*-d {\"full_job_description\":null}" "$tmp/log"; }
patched_before_resume() { [ "$(grep -n "^PATCH" "$tmp/log" | cut -d: -f1)" -lt "$(grep -n "/resume" "$tmp/log" | head -n 1 | cut -d: -f1)" ]; }
ok() { echo "ok $1"; }
bad() { echo "FAIL $1"; fail=1; }

run 201 202 && deleted && [ ! -e "$tmp/out/Smoke Test Co" ] && ok "success cleans up what it created" || bad "success"
run 201 202 && sent_as_string && ok "resume body sends the ID as a string" || bad "id as string"
run 200 202 && ! deleted && [ -f "$saved" ] && ok "existing application kept" || bad "existing kept"
run 401 201; [ $? -ne 0 ] && ! deleted && ok "application401" || bad "application401"
run 201 404; [ $? -ne 0 ] && deleted && ok "resume404 still cleans up" || bad "resume404"
run 200 401; [ $? -ne 0 ] && ! deleted && ok "resume401" || bad "resume401"
run 201 202 none; [ $? -ne 0 ] && deleted && ok "missing file" || bad "missing file"
run 201 202 '{"not":"pdf"}'; [ $? -ne 0 ] && ok "notpdf" || bad "notpdf"
(STUB_NAME="$saved" run 201 202); [ $? -ne 0 ] && deleted && [ -f "$saved" ] && ok "a host path in saved_path fails" || bad "host path"
(STUB_NAME="other.pdf" run 201 202); [ $? -ne 0 ] && deleted && ok "an unexpected file name fails" || bad "file name"
(OUTPUT_DIR="$tmp/elsewhere" run 201 202); [ $? -ne 0 ] && deleted && ok "a file missing under OUTPUT_DIR fails and still cleans up" || bad "output dir"
(STUB_DOCS=200 run 201 202); [ $? -ne 0 ] && ! deleted && ok "docs served fails before creating anything" || bad "docs served"
run 201 202 && grep -q "^CREATE" "$tmp/log" && ok "docs listener healthy passes" || bad "docs listener healthy"
(STUB_DOCS_LISTENER=404 run 201 202); [ $? -ne 0 ] && ! created_any && ok "docs listener missing fails before creating anything" || bad "docs listener missing"
(STUB_VIEWER=200 run 201 202); [ $? -ne 0 ] && ! created_any && ok "public viewer fails before creating anything" || bad "public viewer"
(STUB_VIEWER_LISTENER=404 run 201 202); [ $? -ne 0 ] && ! created_any && ok "viewer missing on the docs listener fails" || bad "viewer missing"
(STUB_SCHEMA="$(printf '%s' "$fifteen" | sed 's/,"\/cover-letter\/{application_id}\/status":{"get":{}}//')" run 201 202); [ $? -ne 0 ] && ! created_any && ok "fourteen operations (no cover letter status) fail" || bad "fourteen operations"
(STUB_SCHEMA="$thirteen" run 201 202); [ $? -ne 0 ] && ! created_any && ok "thirteen operations (before the status endpoints) fail" || bad "thirteen operations"
(STUB_SCHEMA="$fifteen" run 201 202); [ $? -ne 0 ] && ! created_any && ok "fifteen operations (before the viewer writes) fail" || bad "fifteen operations"
(STUB_SCHEMA='{"paths":{"/health":{"get":{}}}}' run 201 202); [ $? -ne 0 ] && ! created_any && ok "wrong operation count fails" || bad "operation count"
(STUB_SCHEMA='not json' run 201 202); [ $? -ne 0 ] && ! created_any && ok "unreadable schema fails" || bad "unreadable schema"
(DOCS_URL=off STUB_DOCS_LISTENER=404 run 201 202) && ok "DOCS_URL=off skips the docs listener" || bad "docs off"
run 201 202 && ! patched && ! grep -q "full_job_description" "$tmp/log" && ok "fresh application has no posting text" || bad "fresh posting text"
run 200 202 && patched && patched_before_resume && ok "leftover application's posting text cleared before the resume" || bad "leftover cleared"
(STUB_PATCH=500 run 200 202); [ $? -ne 0 ] && ! grep -q "/resume" "$tmp/log" && ok "failed PATCH stops before the resume" || bad "failed patch"
(STUB_MATCH=tailored run 201 202); [ $? -ne 0 ] && deleted && ok "a tailored smoke resume fails" || bad "match status"
letter_sent() { grep -q "^LETTER .*http://x/cover-letter .*-d {\"application_id\":\"$id\"}" "$tmp/log"; }
letter_after_resume() { [ "$(grep -n "^LETTER" "$tmp/log" | cut -d: -f1)" -gt "$(grep -n "/resume" "$tmp/log" | head -n 1 | cut -d: -f1)" ]; }
run 201 202 && letter_sent && letter_after_resume && ok "cover letter requested after the resume, and 422 passes" || bad "letter 422"
(STUB_LETTER=202 run 201 202); [ $? -ne 0 ] && deleted && ok "a cover letter accepted without posting text fails" || bad "letter 202"
(STUB_LETTER=500 run 201 202); [ $? -ne 0 ] && ok "a cover letter 500 fails" || bad "letter 500"
(STUB_LETTER_FILE=1 run 201 202); [ $? -ne 0 ] && ok "a cover letter file beside the resume fails" || bad "letter file"
run 201 404; ! grep -q "^LETTER" "$tmp/log" && ok "no cover letter request after a failed resume" || bad "letter after failure"
polled() { grep -q "^STATUS .*http://x/resume/$id/status" "$tmp/log"; }
run 201 202 && polled && ok "resume status polled on the public address" || bad "status polled"
(STUB_RUNNING=2 run 201 202) && [ "$(grep -c '^STATUS' "$tmp/log")" -eq 3 ] && ok "polls until the job is done" || bad "polls until done"
(STUB_JOB=failed run 201 202); [ $? -ne 0 ] && deleted && ! grep -q "^LETTER" "$tmp/log" && ok "a failed job fails and still cleans up" || bad "failed job"
(STUB_RUNNING=99 run 201 202); [ $? -ne 0 ] && deleted && [ "$(grep -c '^STATUS' "$tmp/log")" -eq 4 ] && ok "a job still running at the timeout fails and still cleans up" || bad "job timeout"
(STUB_STATUS=404 run 201 202); [ $? -ne 0 ] && deleted && ok "a status endpoint 404 fails and still cleans up" || bad "status 404"
(STUB_STATUS=401 run 201 202); [ $? -ne 0 ] && deleted && ok "a status endpoint 401 fails" || bad "status 401"
run 201 201; [ $? -ne 0 ] && deleted && ! polled && ok "an old synchronous 201 fails" || bad "resume 201"
env -u API_KEY PATH="$tmp:$PATH" sh "$here/smoke_test.sh" http://x >/dev/null 2>&1 && bad "nokey" || ok "nokey"
exit $fail
