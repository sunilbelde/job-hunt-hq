# Proposal

## Why

The viewer's sidebar is hard to scan. Each entry has a status dropdown, a **Fill form** button and a **Delete** button on every row, and the filters are stacked labels. Most of the space goes to controls instead of the company, role and score. Also, to generate or regenerate a resume or cover letter, the owner still has to call the keyed API by hand. The viewer already shows both documents next to their base versions, so it is the natural place to start those runs.

## What Changes

- **Cleaner sidebar.** Each list entry becomes one clickable card showing the company, role, a coloured status pill, the match badge, the score (coloured against the threshold) and the recorded date. Cards have no controls. A small indicator shows when a resume or cover letter job is running for that application.
- **Compact filter bar.** A new text search filters by company or role. The status filter and the recorded-date range sit in a tidier bar, with a **Clear** control whenever a filter is set. All filtering still happens in the page.
- **Action bar in the detail view.** For the selected application, the header holds the status control, **Generate/Regenerate resume**, **Generate/Regenerate cover letter**, **Fill form** and **Delete**. The status control, Fill form and Delete move here from the list entries. Their behaviour (immediate save, confirmation before delete, Herdr tab notes) stays the same.
- **Generation from the viewer.** Two new no-key viewer writes, `POST /viewer/application/{application_id}/resume` and `POST /viewer/application/{application_id}/cover-letter`, start the same background jobs as `POST /resume` and `POST /cover-letter`. They follow the same one-running-job-per-kind rule and return the same 202. Like the other viewer writes, they exist only where the viewer is and refuse cross-site requests. Before replacing an existing document, the page asks for confirmation.
- **Job progress in the viewer.** `GET /applications` gains a `jobs` summary per application: each kind's state, start time, finish time and fixed error message, with no result, text or path. While any job is running, the page re-reads the list every few seconds. When the selected application's job finishes, it reloads the affected document and scores, or shows the failure.
- Documented operations go from eighteen to twenty. The smoke test expects twenty.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `resume-viewer`:
  - The list carries job summaries and entries become control-free cards.
  - Status, Fill form and Delete move to a detail action bar.
  - A text search is added.
  - New viewer generation endpoints and Generate/Regenerate actions with job progress are added.
  - The "reads never change data" and logging rules now cover generation started from the viewer.
- `api-docs`: the documented operations go to twenty, the two viewer generation endpoints are documented, and the list's `jobs` field is documented.
- `local-service-hosting`: the smoke test expects twenty operations.

`generation-jobs` behaviour is unchanged. The viewer endpoints reuse its jobs, its records and its one-running-job rule.

## Impact

- `app/viewer.py`: page CSS, markup and script. Covers the sidebar cards, filter bar, search, detail action bar, generate buttons and polling.
- `app/main.py`: two viewer POST routes that reuse `start_generation`, `resume_work` and `cover_letter_work`, plus the `jobs` field on `GET /applications`.
- `app/applications.py`: `list_with_reports` joins `generation_jobs`.
- `app/models.py`: `JobSummary` and `ApplicationListItem.jobs`.
- Tests: `tests/test_viewer.py`, `tests/test_docs.py` and `tests/test_applications.py`. `scripts/smoke_test.sh` and `scripts/test_smoke_test.sh` expect twenty operations. README viewer section.
- Depends on `viewer-fill-form`, which is merged but not yet archived. Its requirements (the fill endpoint, the Fill form button, eighteen operations) are the baseline this change modifies.
- Out of scope:
  - Editing posting text from the viewer. A cover letter for an application without posting text still gets the endpoint's 422, shown on the page.
  - Cancelling a running job.
  - Any change to how resumes or letters are generated.
