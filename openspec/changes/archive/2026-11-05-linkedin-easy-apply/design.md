# Design

## Context

See proposal.md for why. The relevant state today:

- `posting_source_type` and `verification_method` are `Literal` fields on `ApplicationRow`, with a pairing validator. In the store they are plain `TEXT` columns with no `CHECK`. Both are in `IMMUTABLE_FIELDS`.
- `GET /applications` returns only `LIST_COLUMNS`, which excludes the source type, so the viewer's list cannot see it yet.
- The skill says the profile document's Hard filters section "outranks this list wherever they differ", and that section contains "Official company careers page only". A skill-level exception has to name this explicitly or the profile's filter wins.
- The form filler's Step 7 and "Wrap up" define the Submitted question and the tab closing. Its confirmation check reads the form tab, which does not exist here.
- `dedupe_key` only strips `trk`-style parameters. `/jobs/view/<slug>-<id>`, `/jobs/collections/...?currentJobId=<id>` and regional hosts all produce different keys for one posting.

## Goals / Non-Goals

**Goals:**

- A marker that says truthfully what was and was not verified, and that the workflow can read back on a later run.
- One branch point in the skill, decided from the stored row.

**Non-Goals:**

- Detecting Easy Apply from the page, or logging in to LinkedIn.
- Automating anything on LinkedIn. The owner applies.
- Linking an Easy Apply row to an official posting that appears later. It would be a separate row.
- Changing `job-application-form-filler` or the `/fill` endpoint. Only the viewer stops offering the button. Running the form filler by hand on such an ID hits LinkedIn's sign-in wall, which it already hands to the owner.
- A viewer filter for Easy Apply, or a link box option to declare it up front.

## Decisions

### The marker is a new `posting_source_type` value

`posting_source_type` `linkedin_easy_apply`, paired with `verification_method` `owner_confirmed` and an empty `official_apply_url`.

The source type is the field that already answers "where does this posting live", it is already immutable, and needs no migration. Each pairing also keeps the rule that the source and method agree.

- *`added_via` `easy_apply`:* rejected. It says how a row got in, and an Easy Apply row still came in by link. The value would also replace the ByLink tag.
- *A new boolean column:* rejected. It needs a migration and a new immutable field, and leaves the row claiming `official_apply_match`, the false statement this change removes.
- *`recruiting_platform` with a LinkedIn check:* rejected for the same reason.
- *`official_apply_url` equal to `job_link`:* rejected. The field means an official apply link, and there is none. Empty also matches `employer_site`, and the form filler's fallback to `job_link` is unaffected.

`job_link` is not validated to be on `linkedin.com`. The pairing rules check the claim's shape, not the world, and the only writer of this value is the skill.

### Detection is the owner's answer, and it comes last

**It's LinkedIn Easy Apply** is a fourth option at the existing question, shown only for LinkedIn links. That is within AskUserQuestion's limit of four. The board and careers page search still runs first, so an official posting always wins and the exception is taken only when one really is missing. The cost is a search the owner may already know is pointless, which is small and keeps a single path. "I'll sign in, try again" stays useful: the owner can see Easy Apply once signed in, and the retry comes back to the same question.

### The branch reads the row, not the run

Step 8 goes to the Easy Apply ending when the row's `posting_source_type` is `linkedin_easy_apply`, and Step 6 skips the cover letter check on the same test. So a rerun of a stored application behaves the same as the first run, without the question being asked twice. The "No, not submitted" answer relies on this: the rerun lands straight on the Submitted question.

### Reduce LinkedIn links in Step 1

The reduction runs before the first lookup rather than only at recording. Otherwise a rerun with a different copy of the link would miss the row, repeat the search and ask the question again. It only changes the link used for lookup and for `job_link` on Easy Apply. An official posting is recorded under its own link as before. The skill does this, not `dedupe_key`, which would otherwise change keys for stored rows.

### New Step 9 in the skill

Step 8 stays the handoff and opens with the Easy Apply test. Step 9 holds the Submitted question and wrap-up. It follows the form filler's order with two differences:

- No confirmation read. The Chrome window is logged out and the owner applies elsewhere, so the owner's answer is the evidence.
- No profile document step. This path asks no form questions, so there are no new answers to save.

The options match the form filler's wording. "Reviewed" is dropped, since there is no filled form to review.

### Viewer

The list gains `posting_source_type` through `LIST_COLUMNS` and `ApplicationListItem`. A separate `.pill` beside the origin tag shows Easy Apply, so ByLink still shows. Fill form is hidden in the action bar for these rows with the `.hidden` class, because `button.action` sets `display` and would override the `hidden` attribute. The action bar reads the source type from the application it is given, and both the list entry and `GET /application/{id}` carry it, so no extra request is needed.

## Risks / Trade-offs

- [Easy Apply postings are more often from staffing firms] → The recruiter filter still runs, and an unclear poster goes to the owner.
- [The logged-out page truncates the description] → The "no full job description" filter drops it. The skill must expand the page's "show more" before judging.
- [The owner chooses Easy Apply wrongly] → The fields are fixed, so the row must be deleted and rerun. Delete is one click, and the job link is freed.
- [The workflow's own row is the only record of "owner_confirmed"] → Nothing verifies it, by design. The name says so.
- [A posting later appears on an official board] → It gets a second row. The owner sees both.
- [Public `POST /application` accepts new values] → Same key, same validation, no new endpoint. Nothing on the public listener reads them.

## Migration Plan

No schema change. Existing rows are untouched and list as before.

The one row recorded with the workaround stays wrong until fixed, because `PATCH` refuses these fields. Fix it by hand after deploy, as listed in tasks.md. A migration is not worth writing for one row, and no code should carry that row's ID.

Rollback: revert the code. Rows with the new values still read and list, since the columns are text and `StoredApplication` types them as `str`. Only new recordings would be refused.
