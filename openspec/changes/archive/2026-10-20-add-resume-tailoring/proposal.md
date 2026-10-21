# Proposal

## Why

`POST /resume` returns the same base resume for every posting: `generate_output` is a stub that ignores the application. The owner wants each posting to get a resume that matches it as closely as the facts allow:

1. Check how well the base resume matches the posting.
2. Below a 70% match, rework the wording, order and emphasis of what is already there, without inventing anything.
3. Always produce a single page in the same template, with the page used fully.

The owner wants this built as a Claude Code skill plus scripts. Claude makes the judgment calls (what the posting asks for, how to phrase true facts), and scripts enforce every rule that can be checked mechanically.

## What Changes

- **New Claude Code skill `tailor-resume`** in `.claude/skills/tailor-resume/`: `SKILL.md` (the workflow and the no-fabrication rules), reference notes, and a Python script (`scripts/resume_tool.py`, called through a small `scripts/run` launcher) with these subcommands:
  - `prepare`: turn `data/BASE.tex` into an editable content model
  - `score`: compute the match score
  - `terms`: list the posting keywords the judge approved, and where each may go
  - `build`: render content into the base template, compile it and check it
  - `judge-input`, `judge-result`: the service's steps around the judge
  - `verify`: the service's final gate
  The service runs the skill headlessly (`claude -p`). The owner can also run it by hand in this repo.
- **The judge, a second skill `judge-resume-terms`** (the owner's request after the first trial run). Many keywords a posting asks for are abilities the owner's work shows without naming them, such as testing or reliability. Before tailoring, a separate Claude run rules on each posting keyword the base resume lacks. It sees only the base resume, the owner's profile list and those keywords, never the posting, so the job cannot sway it. A script accepts an approval only with evidence: a passage found in the resume, or an entry of the profile list. A rejected keyword is left out and never fails a request.
- **The owner's profile list, `data/PROFILE.md`:** skills and abilities the owner has beyond `BASE.tex`, one per line, which the judge treats as true. It is the first piece of the planned full profile document.
- **Match score (hybrid, script-scored).** Claude lists the posting's keywords and requirements, and quotes the resume as evidence for each requirement it marks met. The script computes a 0–100 score: half from weighted keyword coverage, half from weighted requirement coverage. Required items count double. A quote that does not appear in the resume counts as missing. The threshold is 70.
- **`POST /resume` workflow:**
  - Posting text missing or too short (under 50 words): the base resume is saved, unscored, as today.
  - Base score of 70 or more: the base resume is saved.
  - Base score below 70: a tailored resume is saved.
  The request stays **synchronous**, with the same 201 response plus a new `match` object (`status`, `threshold`, `base_score`, `tailored_score`, `added_terms`). It now takes about 1–5 minutes instead of a few seconds. The Claude runs for one resume (analysis, judge, tailoring) share one time limit (7 minutes by default, 8 at most), so a request finishes within 10 minutes.
- **No fabrication, enforced by script:**
  - Header, education, job headings (employer, title, location, dates) and certifications are copied from `BASE.tex` and cannot be edited.
  - Skills may only be reordered, regrouped under the existing labels, or dropped, and the only new items allowed are keywords the judge approved.
  - Every bullet must cite the base bullet(s) of the same job it comes from.
  - Every number in a bullet must appear in the bullets it cites.
  - A posting keyword the base resume lacks may appear only when the judge approved it: in a skills line, or in a bullet citing the base bullet that holds its resume evidence. One approved from the profile list alone goes in skills lines only. No keyword the base resume has may be dropped.
- **Same template, one page, used efficiently.** Claude never writes TeX: the script splices its content into `BASE.tex`, so the preamble, header, spacing and section order are the base file's own.
  - Hard limits: exactly one page, content filling at least 90% of the text area, and no line running into the margin.
  - Targets the skill iterates toward: at least 96% fill, and no bullet whose last line is nearly empty. The tectonic render of `BASE.tex` measures 98.7% fill, and 3 of its 16 bullets end with 2–3 words.
- **Failures return an error** (the owner's choice). These cases all get 500 `{"ok": false, "message": "Resume generation failed"}`, write nothing, and keep any earlier resume:
  - Claude is unavailable or unconfigured, or the runs hit the time or spend cap.
  - The judge's output is unusable.
  - The content fails a check.
  - Rendering fails.
  **Behavior change:** today, generation fails only if TeX fails.
- **Configuration:**
  - `CLAUDE_CODE_OAUTH_TOKEN` (new, from `claude setup-token`, uses the owner's Claude plan) or `ANTHROPIC_API_KEY` (existing, now used, billed per run)
  - `TAILORING_MODEL` (default `claude-opus-5-5`)
  - `TAILORING_TIMEOUT_SECONDS`
  - `TAILORING_MAX_BUDGET_USD`
  - `CLAUDE_BIN`
- **Hosting:**
  - The install script warns when the Claude CLI or a credential is missing, and makes one minimal live call to confirm the credential works.
  - The status script reports whether tailoring is configured.
  - The smoke test clears its synthetic posting text, so it never starts a paid Claude run.
- **Logging:** the existing `resume_request` line gains the match status, both scores, the Claude runs' turns and estimated cost, and the judge's approved and rejected counts. A failed generation adds a `tailoring_error` line with the stage and reason. Neither line includes posting text, resume text, keywords or paths.
- **Dependency:** `pdfplumber` (MIT) becomes a runtime requirement for the layout checks.
- **TODO, not implemented:** growing the profile list into a full profile document, a second source of facts (projects, roles, results) that bullets can cite on top of the base resume. TODO markers go in the skill, the scripts, `app/tailoring.py` and `data/PROFILE.md`.
- **Docs:** the OpenAPI description of `POST /resume` (the `match` object, latency, what 500 now covers), the README, `.env.example` and the docs tests.

## Capabilities

### New Capabilities

- `resume-tailoring`: how a resume is matched against a posting and tailored to it. Covers the match score and threshold, the judge and the owner's profile list, the no-fabrication rules, the template and one-page layout checks, the skills and their scripts, and the limits on the headless Claude runs.

### Modified Capabilities

- `job-api`: the `POST /resume` success response gains `match`. Stubbed generation is replaced by score-then-tailor generation. Generation failures now include tailoring failures. The `resume_request` log line gains the match details.
- `service-config`: new optional variables for the Claude credential, model, timeout, spend cap and CLI path. `ANTHROPIC_API_KEY` is now used.
- `resume-pdf-rendering`: rendering covers tailored TeX built from the base template, with the same isolation, time limit and offline guarantees as the baseline.
- `local-service-hosting`: install and status report on the Claude prerequisites, and the smoke test never triggers a Claude run.

## Impact

- **Code:**
  - New: `.claude/skills/tailor-resume/`, `.claude/skills/judge-resume-terms/`, `data/PROFILE.md` and `app/tailoring.py` (prepares the folders, runs the analysis, the judge and the tailoring, runs the gate).
  - Changed: `app/generation.py`, `app/main.py` (response, errors, logging, docs text), `app/models.py` (`ResumeMatch`, `ResumeCreated.match`), `app/settings.py`.
  - Hosting: the plist template (`CLAUDE_BIN`), `scripts/install_service.sh`, `scripts/service_status.sh`, `scripts/smoke_test.sh` and its test.
  - `requirements.txt`.
- **API:** additive `match` field on the 201 response, including the keywords the judge let tailoring add. `POST /resume` is much slower, so clients need a timeout of several minutes. 500 now also means tailoring failed.
- **Cost and limits:** about 1–2 USD per tailored resume on an API key (estimate), or a share of the owner's Claude plan when using a subscription token. That plan is Pro, and its limits are shared with interactive Claude Code use. A tailored resume takes three runs (the judge's is short); postings that already match cost one shorter scoring run.
- **Security:** posting text is untrusted, since it is scraped from the web and sent through a public API. The Claude runs get no network tools and no MCP servers. The judge never sees the posting and runs no commands. Its file access and shell commands are confined to a temporary work folder, where it can run the skill's script and read-only commands and nothing else. The commands it runs never see its credential. It never receives the service's `API_KEY`, and the owner's shell profile and Claude Code settings are never loaded. The saved PDF is always re-rendered and re-checked by an untouched copy of the script, never taken from the run.

## Open Questions

These were assumed so the plan could proceed. Each can be changed before apply.

1. **No usable posting text.** A missing posting, or one under 50 words, saves the base resume with `match.status` `no_job_description` (201), as today, rather than an error. There is nothing to match against.
2. **Model.** `claude-opus-5-5` at `high` effort, with `claude-sonnet-5-5` as Claude Code's fallback when Opus is overloaded or unavailable on the plan.
3. **Credential (decided).** The owner starts on the Pro plan, with `CLAUDE_CODE_OAUTH_TOKEN` in `.env`. If Pro limits start failing runs, the owner adds `ANTHROPIC_API_KEY`. It then takes precedence, which is Claude Code's own behavior in `-p` mode, with no code change.
4. **No match report file.** Scores go in the response and the log only. Saving a report next to the resume (requirements, gaps, changed bullets and their sources) is a possible follow-up.
5. **Layout thresholds.** A hard floor of 90% fill. Targets of 96% fill, and no bullet whose last line uses under a quarter of the width. These are constants in the script.
6. **Limits.** Postings over 60,000 characters are refused (500). There is no cap on concurrent tailoring requests, and each request's runs share one time limit and one spend cap.
7. **Where approved keywords may go.** In any skills line, and in bullets that cite the base bullet holding the judge's resume evidence. A keyword approved from the profile list alone goes in skills lines only, until the full profile document can say which job it belongs to.
8. **The profile list's first entries** are the eight abilities the owner said they have after the first trial (agent harnesses, testing, code quality, reliability, context engineering, post-training, browser automation, TypeScript). The owner edits the file.
