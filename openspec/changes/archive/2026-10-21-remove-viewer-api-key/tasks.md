# Tasks

## 1. Viewer reads without a key

- [x] 1.1 In `app/main.py`, remove the `x_api_key: ... = Security(api_key_header)` parameter and the `api_key_valid` check from `list_applications`, `read_application`, `read_saved_resume` and `read_base_resume`. Drop `401` from their `errors(...)` lists, and drop the `api_key_valid` argument from `register_viewer`'s signature and its call. Verify with `.venv/bin/python -m pytest tests/test_viewer.py` after 1.3.
- [x] 1.2 Update the `register_viewer` docstring and the `/viewer` comment to say the reads need no key and that the docs-only registration (tailnet listener) is their only guard. Change the API `DESCRIPTION` line so it says the health checks and the viewer reads need no `X-API-Key`. Verify by reading the `/docs` description in a dev server or in the `create_app(...).openapi()` output.
- [x] 1.3 In `tests/test_viewer.py`, replace `test_reads_need_the_key` with a test that each of `READ_PATHS` gives no 401 with no key and with a wrong key (200 for `/applications`, 404 "Application not found" for the unknown ID, and so on). Have the list, detail and PDF tests send no key. Extend `test_not_served_without_docs` to send each path with no key too, and expect 404. Verify `.venv/bin/python -m pytest tests/test_viewer.py` passes.
- [x] 1.4 In `tests/test_docs.py`, change `RESPONSES` for the four viewer reads to `{"200","503"}`, `{"200","404","503"}`, `{"200","404","503"}` and `{"200","500"}`, and make the security-scheme test expect the key only on the three application writes and `POST /resume`. Verify `.venv/bin/python -m pytest tests/test_docs.py` passes and the operation count is still 10. `scripts/smoke_test.sh` keeps its count of 10.

## 2. Viewer page opens directly

- [x] 2.1 In `app/viewer.py`, remove the `#gate` key form and its CSS, the `apiKey` variable, `Unauthorized`, `lock()` and the 401 branch in `api()`. Fetch with no headers (keep `cache: "no-store"` and `credentials: "omit"`). Call `loadList()` on start, show a load failure with a retry button in the status/detail area, and drop the `apiKey !== null` guard from the `hashchange` handler. Verify on a dev server (`API_DOCS_ENABLED=true OUTPUT_DIR=/tmp/job-hunt-hq-dev .venv/bin/uvicorn app.main:create_app --factory --port 8080`) that `/viewer` lists applications with no prompt and still does after a reload.
- [x] 2.2 In `tests/test_viewer.py`, replace `test_page_sends_the_key_only_as_a_header` with a test that the page HTML contains no `X-API-Key`, no key input and no `localStorage`/`sessionStorage`/`document.cookie`. Keep the CSP, nonce and no-data tests. Verify `.venv/bin/python -m pytest` passes.

## 3. Documentation

- [x] 3.1 In `README.md`, rewrite the Resume viewer section's key sentence: the page opens directly with no key, and anyone on the tailnet can read it. Update the line about storage (around line 140) so files are served to the viewer on the tailnet-only listener without a key. Update the "API docs on the tailnet" note so it says the viewer needs no key and points to the `tcp:8444` policy rule. Update the access-control sentence in "Running on the Mac mini". Note in the dev-server section that the viewer reads have no key, so don't bind a docs-enabled dev server beyond loopback. Verify with `grep -n "viewer" README.md` that no line still tells the owner to enter the key in the viewer.

## 4. Integration check

- [x] 4.1 Run `.venv/bin/python -m pytest`, `sh scripts/test_smoke_test.sh` and `sh scripts/test_install_service.sh`, and verify all pass.
- [x] 4.2 After deploying to the Mac mini, run `scripts/smoke_test.sh` against the public URL (it checks that `/viewer` is 404 there). Then verify `curl -s -o /dev/null -w '%{http_code}' https://<machine>.<tailnet>.ts.net/applications` returns 404, and that `https://<machine>.<tailnet>.ts.net:8444/viewer` opens straight to the list on a tailnet device.
