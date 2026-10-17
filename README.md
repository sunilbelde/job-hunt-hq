# resume-generation-workflow

## Reading the Google Sheet

`scripts/read_sheet.sh` prints a tab of the job-tracking Google Sheet as CSV. It only needs `curl`.

### Requirement: the sheet must be link-shared

The sheet must be shared as **"Anyone with the link can view"**. Anyone with the link can read it, so keep sensitive data out of it. If it isn't shared, the script exits with an error rather than printing Google's sign-in page.

### Usage

```sh
scripts/read_sheet.sh                          # project sheet, gid 0, CSV to stdout
scripts/read_sheet.sh <sheet_id> <gid>         # another spreadsheet / tab
scripts/read_sheet.sh "" 0 resume.csv          # write to a file (empty id = default)
scripts/read_sheet.sh -h                       # help
```

`SHEET_ID` and `SHEET_GID` environment variables set the defaults. The `gid` is the number after `gid=` in the sheet's URL.

Errors go to stderr with a non-zero exit, so stdout is always safe to pipe.

### Tests

```sh
sh scripts/test_read_sheet.sh   # stubbed curl; no network needed
```

## Job output service

A small FastAPI service. `POST /jobs` takes a job posting, renders a resume PDF, stores it in Cloudflare R2, and returns a pre-signed download link.

The generation step is a stub: `generate_output` in `app/generation.py` validates the posting but ignores its contents and renders the baseline resume (`data/BASE.tex` + `data/resume.cls`, compiled with [tectonic](https://tectonic-typesetting.github.io/)), so the PDF is equivalent to `data/BASE.pdf`. **Not implemented yet (backlog):** tailoring the resume to the posting; that change will replace the stub with generated TeX rendered through the same path.

| Endpoint | Auth | Description |
|---|---|---|
| `GET /healthz`, `GET /health` | none | `200 {"status": "ok"}`, no R2 call. Use `/health` on Cloud Run, which intercepts `/healthz` on `*.run.app` URLs |
| `POST /jobs` | `X-API-Key` | `201 {"job_id", "url", "expires_at", "key"}`; 401 bad key, 422 bad body, 500 render failure, 502 storage failure |

Code layout: `app/main.py` (HTTP), `app/models.py` (`JobRow`), `app/generation.py` (stub generator), `app/rendering.py` (TeX to PDF), `app/storage.py` (R2 upload and signed URLs), `app/settings.py` (config), `data/` (resume template assets).

### Request body (`JobRow`)

All values are plain strings and are not parsed or validated beyond type. Extra fields are ignored. Missing or empty required fields, or non-string values, return 422 (the error lists field names, never values).

| Field | Required |
|---|---|
| `company`, `role`, `full_job_description` | yes (non-empty) |
| `location`, `work_type`, `salary`, `date_posted`, `sponsorship`, `why_it_fits`, `job_link` | no |

### Configuration

Copy `.env.example` to `.env` (git-ignored) and fill it in. Variables: `API_KEY`, `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`, `SIGNED_URL_TTL_SECONDS` (default and max 604800), `ANTHROPIC_API_KEY` (optional for now). The service refuses to start if a required value is missing or invalid.

### Run locally

Rendering needs `tectonic` on your PATH (`brew install tectonic`); the first render downloads TeX packages into its cache.

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/uvicorn app.main:create_app --factory --port 8080

curl -X POST localhost:8080/jobs -H "X-API-Key: $API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"company":"Acme","role":"Software Engineer","full_job_description":"Build things."}'
API_KEY=... scripts/smoke_test.sh http://localhost:8080   # POST, fetch the link, expect 200 and a PDF
```

### Tests

```sh
.venv/bin/python -m pytest        # storage is mocked; no network needed
sh scripts/test_smoke_test.sh     # smoke script with a stubbed curl
```

### Deploying to Google Cloud Run

**1. R2 bucket and scoped token.** In the Cloudflare dashboard: R2 → *Create bucket* (leave public access off). Then R2 → *Manage API tokens* → *Create API token* with permission **Object Read & Write**, scoped to *only this bucket*. Note the Account ID, Access Key ID and Secret Access Key (the secret is shown once).

**2. R2 lifecycle rule.** Bucket → *Settings* → *Object lifecycle rules* → add a rule with prefix `outputs/` that deletes objects 30 days after creation. Signed links stop working once the object is gone, so keep the rule's age at or above the longest link TTL you use.

**3. Secrets in Secret Manager.**

```sh
PROJECT=my-project; REGION=us-central1
gcloud services enable secretmanager.service.googleapis.com run.googleapis.com --project $PROJECT
for name in API_KEY R2_ACCOUNT_ID R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY R2_BUCKET; do
  printf '%s' "<value for $name>" | gcloud secrets create $name --data-file=- --project $PROJECT
done
# Optional: ANTHROPIC_API_KEY, created the same way.

# The Cloud Run runtime service account (default: the Compute Engine one) must read them:
gcloud projects add-iam-policy-binding $PROJECT \
  --member "serviceAccount:<runtime-sa-email>" --role roles/secretmanager.secretAccessor
```

**4. Deploy.** Auth is the API key, so unauthenticated invocation is allowed.

```sh
gcloud run deploy job-output-service \
  --project $PROJECT --region $REGION \
  --source . \
  --allow-unauthenticated \
  --timeout 900 --memory 1Gi --concurrency 2 \
  --min-instances 0 --max-instances 3 \
  --set-secrets API_KEY=API_KEY:latest,R2_ACCOUNT_ID=R2_ACCOUNT_ID:latest,R2_ACCESS_KEY_ID=R2_ACCESS_KEY_ID:latest,R2_SECRET_ACCESS_KEY=R2_SECRET_ACCESS_KEY:latest,R2_BUCKET=R2_BUCKET:latest
```

`--concurrency 2` keeps simultaneous renders within the 1Gi memory limit. The image bundles tectonic and a pre-warmed package cache, so rendering needs no network at runtime. Optionally add `--set-env-vars SIGNED_URL_TTL_SECONDS=604800`. Cloud Run sets `$PORT`, which the container honors.

**5. Verify.**

```sh
URL=$(gcloud run services describe job-output-service --region $REGION --format 'value(status.url)')
API_KEY=... scripts/smoke_test.sh "$URL"
```
