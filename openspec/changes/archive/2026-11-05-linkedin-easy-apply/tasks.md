# Tasks

## 1. API values and list field

- [x] 1.1 In `app/models.py`, add `linkedin_easy_apply` and `owner_confirmed` to the `Literal`s and a third branch to `_verified_pairing`, with messages naming fields only. Verify with new parametrized cases in `tests/test_api.py` covering the accepted pair, a non-empty `official_apply_url`, `official_apply_match` on the new source, and `owner_confirmed` on each older source; "linkedin" stays a 422.
- [x] 1.2 Add `posting_source_type` to `LIST_COLUMNS` in `app/applications.py` and to `ApplicationListItem`. Verify by updating the key set in `tests/test_applications.py:605` and adding a store test that an Easy Apply row round-trips and lists its source type.
- [x] 1.3 Verify `PATCH` still refuses both fields for an Easy Apply row, with a test in `tests/test_api.py`.
- [x] 1.4 Update the `POST /application` description and the `GET /applications` description in `app/main.py`. Update the enums in `tests/test_docs.py:180-181` and add a test for the pairing text and the list entry field. Verify `python -m pytest tests/test_docs.py` passes and the operation count in `scripts/smoke_test.sh` stays 21, with no edit needed.
- [x] 1.5 Update `README.md` lines 37, 38 and the pairing list at line 45 with the new values. Verify by reading them against `app/models.py`.

## 2. Viewer

- [x] 2.1 In `app/viewer.py`, add the Easy Apply pill and its style beside the origin tag in `entry()`, shown only for `linkedin_easy_apply`. Verify with an assertion in `tests/test_viewer.py` next to the existing ByLink check at line 1209.
- [x] 2.2 Hide the Fill form button in the action bar for these applications with the `.hidden` class. Verify with a `tests/test_viewer.py` assertion and the `run` skill: an Easy Apply row in a local store shows the tag, no Fill form, and working status and generate controls.

## 3. Skill

- [x] 3.1 In `.claude/skills/apply-from-link/SKILL.md`, reduce LinkedIn links to `https://www.linkedin.com/jobs/view/<job id>/` at the start of Step 1, and update the frontmatter description. Verify with a test in `tests/test_apply_from_link_skill.py` for the form and for `currentJobId`.
- [x] 3.2 In Step 3, add **It's LinkedIn Easy Apply** to the question for LinkedIn links only, and say the owner's answer is the only signal. Verify by extending `test_resolving_does_not_depend_on_linkedin_sign_in`.
- [x] 3.3 In Step 4, state the exception to the profile's official careers page filter, naming that it overrides "outranks this list", and that every other filter still runs on the LinkedIn posting, after expanding its full text. Verify with a test.
- [x] 3.4 In Step 5, add the Easy Apply row to the verification table. Verify by extending `test_recording_marks_the_origin_and_both_source_types`.
- [x] 3.5 In Step 2, read `posting_source_type` along with `status`. In Step 6, skip the cover letter check for `linkedin_easy_apply`. In Step 7, add the Easy Apply report items: the resume file and folder, and that no letter was generated. Verify with a test.
- [x] 3.6 Make Step 8 send `linkedin_easy_apply` to a new Step 9 that holds the Submitted question, the No answer, and the wrap-up order: mark applied, close this run's Chrome tab, final report, close the Herdr tab if its label ends with the ID. Verify by changing `test_steps_run_in_order` to nine steps and adding a test for the options and order. Keep `test_handoff_passes_only_the_id` and the personal data test passing.
- [x] 3.7 Update the Apply from a link section of `README.md` with the Easy Apply path. Verify by reading it against the skill.

## 4. Integration

- [x] 4.1 Run `python -m pytest` and `openspec validate linkedin-easy-apply --strict`. Both pass.
- [x] 4.2 Run the service locally against a throwaway store and record an Easy Apply body: confirm 201, the row in `GET /applications`, and the 422s from 1.1 over HTTP. Run `scripts/test_smoke_test.sh`.

## Workflow follow-up

- With the owner's go-ahead after deploy, correct the row that was recorded with the workaround: back up the store, then set `posting_source_type` `linkedin_easy_apply`, `verification_method` `owner_confirmed` and `official_apply_url` `''` for that one ID directly in SQLite, since the API refuses it. The owner has the ID; it stays out of the repo.
- Try one real Easy Apply posting from the viewer's link box, then archive the change.
