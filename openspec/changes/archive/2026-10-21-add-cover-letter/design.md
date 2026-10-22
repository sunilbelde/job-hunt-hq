# Design

## Context

`POST /resume` (in `app/main.py`) runs `generate_output` (in `app/generation.py`). When a resume needs tailoring, that calls `app/tailoring.run`, which drives the `tailor-resume` skill headlessly. The machinery around those runs is already built and tested: a throwaway work folder, an environment built from scratch with one hidden credential, `--allowedTools` limited to the skill's `run` script, a shared time limit and spend cap (`_Runs`), process-tree cleanup, and a final gate (`verify`) that runs the repo's own copy of the scripts. `resume_model` parses `BASE.tex` and `PROFILE.md` into jobs, bullets `jN.bK`, facts `jN.fK` and skills lines, and escapes TeX. `resume_checks` has the number check and the echoed-phrase check, and `resume_score` validates a posting analysis (`keywords` and `requirements` with `importance`). `storage.cover_letter_path(resume_path)` and the `cover_letter_path` field in `/resume` are placeholders. Nothing writes the file.

See proposal.md for why letters are generated on request only, and specs/ for the behavior.

## Goals / Non-Goals

**Goals:**
- Reuse the resume pipeline's isolation, limits, parsing and checks rather than building a second copy of them.
- One skill and one set of checks for both the tailored letter and the base letter, so the two cannot drift apart.
- A letter that reads as written by the owner: concrete, sourced and not padded, in 250–400 words.

**Non-Goals:**
- Showing letters in the resume viewer, or storing a letter report in the application store. The response's `text` and the saved PDF are enough for now.
- Scoring a letter against the posting the way resumes are scored. Letters have no threshold and are always tailored.
- A judge run for the posting keywords the owner lacks. A letter simply may not name them (see Decision 5).
- Serving the base letter, or using it as an input to tailored letters.

## Decisions

### 1. One skill, `write-cover-letter`, with two modes chosen by the work folder
If `posting.md` is present, the skill tailors the letter to it. Without one, it writes the generic base letter. Both modes share the source, structure, number, length, TeX and page checks. Only tailored mode adds the posting checks: company and role, keywords, requirements and echo.
- *Alternative*: two skills (`tailor-cover-letter`, `draft-base-cover-letter`). Rejected because the rules would be duplicated and drift apart, and the base letter would stop being a faithful sample of what tailored letters look like.

### 2. The skill's scripts reuse `tailor-resume`'s modules instead of copying them
`.claude/skills/write-cover-letter/scripts/` holds `letter_tool.py` (the CLI) and `letter_checks.py`. Its `run` launcher works like `tailor-resume`'s: it uses `TAILOR_PYTHON` or the repo's `.venv`. `letter_tool.py` itself puts `../../tailor-resume/scripts` on `sys.path`, so it works the same when run directly. That gives the letter scripts `resume_model` (parsing, IDs, TeX escaping, `compile_tex`), the number and echo helpers in `resume_checks`, and the analysis validation in `resume_score`. The service copies both skill folders into the work folder, so the imports resolve there too. The run's `--allowedTools` still allows only the letter skill's `run`.
- *Alternative*: move the shared code into a common package. That is cleaner, but it is a refactor of the resume skill that this change does not need. Revisit if a third skill appears.
- *Alternative*: put letter commands into `resume_tool.py`. Rejected because it mixes two skills' CLIs and the resume skill's docs tests.

### 3. Claude writes structured JSON, and scripts produce the whole letter
The run writes `out/letter.json`:
```json
{"paragraphs": [
  {"role": "opening", "text": "..."},
  {"role": "body", "text": "...", "sources": ["j1.b2", "j1.f3"], "requirements": ["R1", "R3"]},
  {"role": "body", "text": "...", "sources": ["j3.f4"], "requirements": ["R2"]},
  {"role": "closing", "text": "..."}]}
```
`run build` checks it, then renders `out/letter.tex` from it and compiles it. The page uses `resume.cls` with the `\name`/`\address` header copied from `BASE.tex`'s preamble, so the contact details have one source and the letter matches the resume. The scripts also set the date, the greeting ("Dear <Company> Hiring Team," or "Dear Hiring Manager,"), the paragraphs and the sign-off ("Sincerely," and the `\name`). The response's `text` is rendered from the same JSON, so the PDF and `text` cannot differ.
- *Alternative*: Claude writes TeX or free Markdown. Rejected because that makes injection possible, the header and sign-off could drift, and paragraphs could not carry their sources.

### 4. Tailored mode runs its own posting analysis
Step one of the run writes `out/analysis.json` (keywords and requirements) in the `tailor-resume` format, and `run analyze` validates it with `resume_score`'s validation. The letter's body paragraphs then name requirement IDs from it. The resume run's analysis is not reused, because a letter must work without a resume and the stored report is the viewer's, not a contract.
- *Trade-off*: Claude's own analysis is what the keyword check runs against, so an analysis that leaves out a keyword weakens that check for that keyword. The same trust applies to resume tailoring today. The source and number checks do not depend on it.

### 5. Keyword rule: posting keywords in the letter must exist in the base resume text or `PROFILE.md`
This is checked case-insensitively with aliases, as `resume_checks` matches keywords today. There is no judge run. The resume needs the judge to put new skills on the page, but a letter only describes work, and the profile already lists what the owner claims. This keeps it to one Claude run per letter.
- *Alternative*: run the judge for letters too. Rejected because it adds a run and roughly doubles the cost, for little gain, since the source rule already limits the claims.

### 6. The echo check is hard for letters
The gate fails on `echoed_phrase`, using `resume_checks`' echo detection with the paragraph's cited sources as allowed text, plus the stored company and role. A copied phrase in prose is the clearest sign of an AI-written letter. Resume bullets keep the soft check, which this change does not touch.
- *Risk*: more 500s. Mitigation: `run build` reports echoes as `fix` lines, the skill gets up to 5 builds to reword, and the gate's check is the same function, so a build that passes will pass the gate.

### 7. `app/cover_letter.py` reuses `app/tailoring.py`'s run machinery
`claude_command` is generalized to take the skill's name, and the work-folder preparation is factored so it can copy a list of skill folders. `_Runs`, `claude_env`, `_run_claude`, `_ready` and `TailoringError` are reused unchanged, with stages `prepare`, `letter` and `verify`. `cover_letter.run(application, settings)` returns `LetterResult(pdf, text, run: RunStats)` or raises `TailoringError`. The gate is `letter_tool.py verify --template data --profile data/PROFILE.md --work <w> --analysis <gate copy> --pdf-out <gate>/letter.pdf --text-out <gate>/letter.txt`, run from the repo's own copy. As with resumes, the analysis is snapshotted into the gate folder before the gate reads it.
- Settings: the existing `tailoring_model`, `tailoring_timeout_seconds` and `tailoring_max_budget_usd`. No new environment variables. The turn limit is 30 (`LETTER_MAX_TURNS`), because a letter has fewer build cycles than a resume.

### 8. Endpoint shape mirrors `POST /resume`
The handler's order is key, body, ID, store lookup, posting check (422 before any run), the run in a thread pool, `storage.save_cover_letter`, then the 201 response. The body is validated by a `CoverLetterRequest` model, the same shape as `ResumeRequest`, which keeps the docs separate. The log event is `cover_letter_request`, with the same middleware pattern (`note_generation`) for turns and cost. No report is stored.
- An unusable posting is a 422 rather than a 409, because it is about the request's target data. The message names the fix ("add full_job_description"). A posting over 60,000 characters is a 422 too: unlike resumes, there is no unscored result to fall back to.

### 9. Storage: `save_cover_letter` shares the atomic write with `save_resume`
`LocalStorage._write(path, content)` takes the existing mkstemp, fsync and `os.replace` body. `save_resume` and `save_cover_letter` compute their paths with `resume_path(root, company, id)` and `cover_letter_path(root, company, id)`, and both get the same escape check. `cover_letter_path` changes signature. Its only callers are `main.py` (removed) and the tests.

### 10. Base letter files live in `data/` and are committed
`run publish-base --work <w> --data data` is allowed only from an interactive session, because the service's `--allowedTools` cannot reach it: it writes outside the work folder. After a passing build in base mode, it writes `data/COVER_LETTER.md` (paragraphs separated by blank lines, greeting and sign-off included) and `data/COVER_LETTER.pdf`. `run render-base --data data` re-renders the PDF from an edited `.md`, with escaping and the one-page check but no source checks, because the owner's own words are trusted like `PROFILE.md`. `app/rendering.TEMPLATE_SUFFIXES` does not include `.md` or `.pdf`, so these files never reach resume renders.

## Risks / Trade-offs

- **[Removing `cover_letter_path` breaks Muse if it reads the field]** → Called out as BREAKING in the proposal and README. The owner updates Muse's action schema in the same rollout (see Migration Plan).
- **[Prose claims are harder to check than bullets]** → Sources, numbers, keywords and echoes are checked mechanically. Softer claims ("I led…" when a source says "contributed") rely on the skill's rules, which require the wording to stay within what the cited sources say. The gate cannot fully enforce this, so the owner should skim each letter before sending it.
- **[The letter's own analysis can be thin]** → See Decision 4. The skill's reference reuses `tailor-resume/reference/scoring.md` for how to list keywords, so its analyses match the resume's in quality.
- **[Company facts in the opening]** ("your work on X") come from the posting and can't be checked against the owner's sources → The echo check stops copying. The rules allow at most one sentence about the company, and it must be drawn from the posting or `why_it_fits`.
- **[Cross-skill import coupling]** → If `resume_model`'s API changes, letter scripts break. Mitigation: the letter scripts' tests run in the same suite, so the break shows up in CI right away.
- **[Cost]** → One run of up to `tailoring_max_budget_usd`, requested only when needed.

## Migration Plan

1. Implement, then run the tests and the smoke test (11 operations, cover letter 422).
2. The owner drafts the base letter once: `/write-cover-letter` in a session on a base-mode work folder, then `run publish-base`. They review and edit `data/COVER_LETTER.md`, then run `run render-base` and commit.
3. Reinstall the service (`scripts/install_service.sh`), then update Muse: drop `cover_letter_path`, and add a `POST /cover-letter` action with a timeout of at least 10 minutes.
4. Rollback: revert the commit and reinstall. Saved letters stay on disk, which is harmless.
