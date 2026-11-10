# Design

## Context

The viewer is one self-contained HTML string in `app/viewer.py`. It loads `GET /applications` once, filters in the page (search, status, recorded dates) and writes through `/viewer/application/...` endpoints that exist only on the local docs listener and refuse cross-site requests. Rows live in SQLite; columns added later are migrated in place via the `MIGRATION` map. See proposal.md for motivation.

## Goals / Non-Goals

**Goals:**
- Hiding is quick, reversible and persistent across browsers and restarts.
- Hidden applications are one click away, never lost.

**Non-Goals:**
- No effect on the keyed public-facing API behaviour, generation, email matching or dedupe.
- No new status value and no automation based on status.

## Decisions

**1. Store a `hidden` column on the row (INTEGER 0/1, default 0), not browser localStorage.** The viewer is used from more than one browser/device on the tailnet and the owner wants it to stick. Alternatives: localStorage (per-browser, silently lost) and a new `hidden` status (would erase the real status such as `rejected`, and the status control already has six values specified). Migration follows the existing pattern: add to `MIGRATION`, `ALTER TABLE ... DEFAULT 0`. `COPIED_COLUMNS` for the integer-ID migration gets the column too.

**2. Dedicated endpoint `PUT /viewer/application/{id}/hidden`, body `{"hidden": bool}`, response `{"ok": true, "application_id", "hidden"}`.** Alternative was extending the viewer `PATCH`, but that endpoint is specified as status-only with required `status`; overloading it muddies validation. PUT is idempotent, which fits a set-to-value call. It reuses the same-origin check, UUID parsing, 404-before-422 ordering and docs-only registration of the other viewer writes. It sets `updated_at` like other writes. Cost: operation count 22 → 23 in docs spec, docs test and smoke test.

**3. `hidden` is not in `UPDATABLE_FIELDS`.** The keyed `PATCH /application` stays unable to change it; a separate store method `set_hidden` writes it. `hidden` is added to `LIST_COLUMNS` so the list carries a boolean (converted from 0/1). `GET /application/{id}` is unchanged.

**4. UI placement.**
- *Action bar* (selected application): `[Status ▾] [Generate…] [Fill form] ····· [Hide] [Delete]`. Hide is a plain secondary button (not red) placed immediately left of Delete, so the destructive one stays last. When hidden it reads **Unhide**. Disabled while a write is in flight, like the other controls. Note text: "Hidden" / "Unhidden" / "Not saved: …".
- *List filters*: a checkbox row "Show hidden (N)" under the status select, N = number of hidden applications; shown only when N > 0. Default off, per page load (not persisted).
- *List entries*: hidden ones (only visible when the checkbox is on) get a muted style and a "Hidden" pill in the meta row.
- *Header count*: counts visible applications, with " · N hidden" appended when N > 0 and the checkbox is off, e.g. "17 applications · 3 hidden". With the checkbox on, hidden ones count in the total. Filter counts keep "x of y" where y is the visible-scope total.
- *Hiding the selected application*: details stay open (matches the existing rule that a filter hiding the selected entry keeps its details); the entry leaves the list unless Show hidden is on. After Unhide the entry reappears.
- The show-hidden checkbox is not a "filter" for Clear/“x of y” purposes, so Clear filters leaves it alone.
- Empty state: when every application is hidden and the box is off, the list says "All applications are hidden." with the checkbox visible.

**5. Filtering stays client-side.** `matches()` gains `item.hidden && !showHidden → false`; no request on toggling.

## Risks / Trade-offs

- [Owner forgets something is hidden] → the header shows the hidden count and the checkbox stays visible whenever any are hidden.
- [Hidden application re-posted by link or matched by an email] → it keeps matching and stays hidden; documented, not changed.
- [Operation count touches several tests] → listed explicitly in tasks so none is missed.

## Migration Plan

Column added on startup by the existing in-place migration; all rows default to visible. Rollback: older code ignores the extra column.
