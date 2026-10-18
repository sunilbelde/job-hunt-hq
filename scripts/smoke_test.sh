#!/bin/sh
# Smoke test: record a synthetic application on a running service, generate its resume, and
# check that the file at the returned saved_path is a PDF. Must run on the Mac itself, since it
# reads the saved file from disk. If this run created the application, it deletes it and its
# resume folder again; an application left over from an earlier run is reused and kept.
# Usage: API_KEY=... scripts/smoke_test.sh <base_url>
set -eu

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  echo "Usage: API_KEY=<key> $0 <base_url>   (run on the Mac hosting the service)"
  exit 0
fi
if [ $# -ne 1 ]; then
  echo "Usage: API_KEY=<key> $0 <base_url>   (run on the Mac hosting the service)" >&2
  exit 2
fi
: "${API_KEY:?API_KEY must be set}"
base=${1%/}
link=https://example.com/job-hunt-hq-smoke-test

json_field() {
  python3 -c 'import json,sys; print(json.load(sys.stdin)[sys.argv[1]])' "$1"
}

application_id=""
created=""
saved=""
cleanup() {
  [ "$created" = 1 ] || return 0
  curl -sS -o /dev/null -X DELETE "$base/application/$application_id" -H "X-API-Key: $API_KEY" || true
  if [ -n "$saved" ]; then
    # rmdir only removes empty folders, so nothing but the smoke test's own file can be lost.
    rm -f "$saved"
    rmdir "$(dirname "$saved")" 2>/dev/null || true
    rmdir "$(dirname "$(dirname "$saved")")" 2>/dev/null || true
  fi
}
trap cleanup EXIT

resp=$(curl -sS -w '\n%{http_code}' -X POST "$base/application" \
  -H "X-API-Key: $API_KEY" -H 'Content-Type: application/json' \
  -d '{"company":"Smoke Test Co","role":"Software Engineer","job_link":"'"$link"'","posting_source_type":"employer_site","verification_method":"employer_site","official_apply_url":"","full_job_description":"Smoke test posting."}')
status=$(printf '%s\n' "$resp" | tail -n 1)
body=$(printf '%s\n' "$resp" | sed '$d')
case "$status" in
  201) created=1 ;;
  200) ;;
  *) echo "FAIL: POST /application returned $status" >&2; exit 1 ;;
esac
application_id=$(printf '%s' "$body" | json_field application_id)

resp=$(curl -sS -w '\n%{http_code}' -X POST "$base/resume" \
  -H "X-API-Key: $API_KEY" -H 'Content-Type: application/json' \
  -d "{\"application_id\":\"$application_id\"}")
status=$(printf '%s\n' "$resp" | tail -n 1)
body=$(printf '%s\n' "$resp" | sed '$d')
if [ "$status" != "201" ]; then
  echo "FAIL: POST /resume returned $status" >&2
  exit 1
fi

saved=$(printf '%s' "$body" | json_field saved_path)
echo "Saved: $saved"
if [ ! -f "$saved" ]; then
  echo "FAIL: no file at saved_path (is this running on the service's Mac?)" >&2
  exit 1
fi
if [ "$(head -c 4 "$saved")" != "%PDF" ]; then
  echo "FAIL: saved file is not a PDF" >&2
  exit 1
fi
echo "OK: resume saved as a PDF ($(wc -c < "$saved" | tr -d ' ') bytes)"
