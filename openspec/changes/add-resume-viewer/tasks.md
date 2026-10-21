# Tasks

## 1. Score breakdown from the skill script

- [x] 1.1 Add a breakdown helper to `.claude/skills/tailor-resume/scripts/resume_score.py` that returns `Score.to_json()` with each requirement's `text` and `evidence` merged in from the analysis and assessment; verify with new cases in `tests/test_resume_score.py` (met, partial, unverified quote → `counted` `missing` with reason)
- [x] 1.2 Make `resume_tool.py judge-input` print `"base": <breakdown>` and `verify` print `"base"`, `"tailored"` and `"rejected_terms"` (term and reason from the ruling), keeping every existing key; verify with `tests/test_resume_verify.py` cases for keep, tailored and a failed check (no `tailored` on failure)
- [x] 1.3 Carry the breakdowns and rejected terms through `app/tailoring.py` (`Match` fields left out of `to_dict()`) and `app/generation.py`; verify `tests/test_tailoring.py` and `tests/test_generation.py` show the fields populated for keep and tailored, and `Match.to_dict()` output unchanged

## 2. Report storage

- [x] 2.1 Add the `resume_reports` table (created if missing on startup) and `save_report`, `get_report`, `delete_report`, `list_with_reports` to `ApplicationStore`; make `delete` remove the report in the same transaction; verify with `tests/test_applications.py`: pre-existing store upgrades with rows unchanged, upsert keeps one report, delete removes it, update keeps it
- [x] 2.2 Build the report document (`version`, `status`, `threshold`, `generated_at`, `saved_path`, `base`, `tailored`, `added_terms`, `rejected_terms`) from `GeneratedFile` and store it in `create_resume` after `save_resume`; on `ApplicationStoreError` log `report_store_error` (no content), try `delete_report`, and still return 201; verify in `tests/test_api.py`: report stored for each match status, failed generation keeps the earlier report, store failure still 201 with an unchanged body, no keyword or requirement text in any log line

## 3. Read endpoints (docs listener only)

- [x] 3.1 Add `storage.resume_path(root, company, id)` and use it in `save_resume`; verify `tests/test_storage.py` passes unchanged plus a case for the helper
- [x] 3.2 Add response models (`ApplicationListItem`/`ApplicationList`, `ApplicationDetail`, `ResumeReport` and breakdown models) to `app/models.py` with field descriptions; verify they import and appear in the schema in 3.6
- [x] 3.3 Register `GET /applications` and `GET /application/{application_id}` inside the docs-enabled branch of `create_app`, with the inline key check, 404 and 503 handling; verify in a new `tests/test_viewer.py`: ordering by generation then recording time, `report: null` for legacy rows, no posting text in the list, 401/404/503, and 404 for all of them when docs are disabled
- [x] 3.4 Register `GET /application/{application_id}/resume.pdf` reading the report's `saved_path` (or the current-company path without a report), checked to be a regular file inside `OUTPUT_DIR`, served `application/pdf` with `Cache-Control: no-store`; verify in `tests/test_viewer.py`: exact bytes, renamed company still served from the stored path, never generated → 404 "Resume not found", stored path outside `OUTPUT_DIR` → 404, 401 without key
- [x] 3.5 Register `GET /resume/base.pdf` with an in-process cache keyed by the template files' name, size and mtime; verify in `tests/test_viewer.py` (render stubbed): second request does not re-render, touching a template file re-renders, `RenderError` → 500 "Resume generation failed"
- [x] 3.6 Extend `request_event` so `/applications` logs `application_request` and `/resume/base.pdf` logs `resume_request`, with method and application ID only; verify in `tests/test_viewer.py` one log line per read request and none for `/viewer`
- [x] 3.7 Document the four operations (summaries, descriptions, tags, `errors(...)`, `application/pdf` 200 content, `ApiKey` security) and update `tests/test_docs.py`: exactly ten operations, statuses per the api-docs delta, security on the four reads, `/viewer` not listed, PDF media types

## 4. Viewer page

- [x] 4.1 Create `app/viewer.py` with the page HTML (inline CSS and JS, no external URLs) and serve it at `GET /viewer` (docs-enabled only, not in the schema) with a per-response nonce CSP, `Cache-Control: no-store` and `Referrer-Policy: no-referrer`; verify in `tests/test_viewer.py`: 200 without a key, 404 when docs disabled, no `http(s)://` asset URL in the HTML, CSP header allows no other origin for scripts, styles and frames, no application data in the HTML
- [x] 4.2 Implement the key prompt (memory only, `X-API-Key` header, 401 clears the key and asks again) and the application list with match status and base → generated scores; verify in a browser against a local `API_DOCS_ENABLED=true` server with a fake store: wrong key rejected, reload asks again, no key in any request URL (devtools network tab)
- [x] 4.3 Implement the detail view: application details with links and the posting text collapsed, inserted only via `textContent`; score cards with threshold and coverages; "Added" (added keywords, requirements improved by counted status); "Gaps" (uncovered keywords with importance, partial/missing requirements, rejected keywords with reason); requirement table with expandable evidence; legacy and `no_job_description` messages; verify in a browser with seeded tailored, base-kept, unscored and legacy applications, and that a posting containing `<script>` shows as text
- [ ] 4.4 Implement the side-by-side PDF panes from blob URLs (labels "Base" and "Generated", "base unchanged" note, "not generated" placeholder, stacked base-first below the breakpoint, object URLs revoked on change, `#<id>` deep link); verify in Chrome and Safari on the Mac that both PDFs render inline, the panes stack at narrow width, and opening `/viewer#<id>` selects that application after the key is entered

## 5. Hosting, scripts and docs

- [x] 5.1 Update `scripts/smoke_test.sh`: public `GET /viewer` must be 404, docs listener `GET /viewer` must be 200, operation count 10; update `scripts/test_smoke_test.sh` to match and verify it passes
- [x] 5.2 Update `scripts/install_service.sh` to check `/viewer` is 404 on the public port and 200 on the docs port and to print the local and tailnet viewer URLs; verify with `scripts/test_install_service.sh`
- [x] 5.3 Update README (viewer section: what it shows, URL on the tailnet, key prompt, legacy resumes) and the `API_DOCS_ENABLED` note in `.env.example`; verify `tests/test_settings.py`/docs tests that check `.env.example` still pass

## 6. Integration

- [x] 6.1 Run the full test suite (`pytest`) with docs enabled and disabled and verify every existing API test passes unmodified
- [ ] 6.2 On the Mac mini: reinstall, run the smoke test, generate a resume for one tailored and one base-kept application, then open the viewer from another tailnet device and verify details, scores, added terms, gaps and both PDFs side by side; verify `https://<mac-tailscale-name>/viewer` and `/applications` answer 404 from outside the tailnet

## Workflow follow-up

- Archive the change once implemented and reviewed, syncing the delta specs into `openspec/specs/`.
