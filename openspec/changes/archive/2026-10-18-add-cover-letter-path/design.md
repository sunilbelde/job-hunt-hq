# Design

## Context

`POST /resume` (`app/main.py` `create_resume`) calls `storage.save_resume(company, application_id, content)`. That returns the absolute path of the resume it wrote, and the handler sends it back as `saved_path`. The folder rules (`company_folder`, the `<company>/<application_id>/` layout and the `RESUME_FILE_NAME` constant) all live in `app/storage.py`. Nothing generates a cover letter today: `app/generation.py` only renders the baseline resume.

## Goals / Non-Goals

**Goals:**
- Return the cover letter path, built by the same folder rules as the resume, with no new I/O.
- Leave one obvious place for the later cover letter generation to plug in.

**Non-Goals:**
- Any cover letter content, rendering or file write.
- Telling clients whether the cover letter file exists yet. Clients that need to know can check the path.

## Decisions

**Derive the path from the saved resume path.** The cover letter path is `resume_path.parent / COVER_LETTER_FILE_NAME`, with `COVER_LETTER_FILE_NAME = "SUNIL BELDE - Cover Letter.pdf"` defined in `app/storage.py` next to `RESUME_FILE_NAME`. A small helper there, `cover_letter_path(resume_path)`, returns it, and the handler calls it after `save_resume` succeeds.
- *Alternative:* add a `cover_letter_path(company, application_id)` method to the `Storage` protocol. That would repeat the folder rules and the escape check, and every storage (including `FakeStorage` in tests) would have to implement it. Deriving from the returned path guarantees "same folder as the resume" by construction.

**Placeholder: return the computed path, write nothing.** The response always includes `cover_letter_path`, even though no file exists there yet. A `TODO` comment in `create_resume`, where the cover letter would be generated and saved, marks the future work. A one-line `TODO` next to `generate_output` points at the same place.
- *Alternative:* return `null` until it is implemented. That would change the field's type later, and the user chose the stable path.
- *Alternative:* write a stub PDF. That creates files that would have to be cleaned up or overwritten later, and the user chose not to.

**Keep `saved_path`.** The change only adds a field, so Muse and `scripts/smoke_test.sh` are unaffected. `ResumeCreated` gains `cover_letter_path: str`, so `/openapi.json` documents it automatically.

## Risks / Trade-offs

- [A client may treat `cover_letter_path` as a file that exists] → The README and the OpenAPI field description say that no cover letter is generated yet.
- [Response key-set checks break] → Only `tests/test_api.py` asserts the exact key set. It is updated in this change.
