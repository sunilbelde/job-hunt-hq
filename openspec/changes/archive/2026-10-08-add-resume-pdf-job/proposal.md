# Proposal

## Why

The service currently accepts any JSON object and returns a JSON echo file. The real product renders a tailored resume PDF for a job posting. Before building the tailoring pipeline (backlog, to be described later), we need to prove the two new pieces of plumbing: a typed job-posting request, and server-side LaTeX-to-PDF rendering whose output goes through the existing R2 upload and signed-link flow, locally and on Cloud Run.

## What Changes

- `POST /jobs` body is validated against a `JobRow` model: `company`, `role`, `full_job_description` required; `location`, `work_type`, `salary`, `date_posted`, `sponsorship`, `why_it_fits`, `job_link` optional. All are plain strings with no format parsing. Validation failures return 422. **BREAKING**: arbitrary JSON objects are no longer accepted.
- The `generate_output` stub now takes the validated job row, compiles the baseline `data/BASE.tex` to PDF, and returns it as `application/pdf` with extension `pdf`. The job details are validated but not yet used to alter the resume (a re-render of the baseline, equivalent to `data/BASE.pdf`).
- The PDF is uploaded to R2 and returned via the existing signed-link response, unchanged in shape.
- The container image gains a TeX engine and the bundled template assets (`BASE.tex`, `resume.cls`), with the engine's package cache warmed at build time so rendering needs no network at request time.
- A render failure returns a generic 500 and is logged server-side.
- Smoke test and README updated for the new request body and PDF output.

Out of scope (backlog): the resume tailoring pipeline (Claude Agent SDK, skills, generated TeX), any use of job fields to change the document, PDF caching, async processing.

## Capabilities

### New Capabilities
- `resume-pdf-rendering`: Compiling the baseline resume TeX source into a PDF inside the service, with bundled template assets, bounded render time and offline operation.

### Modified Capabilities
- `job-api`: The request body becomes a typed job posting (required/optional string fields, 422 on violations), the generated output becomes a PDF, and render failures get a defined response.

## Impact

- Code: `app/main.py` (typed body), new `JobRow` model, `app/generation.py` (PDF render), new render helper, tests, `scripts/smoke_test.sh`, README.
- Data: `data/BASE.tex` and `data/resume.cls` become runtime assets. `resume.cls` is not yet in the repo; the user is adding it to `data/`, and implementation depends on it.
- Container: `Dockerfile` gains a TeX engine (tectonic) and `COPY data`; image size and build time increase.
- Privacy: the stored PDF contains personal resume data, reachable only through the signed link and removed by the existing 30-day lifecycle rule.
- Dependencies: pydantic is already present; no new Python packages expected.
