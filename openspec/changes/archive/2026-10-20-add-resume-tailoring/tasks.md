# Tasks

## 1. Spike: confirm headless Claude Code behavior (scratch folder, no project code)

- [x] 1.1 In a scratch folder outside the repo, build probe work folders. Each holds a `probe` skill (`disable-model-invocation: true`, `allowed-tools: Bash(${CLAUDE_SKILL_DIR}/scripts/run *)`) and a `scripts/run` launcher that runs `probe.py` with `$TAILOR_PYTHON`. Run `claude -p "/probe ."` with the Decision 9 flags and an environment built from scratch: an empty `HOME`, a config folder and a `PATH` entry containing spaces, and the `CLAUDE_CODE_OAUTH_TOKEN` the owner made with `claude setup-token` and keeps in the main checkout's `.env`. Run A uses the production flags, and run B adds `--restricted`. Verify:
  - the skill expands, the launcher runs, and a Write inside `out/` is allowed
  - these are denied: `ls ~`, `cat` and Read of a file outside the folder, Writes outside `out/`, and `python3 -c`
  - the script's environment has no credential, and nothing lands in the owner's `~/.claude`
  - the JSON envelope has `is_error`, `subtype`, `num_turns`, `total_cost_usd` and `modelUsage`

  Record in design.md Decision 9 which flag set works
- [x] 1.2 With the same probe, record in design.md Decision 9 the exit codes and `subtype` values for `--max-turns 1` (run C), `--max-budget-usd 0.01` (run D), and SIGTERM to Claude's process group while `probe.py` holds a child `sleep` (run E: expect 143, and check that the `sleep` dies). Verify by the recorded values matching what `app/tailoring.py` maps in 5.3

## 2. Skill scripts: content model, renderer and layout checks

- [x] 2.1 Scaffold `.claude/skills/tailor-resume/` (`SKILL.md` with frontmatter only, `scripts/`, `reference/`) and the executable `scripts/run` launcher. The launcher runs `resume_tool.py` with `$TAILOR_PYTHON` when it is set, and otherwise with the repo's `.venv/bin/python`, found relative to the script. Add `pdfplumber>=0.11,<0.12` to `requirements.txt`, and add a helper in `tests/conftest.py` that puts the skill's `scripts/` directory on `sys.path` for tests. Verify that `.venv/bin/pip install -r requirements-dev.txt` succeeds and `.venv/bin/python -c "import pdfplumber"` runs, and that a test shows `run` uses `TAILOR_PYTHON` when set and the repo venv otherwise
- [x] 2.2 Implement `scripts/resume_model.py` and the `prepare` subcommand of `scripts/resume_tool.py` (`--template --posting --out`):
  - the `BASE.tex` parser: skills lines with items split on commas outside parentheses; jobs `j1`–`j4` with bullet IDs `jN.bM`, fixed headings and the plain `text`
  - TeX↔markup conversion (`**bold**`, `*italic*`)
  - escaping of `% & $ # _ { } ~ ^` and backslash rejection
  - the splice renderer and its line map

  Verify with `tests/test_resume_model.py`: the real `BASE.tex` gives 4 jobs, 16 bullets and 7 skills lines. Rendering the base model reproduces `BASE.tex` except for `\item` indentation. "R&D" and "30%" are escaped and `\input{x}` is rejected. A skills line with an unknown command fails naming its line number. `prepare --help` documents the arguments
- [x] 2.3 Implement compiling and layout measurement in `scripts/resume_checks.py`:
  - tectonic `-X compile --untrusted --keep-logs` in its own temp dir with only the TeX and `resume.cls`, a 90 s timeout, and `TECTONIC_CACHE_DIR` from the environment
  - page count; fill `(bottom − 36)/720`; lines free from the median pitch
  - short last lines (< 25% of the width) mapped to bullet IDs by order
  - overfull hboxes mapped through the line map, ignoring those outside spliced content

  Verify with `tests/test_resume_checks.py` (skipped without tectonic): the base model gives 1 page, fill within 0.5 points of 98.7%, and short last lines on `j4.b1`, `j4.b2` and `j4.b3`. Content padded to two pages fails `one_page`. An 80-character unbreakable token fails `overfull_line`. The header's warning is ignored. The temp dir is removed and the template files are unchanged

## 3. Skill scripts: scoring, guards and the gate

- [x] 3.1 Implement `scripts/resume_score.py` and `resume_tool.py score base|tailored`:
  - normalization; keyword matching with aliases and `(?<!\w)…(?!\w)` boundaries
  - evidence verification: at least 3 words, found in the scored text, otherwise unverified
  - the weighted floor score, with threshold 70, weights and bounds as constants
  - analysis validation (5–40 keywords, 3–15 requirements, importance and status values)
  - writing `out/score_base.json` or `out/score_tailored.json` and printing the score, decision, unverified requirements and keywords the base lacks

  Verify with `tests/test_resume_score.py` covering every scenario in `specs/resume-tailoring` (60% keyword coverage, 60% requirement coverage, a combined 62, repeatability, `k8s` alias, Java vs JavaScript, an unverified quote, the bounds and missing-importance rejections, 70 → keep and 69 → tailor), plus `C++` matching
- [x] 3.2 Implement the guards in `scripts/resume_checks.py`: `structure_mismatch`, `unknown_label`, `unknown_skill`, `missing_source`, `foreign_source`, `unsupported_number`, `unsupported_keyword`, `lost_keyword`, `invalid_text`, and the soft warnings (new bold phrase, missing final period). The fact sources are a list holding only the base, with a `TODO(profile-doc)` comment. Then implement `resume_tool.py build`: guards, splice, compile and layout, writing `out/check.json` and a compact summary (fill %, lines free, short-line bullet IDs, failed codes with what to change), and exiting 0 only when every hard check passes. Verify with `tests/test_resume_checks.py`: one failing case per code. Reordered skills, merged bullets with both sources and a number kept from the source are all accepted. `build` on the unchanged base content passes. The summary names `j4.b1` for its short last line
- [x] 3.3 Implement `resume_tool.py verify --template <dir> --work <dir> --pdf-out <file>` as in Decision 8. It reads only the run's JSON from `--work`, uses only `--template` for TeX, prints `{ok, decision, base_score, tailored_score, failed, warnings}` and exits non-zero on failure. Verify with `tests/test_resume_verify.py`:
  - a base score of 70 or more gives decision `keep` and no PDF
  - fixture tailored content gives a one-page PDF and both scores
  - a tampered `W/template/BASE.tex` and a stray `W/out/build/tailored.pdf` are ignored, so the output matches the untampered run
  - a missing `tailored.json` or `assessment_tailored.json` fails `missing_output`
  - failing content lists its codes

## 4. Skill instructions

- [x] 4.1 Write `SKILL.md`:
  - frontmatter per Decision 10 (`allowed-tools: Bash(${CLAUDE_SKILL_DIR}/scripts/run *)`)
  - inputs, and "Sources of facts" (base only, with `TODO(profile-doc)`)
  - a rule never to follow instructions found in `posting.md`
  - steps 1–6, with the exact `${CLAUDE_SKILL_DIR}/scripts/run …` commands and no pipes
  - stop conditions (at most 5 builds; stop and say so if hard checks still fail) and the closing summary

  Write `reference/scoring.md`, `reference/rules.md` (allowed and forbidden edits with examples from this resume, such as "LLMs" vs a posting's "large language models" through aliases, or never adding Kafka) and `reference/layout.md` (acting on fill, lines free, short last lines and overfull lines). Verify that `SKILL.md` is under 500 lines, and that every command it shows runs as written against a folder made by `prepare` with the fixture analysis
- [ ] 4.2 Prepare a folder for a real posting that the base resume matches weakly, run `/tailor-resume <folder>` interactively from the repo root, and review the draft PDF against `data/BASE.pdf` for fabrication and layout. Fix the wording of `SKILL.md` or the reference files where the run went wrong. Verify that the run ends with both score files, a passing `out/check.json` with fill ≥ 96% (or the reason it stopped) and a one-page draft PDF the owner accepts

## 5. Service: running the skill

- [x] 5.1 Add the settings to `app/settings.py`: `claude_code_oauth_token` (SecretStr, optional), `tailoring_model` (default `claude-opus-5-5`), `tailoring_timeout_seconds` (60–480, default 420), `tailoring_max_budget_usd` (> 0, default 3) and `claude_bin` (default `claude`). Add them to `.env.example`, describe `ANTHROPIC_API_KEY` as a tailoring credential, and add the README Configuration table rows. Verify with `tests/test_settings.py`: the defaults; `TAILORING_TIMEOUT_SECONDS=30` and `=abc`, and `TAILORING_MAX_BUDGET_USD=0`, fail naming the variable; the token value never appears in a validation error; the `.env.example` entries are present
- [x] 5.2 In `app/tailoring.py`, implement:
  - posting usability: null, blank or under 50 words gives `no_job_description`; over 60,000 characters raises `TailoringError("posting", "posting_too_long")`
  - the work folder: `mkdtemp("tailor-")`, the skill copy, the template copy, and `posting.md` with the untrusted-data heading and space-only wrapping, with a `TODO(profile-doc)` comment where a profile would be copied
  - the `prepare` call with the service's python and the repo copy of the script
  - `MATCH_THRESHOLD = 70`

  Verify with `tests/test_tailoring.py`: the word and size limits; the folder layout; wrapping that keeps every word intact; a test that `MATCH_THRESHOLD` equals the script's constant
- [x] 5.3 Implement the Claude run in `app/tailoring.py` per Decision 9:
  - the command and flags, including the `--settings` block, with no `Write(...)` rule and no `--restricted`
  - the from-scratch environment:
    - one credential, with the API key taking precedence, and no `API_KEY`
    - `HOME` and `CLAUDE_CONFIG_DIR` under `<OUTPUT_DIR>/.claude-runtime/`, created with mode 700
    - `TAILOR_PYTHON`, `CLAUDE_CODE_SHELL`, `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1` and the other variables Decision 9 lists
  - `start_new_session`, and on timeout: record Claude's descendants, SIGTERM the group, wait 15 s, then SIGKILL the group and the recorded descendants
  - envelope parsing:
    - failure on a non-zero exit or `is_error`
    - the reasons `claude_auth`, `claude_max_turns`, `claude_budget`, `claude_timeout`, `claude_error:<subtype>` and `claude_exit:<n>`
    - `not_configured`, with no subprocess started, when no credential is set; `cli_missing`

  Verify with `tests/fake_claude.py` (set as `CLAUDE_BIN`) and `tests/test_tailoring.py`:
  - the recorded argv has every flag and no `Write(` rule
  - the env has exactly one credential, no `API_KEY`, and the listed variables
  - cwd holds the skill and `posting.md`
  - the spike's envelopes map to their reasons: a 401 with `subtype` `success`, `error_max_turns` and `error_max_budget_usd`
  - a 1 s timeout kills a child `sleep` that the fake started in a process group of its own
  - no credential means no subprocess
- [x] 5.4 Implement the gate call (`verify` from the repo copy with a 120 s timeout, into a service-owned temp dir), result mapping, cleanup of W and V in `finally`, and `python -m app.tailoring --check`. The check builds the same env, runs `claude --version` and `claude auth status`, and prints ready, not configured or FAILING with the credential kind, model and CLI version, never the credential. `--check --live` also sends one minimal prompt (`claude-haiku-5-5`, `--max-turns 1`, no tools) and reports a rejected credential as `FAILING (credential rejected)`. Verify in `tests/test_tailoring.py`:
  - keep and tailor results return the right match and bytes
  - a `verify` failure raises `check_failed` with its codes
  - W and V are gone after success, after a Claude failure and after a `verify` failure
  - `--check` output contains no credential value and makes no model call
  - `--check --live` maps a fake 401 envelope to the rejected-credential message
- [x] 5.5 Rework `app/generation.py`: `generate_output` routes an unusable posting to `render_pdf()` with match `no_job_description`, the keep decision to `render_pdf()` with the base score, and the tailor decision to the gate's PDF. `GeneratedFile` gains optional `match` and `run` fields, and the stub docstring is replaced. Verify `tests/test_generation.py` for each route, and that `TailoringError` propagates

## 6. API, logging and API docs

- [x] 6.1 In `app/models.py`, add `ResumeMatch` and `ResumeCreated.match`. In `app/main.py`:
  - put `match` in the 201 body
  - catch `TailoringError` beside `RenderError` and return 500 `{"ok": false, "message": "Resume generation failed"}`, logging a `tailoring_error` line with stage, reason, codes, subtype and exit code only
  - add `match_status`, `base_score`, `tailored_score`, `claude_turns` and `claude_cost_usd` to the `resume_request` line through `request.state`
  - update the conftest fake to return a match

  Verify with `tests/test_api.py`:
  - the exact key set including `match`, and the three `match` shapes from the spec
  - a `TailoringError` gives exactly that 500 body, writes no file and leaves a previous resume unchanged
  - the log fields appear, with no posting text, skill names or paths
  - the updated one-log-line test, and the health-during-slow-generation test, still pass
- [x] 6.2 Update the OpenAPI text: the `/resume` description (statuses, a 1–5 minute duration and a client timeout of at least 10 minutes, what 500 covers), `ERROR_DESCRIPTIONS[500]`, and the field descriptions on `ResumeMatch` and `ResumeCreated.match`. Verify with `tests/test_docs.py`: the 201 schema has `match` with a `status` enum of exactly the three values and nullable integer scores; the description mentions the duration; the operation count is still six, so `scripts/smoke_test.sh` keeps expecting 6
- [x] 6.3 Update the README:
  - the `POST /resume` table row and example response with `match`
  - a new "How resumes are tailored" section: the workflow and threshold, the score, the no-fabrication rules, the one-page and fill rules, statuses, timing, failures, cost and plan limits, and running `/tailor-resume` by hand
  - the stub text replaced, and a backlog line for the profile document

  Verify that the example response matches a test-client response and that every command shown runs as written

## 7. Hosting scripts

- [x] 7.1 Add `CLAUDE_BIN` to the `EnvironmentVariables` of `deploy/local.job-hunt-hq.plist.template`. In `scripts/install_service.sh`:
  - resolve `command -v claude` and render it into the plist
  - warn without failing when the CLI is missing or `.env` assigns neither credential; the check is by name only, and the warnings name `claude setup-token` and `ANTHROPIC_API_KEY`
  - after the service starts, run `.venv/bin/python -m app.tailoring --check --live` once, and warn without failing when the credential is rejected, saying to paste the token as one line

  Update the README prerequisites. Verify with new cases in `scripts/test_install_service.sh`: the CLI found is rendered and passes `plutil -lint`; a missing CLI warns while the install completes; no credential warns and prints no value; a rejected credential (stubbed `--check --live`) warns while the install completes
- [x] 7.2 Add a `tailoring:` line to `scripts/service_status.sh` from `.venv/bin/python -m app.tailoring --check`, and document it in the README status section. Verify with status cases in `scripts/test_install_service.sh`: ready, not configured and failing outputs, with no credential printed
- [x] 7.3 Change `scripts/smoke_test.sh`:
  - the synthetic application has no `full_job_description`
  - a reused (200) application gets `PATCH {"full_job_description": null}` before `POST /resume`
  - the test fails unless `match.status` is `no_job_description`

  Update the usage text and the README smoke-test line. Verify with new cases in `scripts/test_smoke_test.sh` (fresh run, leftover with posting text where the PATCH is sent before the POST, wrong status fails), then run `sh scripts/test_smoke_test.sh` and confirm it prints no `FAIL`

## 8. Integration and rollout

- [x] 8.1 Run the whole suite and validation: `.venv/bin/python -m pytest`, `sh scripts/test_smoke_test.sh`, `sh scripts/test_install_service.sh` and `openspec validate add-resume-tailoring --strict`. Verify that all pass with no `FAIL` output
- [ ] 8.2 On the Mac mini, the token is already in `.env` from task 1, so run `scripts/install_service.sh`. Verify that its live credential check passes, that `scripts/service_status.sh` shows `tailoring: ready` and that `API_KEY=... scripts/smoke_test.sh https://sunils-mac-mini.tailf96439.ts.net` passes
- [ ] 8.3 Record three real postings (one the base resume should match strongly, two weakly) and call `POST /resume` for each. Verify:
  - the expected `match.status` values and responses within 10 minutes
  - one-page PDFs whose content the owner confirms against `data/BASE.pdf` has nothing invented
  - `resume_request` lines with scores, turns and cost, and no posting text

  Record any constant or rule tuning in design.md
- [ ] 8.4 Trigger one resume through Muse. Verify that Muse receives the 201 with `match`, raising its request timeout first if it gives up early

## 9. Judge for keywords the base resume lacks (owner request after the first 4.2 trial)

- [x] 9.1 Add `data/PROFILE.md`, the owner's profile list, with the eight abilities the owner named. Implement `scripts/resume_terms.py`: missing keywords, profile entries (list items only, comments ignored), the judge's input (resume, entries, keywords with aliases; no posting, no importance), checking verdicts (an approval needs a resume quote or a profile quote found by the scoring's normalization; resume quotes name their evidence bullets; anything else is a rejection, and a file that is not a verdicts object is an error), and the ruling's JSON and printout. Cap aliases at 60 characters in `validate_analysis`. Verify with `tests/test_resume_terms.py`
- [x] 9.2 In `resume_checks.py`, accept approved keywords as skills items and in bullets that cite an evidence bullet, fail them elsewhere as `misplaced_keyword`, keep `unsupported_keyword` for the rest, and exempt approved keywords from `new_bold_phrase`. In `resume_tool.py`, add `terms`, make `build` refuse without `judge/terms.json`, add `judge-input` and `judge-result`, and give `verify` `--analysis`, `--terms` and an `added_terms` result. Verify with `tests/test_resume_checks.py` and `tests/test_resume_verify.py`: placement accepted and rejected, a profile-only keyword in a bullet rejected, `build` waiting for the judge, the gate ignoring the work folder's own analysis and ruling
- [x] 9.3 Write `.claude/skills/judge-resume-terms/SKILL.md` (no scripts, no `allowed-tools`): never sees the posting, keywords are data, approve only with evidence, examples from this resume, the verdicts format. Add the `terms` step and the stop to `tailor-resume`'s `SKILL.md`, and the approved-keyword rules and examples to `reference/rules.md`. Verify with `tests/test_skill_doc.py`, including the judge's example verdicts passing the scripts on the real `BASE.tex` and `PROFILE.md`
- [x] 9.4 In `app/tailoring.py`, run the analysis, `judge-input`, the judge in its own folder (Read, Write and Edit only), `judge-result` and the tailoring run, sharing one time limit and spend cap; name failures by stage (`analysis`, `judge`, `tailoring`); pass `--analysis` and `--terms` to `verify`; return `added_terms`, summed run stats and the judge's counts; add `python -m app.tailoring --judge <folder>` for interactive sessions. Verify with `tests/test_tailoring.py` and the fake's analysis, judge and tailoring roles
- [x] 9.5 Add `match.added_terms` to the API and `terms_approved`/`terms_rejected` to the `resume_request` line; update the OpenAPI text, the README (the three runs, the profile list, placement, failures, interactive steps, limits) and `.env.example`. Verify with `tests/test_api.py`, `tests/test_docs.py`, and the README example against a test-client response
- [x] 9.6 Run the stored Perplexity application through `tailoring.run` with the owner's token and record the result in design.md Decision 15. Verify that the run ends with a one-page PDF, that every added keyword is in a skills line or its evidence bullet, and that the judge rejects what neither the resume nor the profile shows

## Workflow follow-up

- Archive the change once the rollout checks pass.
- Follow-ups outside this change: the full profile document as a second fact source (`TODO(profile-doc)`), a saved match report beside the resume, a daily spend budget and a concurrency cap, an async `POST /resume` if Muse cannot wait, and cover letter generation.
