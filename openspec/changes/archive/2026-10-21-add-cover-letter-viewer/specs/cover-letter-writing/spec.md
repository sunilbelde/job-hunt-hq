# Spec Delta

## MODIFIED Requirements

### Requirement: Base cover letter is owned by the owner
After drafting, the owner MAY edit `data/COVER_LETTER.md`. A script command SHALL re-render `data/COVER_LETTER.pdf` from it, with the TeX escaping and one-page check but without source checks. The service SHALL NOT regenerate or change the base letter, and tailored letters SHALL NOT use it as input. The service SHALL only read `data/COVER_LETTER.pdf` to serve it unchanged to the viewer.

#### Scenario: Owner edits the text
- **WHEN** the owner rewrites a paragraph of `data/COVER_LETTER.md` and runs the re-render command
- **THEN** `data/COVER_LETTER.pdf` shows the edited paragraph

#### Scenario: Base letter not used by the service
- **WHEN** `data/COVER_LETTER.md` or `data/COVER_LETTER.pdf` is missing or edited
- **THEN** `POST /cover-letter` behaves the same

#### Scenario: Base letter shown to the viewer only
- **WHEN** the viewer requests `GET /cover-letter/base.pdf` on a listener with API docs enabled
- **THEN** it receives `data/COVER_LETTER.pdf` unchanged, and no other endpoint serves the base letter
