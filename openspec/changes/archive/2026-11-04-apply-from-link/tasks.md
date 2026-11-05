# Tasks

## 1. Application origin

- [x] 1.1 Add `added_via` to the store in `app/applications.py`: schema, `COPIED_COLUMNS`, `LIST_COLUMNS`, an explicit write in `record`, and an idempotent migration that runs before the integer ID rebuild. Verify with `tests/test_applications.py` cases for a new row, a store from before the field, a store with integer IDs, and a second startup.
- [x] 1.2 Add `added_via` to `ApplicationRow`, `IMMUTABLE_FIELDS`, `StoredApplication` and `ApplicationListItem` in `app/models.py`. Verify with `tests/test_api.py` cases for the default, `link`, unknown value, wrong case, wrong type, a duplicate keeping its origin, and `PATCH` answering 422.
- [x] 1.3 Document `added_via` in the OpenAPI schemas and the README's application fields. Verify with `tests/test_docs.py` assertions for the `POST` body, the list and detail schemas, and its absence from both `PATCH` bodies.

## 2. Stored link lookup

- [x] 2.1 Add a store lookup by `dedupe_key` and the optional `job_link` query parameter on `GET /applications`, returning the list shape. Verify with `tests/test_viewer.py` cases for a match, no match, a tracking-decorated link, and no parameter returning every row.
- [x] 2.2 Document the parameter in the operation description and the README. Verify with a `tests/test_docs.py` assertion and a log test showing the link is absent from the structured line.

## 3. Herdr launcher

- [x] 3.1 Extract the shared tab-opening path in `app/form_filler.py` and keep `start` behaving the same. Verify that the existing `tests/test_form_filler.py` tests pass unchanged.
- [x] 3.2 Add `start_link`, the `ByLink-<host>-<hash>` label, the quoted command and the hash-based open-tab match, and update the module docstring. Verify with `tests/test_form_filler.py` cases for the label, a decorated link finding the open tab, a missing workspace, and shell syntax staying inside one argument (checked with `shlex.split`).

## 4. Viewer endpoint

- [x] 4.1 Add a link validator and `POST /viewer/apply-from-link` in `app/main.py`, with request and response models and `BODY_MODELS` updated. Verify with `tests/test_viewer.py` cases for a started tab, `already_open`, each rejected link form with Herdr not called and no value echoed, a body that is not a JSON object, 503, 403 before the body is read, and 404 with docs disabled.
- [x] 4.2 Add the path to `request_event` so it logs as `application_request`. Verify with a log test that one line is written, with the status and without the link.
- [x] 4.3 Keep the public listener closed and prove it. Verify with the operation appearing in the `tests/test_serve.py` blocked list, and add it to the probes in `scripts/smoke_test.sh`.
- [x] 4.4 Update the API docs for the new operation: tag text, description, `RESPONSES`, `VIEWER_WRITES` and the twenty-one count in `tests/test_docs.py`. Verify with `pytest tests/test_docs.py`.
- [x] 4.5 Update `scripts/smoke_test.sh` to 21 operations and `scripts/test_smoke_test.sh` with a `twentyone` stub and a "twenty operations fail" case. Verify with `bash scripts/test_smoke_test.sh`.
- [x] 4.6 Update the README's viewer section and endpoint counts ("five more" writes becomes six). Verify with `grep -n 'apply-from-link' README.md` and a review of the changed paragraphs.

## 5. Viewer page

- [x] 5.1 Add the ByLink and Manual tag to list entries in `app/viewer.py`, with pill styling. Verify with a `tests/test_viewer.py` page assertion and the entry scenario in the spec.
- [x] 5.2 Add the link field, Apply from link button and status line above the list, with empty input sending nothing and the text kept on failure. Verify with `tests/test_viewer.py` page assertions, and check that the page's CSP and same-origin tests still pass.
- [x] 5.3 Add `linkWatchUntil` to the polling, for 15 minutes after a successful start. Verify with a `tests/test_viewer.py` assertion on the script and the manual check in 7.3.
- [x] 5.4 Describe the link box and tags in the README's viewer section. Verify by reading the section against the page.

## 6. Skill

- [x] 6.1 Write `.claude/skills/apply-from-link/SKILL.md` covering each step of the `apply-from-link` spec in order, with `disable-model-invocation: true` and `AskUserQuestion` for every question. Keep the API key out of output, as the form filler does. Verify by checking each spec requirement against the file.
- [x] 6.2 Add `tests/test_apply_from_link_skill.py`, following `tests/test_skill_doc.py`. It checks the frontmatter, length under 500 lines, the untrusted data rule, the endpoints and `added_via`, the `/job-application-form-filler` handoff with no submit instruction, and that the file contains no pay figure and no owner name. Verify with `pytest tests/test_apply_from_link_skill.py`.
- [x] 6.3 Note in the README that the workflow needs the local form filler skill, and how `/apply-from-link <url>` can be run without the viewer. Verify by reading the section.

## 7. Integration

- [x] 7.1 Run `pytest` and `bash scripts/test_smoke_test.sh`, and verify both pass.
- [x] 7.2 Run `openspec validate apply-from-link --strict` and verify it passes.
- [ ] 7.3 On the running service, with the owner, paste a LinkedIn link in the viewer. Verify the tab opens, the posting resolves, the row appears tagged ByLink without a reload, the tab is renamed with the ID, and the form filler starts. Stop before submitting.
- [ ] 7.4 With the owner, run a link that fails a filter and a custom careers page link. Verify that the first records nothing and reports why, and that the second reports the files to attach by hand when Tailored Attach is unavailable.

## Workflow follow-up

- Open a PR to `main` from `apply-from-link`, then restart the service after merging and run `scripts/smoke_test.sh`.
- Archive the change after the PR is merged.
