# Design

## Context

See proposal.md (Why) for the motivation. The requirements are in `specs/resume-tailoring`, `specs/job-api`, `specs/service-config`, `specs/resume-pdf-rendering` and `specs/local-service-hosting`.

**Code today:**
- `create_resume` (`app/main.py`) loads the row as `StoredApplication` and calls `generate_output(application)` in the threadpool. It maps `RenderError` to 500 and `StorageError` to 502, and saves the bytes with `LocalStorage.save_resume` (atomic replace).
- `generate_output` (`app/generation.py`) returns `GeneratedFile(render_pdf(), "application/pdf", "pdf")`.
- `render_pdf` (`app/rendering.py`) copies `data/*.tex|cls` into a temp dir and runs `tectonic -X compile --untrusted` with a 120 s timeout.
- API tests patch `app.main.generate_output` (autouse fixture in `tests/conftest.py`).

**The template.** `data/BASE.tex` has a fixed preamble (lines 1–21: `resume.cls`, 0.5 in margins, header macros). Its body has four `rSection`s:
- EDUCATION
- TECHNICAL SKILLS: 7 lines of the form `\textbf{Label}: item, item \\`
- EXPERIENCE: 4 jobs. Each is a heading line, `\vspace` lines, an `itemize` with `\itemsep -3pt {}`, and one `\item` per line, 16 in total.
- CERTIFICATIONS

Bullets use only `\textbf{}`, `\%` and `\&`.

**Measured on the tectonic render of `BASE.tex`** (scratch analysis with pdfplumber):
- 1 page and 54 lines. The lowest line ends 9.5 pt above the bottom margin, which is 98.7% of the 720 pt text height.
- Body text is Latin Modern at 9.46 pt.
- Bullets start at x = 48.3 pt with their text at x = 57.9 pt, and the right edge is 576 pt.
- 3 of the 16 bullets end on a line with 2–3 words (13–21% of the width), and 2 more end at 35–39%.
- Tectonic warns about an overfull hbox (30 pt) at line 23 (`\begin{document}`, the header's contact line) and an underfull hbox in the certifications.

The committed `data/BASE.pdf` came from a different engine (CM fonts at 8.97 pt). It has the same text but different line breaks. The service has always saved the tectonic render, so every layout number here refers to that render.

**Runtime environment:**
- The service runs as a system launchd daemon under the owner's user, with no login session and therefore no login keychain.
- Its `PATH` is `/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:…`.
- The Claude Code CLI is v2.1.303 at `~/.local/bin/claude`, outside that `PATH`.
- The production checkout is `/Users/belde/dev-workspace/claude Projects/job-hunt-hq`, and `OUTPUT_DIR` defaults to `~/Library/Application Support/job-hunt-hq`. Both paths contain a space.
- The owner starts on the Pro plan: `CLAUDE_CODE_OAUTH_TOKEN` from `claude setup-token` sits in the checkout's `.env`. `ANTHROPIC_API_KEY` is added only if Pro limits get in the way.

**Claude Code behavior this design relies on** (code.claude.com docs: headless, skills, CLI reference, authentication, permissions, environment variables, tools; confirmed by the task 1 spike):
- `-p "/skill-name args"` expands a user-invocable skill, and project skills load from the working directory.
- `--bare` does not read `CLAUDE_CODE_OAUTH_TOKEN`. With `-p`, `ANTHROPIC_API_KEY` always wins when present.
- `CLAUDE_CONFIG_DIR` moves settings, credentials and state.
- These flags exist and are used below: `--output-format json`, `--max-turns`, `--max-budget-usd`, `--tools`, `--allowedTools`, `--disallowedTools`, `--settings`, `--permission-mode dontAsk`, `--permission-prompts none`, `--strict-mcp-config`, `--no-session-persistence`, `--fallback-model`, `--effort`.
- Skill frontmatter `allowed-tools` accepts `${CLAUDE_SKILL_DIR}` paths.
- File writes are checked against `Edit(...)` rules only. A `Write(...)` path rule is accepted but never consulted.
- A built-in set of read-only shell commands (`ls`, `cat`, `echo`, `grep`, `find`, `cd`, read-only `git`) runs without asking in every mode, `dontAsk` included. With `permissions.blockReadsOutsideWorkingDirectories` set, the file tools refuse reads outside the working directories, and shell commands that read there need approval, which `-p` denies.
- When a session starts, the Bash tool sources the shell startup file (`~/.zshrc`, `~/.bashrc` or `~/.profile`) and applies its aliases and functions to every command.
- `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1` removes credentials from the environments of the commands Claude runs, while Claude keeps them for its own API calls.
- SIGTERM ends a run with code 143, and Claude kills its Bash process trees.

## Goals / Non-Goals

**Goals:**
- Every rule that can be checked mechanically is checked by a script, both inside the run (so Claude can fix problems) and again at a gate the run cannot influence.
- The skills serve both the service and the owner's interactive Claude Code sessions.
- A run cannot reach anything outside a throwaway folder, and posting text cannot steer it outside the rules.
- A posting keyword the base resume lacks enters the resume only when a judge that cannot see the posting finds evidence for it.
- The service code stays thin: prepare the folders, run Claude, run the scripts and the gate, save.

**Non-Goals:**
- Cover letters. `cover_letter_path` stays a placeholder.
- The full profile document. There is a profile list the judge reads (Decision 15), a TODO and an extension point (Decision 13).
- An async API, a stored match report, a per-day spend limit, a cap on concurrent runs, and rate limiting.
- Editing the header, education, job headings or certifications. Changing section order, fonts, margins or spacing.
- Third-party Claude providers such as Bedrock or Vertex.

## Decisions

### 1. Thin service; the skill does the judgment, scripts do the checks

```
POST /resume (threadpool) → generate_output(application)
  posting unusable (null, blank, <50 words) → render_pdf()                 match: no_job_description
  posting > 60,000 chars                     → TailoringError(posting_too_long)
  otherwise → tailoring.run(application, settings)        one time limit and spend cap for all runs
    1. W = mkdtemp("tailor-"); copy skill → W/.claude/skills/tailor-resume; write W/posting.md
    2. resume_tool.py prepare  --template data --out W        (repo copy, service python)
    3. analysis run: claude -p "/tailor-resume ."  cwd=W, isolated env, limits (Decision 9)
         Claude writes W/out/analysis.json, runs `score base`; it stops at keep, or when
         `run terms` says the judge has not ruled
    4. resume_tool.py judge-input --work W --out V            (repo copy)
         validates the analysis, copies it to V/analysis.json, decides keep|tailor,
         writes V/judge-input.md for the keywords the base lacks → {decision, base_score, candidates}
         keep → render_pdf() (base, as today); done
    5. candidates > 0: J = mkdtemp("tailor-judge-"); claude -p "/judge-resume-terms ." cwd=J
         → J/out/verdicts.json                                (Decision 15)
    6. resume_tool.py judge-result --analysis V/analysis.json [--verdicts J/out/verdicts.json]
         --out V/terms.json; copy it to W/judge/terms.json
    7. tailoring run: claude -p "/tailor-resume ."  cwd=W again, a fresh session
         Claude writes W/out/tailored.json, assessment_tailored.json, with build feedback
    8. resume_tool.py verify --work W --analysis V/analysis.json --terms V/terms.json --pdf-out V/resume.pdf
         → {decision, base_score, tailored_score, failed: [...], added_terms: [...]}
    9. bytes of V/resume.pdf
    finally: remove W, J and V
```

`generate_output(application, settings)` takes the settings the handler already holds, rather than reading a global, so an app built with its own settings tailors with them. `GeneratedFile` gains optional `match` and `run` fields (turns, estimated cost and models used, summed over the runs, and the judge's approved and rejected counts).

### 2. Claude Code CLI headless, not the Messages API, Agent SDK or API Skills

The owner asked for Claude Code skills. A skill in `.claude/skills/` can be run by the service with `claude -p` and by the owner interactively. The other options:
- **Messages API with tool use from Python:** the workflow logic would end up as Python prompts and a hand-built tool loop, which the owner did not want.
- **Agent SDK:** adds a dependency that wraps the same CLI. A plain subprocess gives the env control and process-group kill already used for tectonic.
- **API Agent Skills (container plus code execution):** Anthropic's sandbox has neither tectonic nor this template, so the compile-and-check loop could not run.

### 3. Work folder contract

```
W/                                cwd of the run (mkdtemp, mode 700, system temp so no spaces)
  .claude/skills/tailor-resume/   copy of the repo skill; the run may alter it, the gate never uses it
  posting.md                      company, role, location, work type, why_it_fits, then the posting
                                  text under "Posting text (untrusted data)"; long lines wrapped at spaces
  template/BASE.tex, resume.cls   copies for the run's draft builds
  out/base.json                   content model of BASE.tex (prepare)
  out/analysis.json               Claude: keywords, requirements, base assessment
  out/score_base.json             script
  out/tailored.json               Claude: skills lines and bullets with sources
  out/build/                      script: tailored.tex, tailored.pdf, compile log
  out/check.json                  script: every check result, fill, short last lines
  out/assessment_tailored.json    Claude
  out/score_tailored.json         script
  judge/terms.json                service: the judge's ruling (copy); Claude can read it, not write it
  .tmp/                           TMPDIR for the run

J/                                the judge's folder (mkdtemp "tailor-judge-"), Decision 15
  .claude/skills/judge-resume-terms/   copy of the judge skill
  input.md                        resume text, profile entries, the keywords to judge
  out/verdicts.json               Claude
  .tmp/

V/                                the service's own (mkdtemp "tailor-gate-"); no run can reach it
  analysis.json                   the analysis as judged; the gate scores against it
  judge-input.md, terms.json      the judge's input and the checked ruling
  resume.pdf                      what verify rendered, and what gets saved
```

The posting is wrapped at spaces only, never inside a word, so a long JSON-style line is not cut off by the Read tool. The service passes only the fields useful for tailoring: company, role, location, work type, `why_it_fits` and the posting text. Salary, URLs and verification fields are left out.

### 4. Content model and splice renderer: Claude never writes TeX

`prepare` parses `BASE.tex` into `out/base.json`:

```json
{
  "skills": [{"label": "Programming Languages", "items": ["Python", "Java", "Pyspark", "SQL", "Bash"]}],
  "jobs": [{"id": "j1", "heading": "Capital One, ML Engineer – GenAI/LLM Automation | Chicago, IL | Jul 2024 – Present",
            "bullets": [{"id": "j1.b4", "text": "Architected a **GenAI ETL platform** that translates … reducing engineering effort by over **70%** …"}]}],
  "text": "<all visible resume text, used for scoring and evidence>"
}
```

Claude writes `out/tailored.json`, which has the same shape without headings or IDs. Each bullet carries `sources`: `{"skills": [{"label", "items"}], "jobs": [{"id": "j1", "bullets": [{"text", "sources": ["j1.b4", "j1.b5"]}]}]}`.

**Markup.** Text is plain, with `**bold**` and `*italic*` only. The renderer escapes `% & $ # _ { } ~ ^` and rejects any backslash. Converting the base's TeX to markup accepts only `\textbf{}`, `\textit{}` and the escaped specials. Any other command in a skills line or bullet makes `prepare` fail and name the line. That is how a future `BASE.tex` edit that breaks the conventions shows up.

**Splicing.** The renderer copies `BASE.tex` line by line. It replaces only the lines of the TECHNICAL SKILLS block and each job's `\item` lines. Preamble, header, education, headings, `\vspace` and `\itemsep` lines and certifications pass through verbatim. It also records a line map (TeX line to skills line or bullet ID), so compiler warnings can point at content.

**Round trip.** Rendering the base content model reproduces `BASE.tex`, apart from the indentation of `\item` lines, and compiles to the same text. A test asserts this.

Alternatives considered:
- **Claude edits a copy of the TeX, and a validator diffs it.** Rejected. It needs TeX-aware diffing, invites `\vspace` and font-size hacks to squeeze content, and leaves TeX injection (`\input`) to blacklists.
- **A Jinja template.** Rejected. It would be a second source of truth beside the `BASE.tex` the owner edits.

### 5. Posting analysis and the score

Claude writes `out/analysis.json`:

```json
{
  "keywords": [{"term": "Kubernetes", "aliases": ["k8s"], "importance": "required"}],
  "requirements": [{"id": "R1", "text": "Built LLM agents used in production", "importance": "required"}],
  "assessment": {"R1": {"status": "met", "evidence": ["ReAct agentic AI pattern to propose, critique, and refine"]}}
}
```

**Validation:** 5–40 distinct keywords and 3–15 requirements, each marked required or preferred. Every status is one of met, partial or missing. Each evidence quote has at least 3 words.

**Matching.** Text is normalized first: NFKC, lowercase, markup stripped, dashes and quote marks unified, whitespace collapsed. Keywords match with `(?<!\w)…(?!\w)` around the escaped term (multi-word terms allow any whitespace), which also works for `C++`, `C#` and `.NET`. An evidence quote must be a substring of the normalized resume text, otherwise the requirement counts as missing and is marked unverified.

**Score:** `floor(100 × (0.5·K + 0.5·R))`.
- `K` is weighted keyword coverage and `R` is weighted requirement coverage (met 1, partial 0.5, missing 0).
- Required items weigh 2 and preferred items 1.
- The threshold 70, the weights and the bounds are constants in `scripts/resume_score.py`. `app/tailoring.py` repeats the threshold for the `no_job_description` response, and a test keeps the two equal.

**Why this split.** The keyword half is what honest rewording can move: using the posting's own terms for things the candidate did, and surfacing skills. The requirement half reflects the facts, which tailoring cannot change. Evidence quotes stop the requirement half from being claimed without proof.

**The tailored score** reuses the keyword and requirement list. Claude reassesses the requirements against the tailored text in `out/assessment_tailored.json`, and its quotes are checked against the tailored text.

### 6. No-fabrication guards

Each check runs in `build`, in the loop with actionable messages, and again in `verify` at the gate. Codes are logged at the gate; text never is.

| Check | Rule | Code |
|---|---|---|
| Structure | same job IDs in the same order, at least one bullet per job, only base skills labels | `structure_mismatch`, `unknown_label` |
| Skills | each item equals a base item, appears as a phrase in the base text, or is an approved keyword | `unknown_skill` |
| Sources | every bullet cites at least one existing bullet of its own job | `missing_source`, `foreign_source` |
| Numbers | number tokens (`\d+(\.\d+)?`, from "75%", "10M+", "3.3-70B", "5 months") are a subset of those in the cited bullets | `unsupported_number` |
| New keywords | a keyword absent from the base text in every form must be absent from the tailored text, unless the judge approved it | `unsupported_keyword` |
| Approved keywords | an approved keyword may appear in a bullet only when the bullet cites a base bullet holding its resume evidence; skills lines may hold it anywhere | `misplaced_keyword` |
| Lost keywords | a keyword present in the base text must be present in the tailored text | `lost_keyword` |
| Text | no backslash, at most 400 characters per bullet, no empty items | `invalid_text` |
| Soft | bold phrases not found in the base text (approved keywords exempt); bullets not ending in "." | warnings only |

Header, education, headings and certifications cannot change, because they are never part of the editable model.

### 7. Layout measurement with pdfplumber

**Compiling.** `tectonic -X compile --untrusted --keep-logs` runs in its own temp dir that holds only the TeX and `resume.cls`. The timeout is 90 s, and `TECTONIC_CACHE_DIR` comes from the environment so the compile works offline.

**Measurements:**
- **Pages:** the pdfplumber page count, cross-checked with the log's `Output written … (N page`.
- **Fill:** words are grouped into lines by baseline (2 pt tolerance). Fill is `(bottom of the lowest line − 36) / 720`.
- **Lines free:** the space left divided by the median line pitch (about 12.4 pt on the base).
- **Short last lines:** a line starting with the `•` glyph begins a bullet, and the lines indented at the bullet's text x after it continue it. A bullet's last line is short when `(x1 − text_x0) / (576 − text_x0) < 0.25`. Bullets map to content IDs by order. If the counts differ, short lines are reported without IDs; this check is soft, so that is acceptable.
- **Overfull lines:** log entries `Overfull \hbox … at lines a--b` map through the line map. One that lands in spliced content fails as `overfull_line`. The header's existing warning at `\begin{document}` and all underfull warnings are ignored.

**Thresholds** come from the base measurement: a hard floor of 90% fill (about 6 lines free) and a target of 96% (about 2 lines).

**Why pdfplumber.** The checks need word boxes (x0, x1, top, bottom). pypdf gives text positions without widths. PyMuPDF is faster but AGPL-licensed. Poppler's `pdftotext -bbox` would be another Homebrew prerequisite. pdfplumber is MIT-licensed, pure Python (pdfminer.six) with pypdfium2 wheels, and needs well under a second for one page. Measuring in TeX (`\pagetotal`, `\pdfsavepos`) was rejected: it would instrument the template and cannot see last-line widths.

### 8. The final gate re-renders and measures the bytes it approves

`verify` runs from the repo's own copy of the scripts, with the repo's `data/`, and reads only the run's JSON files. It takes the analysis from `--analysis`, the copy `judge-input` made right after the analysis run, and the approved keywords from `--terms`, the service's own ruling. The tailoring run can edit its `out/analysis.json` and cannot write `judge/terms.json`, and neither file reaches the gate. Without `--terms`, no keyword the base resume lacks is allowed. Its steps:
1. Validate the analysis and recompute the base score.
2. Decide whether to keep the base resume or tailor it.
3. For tailoring: run every guard with the ruling, splice with the repo's `BASE.tex`, compile, run the hard layout checks, compute the tailored score, list the approved keywords the content uses (`added_terms`), and write the PDF into a temp dir owned by the service.

The service saves exactly that PDF, so what was measured is what is saved, with no gap between check and save. The run's own TeX and PDFs are never read.

The final render does not go through `app/rendering.render_pdf`, because the gate needs the compile log and the PDF together from one compile. `verify`'s compile uses the same flags, isolation and time limits, which `specs/resume-pdf-rendering` now requires of every render. The base resume keeps using `render_pdf`.

### 9. Running Claude: isolation, limits, credentials

**Command** for both `tailor-resume` runs, verified by the task 1 spike (results at the end of this decision), with `<S>` = `W/.claude/skills/tailor-resume`. The judge's command is in Decision 15.

```
$CLAUDE_BIN -p "/tailor-resume ." --output-format json --no-session-persistence
  --model $TAILORING_MODEL --fallback-model claude-sonnet-5-5 --effort high
  --max-turns 40 --max-budget-usd <what is left of $TAILORING_MAX_BUDGET_USD>
  --permission-mode dontAsk --permission-prompts none --strict-mcp-config
  --settings '{"permissions": {"blockReadsOutsideWorkingDirectories": true}}'
  --tools Read,Write,Edit,Bash --disallowedTools WebFetch WebSearch Agent "mcp__*"
  --allowedTools "Read(./**)" "Edit(./out/**)" "Bash(<S>/scripts/run *)"
```

**Environment.** It is built from scratch, never inherited:
- `HOME=<OUTPUT_DIR>/.claude-runtime/home`, an empty folder (mode 700), so no shell startup file is sourced
- `CLAUDE_CONFIG_DIR=<OUTPUT_DIR>/.claude-runtime/config` (mode 700). `company_folder` strips leading dots, so no company folder can collide with `.claude-runtime`.
- `PATH=<repo>/.venv/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin`, so tectonic resolves
- `TAILOR_PYTHON=<the service's venv interpreter>`, which the skill's `scripts/run` launcher executes, so the interpreter never depends on `PATH` or a shell profile
- `TMPDIR=W/.tmp`, `TECTONIC_CACHE_DIR`, `USER`, `LOGNAME`, `LANG`
- Exactly one credential: `ANTHROPIC_API_KEY` if set, else `CLAUDE_CODE_OAUTH_TOKEN`
- `CLAUDE_CODE_SHELL=/bin/zsh`, `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1`, `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`, `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1`, `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`

The service's `API_KEY` is never passed.

**Shared limits.** The runs for one resume share `TAILORING_TIMEOUT_SECONDS` and `TAILORING_MAX_BUDGET_USD`. Each run gets the time left as its timeout and the budget left as `--max-budget-usd`. A run does not start with under 30 s or no budget left; that fails as `claude_timeout` or `claude_budget` for the run that could not start. Turns and estimated cost are summed over the runs.

**Process.** `start_new_session=True`. The shell commands Claude starts run in process groups of their own, so a signal to Claude's group alone does not reach them. On timeout the service:
1. records Claude's descendant processes (from `ps -A -o pid=,ppid=`)
2. sends SIGTERM to Claude's process group and waits 15 s, while Claude ends its command trees and exits with 143
3. sends SIGKILL to the group and to every recorded descendant still running, if any are

**Result.** The service parses the JSON envelope and logs `num_turns`, `total_cost_usd` and the models in `modelUsage`. A run fails when the exit code is non-zero or `is_error` is true. `subtype` alone is not enough, because a rejected token still reports `success`. The reason is:
- `claude_auth` when `api_error_status` is 401 or 403
- `claude_max_turns` for `error_max_turns`, and `claude_budget` for `error_max_budget_usd`
- `claude_timeout` when the service stopped the run
- otherwise `claude_error:<subtype>`, or `claude_exit:<n>` when there is no envelope

The files the run wrote are judged only by `verify`.

Why each choice:
- **Copying the skill into W, not using `--add-dir`:** `--add-dir` would grant the run file access to that repo directory. The copy keeps the repo (and its `.env`) out of reach, and any edits land in a throwaway folder.
- **A private config folder and an empty `HOME`:** the daemon has no keychain, and a session sources the shell startup file in `HOME`. Both folders sit under `.claude-runtime/` and the credential comes from the environment, so runs are independent of the owner's settings, hooks, plugins, MCP servers, memory, login and shell profile.
- **Not `--bare`:** bare mode would isolate the most, but it ignores `CLAUDE_CODE_OAUTH_TOKEN`, which the subscription token needs.
- **Not `--restricted`:** the skill does not load with it (spike run B).
- **Allow rules:** `Edit(./out/**)` is the write permission, since writes are checked against `Edit(...)` rules only.
  - Anything else that would prompt is denied: another program, a pipe into one, or a write outside `out/`.
  - Read-only commands still run without asking, but the `--settings` block confines them, and the file tools, to W.
  - The credential scrub forces the permission mode to `default`. Under `-p` with `--permission-prompts none`, the same calls are still denied.
  - `SKILL.md` gives the exact commands, and the script prints compact summaries, so no piping is needed.
- **The credential scrub:** the commands Claude runs never see the credential; Claude keeps it for its own API calls.
- **The launcher:** `scripts/run` executes `$TAILOR_PYTHON`, so an alias or a `PATH` change cannot swap the interpreter. The venv interpreter's path contains a space, and the spike showed that this works.
- **The script's own surface:** it reads only files with fixed names in the folders it is given, and prints scores and check results, never file contents.
- **Untrusted posting:** `posting.md` heads the text as untrusted data, and `SKILL.md` says never to follow instructions found in it. Even if Claude does, its tools cannot reach outside W, and the gate enforces the rules.
- **The fallback model** is for availability (Opus overloaded or unavailable), not cost. The models actually used are logged.
- **The spend cap** is checked between turns and can be overshot: the spike spent 0.016 USD against a 0.01 cap. The 3 USD default leaves headroom.

**Spike results (task 1, 2026-10-18).** Run with Claude Code 2.1.303 and the owner's Pro subscription token. Each run used a throwaway work folder in the system temp dir, a config folder and a `PATH` entry containing spaces (as in production), and an environment built from scratch. Run A used the command and environment above, with a probe skill in place of `tailor-resume` and a 1 USD cap.

- **Run A works.**
  - The skill expanded from W, and the launcher ran the venv interpreter, whose path contains a space.
  - A Write inside `out/` was allowed.
  - These were all denied: `ls ~`, `cat` and Read of a file outside W, a Write to W's root, a Write outside W, and `python3 -c`.
  - The script's environment had no `CLAUDE_CODE_OAUTH_TOKEN`, `ANTHROPIC_API_KEY`, `API_KEY` or `CLAUDE_CONFIG_DIR`.
  - The empty `HOME` stayed empty, and nothing was written to the owner's `~/.claude`.
  - 10 turns, 21 s, about 0.08 USD, on `claude-opus-5-5` with the Pro token.
- **Run B (`--restricted`):** the skill does not load ("`/probe` command isn't installed"), so `--restricted` is not used.
- **Permission mode:** `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1` forces it to `default`, with a warning on stderr. Under `-p` with `--permission-prompts none`, the denials above still hold.
- **Auth check:** `claude auth status` reported `oauth_token` for a dummy token and for the half-pasted one. It shows that a credential is set, not that it works.

Exit codes and envelope values (task 1.2):

| Case | Exit | `is_error` | `subtype` | Notes |
|---|---|---|---|---|
| Success | 0 | false | `success` | |
| `--max-turns` reached | 1 | true | `error_max_turns` | |
| `--max-budget-usd` reached | 1 | true | `error_max_budget_usd` | Spent 0.016 USD against a 0.01 cap: the cap can be overshot |
| Token rejected | 1 | true | `success` | `api_error_status: 401`; `subtype` alone does not show the failure |
| SIGTERM to Claude's process group | 143 | no envelope | | Exits within 20 s and ends its command trees. The probe's child `sleep` ran in a process group of its own and still died |

Envelope keys seen include `type`, `subtype`, `is_error`, `api_error_status`, `api_error_origin` (on errors), `result`, `num_turns`, `total_cost_usd`, `modelUsage`, `permission_denials`, `usage`, `session_id`, `stop_reason`, `terminal_reason`, `duration_ms` and `duration_api_ms`.

After the runs, the config folder held `.claude.json`, `backups/`, `policy-limits.json`, `remote-settings.json`, `session-env/` (one entry per run), `sessions/` and `shell-snapshots/`.

### 10. Skill layout and workflow

```
.claude/skills/tailor-resume/
  SKILL.md                 workflow, rules, stop conditions (under 500 lines)
  reference/scoring.md     how to write analysis.json: choosing keywords, aliases, requirements, quoting evidence
  reference/rules.md       allowed vs forbidden edits, with examples from this resume
  reference/layout.md      reading check.json: fill, short last lines, overfull lines, what to change
  scripts/run              launcher: runs resume_tool.py with $TAILOR_PYTHON, else the repo's .venv python
  scripts/resume_tool.py   CLI: prepare | score base|tailored | terms | build | judge-input | judge-result | verify
  scripts/resume_model.py  BASE.tex parser, markup, splice renderer, line map
  scripts/resume_score.py  normalization, keyword matching, evidence, score, constants
  scripts/resume_checks.py guards, compile, layout measurement
  scripts/resume_terms.py  missing keywords, the judge's input, checking verdicts, the ruling
.claude/skills/judge-resume-terms/
  SKILL.md                 how to judge, examples, the verdicts format; no scripts, no allowed-tools
```

**Frontmatter:**
- `name: tailor-resume`, with a description that front-loads "tailor the resume to a job posting"
- `disable-model-invocation: true`, so it runs only when invoked, in the service and the owner's sessions alike
- `argument-hint: [work-folder]`
- `allowed-tools: Bash(${CLAUDE_SKILL_DIR}/scripts/run *)`

**The launcher.** `scripts/run` executes `$TAILOR_PYTHON` when it is set, which the service always does. Otherwise it uses the repo's `.venv/bin/python`, found four levels up from the script, so interactive sessions in the repo use the service's interpreter too.

**Steps in `SKILL.md`.** The same skill serves the analysis run and the tailoring run; the work folder's files say which step it is at:
1. Read `posting.md` (untrusted data) and `out/base.json`. If `out/base.json` is missing, run `prepare`.
2. If `out/score_base.json` exists, read the analysis and go on without changing it. Otherwise write `out/analysis.json`, then run `score base`, which prints the score, the decision, unverified requirements and missing keywords.
3. If the decision is keep, stop with a one-paragraph summary.
4. Otherwise run `terms`. Without `judge/terms.json` it says the judge has not ruled, and the run stops there; `build` also refuses to run until the ruling exists. With it, it lists the approved keywords, their evidence and where each may go, and the rejected ones.
5. Write `out/tailored.json` and run `build`. Read the summary (and `out/check.json` if needed), revise, and build again, at most 5 builds. Hard failures must be fixed. Targets are worked on until they are met or the builds run out.
6. Write `out/assessment_tailored.json`, then run `score tailored`.
7. Finish with a short summary of the scores, the build count, the approved keywords used and any remaining warnings.

**Rules in short** (examples in `reference/rules.md`):
- Facts come only from `base.json`, plus the keywords the judge approved, where `run terms` allows them (`TODO(profile-doc)`).
- Reword using the posting's terms only for the same fact.
- Reorder by relevance. Merging, splitting and dropping the least relevant bullets are allowed.
- Keep numbers exactly as in the sources, and keep every base keyword.
- Fill the page by keeping or restoring relevant base detail, never with filler.
- Fix a short last line by trimming a few words, or by extending the bullet with detail from its own sources.

**Interactive use:**
1. Run `.claude/skills/tailor-resume/scripts/run prepare --template data --posting <file> --out <folder>`.
2. Run `/tailor-resume <folder>` in a Claude Code session at the repo root. When tailoring is needed, it stops to wait for the judge.
3. Run `.venv/bin/python -m app.tailoring --judge <folder>`. It runs the judge as the service does (same isolation, limits and `.env` credential) and writes the ruling and the judge's verdicts to `<folder>/judge/`.
4. Run `/tailor-resume <folder>` again, and find everything, including the draft PDF, under `<folder>/out/`.

The session uses the owner's own login and permission prompts.

### 11. API surface, errors and logging

**Models.** `ResumeMatch` in `app/models.py` has `status` (Literal of the three values), `threshold`, `base_score`/`tailored_score` (int or None) and `added_terms` (list of strings, from `verify`; empty unless tailored). `ResumeCreated.match` describes it in the docs. The handler adds `generated.match` to the 201 body.

**Errors.** `TailoringError(stage, reason, failed_checks=())` lives in `app/tailoring.py`. The handler catches it beside `RenderError` and returns 500 `"Resume generation failed"`. It logs a `tailoring_error` line with `application_id`, `stage`, `reason`, failed check codes, the Claude `subtype` and exit code, and never stdout or stderr text, which can quote the posting. Stages: `posting`, `claude` (before any run), `prepare`, `analysis`, `judge`, `tailoring` (each Claude run and the script after it) and `verify`. Reasons:
- `not_configured`, `cli_missing`, `posting_too_long`, `prepare_failed`
- `claude_auth`, `claude_max_turns`, `claude_budget`, `claude_timeout`, `claude_error:<subtype>`, `claude_exit:<n>` (Decision 9), for whichever run failed or could not start
- `analysis_invalid` (from `judge-input` or `verify`), `judge_invalid`, `script_error` (`judge-input` or `judge-result` crashed), `missing_output`, `check_failed`, `verify_error`

**Request log.** The `resume_request` line gains `match_status`, `base_score`, `tailored_score`, `claude_turns` and `claude_cost_usd` (summed over the runs), and `terms_approved` and `terms_rejected` when the judge step ran, set through `request.state` the way `application_id` already is. The keywords themselves are never logged.

**OpenAPI.** The `/resume` description covers the three statuses, the judge and `added_terms`, the 1–5 minute duration (a client timeout of at least 10 minutes) and what 500 now covers. `ERROR_DESCRIPTIONS[500]` and `ResumeCreated.match` get descriptions. There are still six operations, so the smoke test's count is unchanged.

### 12. Configuration and hosting

**Settings:**
- `claude_code_oauth_token: SecretStr | None`
- `tailoring_model: str = "claude-opus-5-5"`
- `tailoring_timeout_seconds: int` (60–480, default 420), for all the Claude runs of one resume together
- `tailoring_max_budget_usd: float` (> 0, default 3), likewise
- `claude_bin: str = "claude"`

The total stays under 10 minutes: Claude for at most 480 s across its runs, `verify` for at most 120 s (its compile is capped at 90 s), and the other scripts for a few seconds (no compile; capped at 60 s each).

**Hosting scripts:**
- **Install script:**
  - resolves `command -v claude` from the owner's shell `PATH` and renders it as `CLAUDE_BIN` into the plist, which wins over `.env` like `API_DOCS_ENABLED`
  - warns if `claude` is missing, or if `.env` assigns neither credential (checked by name, no value printed)
  - installs pdfplumber through `requirements.txt`
  - runs `python -m app.tailoring --check --live` once after the service starts, and warns without failing if the credential is rejected
- **`python -m app.tailoring --check`** builds the same env the service uses and runs `claude --version` and `claude auth status`, with no model call. It prints, for example, `tailoring: ready (subscription token, claude-opus-5-5, Claude Code 2.1.303)`, `not configured` or `FAILING`.
- **`--check --live`** also sends one minimal prompt (`claude-haiku-5-5`, `--max-turns 1`, no tools) and reports a rejected credential as `FAILING (credential rejected)`. It exists because `claude auth status` only shows that a credential is set; the spike's half-pasted token passed it.
- **Status script:** shows the `--check` result on its `tailoring:` line. It stays offline, so running it costs nothing.
- **Smoke test:** drops `full_job_description` from its synthetic application, PATCHes it to null when it reuses a leftover row, and asserts `match.status` is `no_job_description`.

### 13. Extension point for the full profile document (TODO only)

The first piece exists: `data/PROFILE.md`, a list of skills and abilities that only the judge reads (Decision 15). Tailoring sees it only through approved keywords, which may go in skills lines. When the owner grows it into the full profile document (projects, roles, results):
- `prepare` adds it as source `p`
- bullets may cite `p.*` entries, and approved keywords may follow their evidence there
- every guard checks against the base and the profile together

`TODO(profile-doc)` markers sit in `SKILL.md`, `resume_checks.py`, `app/tailoring.py` (work folder preparation), `data/PROFILE.md` and the README backlog.

### 14. Testing without spending money

- **Script tests** (`tests/test_resume_tool.py` and companions) import the skill's scripts through a path helper in `tests/conftest.py`. They cover:
  - parsing the real `BASE.tex` (4 jobs, 16 bullets, 7 skills lines) and the round trip
  - escaping and backslash rejection
  - the spec's scoring examples, evidence checks and every guard code
  - layout on PDFs compiled from fixtures, skipped without tectonic: base fill near 98.7%, the short last lines of `j4.b1`–`j4.b3` found, a two-page content set and an unbreakable token both failing
  - `verify` end to end on fixture JSON
- **Judge script tests** (`tests/test_resume_terms.py`): missing keywords, profile entries (list items only), the judge's input (no posting text, no importance), every way an approval is accepted or rejected, the ruling's round trip, and the `terms`, `judge-input` and `judge-result` commands. `tests/test_skill_doc.py` checks that the judge skill's example verdicts pass these scripts on the real `BASE.tex` and `PROFILE.md`.
- **`app/tailoring.py` tests** use a fake `claude` (`tests/fake_claude.py`, set as `CLAUDE_BIN`). It records its argv, env and cwd, tells the analysis, judge and tailoring runs apart, then writes fixture outputs or misbehaves in a chosen run. The tests check:
  - the env: one credential and no `API_KEY`; `HOME` and the config dir under `.claude-runtime/`; `TAILOR_PYTHON` and the scrub; cwd = W with the skill present
  - the flags, including the `--settings` block, and no `Write(...)` rule
  - the envelopes the spike recorded mapping to their reasons: a rejected token (`is_error` true, `subtype` `success`, `api_error_status` 401), `error_max_turns` and `error_max_budget_usd`
  - a timeout killing a child `sleep` that the fake started in a process group of its own, and W being removed
  - the three runs in order, the judge's flags (no Bash) and folder (no posting), the budget left passed to each run, a run that cannot start once time or budget is used up, failures named by run, unusable verdicts, no judge run when nothing is missing, a rejected keyword failing the gate, and the gate ignoring a tampered analysis
- **API and docs tests:** the conftest fake returns a `match`. New tests cover the 500 mapping, `match` in the body, the log fields and the `ResumeMatch` schema.
- **No automated test calls the real Claude.** The spike and the rollout tasks do, by hand.

### 15. The judge for keywords the base resume lacks

The first trial (task 4.2, a Perplexity posting) scored 49 before and after tailoring. What the posting asked for and the base resume lacked was mostly abilities the owner's work shows without naming them (testing, reliability, code quality, agent harnesses, context engineering) plus a few things it does not show. The strict rule (no keyword the base resume lacks) could not tell the two apart, so tailoring could only change emphasis. The owner asked for a Claude judge that decides which additions are genuine.

**Flow.** After the analysis run, `judge-input` lists the posting keywords the base resume lacks in every form. If there are none, no judge runs. Otherwise the judge runs in its own folder:

```
$CLAUDE_BIN -p "/judge-resume-terms ." --output-format json --no-session-persistence
  --model $TAILORING_MODEL --fallback-model claude-sonnet-5-5 --effort high
  --max-turns 8 --max-budget-usd <budget left>
  --permission-mode dontAsk --permission-prompts none --strict-mcp-config
  --settings '{"permissions": {"blockReadsOutsideWorkingDirectories": true}}'
  --tools Read,Write,Edit --disallowedTools Bash WebFetch WebSearch Agent "mcp__*"
  --allowedTools "Read(./**)" "Edit(./out/**)"
```

with the same environment as the other runs (Decision 9), `TMPDIR` in its own folder.

**What it sees.** `input.md` holds the base resume's text, the profile list's entries and the keywords with their aliases. It does not hold the posting, the requirements or each keyword's importance. Not knowing what the job wants keeps "does the owner have this?" apart from "would this raise the score?". It also keeps the posting's text, the one untrusted input, away from the judge: only keyword strings of at most 60 characters reach it, marked as data.

**What it decides.** For each keyword, approve or reject. An approval needs evidence, which `judge-result` checks with the scoring's own normalization:
- resume quotes found in the base resume text; the base bullets holding them are recorded as the keyword's evidence bullets
- profile quotes found inside a profile list entry; headings and prose of `PROFILE.md` are not entries

An approval without any evidence found is a rejection. A missing verdict is a rejection. Only a file that is missing or not a verdicts object fails the request (`judge_invalid`), since that means the judge did not do its job.

**Where an approved keyword may go.** Any skills line, and bullets that cite one of its evidence bullets (`misplaced_keyword` otherwise). A keyword approved from the profile list alone goes in skills lines only: the list does not say which job used it. The tailoring run gets the ruling as `judge/terms.json` and reads it through `run terms`, which prints each approved keyword's evidence and where it may go.

**The profile list.** `data/PROFILE.md` holds the abilities the owner has beyond `BASE.tex`, one list item each. The judge treats them as true. Its first entries are the eight the owner named after the trial.

**Why a fresh tailoring run, not a resumed session.** The second `/tailor-resume .` run re-reads the posting and the analysis, a few thousand tokens and a few turns. Resuming the first session would need session persistence, which leaves transcripts with posting text in the config folder. The skill tells the two runs apart by the files present.

**Trial (2026-10-18).** The same stored Perplexity application, through `tailoring.run` with the owner's Pro token:
- 216 s and 40 turns over the three runs, about 0.94 USD estimated.
- The analysis found 19 keywords the base resume lacks. The judge approved 10: agent harnesses, tool interfaces, context engineering, testing, reliability, code quality, full-stack and TypeScript with resume quotes, and post-training and browser technologies from the profile list. It rejected Go, Rust, reinforcement learning, multimodal models, CDP, Playwright, browser extension development, permission architectures and payload classifiers. Playwright was rejected because the profile entry "Browser automation" does not name it.
- Score 38 → 65: keywords 26% → 74%, requirements 50% → 57%. One page, 97.5% fill, 4 builds, no short last lines left. Every added keyword sits in a skills line or in the bullet holding its evidence.
- The first trial's analysis of the same posting scored the base resume 49. The keyword list varies between runs, as the risks below expect.

**Alternatives considered:**
- **Judge after tailoring.** One tailoring run may use implied keywords, and a judge then checks them. Rejected by the owner: a rejected keyword would fail the whole request.
- **The tailoring run judges itself.** It wants the score up, and it reads the untrusted posting. The judge must be separate and must not see the posting.
- **A subagent inside the tailoring run.** The tailoring run would write its prompt, and could write the verdicts file itself.
- **Structured output (`--json-schema`).** Not verified by the spike. Writing `out/verdicts.json` uses the permissions the spike verified.

## Risks / Trade-offs

- [The judge approves too much, such as "Playwright" from a profile entry "Browser automation"] → Its instructions say a tool counts only when named or required by the work shown, and to reject when in doubt. Every approval carries evidence that a script checks. `match.added_terms` shows the owner what was added, and the log counts approvals and rejections for calibration.
- [The judge rejects what the owner has] → The owner lists it in `data/PROFILE.md`, which the judge treats as true.
- [Three runs take longer and cost more than one] → The judge's run is short (one read and one write), and the runs share one time limit and spend cap. The trial measures the totals.

- [A synchronous call now takes 1–5 minutes, and Muse or Funnel may time out] → Document a client timeout of at least 10 minutes and confirm with a real Muse call during rollout. If it fails, an async variant is the follow-up.
- [The Pro plan's limits are shared with the owner's interactive Claude Code use] → The owner starts on Pro anyway; Opus 5.5 ran on it in the spike. A run that hits a limit fails with its reason logged. Adding `ANTHROPIC_API_KEY` to `.env` then moves runs to API billing with no code change, and the status script shows which credential is in use.
- [API-key cost is about 1–2 USD per tailored run, and nothing caps runs per day] → A per-run spend cap. A daily budget is a follow-up.
- [Claude's keyword and requirement list varies between runs, so scores near 70 can flip] → The script does the arithmetic and verifies evidence, the constants live in one place, and scores are logged so the weights and threshold can be calibrated on real postings.
- [Guards that are too strict cause 500s (number tokens in product versions, skills split from "LLMs (Llama, Mistral)")] → In-loop messages say exactly what to fix, and gate failures are logged by code. A rollout task runs several real postings and tunes the rules.
- [Prompt injection in posting text] → Reads, writes and shell commands are confined to W, and only the script and read-only commands run. Commands never see the credential, and there are no network or MCP tools. The posting is marked untrusted, and the repo's own scripts re-check everything at the gate.
- [Claude Code updates itself in `~/.local/bin` and could change flag behavior] → The spike settled the flags against 2.1.303. The status script shows the version. `--check` fails fast when the CLI or its configuration breaks, and `--check --live` when the credential stops working.
- [A `BASE.tex` edit outside the conventions breaks parsing] → `prepare` fails naming the line, and a test runs on the real file. The README lists the conventions.
- [pdfplumber merges words on tightly justified lines] → It is used only for line geometry, never for text. Bullets are found by glyph, and an ID mismatch only weakens the soft check.
- [Parallel requests mean parallel runs] → Each run is isolated, at the cost of more spend and plan usage. A concurrency cap is a follow-up.

## Migration Plan

1. `git pull`. `CLAUDE_CODE_OAUTH_TOKEN` is already in `.env` from task 1. If it is ever regenerated, paste it as one line: `claude setup-token` wraps it inside its box, and a copy can keep that line break. Add `ANTHROPIC_API_KEY` only if Pro limits get in the way. Optionally set the `TAILORING_*` variables.
2. Run `scripts/install_service.sh`. It installs pdfplumber, renders `CLAUDE_BIN`, confirms the credential with one live call, and warns about anything missing.
3. Check that `scripts/service_status.sh` shows `tailoring: ready`, then run the smoke test (no Claude run).
4. Run one real posting end to end (a rollout task) and raise Muse's request timeout.

**Rollback:** check out the previous commit and reinstall. There is no data migration, and older builds ignore the new `.env` variables (`extra="ignore"`). Resume files are replaced per request as before, and `OUTPUT_DIR/.claude-runtime` can be deleted.

## Open Questions

- Calibrating the 50/50 weighting, the 96% target and the 25% short-line cutoff against real postings. These are script constants.
