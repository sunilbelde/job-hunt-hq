#!/bin/sh
# Smoke test: POST a sample job posting to a running service, then fetch the returned
# link and check that it is a PDF.
# Usage: API_KEY=... scripts/smoke_test.sh <base_url>
set -eu

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  echo "Usage: API_KEY=<key> $0 <base_url>"
  exit 0
fi
if [ $# -ne 1 ]; then
  echo "Usage: API_KEY=<key> $0 <base_url>" >&2
  exit 2
fi
: "${API_KEY:?API_KEY must be set}"
base=${1%/}

resp=$(curl -sS -w '\n%{http_code}' -X POST "$base/jobs" \
  -H "X-API-Key: $API_KEY" -H 'Content-Type: application/json' \
  -d '{"company":"Smoke Test Co","role":"Software Engineer","full_job_description":"Smoke test posting.","location":"Remote","salary":"$100k-$120k","job_link":"https://example.com/job"}')
status=$(printf '%s\n' "$resp" | tail -n 1)
body=$(printf '%s\n' "$resp" | sed '$d')

if [ "$status" != "201" ]; then
  echo "FAIL: POST /jobs returned $status" >&2
  exit 1
fi

url=$(printf '%s' "$body" | python3 -c 'import json,sys; print(json.load(sys.stdin)["url"])')
echo "Link: $url"

out=$(mktemp)
trap 'rm -f "$out"' EXIT
code=$(curl -sS -o "$out" -w '%{http_code}' "$url")
if [ "$code" != "200" ]; then
  echo "FAIL: fetching link returned $code" >&2
  exit 1
fi
if [ "$(head -c 4 "$out")" != "%PDF" ]; then
  echo "FAIL: downloaded file is not a PDF" >&2
  exit 1
fi
echo "OK: link returned 200 and a PDF ($(wc -c < "$out" | tr -d ' ') bytes)"
