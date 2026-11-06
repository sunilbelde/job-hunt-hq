# Proposal

## Why

Some LinkedIn postings have no employer or applicant tracking system posting at all: the only way in is LinkedIn Easy Apply, which the owner completes on LinkedIn. The apply-from-link workflow has no path for these. A real run had to override the "official careers page only" filter by hand and record the row as `recruiting_platform`/`official_apply_match`, which claims a verification that never happened and leaves the row looking like any other.

## What Changes

- The workflow's "official link not found" question gains an **It's LinkedIn Easy Apply** option, offered only for LinkedIn links. This is how Easy Apply is detected: the Chrome window is logged out of LinkedIn, so the owner's answer is the only signal. The search for an official posting still runs first.
- Easy Apply is an accepted exception to the profile's "official careers page only" filter. Every other hard filter still applies, and they run on the LinkedIn posting.
- LinkedIn job links are reduced to `https://www.linkedin.com/jobs/view/<job id>/` before the stored check, so one posting has one row however its link was copied.
- New `posting_source_type` value `linkedin_easy_apply`, paired only with a new `verification_method` value `owner_confirmed` and an empty `official_apply_url`. Both fields stay fixed once recorded.
- For an Easy Apply application, new or stored, the workflow stops after the resume: no cover letter check and no form filler handoff. It names the resume file, asks the owner the Submitted question through AskUserQuestion, and on Yes marks the application applied, then closes its Chrome tab and its Herdr tab as the form filler does. On No it changes nothing.
- `GET /applications` entries carry `posting_source_type`. The viewer shows an **Easy Apply** tag on those entries and offers no **Fill form** button for them.
- API docs, docs tests and README updated in the same change. No operation is added, so the smoke test's count stays at twenty-one.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `apply-from-link`: the unresolved-posting question, the filter exception, recording, the LinkedIn link form, and the Easy Apply ending in place of the handoff.
- `application-api`: the new source type and method values and their pairing rule.
- `resume-viewer`: `posting_source_type` in the application list, the Easy Apply tag, and no Fill form for those applications.
- `api-docs`: the new values and the list field are documented.

## Impact

- **Skill:** `.claude/skills/apply-from-link/SKILL.md`. `job-application-form-filler` is unchanged.
- **Code:** `app/models.py`, `app/applications.py` (list columns), `app/main.py` (docs text), `app/viewer.py`.
- **API:** additive. `POST /application` is on the public listener, so the new values are accepted there, behind the same API key. Existing bodies and rows are unaffected.
- **Data:** no migration. Both fields are plain text columns. The row recorded with the workaround keeps its values until corrected by hand, because the API refuses to change them (see tasks.md).
- **Tests and docs:** `tests/test_models.py`, `tests/test_api.py`, `tests/test_applications.py`, `tests/test_docs.py`, `tests/test_viewer.py`, `tests/test_apply_from_link_skill.py`, `README.md`.
- **Dependencies:** none.
