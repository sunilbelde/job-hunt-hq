# Design

## Context

- The viewer is one inline HTML page (`app/viewer.py`). It uses a nonce CSP, has no external assets, and builds every node with `textContent`. All list rendering happens in `renderList()`, which rebuilds the whole `<nav>` on every change. Per-entry write state lives in `notes` and `busy`.
- Viewer routes are registered in `register_viewer(...)` in `app/main.py`, only when docs are enabled. The keyed generation path (`requested_application` → `start_generation(request, kind, application, work)` with `resume_work` / `cover_letter_work`) is a set of closures inside `create_app`, so `register_viewer` cannot reach it today.
- `ApplicationStore.start_job` already makes the one-running-job claim atomic across both listeners. `get_job` reads one job. `list_with_reports` joins only `resume_reports`.
- `viewer-fill-form` is merged but not archived. Its delta (the fill endpoint, the Fill form button, eighteen operations) is the baseline that the MODIFIED blocks here build on.

## Goals / Non-Goals

**Goals:**
- One generation code path. A run started from the viewer must be indistinguishable from a keyed one: same job row, same log lines, same status endpoint.
- No new read endpoint for progress. The list already loads on page start, so the job summaries ride on it.
- The sidebar redesign stays within the existing CSS tokens and light/dark themes, with no new assets.

**Non-Goals:**
- Server-push updates (SSE or WebSocket). Polling a small list every 5 s while something runs is enough for a single owner.
- Showing a running job's partial progress. Jobs only expose running, done or failed.

## Decisions

### 1. Viewer generation routes reuse `start_generation`

Pass `register_viewer` a `generate(request, kind, application)` callable. It is built in `create_app` from `start_generation` plus `resume_work` / `cover_letter_work`, so the viewer routes call the exact same claim → thread → `run_job` path. The cover letter route runs `letter_posting_usable` and returns the same 422 message as the keyed route. Pull that message into a module constant so the two routes can't drift apart.

The new routes follow the shape of the fill route: `same_origin` check first, `parse_application_id`, store read, then `generate`. They take no body, so `requested_application` (which parses a JSON body) isn't used.

- *Alternative:* register the viewer POSTs inside `create_app` next to the keyed ones. Rejected because it would split the docs-only routes across two places and make the "only where the viewer is" rule easier to break.
- *Alternative:* have the page call `POST /resume` with a key. Rejected because the viewer is deliberately keyless and must never hold the API key.

### 2. Job summaries ride on `GET /applications`

Extend `list_with_reports` with two `LEFT JOIN generation_jobs` (one per kind) that select only `status, started_at, finished_at, error`. The result and the saved path are never selected, so they can't leak into the list. The models get a `JobSummary` and `ApplicationListItem.jobs: {resume: JobSummary | None, cover_letter: JobSummary | None}`.

- *Alternative:* keyless viewer copies of the two status endpoints. Rejected because they add two more operations and N requests per poll, and they return `match` and `text`, which the list doesn't need.

### 3. Polling and refresh in the page

- After `loadList()` and after every successful generation POST, if any item has a `running` job, schedule `setTimeout(pollList, 5000)`. Keep only one timer at a time.
- `pollList` re-reads `/applications`, swaps `applications`, re-renders the list, and diffs each kind's `status` for the selected ID against the previous snapshot.
- If a job went `running → done`:
  - For a resume, re-run the detail load for the selected app while keeping the current document tab. Today `select()` always resets to Resume, so add a `keepDocument` option.
  - For a letter, mark the letter panes stale so they refetch on the next switch, or right away if the letter view is showing.
- If a job went `running → failed`, write a note with `job.error`.
- A poll failure keeps the last list and retries on the next tick. It doesn't clear the page.

### 4. "Generate" vs "Regenerate"

The page treats a document as existing when any of these is true:
- *resume*: `report` is non-null, `jobs.resume.status === "done"`, or the generated resume PDF loaded (not 404) for the selected app.
- *letter*: `jobs.cover_letter.status === "done"`, or the generated letter PDF loaded.

Regenerate uses `confirm()`, as Delete already does.

*Known gap:* a letter written before job records existed, which the owner hasn't opened yet, reads "Generate" and isn't confirmed. Running it only replaces that file once the new letter is done. Acceptable.

### 5. Layout

- **Sidebar** (320 px):
  - A sticky filter bar with the search input across the full width.
  - A second row with the status `<select>` and a "Recorded" from–to pair in compact date inputs.
  - A "Clear" text button that appears only while filtering.
- **Card**: one `<button class="entry">`.
  - Row 1: company (600 weight, ellipsised), with the score right-aligned and coloured by `score >= threshold`.
  - Row 2: role (muted, two-line clamp).
  - Row 3: a status pill (one colour per status, from the existing good/warn/bad/accent tokens; verified and withdrawn use muted), the match badge, and the recorded date (`toLocaleDateString`, short month).
  - A running job adds a small pulsing dot with "Resume…" or "Letter…". Under `prefers-reduced-motion`, the dot doesn't animate.
  - The current card keeps the inset accent bar.
- **Detail header**: a sticky action bar above the details card.
  - Title: role · company.
  - Controls: status select, Generate/Regenerate resume, Generate/Regenerate cover letter, Fill form, and Delete pushed to the far right as a quiet danger button.
  - One `aria-live="polite"` note line under the bar replaces the per-entry `notes` map.
  - Notes are keyed by application ID, so a result arriving after the owner moved on still shows when they come back.
- **Narrow screens** (≤800 px): the existing single-column fallback stays. The action bar wraps.

### 6. Write state moves from entries to the selected app

Every write is now started from the action bar, so `busy` stays keyed by ID but only drives the action bar. List cards read only `applications` and `jobs`. The rule that a write never selects an application no longer applies, because writes act on the selected one. The specs drop the old "act on an unopened entry" scenarios.

## Risks / Trade-offs

- [Owner regenerates by mistake and spends a Claude run] → Confirmation on Regenerate. The previous file stays until the new run succeeds. A failed run leaves it untouched (generation-jobs).
- [Deleting while a job runs] → Already allowed via the keyed API. The job row goes with the application and `finish_job` writes nothing. Leave the Delete behaviour unchanged.
- [Polling never stops if a job hangs] → Jobs are capped at about 10 min, and a restart fails stuck jobs. Polling stops as soon as no job reads `running`.
- [List response grows] → Four short fields per kind per application. Negligible at this scale.
- [Spec baseline depends on an unarchived change] → Archive `viewer-fill-form` before archiving this one (task 1.1). Otherwise the MODIFIED "Fill form from the viewer" and "Smoke test checks the docs listener" blocks have no target.

## Migration Plan

- No schema change: `generation_jobs` already exists.
- Deploy by reinstalling the service as usual. The smoke test then expects twenty operations.
- Rollback is reverting the commit. Jobs started from the viewer are ordinary job rows.
