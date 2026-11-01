# Design

## Context

The installed service runs under launchd, outside any Herdr pane, as the owner's user. The Herdr CLI reaches the owner's session through its default socket (`~/.config/herdr/herdr.sock`) without `HERDR_*` variables, so the service can call it directly.

## Decisions

### An interactive tab, not `claude -p`
The form filler needs the owner mid-run: enabling a site in the Tailored Attach popup, consent boxes, questions the profile doesn't answer, multi-page forms. A headless run could not ask, and would need permission checks turned off to drive Chrome. The tab runs the same command the owner would type, so permissions and questions work as usual.

### `pane run` with a fixed command
The command is `<CLAUDE_BIN> --chrome '/job-application-form-filler <id>'`, built with `shlex.quote`. The only variable part is the application ID, which the endpoint has already parsed as a UUID and looked up. Company and role go only into the tab label, passed to Herdr as a separate argument (no shell), with control characters dropped and each part capped at 60 characters. `herdr agent start` was not used: it blocks up to 30 s waiting for the agent and fails on a first-run trust prompt, which the owner can answer in the tab anyway.

### Finding the workspace and an open tab
The workspace is found by label on every call, since Herdr IDs change across server restarts. If it is missing, it is created, and its first tab is renamed and used. An open tab is recognised by a label ending in the application ID, so a company renamed since still matches. A lock in the launcher serialises starts, so a double click cannot open two tabs.

### Errors
Any Herdr failure (binary missing, non-zero exit, a reply without the expected fields) is `HerdrUnavailable` → 503 `Herdr unavailable`, logged as `herdr_error` with the subcommand and exit code only, never Herdr's output.

### Tests never reach the real Herdr
An autouse fixture replaces `run_herdr` with one that always fails. Launcher tests use a fake that answers with the shapes the real CLI returned (`tab create` → `result.tab`, `result.root_pane`; `pane run` prints nothing).

## Risks

- Anyone on the tailnet can open a session on the mini, as they can already delete an application. The session is interactive and asks before acting, and the button never asks to submit.
- The session uses whichever `job-application-form-filler` skill Claude Code finds from the repo (the gitignored project copy or the synced user copy).
