# Design

## Context

The viewer is one self-contained page in `app/viewer.py`: an inline script under a nonce CSP, with no inline styles or handlers and no browser storage. Today each list entry is a single `<button data-id>`, and a delegated click handler on `#list` calls `select(id)`. `statusControl(app)` and `deleteButton(app)` already do the PATCH/DELETE work, and `removed(id)` already cleans up the list and the detail pane. Both controls are rendered in `detailsCard`. `GET /applications` already returns `status` and `created_at` for every application, so the filters need nothing beyond what the page already has.

## Goals / Non-Goals

**Goals:**
- Reuse the existing status/delete logic, moved to the list entries, with valid HTML (no interactive element inside a `<button>`).
- Filter in the page, with no new request.

**Non-Goals:**
- Any API, OpenAPI, model or smoke-test change.
- Keeping filters across reloads. The page keeps no storage, and the URL fragment stays the selected ID.
- Bulk actions, sorting changes, or filtering by posting date, company or score.

## Decisions

**List entry markup.** Each entry becomes a `<div class="entry" data-id>` that holds two things:
- a `<button class="open">` with the company, role, badges and scores (the part that is clickable today);
- a row with the status `<select>` and the Delete button.

`aria-current` moves to the entry's open button. The delegated `#list` click handler narrows to `button.open`, so the select and Delete never call `select()`. Alternative: keep the entry a `<button>` and call `stopPropagation` in the controls. Rejected: a `<select>` inside a `<button>` is invalid HTML, and browsers handle it inconsistently.

**Controls built from the list item.** `statusControl` and `deleteButton` are built for each entry from its list item (`id`, `company`, `role` and `status` all come from `/applications`). After a status save, the code updates the list item. If that ID is selected, it also updates the detail's status text, through a kept reference to its `<dd>`. Then it re-renders the list. The request literals stay the same (`"/viewer/application/" + app.id, false, { method: "PATCH"` and the confirm text), so the existing page test keeps passing.

**Keeping the inline note across re-renders.** `renderList()` rebuilds the list from scratch, which would wipe the "Saved" or error note right after a save. The note is kept in a small map keyed by ID (`notes[id] = {text, error}`) that `renderList()` reads. A note is cleared on the next action for that ID. Alternative: patch the one entry in place. Rejected: the list has to re-filter after a status change anyway, so a single render path is simpler.

**Filter state.**
- One `filters = { status: "", from: "", to: "" }` object is bound to a `<select>` and two `<input type="date">`.
- They sit in a filter bar above `#list`. An `<aside>` wraps the bar and the nav, so the bar stays in place while the list scrolls.
- `renderList()` iterates `applications.filter(matches)`.
- Date matching turns `created_at` into the local calendar day (`YYYY-MM-DD` from the local `Date` getters) and compares it as a string with the inputs' values, which are already `YYYY-MM-DD`. That gives inclusive local-day bounds without any time-zone arithmetic.

**Count.** One `updateCount()` writes "N applications", or "M of N applications" when any filter is set. It replaces the two copies of the count line in `loadList` and `removed`.

**No-match state.** When the filters hide every entry, the list shows "No applications match these filters." and a "Clear filters" button. The same delegated listener handles the button through a distinct class, and it resets the three inputs and `filters`.

**Detail pane.** `detailsCard` shows the status as text in the Status field and drops the Delete button and the `.title-row .delete-control` style.

## Risks / Trade-offs

- [A select and a button on every entry crowd the narrow (300px) left column] → Put them on their own compact row under the badges, in a small font. The mobile layout already stacks the list above the detail.
- [Re-filtering right after a status change makes the entry vanish, so its "Saved" note is never seen] → Acceptable: the updated count shows the change, and the note still shows when the entry stays visible.
- [`confirm()` blocks the page] → Unchanged from today.

## Migration Plan

This change touches only the page. Deploy by restarting the service; roll back by reverting the commit.
