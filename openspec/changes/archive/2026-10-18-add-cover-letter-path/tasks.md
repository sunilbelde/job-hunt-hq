# Tasks

## 1. Cover letter location

- [x] 1.1 Add `COVER_LETTER_FILE_NAME = "SUNIL BELDE - Cover Letter.pdf"` and a `cover_letter_path(resume_path)` helper to `app/storage.py`, returning the path in the resume's folder. Verify with a unit test in `tests/test_storage.py` that the helper returns `<folder>/SUNIL BELDE - Cover Letter.pdf` for a resume saved by `LocalStorage` (including a company that needs folder sanitising) and creates no file.

## 2. Resume endpoint response

- [x] 2.1 Add `cover_letter_path: str` to `ResumeCreated` in `app/models.py`, with a field description saying the cover letter is not generated yet. Verify that `/openapi.json` lists `cover_letter_path` in the `POST /resume` 201 schema (`tests/test_docs.py`).
- [x] 2.2 In `create_resume` (`app/main.py`), add `cover_letter_path` to the 201 body, computed from the saved resume path. Add a `# TODO:` comment where cover letter generation and saving will go, and update the endpoint description to mention the new field. Verify that `pytest tests/test_api.py` passes after 2.3.
- [x] 2.3 Update `tests/test_api.py`: the exact key set now includes `cover_letter_path`. Assert it equals `<OUTPUT_DIR>/Acme Corp/<id>/SUNIL BELDE - Cover Letter.pdf`, shares its parent with `saved_path`, is the same on repeated requests, has no file at it after a resume is generated, and leaves a pre-existing file there untouched. Also assert the `resume_request` log line does not contain the cover letter path. Verify with `pytest`.
- [x] 2.4 Add a one-line `TODO` to `generate_output` in `app/generation.py` that points to the cover letter work. Verify that `pytest tests/test_generation.py` still passes.
- [x] 2.5 Update the README `POST /resume` row and its example response to show `cover_letter_path`, and note that it is a placeholder with no file yet. Verify that the example matches a real response from the test client.

## 3. Integration check

- [x] 3.1 Run the full suite (`pytest` and `scripts/test_smoke_test.sh`), and verify that everything passes and that the smoke test still checks only `saved_path`.
