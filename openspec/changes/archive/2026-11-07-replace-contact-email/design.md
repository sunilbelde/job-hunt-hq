# Design

## Context

- Nothing tracked in the repo contains the old address. It appears only in gitignored owner data in the main checkout
  (`/Users/belde/dev-workspace/claude Projects/job-hunt-hq/data/`): `BASE.tex` line 13, the profile Markdown's contact
  table (`| Email | … |`), and the rendered `BASE.pdf` and `COVER_LETTER.pdf`. This worktree's `data/` holds only
  `samples/` (Jane Doe), and that stays as it is.
- Tailored resumes are generated from `BASE.tex`. Cover letter headers come from `BASE.tex` too: `letter_tool.py` reads
  it in `prepare`, `verify`, `publish-base` and `render-base`. So editing `BASE.tex` is enough for all future documents.
- `app/storage.py` reads only `\name{...}` from `BASE.tex`, and only at startup. The email is not part of it, so the
  service does not need a restart.
- The form filler already reads contact details from the profile document (Step 1 table, Step 3 "Contact, name, links,
  location"), and it already reads the tailored resume and cover letter PDFs.
- The applications database has no copy of the address (checked: 0 rows in `applications`, `generation_jobs` and
  `resume_reports`).

## Goals / Non-Goals

**Goals:**
- Every document and form answer from now on carries the new address.
- The owner hears about it before submitting a form whose attached PDF still has the old address.

**Non-Goals:**
- Regenerating or rewriting the 302 existing PDFs under `OUTPUT_DIR` (the owner chose to leave them).
- Changing the Medium username.
- Changes to the service, API or viewer.

## Decisions

- **Edit the data files in place in the main checkout, outside git.** They are gitignored on purpose
  (`personal-data-local-only`), so the PR carries only the skill change, its test and these planning artifacts.
  *Alternative:* add a config value for the email and template it into `BASE.tex`. Rejected: this would add machinery
  for a value that changes about once, and the profile document is already the single source for form answers.
- **Re-render the base PDFs with the project's own tools.** Use `app.rendering.render_pdf(template_dir=data)` for
  `BASE.pdf`, and `.claude/skills/write-cover-letter/scripts/run render-base --data data` for `COVER_LETTER.pdf`. These
  are the same paths the service and README use, so the output matches what the service would produce.
- **The mismatch check is a report-only red flag, not a stop.** It goes into the existing Step 6 red flags list, which
  the owner already reviews before approving a submit. Blocking would stop the owner from submitting on purpose with an
  older PDF. *Alternative:* regenerate automatically from the skill. Rejected: the owner said to leave existing PDFs, and
  regeneration costs a model run.
- **Compare against the profile document at run time, with no address written into the skill.** This keeps personal
  data out of a tracked file, and it keeps working the next time the email changes.

## Risks / Trade-offs

- [Edits to gitignored files leave no history] → Before editing, copy the four files to the session scratchpad. After
  editing, grep the files for the old address (expect 0) and the new one (expect 2 in `BASE.tex`, 1 email row in the
  profile).
- [`BASE.tex` render fails (missing TeX or font)] → Check before replacing `BASE.pdf`. On failure, restore the backup
  and report. Tailoring renders the same file, so a failure here would also break tailoring.
- [The PDF email text is hard to read (for example, ligatures or a split link)] → The spec reports "could not check" in
  that case, rather than a false mismatch.
- [36 unapplied applications still have old-email PDFs] → The new red flag catches them when they are filled.
  Generating them again from the viewer fixes them one by one.
