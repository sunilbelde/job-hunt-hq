# Tasks

## 1. Request model

- [x] 1.1 Add `app/models.py` with `JobRow` (strict string fields; `company`, `role`, `full_job_description` required and non-empty; others optional; extras ignored) and unit tests for the field-rule scenarios (missing, empty, wrong type, free-form optional values, minimal posting); verify `pytest tests/test_models.py` passes
- [x] 1.2 Validate the parsed body with `JobRow` in `POST /jobs` after auth, returning 422 with field-level details that do not echo values; update `tests/test_api.py` so `{}`, missing fields and wrong types return 422 with zero uploads, and success tests use a valid posting; verify the suite passes

## 2. PDF rendering

- [x] 2.1 Add `app/rendering.py` (`render_pdf`, `RenderError`): temp-dir copy of `data/` template files, `tectonic -X compile --untrusted`, 120 s timeout, bytes returned, directory cleaned in all outcomes; verify mocked-subprocess tests cover success, non-zero exit, timeout, missing output/binary, cleanup and unchanged source files
- [x] 2.2 Add a real-render test (skipped when tectonic is absent) asserting `%PDF` signature, 1 page and the owner's name via `pypdf` (add to `requirements-dev.txt`); verify it passes locally

## 3. Wire generation into the API

- [x] 3.1 Change `generate_output` to `(job: JobRow, *, job_id=None)` returning `application/pdf`/`pdf` from `render_pdf()`, replacing the JSON-echo stub and its test; verify a unit test with `render_pdf` patched checks the returned `GeneratedFile`
- [x] 3.2 Call `generate_output` via `run_in_threadpool` and map `RenderError` to a generic 500 with details logged server-side and no upload; verify tests for the 500 body (no TeX output or paths), zero uploads, a log line with the job id, and that `/health` still responds while a slow render is in flight
- [x] 3.3 Update the success-path API test to assert uploaded content type `application/pdf`, extension `pdf` and the `%PDF` signature (with `generate_output` patched so tectonic is not needed); verify `pytest` passes offline

## 4. Container

- [x] 4.1 Update the `Dockerfile`: multi-stage download of the pinned tectonic release for `TARGETARCH` (checksum verified), `COPY data ./data`, `TECTONIC_CACHE_DIR` owned by the non-root user, and a build-time warm-up compile of `BASE.tex`; verify `docker build` succeeds and record the image size
- [x] 4.2 Verify in Docker, as non-root with outbound network blocked (`--network none`), that `render_pdf()` produces a valid 1-page PDF whose text matches `BASE.pdf` (copy the PDF out and compare with `pypdf`); verify the image contains `data/resume.cls` and no `.env`

## 5. Smoke test and docs

- [x] 5.1 Update `scripts/smoke_test.sh` to send a sample `JobRow`, require 201, fetch the link and require 200 and a body starting with `%PDF`; extend `scripts/test_smoke_test.sh` for PDF success and non-PDF failure; verify the stubbed tests pass
- [x] 5.2 Update the README (`JobRow` field table, PDF output, `data/` template assets, `--concurrency 2` in the deploy command, backlog note that tailoring is not implemented); verify the documented example request returns 201 locally

## 6. End-to-end acceptance

- [x] 6.1 Run locally against real R2: POST a sample posting, open the returned link and confirm a PDF with the baseline resume content downloads; confirm an invalid posting returns 422 and writes no object
- [x] 6.2 Redeploy to Cloud Run with `--concurrency 2` and rerun `scripts/smoke_test.sh <url>`; verify 201 then a 200 PDF download, and note cold-start and render time from the logs

## Workflow follow-up

- Archive the change after the Cloud Run acceptance check passes.
- Backlog (separate change, workflow to be described by the user): the resume tailoring pipeline that replaces the baseline render with generated TeX.
