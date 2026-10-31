# Tasks

## 1. Status endpoints return the file name

- [x] 1.1 Add a `file_name(path)` helper in `app/main.py`: `PurePath(path).name`, or `None` for `None`. Use it for `saved_path` in the `job_status` response body, and leave `run_job` and `finish_job` storing the absolute path. Verify with `.venv/bin/pytest tests/test_api.py -k status`.
- [x] 1.2 Change the `JobState.saved_path` description in `app/models.py` to say it is the saved PDF's file name only, with no directory, and null unless `done`. Verify that the `saved_path` description in `/openapi.json` for both status responses contains no `/` and no "absolute path".
- [x] 1.3 Update the `tests/test_api.py` assertions that compare `job["saved_path"]` with an absolute path (around lines 551, 560, 607–609, 678, 862, 930, 964, 982, 1073, 1119, 1137–1148 and 1225). Expect `RESUME_FILE_NAME` or `COVER_LETTER_FILE_NAME`, and get the file on disk from `resume_path` or `cover_letter_path` for the company the application had when it was generated. Verify that the whole `tests/test_api.py` passes.
- [x] 1.4 Add tests: the resume and cover letter status endpoints return exactly `SUNIL BELDE.pdf` and `SUNIL BELDE - Cover Letter.pdf` when `done`, and `null` while `running` and after `failed`; after a status read, the stored job record still holds the absolute path. Verify that the new tests pass.

## 2. Application detail returns the file name

- [x] 2.1 In `read_application`, return a copy of the report with `saved_path` set to `file_name(...)`. Leave the `found` dict that `find()` returns unchanged, so `read_saved_resume` and `read_cover_letter` still use the stored absolute path. Verify that `GET /application/{id}` gives `report.saved_path == "SUNIL BELDE.pdf"`.
- [x] 2.2 Change the `ResumeReport.saved_path` description in `app/models.py` to "the saved resume's file name only". Update the `tests/test_viewer.py` assertions around lines 150–160 so `report.saved_path` is the file name. Verify that `tests/test_viewer.py` passes, including `test_renamed_company_still_served_from_the_saved_path` and `test_letter_written_before_a_rename_found_beside_the_resume`, unchanged apart from the field's value.
- [x] 2.3 Add a test: after a company rename, `GET /application/{id}` still reports `saved_path` `SUNIL BELDE.pdf`, and both PDF endpoints return the files from the old folder. Verify that it passes.

## 3. API docs

- [x] 3.1 In `tests/test_docs.py`, check that the `saved_path` descriptions of `JobState` and `ResumeReport` say "file name" and contain no `/` or "absolute path". Verify with `.venv/bin/pytest tests/test_docs.py`. The operation count stays at fifteen, and the smoke test's count is unchanged.
- [x] 3.2 Update the `job_status` and `POST /resume` / `POST /cover-letter` description strings in `app/main.py` that mention where the file "is saved on the service host at the job's `saved_path`". They should say the file name is returned in `saved_path`. Verify with a grep that no OpenAPI description says the path is absolute.

## 4. No path in any response

- [x] 4.1 Add the leak sweep test from design.md, for example `tests/test_api.py::test_no_response_contains_a_host_path`. Generate a resume and a tailored cover letter. Call every JSON and HTML endpoint, plus 401, 404 (unknown ID, no job, unknown path) and 422 cases, on the docs-enabled app. Assert that no body contains `str(settings.output_dir)`, its resolved form, `str(tmp_path)` or `str(Path.home())`. Skip `application/pdf` bodies. Verify that it passes, and that it fails if task 1.1's trim is temporarily reverted.

## 5. Smoke test

- [x] 5.1 In `scripts/smoke_test.sh`, read `OUTPUT_DIR`, defaulting to `$HOME/Library/Application Support/job-hunt-hq`. Fail if `saved_path` contains `/` or is not `SUNIL BELDE.pdf`. Build `saved="$OUTPUT_DIR/Smoke Test Co/$application_id/$name"`, and keep the PDF check, the cover letter check and the cleanup on that path. Say in the failure message that `OUTPUT_DIR` must match the service's. Update the usage text and the header comment.
- [x] 5.2 In `scripts/test_smoke_test.sh`, make the stub return the bare file name, and pass `OUTPUT_DIR="$tmp/out"`. Add cases for a returned path containing `/` (fails) and a missing file under `OUTPUT_DIR` (fails and still deletes the application). Verify with `sh scripts/test_smoke_test.sh`.

## 6. README

- [x] 6.1 Update `README.md`: the `GET /resume/{application_id}/status` table row (line 11; `saved_path` is the resume's file name), any cover letter status row, the curl examples (around lines 223 and 231: `"saved_path":"SUNIL BELDE.pdf"` and `"saved_path":"SUNIL BELDE - Cover Letter.pdf"`), and the smoke test section (around lines 378–384: `OUTPUT_DIR` must match the service's). Verify with `grep -n 'saved_path' README.md` that no example shows a directory.

## 7. Integration check

- [x] 7.1 Run `.venv/bin/pytest` and `sh scripts/test_smoke_test.sh`, and confirm both pass. Then run `grep -rn saved_path app/ tests/ README.md scripts/` and confirm that every remaining absolute-path use is internal: the store, `run_job`, the PDF readers, or store-level tests.

## Workflow follow-up

- Sync the delta specs and archive the change once it is reviewed (`/opsx:archive`).
- Open a PR from `hide-saved-paths` to `main`. Do not push to `main`.
