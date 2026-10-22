# Proposal

## Why

Only some applications ask for a cover letter, so making one alongside every resume would waste Claude runs on letters nobody sends. `POST /resume` already returns a `cover_letter_path` placeholder that no code ever writes, which wrongly suggests the two come as a pair. The owner wants to ask for a cover letter only for the applications that need one: a letter tailored to the posting, built only from facts the resume and profile support. They also want one generic letter, written once, to keep for reference.

## What Changes

- **New `POST /cover-letter`** (`X-API-Key`): body `{"application_id": "<uuid>"}`. It writes a one-page cover letter tailored to the stored posting, saves it beside the resume at `<OUTPUT_DIR>/<company folder>/<id>/SUNIL BELDE - Cover Letter.pdf` (replacing any earlier one), and returns `201 {"ok": true, "application_id", "saved_path", "text"}`. `text` is the letter as plain paragraphs, so it can be pasted into application forms that have a text box instead of an upload. It always tailors and never falls back to a generic letter. An application with no usable posting text is a 422. Generation failures are 500, write failures 502, store failures 503, an unknown ID is 404, and a bad key is 401, as for resumes.
- **New `write-cover-letter` skill**: a Claude Code skill whose scripts check every rule that can be checked mechanically. Every paragraph cites the base-resume bullets and profile facts it draws on. Numbers must come from those sources. The letter may not name a posting keyword that neither the resume nor the profile contains, and may not echo the posting's phrasing. It must name the company and role as stored, and must fit on one page within a word range. The service runs the skill headlessly, with the same isolation, time limit and spend cap as resume tailoring, then re-checks the result with its own copy of the scripts before rendering.
- **Base cover letter, written once**: the owner runs the same skill in their own Claude Code session with no posting. It writes a generic letter with the same rules and saves `data/COVER_LETTER.md` (editable text) and `data/COVER_LETTER.pdf` for the owner to review and commit. The owner reads it directly, so no endpoint serves it, and the service never reads it. A script command re-renders the PDF after the owner edits the text.
- **BREAKING: `POST /resume` no longer returns `cover_letter_path`.** Its 201 body becomes `{"ok", "application_id", "saved_path", "match"}`. Resume generation still never creates, replaces or deletes a cover letter file. Clients that read `cover_letter_path` (Muse) must stop doing so.
- API docs, the README, the docs tests and the smoke test cover the new endpoint. The documented operation count goes from 10 to 11. The smoke test checks that `POST /cover-letter` answers 422 for its application without posting text, so it still never starts a Claude run.

## Capabilities

### New Capabilities
- `cover-letter-api`: the `POST /cover-letter` endpoint: auth, request body, response, error handling, logging, and leaving the application unchanged.
- `cover-letter-writing`: how a letter is written and checked: sources of facts, structure and length, the posting-phrasing and keyword rules, the service's isolated Claude run and final gate, and the base letter drafted once and owned by the owner.

### Modified Capabilities
- `job-api`: the `POST /resume` response drops `cover_letter_path`, and the request log no longer mentions it.
- `output-storage`: the cover letter path no longer derives from the resume path, and the "not yet written" rule is replaced. Only `POST /cover-letter` writes the file, atomically and privately. Resume generation leaves it alone.
- `api-docs`: 11 documented operations. `POST /cover-letter` has its body, responses, errors and API-key requirement documented.
- `local-service-hosting`: the smoke test expects 11 operations and checks the `POST /cover-letter` 422 without starting a Claude run.

## Impact

- **Code**: new `app/cover_letter.py` (headless run and gate). It reuses the run machinery in `app/tailoring.py`, which is generalized to take a skill name. `app/main.py` gets the new route, and `cover_letter_path` comes out of `/resume`. `app/models.py` gets `CoverLetterRequest`/`CoverLetterCreated`, and `ResumeCreated` loses a field. `app/storage.py` gets `save_cover_letter`, and `cover_letter_path` takes `(root, company, id)`. The stale TODO in `app/generation.py` is removed.
- **Skill**: new `.claude/skills/write-cover-letter/` (SKILL.md, reference rules, scripts that reuse `tailor-resume`'s resume model, text checks and TeX escaping).
- **Data**: new `data/COVER_LETTER.md` and `data/COVER_LETTER.pdf`, drafted once and committed by the owner.
- **Tests**: new API, storage, skill-script and gate tests. `tests/test_api.py`, `tests/test_storage.py` and `tests/test_docs.py` are updated for the removed field and the 11th operation. So is the smoke test and its test.
- **Clients**: Muse must drop `cover_letter_path` from `/resume` and call `POST /cover-letter` when an application asks for a letter. It should use a client timeout of at least 10 minutes.
- **Cost**: one Claude run per requested letter. No cost for applications that don't ask for one.
