# Design

## Context

- `POST /resume` (`app/main.py`) calls `generate_output` → `tailoring.run`, which runs Claude in throwaway folders and then the repo's own `resume_tool.py judge-input` and `verify`. Those print one JSON object each, with scores and codes only. All work folders, including `analysis.json`, `assessment_tailored.json` and `terms.json`, are deleted in `run`'s `finally`. So today the only lasting outputs are the PDF and the `match` object in the response.
- `resume_score.score()` already computes everything the viewer needs per resume: keyword rows (`term`, `importance`, `present`), requirement rows (`id`, `importance`, `status`, `counted`, `unverified`, `reason`) and both coverages. Requirement `text` and evidence quotes are in the analysis and assessment, not in the rows. Rejected keywords with reasons are in `terms.json` (`Terms.rejected`).
- `app/serve.py` runs two `create_app` instances on one store: the public one (Funnel) with `api_docs_enabled` forced off, and the docs one (tailnet only) with it on. The output-storage spec forbids serving resume files, and the hosting spec forbids them on the public address.
- `output-storage` requires the resume to be the only file in its application folder, so a report can't sit next to the PDF.
- The request log middleware's `request_event` keys off `/resume` and `/application[/...]`; `/applications` and `/resume/base.pdf` match neither today.

## Goals / Non-Goals

**Goals:**
- Keep the existing `POST /resume` contract, logs and failure behaviour exactly as they are; the report is a side effect after a successful save.
- One self-contained page, vanilla HTML/CSS/JS served from a Python string, with nothing loaded from a CDN.
- Same data-protection posture as `/docs`: tailnet-only, API key in memory only.

**Non-Goals:**
- Editing applications, regenerating resumes or changing status from the viewer (read-only; `/docs` already does writes).
- A line-by-line text diff of the resumes. The PDFs side by side plus the keyword and requirement comparison cover "what changed"; a bullet diff can come later from stored content.
- Backfilling reports for resumes generated before this change.
- Report history; only the latest generation is kept.

## Decisions

### 1. The scripts return the breakdown; the service stores it as JSON
Extend `resume_tool.py`: `judge-input` adds `"base": <breakdown>` and `verify` adds `"base"`, `"tailored"` and `"rejected_terms"`. A breakdown is `Score.to_json()` plus, per requirement, its `text` and `evidence` merged in from the analysis/assessment (one helper in `resume_score`, e.g. `breakdown(score, requirements, assessment)`). `tailoring.Match` grows `base_breakdown`, `tailored_breakdown` and `rejected_terms` fields, which `to_dict()` leaves out, so the response is unchanged.

*Alternative*: keep the work folders' JSON files and parse them in the service. Rejected: the service deliberately trusts only its own gate's output (Decision 8 of the tailoring design), and the folders are attacker-influenced by the run.

### 2. Reports live in a `resume_reports` table in `applications.sqlite3`
`resume_reports(application_id TEXT PRIMARY KEY REFERENCES applications(id), generated_at TEXT NOT NULL, saved_path TEXT NOT NULL, report TEXT NOT NULL)`, `report` a JSON document (`version: 1`, `status`, `threshold`, `base`, `tailored`, `added_terms`, `rejected_terms`). Created with `CREATE TABLE IF NOT EXISTS` in `ApplicationStore.__init__`. `ApplicationStore` gains `save_report`, `get_report`, `list_with_reports`; `delete` removes the report in the same transaction. Upsert with `INSERT ... ON CONFLICT(application_id) DO UPDATE`.

*Alternatives*: a JSON file beside the PDF (breaks "resume is the only file in its folder" and needs its own atomic write); columns on `applications` (mixes generated output into the posting record and its update rules). A JSON blob over normalized tables because the viewer always reads the whole report and the shape tracks the script's output.

The foreign key is documentation only (SQLite enforces it only with `PRAGMA foreign_keys`); deletion is explicit in `delete`.

### 3. Storing the report never fails the request
In `create_resume`, after `storage.save_resume` succeeds: `applications.save_report(...)` in the threadpool; an `ApplicationStoreError` logs `{"event": "report_store_error", "application_id", "error"}` and the 201 is returned as before. The PDF on disk is the user-visible result; a missing report only degrades the viewer to the legacy view.

### 4. Everything new is gated by `api_docs_enabled`
The four read routes and `/viewer` are registered inside `if docs:` in `create_app`, so on the public app they do not exist (404 from routing, like `/docs`). No new setting: the docs listener already is "the tailnet-only, owner's-devices listener", and a second flag would let the two drift.

*Alternative*: serve the read endpoints on both listeners behind the key. Rejected: it would publish posting text and resume PDFs to the internet with the key as the only guard, which the hosting spec rules out.

### 5. Read endpoints follow the existing handler style
Same inline key check (`api_key_valid` → 401 `{ok:false}`), `parse_application_id` → 404, `store_unavailable` → 503, documented with `errors(...)` and response models (`ApplicationList`, `ApplicationDetail`, `ResumeReport` in `app/models.py`, description-only as today). PDF responses use `Response(content, media_type="application/pdf", headers={"Cache-Control": "no-store", "Content-Disposition": "inline"})` and are documented with `responses={200: {"content": {"application/pdf": {}}}}`.

Route order matters: `GET /application/{application_id}/resume.pdf` and `GET /application/{application_id}` are separate paths, no conflict; `/applications` is a distinct literal path.

### 6. Generated PDF path: the stored `saved_path`, checked against `OUTPUT_DIR`
Read `report.saved_path`; without a report fall back to `<OUTPUT_DIR>/<company_folder(company)>/<id>/SUNIL BELDE.pdf` (new `storage.resume_path(root, company, id)`, reused by `save_resume`). Resolve and require `is_relative_to(OUTPUT_DIR.resolve())` and a regular file, else 404 "Resume not found". Read via `run_in_threadpool`.

### 7. Base PDF: rendered, cached by template fingerprint
`render_pdf()` takes seconds (Tectonic), so cache the bytes in process keyed by the `(name, size, mtime_ns)` of the template files `render_pdf` copies. Cache miss renders in the threadpool; `RenderError` → 500 "Resume generation failed". Not `data/BASE.pdf`: it is a checked-in artifact that can lag `BASE.tex`, and the viewer must show exactly what `POST /resume` would save as the base.

### 8. Viewer page: one HTML string in `app/viewer.py`
- Served by `GET /viewer` (`include_in_schema=False`) with `Content-Security-Policy: default-src 'none'; script-src 'nonce-<random>'; style-src 'nonce-<random>'; connect-src 'self'; frame-src blob:; object-src blob:; img-src 'self' blob:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'` and a fresh nonce per response, plus `Cache-Control: no-store` and `Referrer-Policy: no-referrer`.
- Key prompt: a single password input shown first; the key lives in a JS variable. `fetch` with `X-API-Key`; any 401 clears it and shows the prompt.
- Layout: left column list (company, role, status, match status badge, base → generated score); right: details header, score cards, "Added" and "Gaps" lists, requirement comparison table (expand a row for evidence), then the two PDF panes. CSS grid, `@media (max-width: 1100px)` stacks the panes base first. Light/dark via `prefers-color-scheme`.
- PDFs: `fetch` → `Blob` → `URL.createObjectURL` → `<iframe src=blob:...>`, so the browser's built-in PDF viewer renders them and the key never enters a URL. Revoke the previous object URLs on selection change.
- Selection is in the URL hash (`#<application id>`) so a link opens one application after the key is entered; IDs only, never the key.
- All data inserted with `textContent` / `createElement`, never `innerHTML`, so posting text cannot inject markup.
- "Added" requirement changes are computed client-side by joining base and tailored requirement rows on `id` with the order missing < partial < met, using the `counted` status.

*Alternatives*: PDF.js (a third-party library and a CDN load, against the request and the CSP); server-side templates (Jinja is not a dependency; the page is static and data comes from the JSON endpoints).

### 9. Logging
Extend `request_event`: `/applications` → `application_request`; `/resume/base.pdf` → `resume_request`; `/application/{id}...` already maps. `/viewer` returns `None` (not logged), like `/docs`. Handlers set only `request.state.application_id`; no breakdown field enters `LOGGED_STATE`.

## Risks / Trade-offs

- [Report JSON stores posting keywords and requirement text in the store] → Same file and permissions (0600) as `full_job_description`, which is already more sensitive; only readable through key-guarded, tailnet-only endpoints.
- [Breakdown shape changes later break old reports] → `version` field in the report; the page shows the legacy view for an unknown version.
- [Safari or mobile browsers may not render PDFs in iframes from blob URLs (iOS shows the first page only)] → Accepted for an owner-only tool; the pane also offers "open in new tab" of the same blob URL, which stays inside the browser.
- [Base cache keyed on mtimes misses a change that keeps size and mtime] → Practically impossible with editors; a restart clears it.
- [Report write fails after the PDF was saved, leaving an old report describing a different PDF] → On a failed `save_report`, the handler also attempts `delete_report`, so the viewer falls back to the legacy view instead of showing stale scores; both failures are logged.
- [Larger `verify` output] → A few KB of JSON on stdout; no limit is near.

## Migration Plan

- The new table is created on first start; existing rows and files untouched. Old resumes show as "no report" until regenerated.
- Deploy: pull, `scripts/install_service.sh` (restarts, checks `/viewer` on both ports), `scripts/smoke_test.sh`.
- Rollback: install the previous commit. The extra table is ignored by older code and can be left in place.
