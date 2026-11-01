# Tasks

## 1. Launcher

- [x] 1.1 Add `app/form_filler.py`: find or create the `FILL_WORKSPACE` workspace, reuse a tab whose label ends with the ID, otherwise `tab create --label <Company>-<Role>-<id> --cwd <repo> --no-focus`, then `pane run` the fixed `claude --chrome` command. Verify with `tests/test_form_filler.py`.
- [x] 1.2 Add `HERDR_BIN` and `FILL_WORKSPACE` settings.

## 2. Endpoint and button

- [x] 2.1 Add `POST /viewer/application/{application_id}/fill` in `register_viewer` (403 cross-site, 404 unknown, 503 store or Herdr) and `FillFormStarted`. Verify with `tests/test_viewer.py`.
- [x] 2.2 Add the **Fill form** button to each list entry with an inline note for the result. Verify the page tests.
- [x] 2.3 Keep tests off the real Herdr with an autouse fixture in `tests/conftest.py`.

## 3. Docs and deploy

- [x] 3.1 Update `tests/test_docs.py` to eighteen operations and check the fill endpoint's description and statuses.
- [x] 3.2 Update `scripts/smoke_test.sh` and `scripts/test_smoke_test.sh` to eighteen operations.
- [x] 3.3 Pass `HERDR_BIN` through `scripts/install_service.sh` and the plist template; cover it in `scripts/test_install_service.sh`.
- [x] 3.4 Update README (viewer section, settings table, smoke test) and `.env.example`.
- [x] 3.5 Reinstall the service and click **Fill form** on one application at the Mac mini.
