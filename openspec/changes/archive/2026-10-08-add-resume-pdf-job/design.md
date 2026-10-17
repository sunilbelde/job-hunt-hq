# Design

## Context

The deployed service (`app/main.py`, `app/generation.py`, `app/storage.py`) accepts any JSON object, calls `generate_output(payload, *, job_id)`, uploads the result and returns a signed link. Storage is content-agnostic (key extension and Content-Type come from `GeneratedFile`), so it needs no change.

`data/` now holds `BASE.tex`, `resume.cls` and `BASE.pdf`. `BASE.tex` uses `\documentclass{resume}` plus `hyperref`, `geometry` and `fontawesome`. Observed during planning: `tectonic` 0.15.0 (installed locally; no TeX Live) compiles `BASE.tex` with `resume.cls` in about 1 s to a 1-page PDF whose text is about 98% similar to `BASE.pdf` (differences are extraction and embedded-font noise). That compile downloaded a font file (`cmsy9.pfb`) from tectonic's bundle, so a cold cache needs network. Deployed image is `python:3.12-slim` running as a non-root user. See proposal.md for scope.

## Goals / Non-Goals

**Goals:**
- Typed `JobRow` request with 422 on violations, no value parsing.
- A render module that compiles TeX source to PDF bytes, reusable when generated TeX replaces `BASE.tex`.
- Rendering works offline in the container, as non-root, on Cloud Run.

**Non-Goals:**
- Tailoring the resume from job fields (backlog; the workflow will be described later).
- Caching rendered PDFs, async rendering, multiple templates.
- Byte-identical output to `BASE.pdf` (content-equivalent is the bar).

## Decisions

**TeX engine: tectonic, not TeX Live.** A single static binary plus a package cache is far smaller than TeX Live with `texlive-fonts-extra` (needed for `fontawesome`, hundreds of MB), builds faster, and is what's already proven locally, so local and container behavior match. Because tectonic fetches missing files on demand, the image build warms its cache by compiling `BASE.tex` once, and `TECTONIC_CACHE_DIR` points to a path owned by the runtime user. Alternatives rejected: apt TeX Live (large image, slow builds, version drift from local); a remote render service (extra infra for ~20 req/day).

**Installing tectonic in the image.** A build stage downloads the pinned release tarball matching `TARGETARCH` (amd64 for Cloud Run, arm64 for local colima), verifies its checksum, and the final stage copies only the binary. The cache warm-up runs as the non-root user so file ownership is correct.

**Render module (`app/rendering.py`).** `render_pdf(main_tex: str = "BASE.tex") -> bytes`. Create a `TemporaryDirectory`, copy the template files from `data/` into it (never compile in place, so bundled files stay untouched and concurrent renders cannot collide), run `tectonic -X compile --untrusted <file>` via `subprocess.run` with a fixed 120 s timeout and captured output, read the resulting PDF, return bytes. Non-zero exit, timeout, missing output, or missing binary raises `RenderError` carrying details for logging only. `--untrusted` disables shell-escape, which matters once the TeX is model-generated. A missing `resume.cls` surfaces as a compile failure, never a silent fallback.

**Seams.** `generate_output(job: JobRow, *, job_id: str | None = None) -> GeneratedFile` keeps its return type. Its input changes from `dict` to `JobRow`: a deliberate interface change flagged in the proposal. The stub ignores the job fields and returns `render_pdf()` as `application/pdf`/`pdf`. Later, tailoring replaces the body and calls `render_pdf` on generated TeX; HTTP and storage layers do not change.

**Request model.** `app/models.py` defines `JobRow(BaseModel)` with `StrictStr` fields (a number or null for a string field is a 422, not silently coerced), required fields `min_length=1`, optional fields default `None`, unknown extra fields ignored. The route keeps parsing JSON manually so auth runs before body errors, then calls `JobRow.model_validate(payload)` and maps `ValidationError` to 422 with field names and messages but not input values, so resume or job text is never echoed into responses or logs. Non-object JSON still returns 422.

**Blocking work off the event loop.** Rendering takes seconds and blocks, so the route calls `generate_output` through `run_in_threadpool`; otherwise one render would stall every other request on the instance, including health checks.

**Errors.** `RenderError` maps to a generic 500 (`"Resume generation failed"`), distinct from the 502 for storage failures, logged with the job id and exception detail, with no upload attempted. The per-request log line already records the status.

**Deployment.** Rendering uses CPU and memory per request, so the README deploy command adds `--concurrency 2` to keep peak memory within 1 Gi. Timeout 900 s and max instances 3 are unchanged. Memory and cold start are measured in the Cloud Run acceptance task rather than assumed.

**Tests.** Unit tests mock `subprocess.run` and storage, needing neither network nor tectonic: render success, non-zero exit, timeout (process killed, `RenderError`), temp-dir cleanup, `JobRow` field rules, 422 cases with zero uploads, 500 with zero uploads and no TeX output in the body. One real-render test runs only when `tectonic` is present and the cache is warm, and checks the PDF signature, page count and owner name via `pypdf` (added to dev requirements). It runs locally and in the Docker verification step, not in the offline suite.

## Risks / Trade-offs

- [Output is not byte-identical to `BASE.pdf` (timestamps, engine, fonts)] → acceptance is content equivalence (page count, extracted text), as measured during planning.
- [Tectonic cache warm-up fetches from the network at build time; the bundle host could be unavailable] → fail the build loudly and retry; runtime has no network dependency, verified with `--network none`.
- [Cache warm-up may miss files only needed by other documents] → acceptable now since only `BASE.tex` is rendered; the future tailoring change must re-check offline rendering for any new packages it uses.
- [Image size and build time grow] → copy only the binary and cache; record image size in the Docker task.
- [Resume PII sits in R2 behind signed links up to 7 days] → unchanged mechanism; 30-day lifecycle rule; the stub embeds no job data. A shorter TTL for PDFs is a backlog consideration.
- [Breaking request contract: arbitrary JSON now returns 422] → only the smoke test calls it today and is updated here.
- [Concurrent renders could exhaust memory] → per-render temp dir, concurrency 2, 120 s timeout; revisit if load grows.

## Migration Plan

Implement, verify locally and in Docker, redeploy with `--concurrency 2`, run the smoke test (expects a `%PDF` body). Rollback: shift traffic back to the previous Cloud Run revision with `gcloud run services update-traffic --to-revisions`.

## Open Questions

- Should the download have a readable filename (`Content-Disposition`)? Deferrable; the key stays `outputs/.../<uuid>.pdf`.
