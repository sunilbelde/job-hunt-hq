# Design

## Context

The absolute path enters the store in one place: `run_job` in `app/main.py` records `str(saved_path)` on the job, and generation saves the same path in the report (`ApplicationStore.save_report`). Two handlers then return the stored value without changing it:

- `job_status` (`app/main.py`) builds the status body with `"saved_path": job["saved_path"]`.
- `read_application` returns `{"ok": True, **found}`, and `found["report"]` comes straight from `get_report`, which includes `saved_path`.

`find()` returns that same report dict to `read_saved_resume` and `read_cover_letter`. Both need the absolute path: they open the report's path, or the folder it is in, so files saved under a company's old name are still found after a rename.

Every error body is a fixed message built by `application_error`. `store_unavailable` logs the exception and returns the fixed text "Application store unavailable". No error response repeats a path today.

`GET /applications` returns `list_with_reports` summaries. Those hold `generated_at`, status and scores, but no `saved_path`.

## Goals / Non-Goals

**Goals:**
- Reduce `saved_path` to its file name at the two places that build responses. Leave storage, the PDF readers and the job runner as they are.
- Add one test that sweeps every endpoint and fails if any path to `OUTPUT_DIR` or the home directory appears in a response. A future field that leaks a path would then be caught.

**Non-Goals:**
- Changing what the store holds, or migrating existing rows. Old job records and reports stay as they are and are trimmed when read.
- Checking the bytes inside PDFs. The sweep covers JSON and HTML bodies only.
- Changing log lines. They already leave out the saved path, as required by `generation-jobs` and `job-api`.
- Adding a `file_name` field.

## Decisions

**Trim to the file name in the response handlers, not in the store or the models.**
A small helper, for example `file_name(path: str | None) -> str | None`, returns `PurePath(path).name`, or `None` for `None`. `job_status` applies it to `job["saved_path"]`. `read_application` returns a copy of the report with `saved_path` replaced. The `found` dict that `find()` returns is not changed, so the PDF readers still get the absolute path.

Alternatives considered:
- Store only the name. This breaks the lookup after a company rename and needs a data migration. Rejected.
- Add a Pydantic `field_serializer` on the response models. The handlers return plain dicts and no `response_model` is set, so a serializer would never run. Making it run would change how every response is serialized. Rejected.
- Trim inside `get_report` and `get_job`. The PDF readers call `get_report` and need the full path. Rejected.

**Use `PurePosixPath`, not `os.path.basename`.**
Stored paths are POSIX paths on this Mac, so either works. Using `PurePath` matches how the rest of the file handles paths. An empty or odd legacy value gives `""`, or the value itself if it has no `/`. Neither leaks a directory.

**Keep the field name `saved_path`; add no `file_name`.**
Once the value is the name, a second field would hold the same string. Clients would have to choose between them, and `saved_path` could never be removed without breaking them. The cost is that the name `saved_path` now describes the value less well. The OpenAPI description fixes that: "File name of the saved PDF (no directory), or null unless `done`." Rejected alternative: add `file_name` and deprecate `saved_path`. That would add schema, tests and docs for no extra information.

**Smoke test builds the path from `OUTPUT_DIR`.**
The smoke test runs on the Mac and needs the file on disk, both to check it is a PDF and to clean it up. It will read `OUTPUT_DIR` from the environment, defaulting to `$HOME/Library/Application Support/job-hunt-hq` like `app/settings.py`. It then builds `$OUTPUT_DIR/Smoke Test Co/$application_id/$saved_path`. The company folder is fixed because the smoke test sets the company to "Smoke Test Co", which `storage` leaves unchanged. The test also fails if `saved_path` contains `/`.
Rejected alternative: fetch the PDF through `GET /application/{id}/resume.pdf` on the docs listener. That would not work with `DOCS_URL=off`, and cleanup needs the folder on disk anyway.

**Leak sweep test.**
Using the existing test fixtures (`settings` with `output_dir=tmp_path/"out"`, fake Claude, docs enabled), the test generates a resume and a tailored cover letter for one application. It then calls every JSON or HTML endpoint: `/health`, `/healthz`, application POST, PATCH and GET, `/applications`, both status endpoints, `/viewer` and `/openapi.json`. It also calls the error cases: wrong key (401), unknown ID (404), no job (404) and an unknown path. It asserts that `str(settings.output_dir)`, its resolved form, `str(tmp_path)` and `str(Path.home())` are absent from every body. The `tmp_path` and resolved forms catch `/private/var/...` versus `/var/...` on macOS. It skips PDF bodies (`application/pdf`). `DELETE` runs last.

## Risks / Trade-offs

- [A client opens `saved_path` as a file path] → No known client does. Muse and the Tailored Attach extension only read the value, and the extension already handles both forms. The README and proposal mark this as a breaking change for anyone who does.
- [A new response field leaks a path later] → The sweep test calls every endpoint, so it fails when such a field is added.
- [The home-directory check is too broad, for example if a test's `tmp_path` were under `$HOME`] → On macOS, pytest's `tmp_path` is under `/private/var/folders`, so this does not happen. If it ever did, the `OUTPUT_DIR` check would still apply. The home check could then be limited to `$HOME/` followed by the username segment.
- [The smoke test's `OUTPUT_DIR` differs from the service's custom `.env` value] → The failure message says to set `OUTPUT_DIR` to the service's value, and the README smoke section documents it.

## Migration Plan

No data migration. The change applies when the service is restarted on the new version. Rollback: deploy the previous version. The stored data is unchanged, so the old responses come back exactly as before.
