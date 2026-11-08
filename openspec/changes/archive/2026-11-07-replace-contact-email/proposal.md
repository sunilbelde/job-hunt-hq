# Proposal

## Why

The owner is switching their job-hunt contact email to a new address. Every resume, cover letter and application form
should show the new one, and the form filler should type the new one into the contact fields. The old address must not
turn up in anything sent after the switch.

## What Changes

- **Owner data (local only, gitignored, never committed):** replace the old address with the new one in the three places
  it appears as an email:
  - `data/BASE.tex`: the resume header's `\faEnvelope` line, both the `mailto:` link and the visible text. Tailored
    resumes and cover letter headers are built from this file, so all future generations pick up the change.
  - `data/<owner> Profile.md`: the contact table's `Email` row, where the form filler reads the email it types.
  - `data/BASE.pdf` and `data/COVER_LETTER.pdf`: render them again from the edited sources. The viewer shows these as the
    base documents.
- **Not changed:** the Medium profile link. It is a username, not an email address.
- **Existing generated files are left as they are** (the owner's decision). There are 302 PDFs under `OUTPUT_DIR`, and 36
  applications that are not yet applied (35 `verified`, 1 `withdrawn`) have tailored PDFs that still show the old
  address. Those PDFs are only replaced when the owner generates them again from the viewer.
- **Form filler (tracked in the repo):** `job-application-form-filler` gets a new red flag. When the tailored resume or
  cover letter it attaches shows a contact email different from the profile document's `Email` row, the review report
  says so and suggests generating the documents again before submitting. The skill keeps typing the profile document's
  email into the form either way. No address is written into the skill file.

## Capabilities

### New Capabilities
- `application-form-filling`: how the form filler takes contact details from the owner's profile document and checks
  that the documents it attaches agree with them.

### Modified Capabilities
<!-- None: resume and cover letter headers already come from BASE.tex, and the form filler already reads contact details from the profile document. -->

## Impact

- `.claude/skills/job-application-form-filler/SKILL.md`: one new red flag in Step 6 (Report back) and one check in
  Step 1, where the tailored resume is read.
- `tests/`: a small test that the skill file contains the new check, following `tests/test_apply_from_link_skill.py`.
- Local files in the main checkout's `data/` folder. They are gitignored and outside this worktree, so they get edited in
  place and never staged.
- No API, database or service code changes. The service reads `BASE.tex` on every generation, so it does not need a
  restart. `storage.py` reads only the `\name{}` at startup, and that is not changing.
