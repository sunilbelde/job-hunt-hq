#!/bin/sh
# Tests scripts/smoke_test.sh with a stubbed curl (no network).
here=$(cd "$(dirname "$0")" && pwd)
# The smoke test expects files named after the sample resume's \name{JANE DOE}.
export JOB_HUNT_DATA_DIR="$here/../data/samples"
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
fail=0

# Stub curl: http://x is the public base URL, http://d the docs listener. Status codes come from
# STUB_DOCS (public docs and viewer) / STUB_DOCS_LISTENER / STUB_VIEWER_LISTENER / STUB_APP / STUB_PATCH / STUB_RESUME /
# STUB_LETTER / STUB_STATUS, the schema from STUB_SCHEMA, match.status from STUB_MATCH and saved_path from STUB_NAME; POST /application, PATCH,
# DELETE, /resume, its status reads and /cover-letter calls are logged to STUB_LOG. STUB_LETTER_FILE makes /cover-letter
# write a file. The resume job reads `running` for the first STUB_RUNNING polls, then STUB_JOB (default done).
# On the public address the moved endpoints answer 404 unless STUB_PUBLIC_HEALTHZ, STUB_PUBLIC_MOVED (the all-zero
# ID probes), STUB_PUBLIC_DELETE (the all-zero DELETE), STUB_PUBLIC_LINK (the viewer's link POST) or
# STUB_PUBLIC_STATUS (a real ID's status) or STUB_PUBLIC_LIST (GET /applications) say otherwise;
# those probes are logged as a bare PROBE line. The public email status probe is logged as EMAIL and answers
# STUB_EMAIL (default 404) with reason STUB_EMAIL_REASON (default no_match).
cat > "$tmp/curl" <<'STUB'
#!/bin/sh
case "$*" in
  *"http://x/healthz"*) echo PROBE >> "$STUB_LOG"; printf '%s' "${STUB_PUBLIC_HEALTHZ:-404}" ;;
  *"http://x/applications"*) echo PROBE >> "$STUB_LOG"; printf '%s' "${STUB_PUBLIC_LIST:-404}" ;;
  *"http://x/application/email-status"*) echo "EMAIL $*" | tr "\n" " " >> "$STUB_LOG"; echo >> "$STUB_LOG"
    printf '{"ok":false,"reason":"%s","message":"m"}\n%s' "${STUB_EMAIL_REASON:-no_match}" "${STUB_EMAIL:-404}" ;;
  *"http://x/viewer/apply-from-link"*) echo PROBE >> "$STUB_LOG"; printf '%s' "${STUB_PUBLIC_LINK:-404}" ;;
  *"-X DELETE http://x/"*"00000000-0000-0000-0000-000000000000"*) echo PROBE >> "$STUB_LOG"; printf '%s' "${STUB_PUBLIC_DELETE:-404}" ;;
  *"http://x/"*"00000000-0000-0000-0000-000000000000"*) echo PROBE >> "$STUB_LOG"; printf '%s' "${STUB_PUBLIC_MOVED:-404}" ;;
  *"http://x/resume/"*"/status"*) echo "PUBLICSTATUS" >> "$STUB_LOG"
    printf '{"ok":true,"status":"done","saved_path":"JANE DOE.pdf","match":{"status":"no_job_description"}}\n%s' "${STUB_PUBLIC_STATUS:-404}" ;;
  *"http://d/docs"*) printf '%s' "$STUB_DOCS_LISTENER" ;;
  *"http://d/viewer"*) printf '%s' "${STUB_VIEWER_LISTENER:-$STUB_DOCS_LISTENER}" ;;
  *"http://d/openapi.json"*) printf '%s\n%s' "$STUB_SCHEMA" "$STUB_DOCS_LISTENER" ;;
  *"/docs"*|*"/openapi.json"*) printf '%s' "$STUB_DOCS" ;;
  *"/viewer"*) printf '%s' "${STUB_VIEWER:-$STUB_DOCS}" ;;
  *"-X DELETE"*) echo "DELETE $*" >> "$STUB_LOG" ;;
  *"-X PATCH"*) echo "PATCH $*" >> "$STUB_LOG"; printf '%s' "${STUB_PATCH:-200}" ;;
  *"/cover-letter"*) echo "LETTER $*" | tr "\n" " " >> "$STUB_LOG"; echo >> "$STUB_LOG"
    [ -n "${STUB_LETTER_FILE:-}" ] && printf '%%PDF' > "$(dirname "$STUB_SAVED")/JANE DOE - Cover Letter.pdf"
    printf '{"ok":false,"message":"no posting text"}\n%s' "${STUB_LETTER:-422}" ;;
  *"/resume/"*"/status"*) echo "STATUS $*" | tr "\n" " " >> "$STUB_LOG"; echo >> "$STUB_LOG"
    job=${STUB_JOB:-done}; [ "$(grep -c '^STATUS' "$STUB_LOG")" -le "${STUB_RUNNING:-0}" ] && job=running
    printf '{"ok":true,"application_id":"3f2b9c1e-8d4a-4c6e-9b1f-2a7d5e8c0b13","status":"%s","saved_path":"%s","match":{"status":"%s"},"error":"Resume generation failed"}\n%s' \
      "$job" "${STUB_NAME:-JANE DOE.pdf}" "${STUB_MATCH:-no_job_description}" "${STUB_STATUS:-200}" ;;
  *"/application"*) echo "CREATE $*" >> "$STUB_LOG"
    printf '{"ok":true,"application_id":"3f2b9c1e-8d4a-4c6e-9b1f-2a7d5e8c0b13"}\n%s' "$STUB_APP" ;;
  *"/resume"*) echo "$*" | tr "\n" " " >> "$STUB_LOG"; echo >> "$STUB_LOG"
    printf '{"ok":true,"application_id":"3f2b9c1e-8d4a-4c6e-9b1f-2a7d5e8c0b13","status":"running","started_at":"t"}\n%s' \
      "$STUB_RESUME" ;;
esac
STUB
chmod +x "$tmp/curl"

id=3f2b9c1e-8d4a-4c6e-9b1f-2a7d5e8c0b13
saved="$tmp/out/Smoke Test Co/$id/JANE DOE.pdf"
thirteen='{"paths":{"/healthz":{"get":{}},"/health":{"get":{}},"/application":{"post":{}},"/application/{application_id}":{"patch":{},"delete":{},"get":{}},"/resume":{"post":{}},"/cover-letter":{"post":{}},"/applications":{"get":{}},"/application/{application_id}/resume.pdf":{"get":{}},"/application/{application_id}/cover-letter.pdf":{"get":{}},"/resume/base.pdf":{"get":{}},"/cover-letter/base.pdf":{"get":{}}}}'
fifteen='{"paths":{"/healthz":{"get":{}},"/health":{"get":{}},"/application":{"post":{}},"/application/{application_id}":{"patch":{},"delete":{},"get":{}},"/resume":{"post":{}},"/resume/{application_id}/status":{"get":{}},"/cover-letter":{"post":{}},"/cover-letter/{application_id}/status":{"get":{}},"/applications":{"get":{}},"/application/{application_id}/resume.pdf":{"get":{}},"/application/{application_id}/cover-letter.pdf":{"get":{}},"/resume/base.pdf":{"get":{}},"/cover-letter/base.pdf":{"get":{}}}}'
seventeen="$(printf '%s' "$fifteen" | sed 's/}}$/,"\/viewer\/application\/{application_id}":{"patch":{},"delete":{}}}}/')"
eighteen="$(printf '%s' "$seventeen" | sed 's/}}$/,"\/viewer\/application\/{application_id}\/fill":{"post":{}}}}/')"
twenty="$(printf '%s' "$eighteen" | sed 's/}}$/,"\/viewer\/application\/{application_id}\/resume":{"post":{}},"\/viewer\/application\/{application_id}\/cover-letter":{"post":{}}}}/')"
twentyone="$(printf '%s' "$twenty" | sed 's/}}$/,"\/viewer\/apply-from-link":{"post":{}}}}/')"
twentytwo="$(printf '%s' "$twentyone" | sed 's/}}$/,"\/application\/email-status":{"post":{}}}}/')"

# run <app status> <resume status> [file content | "none"]
# Call with prefixed variables inside ( ): sh keeps VAR=x assignments made before a function call.
run() {
  rm -rf "$tmp/out" "$tmp/log"; : > "$tmp/log"
  if [ "${3:-%PDF-1.5}" != none ]; then
    mkdir -p "$(dirname "$saved")" && printf '%s' "${3:-%PDF-1.5}" > "$saved"
  fi
  PATH="$tmp:$PATH" API_KEY=k STUB_DOCS=${STUB_DOCS:-404} STUB_DOCS_LISTENER=${STUB_DOCS_LISTENER:-200} \
  STUB_SCHEMA=${STUB_SCHEMA:-$twentytwo} DOCS_URL=${DOCS_URL:-http://d} OUTPUT_DIR=${OUTPUT_DIR:-$tmp/out} STUB_APP=$1 STUB_RESUME=$2 STUB_SAVED=$saved STUB_LOG=$tmp/log \
    POLL_SECONDS=0 JOB_TIMEOUT=${JOB_TIMEOUT:-3} sh "$here/smoke_test.sh" http://x >/dev/null 2>&1
}
created_any() { grep -q "^CREATE" "$tmp/log"; }
deleted() { grep -q "DELETE.*http://d/application/$id" "$tmp/log"; }
sent_as_string() { grep -q "/resume .*-d {\"application_id\":\"$id\"}" "$tmp/log"; }
patched() { grep -q "PATCH .*http://d/application/$id .*-d {\"full_job_description\":null}" "$tmp/log"; }
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
(STUB_SCHEMA="$seventeen" run 201 202); [ $? -ne 0 ] && ! created_any && ok "seventeen operations (before the fill endpoint) fail" || bad "seventeen operations"
(STUB_SCHEMA="$eighteen" run 201 202); [ $? -ne 0 ] && ! created_any && ok "eighteen operations (before the viewer generation endpoints) fail" || bad "eighteen operations"
(STUB_SCHEMA="$twenty" run 201 202); [ $? -ne 0 ] && ! created_any && ok "twenty operations (before the apply-from-link endpoint) fail" || bad "twenty operations"
(STUB_SCHEMA="$twentyone" run 201 202); [ $? -ne 0 ] && ! created_any && ok "twenty-one operations (before the email status endpoint) fail" || bad "twenty-one operations"
(STUB_SCHEMA='{"paths":{"/health":{"get":{}}}}' run 201 202); [ $? -ne 0 ] && ! created_any && ok "wrong operation count fails" || bad "operation count"
(STUB_SCHEMA='not json' run 201 202); [ $? -ne 0 ] && ! created_any && ok "unreadable schema fails" || bad "unreadable schema"
(DOCS_URL=off run 201 202); [ $? -eq 2 ] && [ ! -s "$tmp/log" ] && ok "DOCS_URL=off is refused before any request" || bad "docs off"
run 201 202 && [ "$(grep -c '^PROBE' "$tmp/log")" -eq 7 ] && ok "the public address is probed for the seven local-only endpoints" || bad "probes"
(STUB_PUBLIC_LIST=200 run 201 202); [ $? -ne 0 ] && ! created_any && ok "a public GET /applications fails before creating anything" || bad "public list"
email_probe() { grep -q "^EMAIL .*-X POST http://x/application/email-status .*\"status\":\"Applied\"" "$tmp/log"; }
run 201 202 && email_probe && [ "$(grep -n "^EMAIL" "$tmp/log" | cut -d: -f1)" -lt "$(grep -n "^CREATE" "$tmp/log" | cut -d: -f1)" ] && ok "public email status probe sends an Applied email before creating anything" || bad "email probe"
(STUB_EMAIL=200 run 201 202); [ $? -ne 0 ] && ! created_any && ok "an email status probe that matches fails" || bad "email 200"
(STUB_EMAIL=404 STUB_EMAIL_REASON=other run 201 202); [ $? -ne 0 ] && ! created_any && ok "an email status 404 without no_match fails" || bad "email reason"
(STUB_EMAIL=401 run 201 202); [ $? -ne 0 ] && ! created_any && ok "an email status 401 fails" || bad "email 401"
(STUB_PUBLIC_HEALTHZ=200 run 201 202); [ $? -ne 0 ] && ! created_any && ok "a public /healthz fails before creating anything" || bad "public healthz"
(STUB_PUBLIC_MOVED=401 run 201 202); [ $? -ne 0 ] && ! created_any && ok "a public status endpoint (401) fails before creating anything" || bad "public status probe"
(STUB_PUBLIC_DELETE=200 run 201 202); [ $? -ne 0 ] && ! created_any && ok "a public DELETE /application fails before creating anything" || bad "public delete"
(STUB_PUBLIC_LINK=422 run 201 202); [ $? -ne 0 ] && ! created_any && ok "a public apply-from-link POST fails before creating anything" || bad "public link"
(STUB_PUBLIC_STATUS=200 STUB_STATUS=404 run 201 202); [ $? -ne 0 ] && deleted && ! grep -q PUBLICSTATUS "$tmp/log" && ok "status served only on the public address fails" || bad "status only public"
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
polled() { grep -q "^STATUS .*http://d/resume/$id/status" "$tmp/log"; }
run 201 202 && polled && ! grep -q PUBLICSTATUS "$tmp/log" && ok "resume status polled on the local listener" || bad "status polled"
(STUB_RUNNING=2 run 201 202) && [ "$(grep -c '^STATUS' "$tmp/log")" -eq 3 ] && ok "polls until the job is done" || bad "polls until done"
(STUB_JOB=failed run 201 202); [ $? -ne 0 ] && deleted && ! grep -q "^LETTER" "$tmp/log" && ok "a failed job fails and still cleans up" || bad "failed job"
(STUB_RUNNING=99 run 201 202); [ $? -ne 0 ] && deleted && [ "$(grep -c '^STATUS' "$tmp/log")" -eq 4 ] && ok "a job still running at the timeout fails and still cleans up" || bad "job timeout"
(STUB_STATUS=404 run 201 202); [ $? -ne 0 ] && deleted && ok "a status endpoint 404 fails and still cleans up" || bad "status 404"
(STUB_STATUS=401 run 201 202); [ $? -ne 0 ] && deleted && ok "a status endpoint 401 fails" || bad "status 401"
run 201 201; [ $? -ne 0 ] && deleted && ! polled && ok "an old synchronous 201 fails" || bad "resume 201"
env -u API_KEY PATH="$tmp:$PATH" sh "$here/smoke_test.sh" http://x >/dev/null 2>&1 && bad "nokey" || ok "nokey"
exit $fail
