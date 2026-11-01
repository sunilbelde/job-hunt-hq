# Proposal

## Why

Filling an application form means opening a terminal, starting `claude --chrome` and typing `/job-application-form-filler <application id>` by hand, after copying the ID out of the viewer. The viewer already lists every application with its ID, so it can start that session itself.

## What Changes

- Each entry in the viewer's application list gets a **Fill form** button.
- New `POST /viewer/application/{application_id}/fill`, served only where the viewer is and with the same no-key, same-origin rules as the other viewer writes. It opens a tab in the Herdr workspace `Claude-Jobs-Automation` (created if missing), labelled `<Company>-<Role>-<application id>`, with the repo as its directory, and runs `claude --chrome "/job-application-form-filler <id>"` there.
- The session is an ordinary interactive Claude Code session: the owner approves its permissions and answers its questions in that tab. The button never asks it to submit.
- A second click while a tab for that application is open in the workspace opens nothing and says so (`already_open`).
- New settings `HERDR_BIN` (default `herdr`) and `FILL_WORKSPACE` (default `Claude-Jobs-Automation`). The install script puts the Herdr path it finds in the launchd job, as it does for `CLAUDE_BIN`.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `resume-viewer`: a fill endpoint and a Fill form button on every list entry; the cross-site and docs-only rules cover the new write.
- `api-docs`: the documented operations go from seventeen to eighteen, and the fill endpoint is documented.
- `local-service-hosting`: the launchd job carries `HERDR_BIN`.

## Impact

- New `app/form_filler.py` (the Herdr calls); `app/main.py` (endpoint, `create_app(form_filler=...)`), `app/models.py` (`FillFormStarted`), `app/settings.py`, `app/viewer.py` (button).
- Tests: new `tests/test_form_filler.py`; `tests/test_viewer.py`, `tests/test_docs.py`; `tests/conftest.py` stops every test from reaching the real Herdr.
- `scripts/smoke_test.sh` expects eighteen operations; `scripts/install_service.sh` and the plist template pass `HERDR_BIN`; README and `.env.example`.
- Out of scope: running the session headless, and starting it from a device other than the Mac mini (the session drives the mini's Chrome).
