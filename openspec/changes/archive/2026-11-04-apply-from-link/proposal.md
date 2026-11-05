# Proposal

## Why

The viewer's **Fill form** button only works for a posting that is already recorded and has a tailored resume. Going from a job link to a filled form is still a manual run of the same steps each time: check for a duplicate, find the official posting, apply the hard filters, record it, generate the documents. Today's runs also showed where that goes wrong: LinkedIn hides Apply links from the logged-out Claude Chrome window, and Tailored Attach can be missing on custom careers pages.

## What Changes

- New committed skill `apply-from-link`, started as `/apply-from-link <url>`. It checks whether the link is stored, reads the posting, resolves LinkedIn and aggregator links to the employer's official posting, applies the hard filters, records the application, generates the resume, generates a cover letter only when the form has a cover letter field, and hands off to `job-application-form-filler`. The form filler is reused unchanged, so its submit rules still apply.
- New viewer endpoint `POST /viewer/apply-from-link`, local listener only, with no API key. It opens a Herdr tab running that skill. The link is the first page-supplied value to reach a command, so it is validated strictly and shell-quoted.
- New link box in the viewer sidebar that calls this endpoint. The list keeps refreshing for a while afterwards, so the new application appears without a reload.
- New optional `POST /application` field `added_via` (`link` or `manual`, default `manual`), fixed once recorded. Existing rows read `manual`.
- `GET /application/{id}` and `GET /applications` return `added_via`, and each viewer list entry shows a **ByLink** or **Manual** tag.
- `GET /applications` gains an optional `job_link` filter, matched on the dedupe key, so the skill can check for a stored posting in one call. This adds no new operation.
- The API docs, docs tests, smoke test and README go from twenty to twenty-one operations in the same change.

## Capabilities

### New Capabilities
- `apply-from-link`: the workflow from a job link to the form filler: stored check, official posting resolution, hard filters, recording, document generation and handoff.

### Modified Capabilities
- `application-api`: `POST /application` accepts `added_via`, and `PATCH` refuses it.
- `application-store`: rows keep `added_via`, and existing stores gain it as `manual`.
- `resume-viewer`: new apply-from-link endpoint and link box, `added_via` and the `job_link` filter on `GET /applications`, and the list entry tag.
- `api-docs`: the new operation is documented, and the coverage count becomes twenty-one.

## Impact

- **Code:** `app/form_filler.py`, `app/main.py`, `app/models.py`, `app/applications.py`, `app/viewer.py`.
- **New file:** `.claude/skills/apply-from-link/SKILL.md`. It contains no personal data: the pay floor and other thresholds are read from the gitignored profile document.
- **API:** one new local-only operation and one optional field on the public `POST /application`, backward compatible for existing clients. The public listener's four endpoints do not change.
- **Data:** a one-column migration of the application store on startup.
- **Tests and docs:** `tests/test_docs.py`, `tests/test_api.py`, `tests/test_applications.py`, `tests/test_form_filler.py`, `tests/test_viewer.py`, a new skill doc test, `scripts/smoke_test.sh`, `scripts/test_smoke_test.sh` and `README.md`.
- **Dependencies:** the workflow needs Herdr, the local `job-application-form-filler` skill and Chrome on the Mac, all already required by Fill form. No new packages.
