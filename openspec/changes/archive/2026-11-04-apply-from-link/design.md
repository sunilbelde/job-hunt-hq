# Design

## Context

See proposal.md for motivation and the specs for requirements. These facts about the current code shape the approach:

- `app/form_filler.py` opens a Herdr tab and runs one fixed command. Its docstring promises that only a parsed UUID reaches the command. A link breaks that assumption, so it needs its own guard.
- `job-application-form-filler` is gitignored and exists only in the main checkout. It takes an application ID, opens the form, attaches with Tailored Attach, and handles review and submit. Its wrap-up closes the Herdr tab only if the label ends with the application ID.
- `POST /application` treats `job_link` as the official posting. It requires `official_apply_url == job_link` for `recruiting_platform` and an empty value for `employer_site`.
- `GET /applications` carries no `job_link`, so the form filler's URL lookup reads every application one at a time.
- The profile document's Hard filters section covers pay, official site, sponsorship and a retrievable description. The recruiter and contract-only rules are not in it.

## Goals / Non-Goals

**Goals:**
- Reuse the form filler with no edits to it.
- Keep the Fill form button and endpoint unchanged.
- Keep the public listener at its four endpoints.

**Non-Goals:**
- Remembering dropped postings. Pasting one again repeats the check.
- Running without the owner. The session stays interactive, as Fill form's does.
- Filtering the viewer list by origin, or showing the tag in the detail pane.
- Telling the viewer that a session dropped a posting. The reason appears in the Herdr tab.
- Batch links.
- Automatic attaching on sites Tailored Attach does not support.

## Decisions

### A new skill, not a new path in the form filler
A new `apply-from-link` skill runs the steps before the form, then invokes `/job-application-form-filler <id>` in the same session.

- The form filler is gitignored and holds personal details, so a path added there could not be reviewed, tested in this repo, or reach a worktree.
- The new skill holds no personal data, so it can be committed and covered by a skill doc test. Thresholds stay in the profile document.
- The form filler stays a single-purpose skill, and Fill form keeps its behaviour.

Set `disable-model-invocation: true`, as `tailor-resume` does: this skill records data, so it runs only when named.

*Alternative:* extending the form filler with a link path keeps one entry point, but it grows an already 300-line skill and leaves the whole workflow outside version control.

### The skill does the work and the endpoint only opens a tab
`POST /viewer/apply-from-link` validates the link and opens the tab. The stored check, filters and recording all happen in the session, where the owner can answer questions and Chrome is available.

*Alternative:* running it as a server job fits the generation jobs, but it would need browser access and a way to ask questions from a background task.

### Link safety at two layers
The endpoint validates with a strict rule: `http` or `https`, a host, no user information, no whitespace or control characters, at most 2048 characters. `shlex.quote` then wraps `/apply-from-link <link>` as one argument. The second layer protects the shell even if validation misses something. The session treats the link as data, and rejecting whitespace also stops a link from carrying extra words into the prompt.

Update the `app/form_filler.py` docstring, since "only the application ID" is no longer true of the module.

### Refactor the launcher around one tab-opening path
Extract the shared part of `_start` into a helper taking a label, a label suffix to match, and a command. `start` keeps its behaviour and existing tests. A new `start_link(link)` builds `ByLink-<host>-<hash>`, with `<hash>` being the first 12 hex characters of the SHA-256 of `dedupe_key(link)`. Both share the existing lock.

Matching on the hash rather than the whole label means `?utm_source=x` still finds the open tab.

### Rename the tab once the ID is known
At first the session has no application ID, so its label cannot satisfy the form filler's wrap-up or Fill form's open-tab check. After recording or finding the row, the skill renames its tab to `<Company>-<Role>-<id>` with `herdr tab rename "$HERDR_TAB_ID"`, using the same label format as `tab_label`. Before that it runs `herdr tab list --workspace "$HERDR_WORKSPACE_ID"` and stops if another tab's label ends with the ID.

This keeps the form filler unchanged and prevents two sessions on one application.

### `added_via` is a real column, not derived
Add `added_via TEXT NOT NULL DEFAULT 'manual'` to `_schema`, `COPIED_COLUMNS` and `LIST_COLUMNS`. Add a `_has_added_via` check beside `_has_status`, since a store can have `status` and still lack this column. The check must run before the integer ID rebuild, which copies `COPIED_COLUMNS`.

Keep it out of `FIELDS`, whose columns are nullable, and write it explicitly in `record`. Put it in `IMMUTABLE_FIELDS`, so `PATCH` refuses it like the other recording facts. The viewer maps `link` to "ByLink" and `manual` to "Manual". `manual` means anything not added by this workflow, including postings recorded by other API clients.

*Alternative:* inferring the origin from `posting_source_type` cannot work, because it describes the posting and not how it arrived.

### Stored lookup through a filter on `GET /applications`
Add an optional `job_link` query parameter, compared by `dedupe_key`, using a new store query on `job_link_key`. It reuses the list shape and adds no operation. The skill then reads `GET /application/{id}` for `status` and `report`.

The check runs twice because the store holds the official link, so a LinkedIn link only matches after resolving. The first check saves the resolving work when the link is already official.

`RedactQueryString` already removes query strings from access logs, and the structured log line records no query.

### Resolving a link
In order, stopping at the first confirmed match:

1. A link already on an employer domain or a known tracking system is official.
2. Read the company and role from the public page, without signing in.
3. Find the employer's board and query its public API: `api.ashbyhq.com/posting-api/job-board/<org>`, `boards-api.greenhouse.io/v1/boards/<org>/jobs`, `api.lever.co/v0/postings/<org>?mode=json`.
4. Search the employer's careers page in Chrome.
5. Ask the owner.

The three board APIs answered without authentication when checked on 2026-11-04, and LinkedIn's public guest job pages did too. These endpoints are outside the project's control, so the skill treats each as a best-effort source and falls through to the next step on a failure.

### Filters
The pay floor comes from the profile document, so no figure is committed. The recruiter and contract-only rules are stated in the skill, as they are general rules. Pay filters on the top of the stated range, because the profile says to drop postings below the threshold and a range reaching it may still pay above it. The form filler's report still flags low pay.

A posting already stored is not filtered again, since the owner already accepted it.

### Cover letter check opens the form
Only the form can show whether the field exists, so the skill opens it after the resume is done, reads for the field, closes that tab, and starts the letter job if needed. Closing it matters because the form filler opens its own tab. A text box asking for a cover letter counts as the field.

Multi-page forms can hide the field. Because the handoff stays in one session, the skill tells the session to generate the letter if the form filler reports the field with no letter, then attach it or give the owner the file.

### Viewer polling
`schedulePoll` runs only while a job runs, so a new row would not appear. Add `linkWatchUntil`, set to now plus 15 minutes after a successful start, and poll while `anyRunning()` or that time is ahead. The existing `listEpoch` handling is unchanged.

The link box goes in the sidebar above the search field and shows its status beneath it, since no application is selected yet.

## Risks / Trade-offs

- [A board API or page format changes] → Each source is best-effort, and the last step is always asking the owner.
- [A near-match posting is recorded as official] → Both company and role must match, and a near match counts as unresolved. The form filler also checks the page against the application.
- [Prompt injection through a posting] → Page text is data in the skill and cannot change filters or submit rules. Submitting still needs the form filler's approval.
- [A public client sends `added_via: link`] → Only the tag is affected, and the API key is still needed.
- [A LinkedIn link is pasted twice while the first session runs past recording] → The hash label no longer matches, but the second session finds the row and sees the first tab by ID, then stops.
- [The session cannot tell the viewer about a drop] → The note says a tab opened, and the reason is shown there. No application appearing is the expected result.
- [The Mac mini's main checkout lacks the form filler] → The workflow stops at handoff with the ID, and the documents are kept.

## Migration Plan

The column is added on the next service start, and `ALTER TABLE ADD COLUMN` keeps all rows. Rollback: older code ignores the extra column, since it names its columns on read and the column has a default for inserts.

Deploy by merging, restarting the service so the viewer and API update, and running the smoke test. The skill arrives with the merge.
