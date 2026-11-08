# Tasks

Paths under `data/` mean the main checkout's `/Users/belde/dev-workspace/claude Projects/job-hunt-hq/data/`. Those
files are gitignored: edit them in place and never stage them.

## 1. Back up the owner data

- [x] 1.1 Copy `data/BASE.tex`, `data/BASE.pdf`, `data/COVER_LETTER.pdf` and `data/Sunil Belde Profile.md` into the
  session scratchpad. Verify that all four copies exist there and are the same size as the originals.

## 2. Switch the address in the sources

- [x] 2.1 In `data/BASE.tex` line 13, replace `<old address>` with `<new address>` in both the
  `mailto:` link and the visible text. Leave the Medium link alone. Verify:
  `grep -c '<old address>' data/BASE.tex` gives 0, `grep -o '<new address>' data/BASE.tex | wc -l`
  gives 2, and the Medium line is unchanged.
- [x] 2.2 In the profile Markdown's contact table, set the `Email` row to `<new address>` and update its "Last
  updated" date to 2026-11-07 if it has one. Verify: `grep -n '| Email |'` shows the new address, and the old address
  appears 0 times in the file.

## 3. Re-render the base documents

- [x] 3.1 Render `data/BASE.pdf` again from the edited `BASE.tex` with `app.rendering.render_pdf(template_dir=data)`,
  using the main checkout's `.venv`, and write the bytes over `data/BASE.pdf`. Verify: the decompressed PDF streams
  contain the new address and 0 copies of the old one, using the same zlib scan used in planning. If rendering fails,
  restore from the 1.1 backup and report.
- [x] 3.2 From the main checkout's root, re-render `data/COVER_LETTER.pdf` with
  `.claude/skills/write-cover-letter/scripts/run render-base --data data`. Verify with the same scan: the new address
  is present and the old one appears 0 times. Verify that `data/COVER_LETTER.md` is unchanged.
- [x] 3.3 With the service running, `curl -s http://127.0.0.1:8081/resume/base.pdf` and `/cover-letter/base.pdf` and
  check that both responses match the new files byte for byte.

## 4. Form filler contact check (tracked in the repo)

- [x] 4.1 In `.claude/skills/job-application-form-filler/SKILL.md` Step 1, add a rule: read the contact email shown on
  the tailored resume and on any cover letter, and compare it with the profile document's `Email` row. Do not put any
  real address in the file. Verify that the rule's wording is in the file.
- [x] 4.2 In Step 3's contact row, state that email fields always get the profile document's `Email`, even when a
  document shows another address. Verify that the wording is in the file.
- [x] 4.3 In Step 6, item 7 (red flags), add: "an attached resume or cover letter shows a contact email other than the
  profile document's — name the document and suggest generating it again before submitting; say so if no email could
  be read from it". Verify that the wording is in the file.
- [x] 4.4 Add tests to `tests/test_apply_from_link_skill.py` (it already loads `FILLER`), or to a new
  `tests/test_form_filler_skill.py` in the same style. The tests check that the skill has the Step 1 comparison, the
  Step 3 rule and the Step 6 red flag, and that the skill file contains no `@gmail.com` address. Verify:
  `.venv/bin/pytest tests/test_apply_from_link_skill.py tests/test_form_filler.py -q` passes, then the full suite
  `.venv/bin/pytest -q` passes.

## 5. Final check

- [x] 5.1 Run `grep -rIl '<old address>'` over the main checkout (without `.venv`, `.git` or `outputs`) and
  over this worktree. Verify it finds 0 files. Also check `git status` in the worktree: only the skill, the test and
  `openspec/changes/replace-contact-email/` are changed, and nothing under `data/` is staged.

## Workflow follow-up

- Commit on `replace-contact-email`, push, and open a PR to `main` (do not push to `main` directly).
- Existing PDFs for the 36 unapplied applications keep the old address until they are generated again from the viewer.
- Archive the change after the PR merges.
