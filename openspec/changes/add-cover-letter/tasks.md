# Tasks

## 1. Decouple the cover letter from `POST /resume`

- [x] 1.1 Remove `cover_letter_path` from the `/resume` handler, `ResumeCreated` (`app/models.py`), the route description, and the TODOs in `app/main.py` and `app/generation.py`. Verify that `tests/test_api.py` asserts the 201 keys are exactly `ok, application_id, saved_path, match` and that no cover letter file appears in the resume folder. Replace `test_resume_cover_letter_path_is_a_placeholder` with a test that a pre-existing cover letter file is left byte-for-byte unchanged by `/resume`.
- [x] 1.2 Update `tests/test_docs.py`: the `/resume` 201 schema properties must be exactly `ok, application_id, saved_path, match`, and the `"not generated yet"` assertion is dropped. Update the README's `/resume` row and curl example the same way, with a BREAKING note for Muse. Verify with `pytest tests/test_docs.py tests/test_api.py`.

## 2. Storage

- [x] 2.1 In `app/storage.py`, factor the atomic write into `LocalStorage._write(path, content)`, change `cover_letter_path` to `(root, company, application_id)`, and add `save_cover_letter` to `LocalStorage` and the `Storage` protocol. Verify with `tests/test_storage.py`: the path and company-folder naming, 0600/0700 modes, atomic replace, no temp file left after a failed write, a letter written with no resume present, and each write leaving the other's file unchanged.

## 3. The `write-cover-letter` skill scripts

- [x] 3.1 Create `.claude/skills/write-cover-letter/scripts/` with a `run` launcher (`TAILOR_PYTHON` or the repo `.venv`; `letter_tool.py` adds `tailor-resume/scripts` to `sys.path`) and `letter_tool.py prepare`, which makes a work folder: a template copy, `out/base.json` from `resume_model`, and `posting.md` when given. Verify with a launcher test like `tests/test_skill_launcher.py`, and check that `prepare` with and without `--posting` yields the expected files.
- [x] 3.2 Implement `letter_tool.py analyze`, which validates `out/analysis.json` with `resume_score`'s analysis validation and is tailored mode only. Verify that a malformed analysis gives `fix` lines and a good one passes.
- [x] 3.3 Implement `letter_checks.py`: structure and roles, `missing_source`/`unknown_source`, `unsupported_number`, `word_count` (250–400), `invalid_text` (control characters, line breaks, over 1,200 characters), and in tailored mode `missing_company`/`missing_role`, `unsupported_keyword`, `requirements_not_addressed` and a hard `echoed_phrase` that exempts the company and role. Verify each code with a failing and a passing case in a new `tests/test_letter_checks.py`, including the spec's examples (65% vs 60%, Kafka vs Playwright, the role title echo).
- [x] 3.4 Implement rendering and `run build`. Render `out/letter.tex` from `out/letter.json` on `resume.cls`, with the `BASE.tex` header, date, greeting, escaped paragraphs and sign-off. Compile with `compile_tex`, check `one_page`, and write the plain `text`. Print `fix`/`aim` lines and `out/check.json`. Verify in `tests/test_letter_render.py` that the PDF is one page, that `\input{...}` renders literally, that the greeting matches each mode, and that the text and the PDF's extracted text agree.
- [x] 3.5 Implement `letter_tool.py verify`, the service's gate: re-check against the given template, profile and analysis snapshot, then write `--pdf-out` and `--text-out` and print one JSON verdict. Verify with a test where the work folder's own scripts were changed to pass everything and the gate still rejects an unsupported number.
- [x] 3.6 Implement `publish-base` (base mode only, after a passing build, writes `data/COVER_LETTER.md` and `.pdf`) and `render-base` (re-renders the PDF from an edited `.md` with escaping and the one-page check only). Verify with tests on a temporary data directory: an invented number writes neither file, and an edited paragraph shows up in the re-rendered PDF's text.

## 4. The skill document

- [x] 4.1 Write `.claude/skills/write-cover-letter/SKILL.md` and `reference/rules.md`: inputs, untrusted posting, both modes, sources of facts, the owner's voice (no echo, no filler such as "I am excited to apply", at most one sentence about the company), steps (analyze, write `out/letter.json`, build at most 5 times), and the reply format. It links `tailor-resume/reference/scoring.md` for the analysis format. Verify with a `tests/test_skill_doc.py`-style test that the commands it names exist in `letter_tool.py` and that it follows a fixture run through to a passing build.

## 5. The service run and gate

- [x] 5.1 Generalize `app/tailoring.py`: make `claude_command` take a skill name and turn limit, and make work-folder preparation copy a list of skill folders. Existing resume behavior stays unchanged. Verify that `tests/test_tailoring.py` passes unchanged except for call sites.
- [x] 5.2 Add `app/cover_letter.py` with `run(application, settings) -> LetterResult(pdf, text, run)`. It prepares the work folder with both skills and `posting.md`, runs `/write-cover-letter .` (30 turns, shared time limit and budget), snapshots the analysis, runs the repo's `letter_tool.py verify`, and always removes its folders. Verify with `tests/test_cover_letter.py` using `tests/fake_claude.py`: success, Claude not configured, timeout (process tree stopped), budget, a gate rejection with failed checks in `TailoringError.log_fields()`, the folders removed in every case, and no `API_KEY` in the run's environment.

## 6. `POST /cover-letter`

- [x] 6.1 Add `CoverLetterRequest` and `CoverLetterCreated` to `app/models.py`, with examples. Add the route in `app/main.py` in this order: key check, body/ID validation (as for `/resume`), store lookup, the posting check (422 with an "add full_job_description" message, for missing, short or over-limit text), `run_in_threadpool(cover_letter.run)`, `save_cover_letter`, then 201 `{ok, application_id, saved_path, text}`. Error mapping: 500 "Cover letter generation failed", 502 and 503. Verify in `tests/test_api.py` with fake Claude: every status in the spec, the 401-before-404 order, the application and its status unchanged, the resume file and report unchanged, and a repeated request replacing the file.
- [x] 6.2 Add the `cover_letter_request` log line (status, duration, `application_id`, turns, cost) through the existing request-logging middleware. Verify that the log tests assert that no company, path, posting text or letter text appears, and that a rejected request is still logged once.
- [x] 6.3 Document the route: its tag, summary, a description covering always-tailored, posting text required, beside the resume, `text` returned and the 10-minute timeout, plus its responses (201, 401, 404, 422, 500, 502, 503), body schema and the `X-API-Key` security. Update `tests/test_docs.py` (`RESPONSES`, `PROTECTED`, the eleven-operation count, the body and response-shape assertions). Add a README row, a request-body note, a curl example and a "How cover letters are written" section. Verify with `pytest tests/test_docs.py` and by loading `/openapi.json` locally with docs enabled.

## 7. Smoke test

- [x] 7.1 In `scripts/smoke_test.sh`, expect 11 operations, and after the resume step, `POST /cover-letter` for the smoke application, asserting 422 and no cover letter file in its folder. Update `scripts/test_smoke_test.sh` to match. Verify with `sh scripts/test_smoke_test.sh`.

## 8. Base cover letter and integration

- [ ] 8.1 Draft the base letter: in an interactive session, run `letter_tool.py prepare` without a posting, then `/write-cover-letter <folder>`, then `run publish-base`. The owner reviews and edits `data/COVER_LETTER.md`, then runs `run render-base`. Verify that `data/COVER_LETTER.md` and a one-page `data/COVER_LETTER.pdf` exist and match, and that the owner has approved the text before commit.
- [ ] 8.2 Run one live end-to-end request against a local service with a real stored posting. Verify a 201, a one-page PDF beside the resume path, `text` equal to the PDF's text, and a `cover_letter_request` log line with turns and cost and no text. Run the full `pytest` suite and confirm it passes.

## Workflow follow-up

- Reinstall the service and update Muse: drop `cover_letter_path` from `/resume`, and add a `POST /cover-letter` action with a timeout of at least 10 minutes.
- Archive the change and sync its specs after review.
