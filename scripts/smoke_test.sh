#!/bin/sh
# Smoke test: check that the public address serves no API docs or resume viewer and that the docs
# listener serves both,
# then record a synthetic application on a running service, generate its resume, and check that
# the file at the returned saved_path is a PDF. The application has no posting text, so the
# service saves the base resume without starting a Claude run, and refuses a cover letter (422)
# without starting one either. Must run on the Mac itself, since it
# reads the saved file from disk. If this run created the application, it deletes it and its
# resume folder again; an application left over from an earlier run is reused and kept.
# Usage: API_KEY=... [DOCS_URL=http://127.0.0.1:8081|off] scripts/smoke_test.sh <base_url>
set -eu

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  echo "Usage: API_KEY=<key> [DOCS_URL=<docs listener url>|off] $0 <base_url>   (run on the Mac hosting the service)"
  echo "The synthetic application has no posting text, so the check never starts a Claude run, for the resume or the cover letter."
  exit 0
fi
if [ $# -ne 1 ]; then
  echo "Usage: API_KEY=<key> $0 <base_url>   (run on the Mac hosting the service)" >&2
  exit 2
fi
: "${API_KEY:?API_KEY must be set}"
base=${1%/}
docs=${DOCS_URL:-http://127.0.0.1:8081}
docs=${docs%/}
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

# The installed service is public, so it must never serve the API reference, its schema or the viewer.
for path in /docs /openapi.json /viewer; do
  status=$(curl -sS -o /dev/null -w '%{http_code}' "$base$path")
  if [ "$status" != "404" ]; then
    echo "FAIL: GET $path returned $status, want 404 (API docs and the viewer must be off on the public address)" >&2
    exit 1
  fi
done

# The docs listener (tailnet only) serves the reference, the viewer and a schema with the eleven operations.
if [ "$docs" != off ]; then
  for path in /docs /viewer; do
    status=$(curl -sS -o /dev/null -w '%{http_code}' "$docs$path" || true)
    if [ "$status" != "200" ]; then
      echo "FAIL: GET $docs$path returned $status, want 200 (is the docs listener running? DOCS_URL=off skips this)" >&2
      exit 1
    fi
  done
  resp=$(curl -sS -w '\n%{http_code}' "$docs/openapi.json" || true)
  status=$(printf '%s\n' "$resp" | tail -n 1)
  count=$(printf '%s\n' "$resp" | sed '$d' | python3 -c 'import json,sys
methods = {"get", "put", "post", "delete", "patch", "head", "options", "trace"}
print(sum(m in methods for ops in json.load(sys.stdin)["paths"].values() for m in ops))' 2>/dev/null || true)
  if [ "$status" != "200" ] || [ "$count" != "11" ]; then
    echo "FAIL: GET $docs/openapi.json returned $status with ${count:-no} operations, want 200 with 11" >&2
    exit 1
  fi
fi

resp=$(curl -sS -w '\n%{http_code}' -X POST "$base/application" \
  -H "X-API-Key: $API_KEY" -H 'Content-Type: application/json' \
  -d '{"company":"Smoke Test Co","role":"Software Engineer","job_link":"'"$link"'","posting_source_type":"employer_site","verification_method":"employer_site","official_apply_url":""}')
status=$(printf '%s\n' "$resp" | tail -n 1)
body=$(printf '%s\n' "$resp" | sed '$d')
case "$status" in
  201) created=1 ;;
  200) ;;
  *) echo "FAIL: POST /application returned $status" >&2; exit 1 ;;
esac
application_id=$(printf '%s' "$body" | json_field application_id)

# An older smoke test stored posting text, which would make the service score and tailor (a paid
# Claude run). Clear it on a reused application, so the resume is always the unscored base one.
if [ "$created" != 1 ]; then
  status=$(curl -sS -o /dev/null -w '%{http_code}' -X PATCH "$base/application/$application_id" \
    -H "X-API-Key: $API_KEY" -H 'Content-Type: application/json' -d '{"full_job_description":null}')
  if [ "$status" != "200" ]; then
    echo "FAIL: PATCH /application returned $status while clearing the smoke test's posting text" >&2
    exit 1
  fi
fi

resp=$(curl -sS -w '\n%{http_code}' -X POST "$base/resume" \
  -H "X-API-Key: $API_KEY" -H 'Content-Type: application/json' \
  -d "{\"application_id\":\"$application_id\"}")
status=$(printf '%s\n' "$resp" | tail -n 1)
body=$(printf '%s\n' "$resp" | sed '$d')
if [ "$status" != "201" ]; then
  echo "FAIL: POST /resume returned $status" >&2
  exit 1
fi

match=$(printf '%s' "$body" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("match", {}).get("status"))')
if [ "$match" != "no_job_description" ]; then
  echo "FAIL: POST /resume reported match.status $match, want no_job_description (no Claude run)" >&2
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

# A cover letter is always tailored, so without posting text the service refuses it before any Claude run.
letter="$(dirname "$saved")/SUNIL BELDE - Cover Letter.pdf"
resp=$(curl -sS -w '\n%{http_code}' -X POST "$base/cover-letter" \
  -H "X-API-Key: $API_KEY" -H 'Content-Type: application/json' \
  -d "{\"application_id\":\"$application_id\"}")
status=$(printf '%s\n' "$resp" | tail -n 1)
if [ "$status" != "422" ]; then
  echo "FAIL: POST /cover-letter returned $status, want 422 (no posting text, so no Claude run)" >&2
  exit 1
fi
if [ -e "$letter" ]; then
  echo "FAIL: a cover letter file exists beside the smoke test's resume" >&2
  exit 1
fi
echo "OK: cover letter refused without posting text (422), no file written"
