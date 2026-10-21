# Proposal

## Why

`POST /resume` returns a match summary once and then forgets it: the scores, the keywords added and the gaps that remain live only in that response, and the tailored PDF sits in a private folder on the Mac. There is no way to look back at an application and see what the service did to the resume and whether it was worth it. A read-only page that shows the base and generated resumes side by side, with the posting and the scoring next to them, makes every generated resume reviewable before it is sent.

## What Changes

- **Generation report, stored**: every successful `POST /resume` stores a report for the application: when it ran, the match status, threshold, base and generated scores with their keyword and requirement coverage, which posting keywords each resume covers, how each posting requirement was assessed for each resume (with the quoted evidence), the keywords added, the keywords the judge rejected and why, and where the PDF was saved. A later generation replaces it; deleting the application deletes it. The `POST /resume` response and log lines do not change.
- **Score breakdown from the tailoring gate**: the repo's skill script (`judge-input`, `verify`) also returns the per-keyword and per-requirement breakdown it already computes, and the rejected keywords, so the service can store them. Nothing in the breakdown is logged.
- **Resume viewer page** at `GET /viewer`: one self-contained HTML page, no third-party scripts, styles or UI libraries, that lists applications with their generated resumes and, for one application, shows:
  - application details (company, role, status, location, work type, salary, posting date, links, why it fits, the posting text);
  - base and generated scores against the threshold, with keyword and requirement coverage;
  - what was added (keywords, requirements that moved from missing or partial to met) and the gaps still found (posting keywords and requirements the generated resume does not cover, keywords the judge rejected);
  - the base resume PDF and the generated resume PDF side by side, rendered inline by the browser's own PDF viewer, with no download, external app or other tool needed.
- **Read endpoints for the page**, API-key protected: `GET /applications` (list with report summaries), `GET /application/{application_id}` (the stored application and its report), `GET /application/{application_id}/resume.pdf` (the saved PDF) and `GET /resume/base.pdf` (the base resume). They are documented in the OpenAPI document; the docs operation count and the smoke test move from 6 to 10.
- **Tailnet-only**: the viewer page and the four read endpoints are served only where API docs are enabled, which the installed service limits to the tailnet-only docs listener. The public Funnel listener answers 404 to all of them, so saved resumes and posting text are still never retrievable from the internet.
- Applications whose resume was generated before this change have no report; the viewer lists them as "no report" and shows their saved PDF beside the base when one exists.

## Capabilities

### New Capabilities
- `resume-viewer`: the read-only viewer page and its read endpoints: what they show, the base-versus-generated side-by-side PDF view, application details, scores, added terms and gaps, API key handling in the page, and where they are served.

### Modified Capabilities
- `resume-tailoring`: the final gate returns the full score breakdown and the judge's rejected keywords, and each successful generation stores a report.
- `application-store`: stores one generation report per application, replaced on regeneration and removed with the application.
- `output-storage`: saved resumes may now be served over HTTP, but only by the viewer's PDF endpoint on the docs listener, with the API key; everywhere else they stay unservable.
- `api-docs`: the documented operations grow from six to ten, with their responses, errors and security.
- `local-service-hosting`: the public listener also never serves the viewer or its read endpoints; the docs listener does, and the smoke test expects ten operations.
- `service-config`: `API_DOCS_ENABLED` also turns the viewer and its read endpoints on.

## Impact

- Code: `app/main.py` (new routes, viewer gating), new `app/viewer.py` (page HTML) and `app/reports.py` or additions to `app/applications.py` (report table), `app/tailoring.py` and `app/generation.py` (carry the breakdown), `app/models.py` (response models), `.claude/skills/tailor-resume/scripts/resume_tool.py` (breakdown in `judge-input` and `verify` output).
- Data: a new `resume_reports` table in `applications.sqlite3`, created in place on startup; no migration of existing rows.
- API: four new `GET` operations, on the docs listener only. Existing endpoints, bodies, statuses and log lines unchanged.
- Scripts and docs: `scripts/smoke_test.sh` (operation count 10, viewer 404 on public), `scripts/install_service.sh` (print the viewer URL), README, tests (`test_api.py`, `test_docs.py`, `test_applications.py`, `test_tailoring.py`, `test_resume_verify.py`, new `test_viewer.py`).
- No new dependencies.
