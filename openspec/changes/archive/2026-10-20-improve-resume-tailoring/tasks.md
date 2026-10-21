# Tasks

## 1. Profile facts in the model

- [x] 1.1 In `resume_model.py`/`resume_terms.py`, parse the "Experience" section of the profile into per-job facts `jN.fK`: level-3 headings matched to the job heading's employer by case-insensitive prefix. Skills entries are the list items outside the Experience section. An unmatched heading raises a profile error naming the employer. Verify with new tests in `tests/test_resume_terms.py`: real `PROFILE.md` parses, facts are numbered, skills exclude facts, unknown employer errors.
- [x] 1.2 Add `--profile` to `prepare` and write each job's `facts` into `out/base.json` (not into `text`); a profile error prints `profile_invalid` and exits non-zero. Verify with a `prepare` test on a fixture profile and one with an unknown employer.

## 2. Checks accept facts as sources

- [x] 2.1 In `resume_checks.check_content`, accept `jN.fK` sources of the same job (`missing_source`, `foreign_source`), allow numbers from cited facts (`unsupported_number`), and compare `new_bold_phrase` and `lost_keyword` against base text plus facts. Verify with tests in `tests/test_resume_checks.py` for each spec scenario under "Bullets trace to the same job" and "Numbers come from the cited bullets".
- [x] 2.2 Rename `Approved.bullets` to `sources`. In `resume_terms`, leave keywords present in a fact out of the judge's candidates, and add them to the ruling as approved with the fact IDs and the reason "in the owner's profile facts". Map judge quotes found in facts to fact IDs. Verify with tests for the "Keyword stated in a fact", "Fact keyword elsewhere" and "Quote from a fact" scenarios.
- [x] 2.3 Keep the judge's rejection reason in `rule` (fallback "rejected by the judge"). Verify with tests for "Judge's reason kept" and "No reason given", and that the reason reaches `verify`'s `rejected_terms`.
- [x] 2.4 Add an "Experience facts" section, per job with IDs, to the judge's `input.md`. Update `judge-resume-terms/SKILL.md` to say facts are true, quotable, and place a keyword in bullets citing them. Verify `tests/test_skill_doc.py` still passes and the input test checks that no posting text or importance appears.

## 3. Echoed phrasing and keyword guidance

- [x] 3.1 Add the soft `echoed_phrase` check (runs of 3+ tokens shared with the posting, 2+ non-stopwords, not in the cited sources). `build` reads `posting.md` from the work folder and skips the check without one. Verify with tests for the "Copied phrase", "Phrase the owner already uses" and "Soft finding" scenarios.
- [x] 3.2 Rewrite the keyword section of `reference/scoring.md`: searchable terms only, the two-postings test, and the OpenAI examples. Add the every-part rule for `met`. In `reference/layout.md`, say how to act on `echoed_phrase`. Verify `tests/test_skill_doc.py` passes and the scoring.md example analysis still validates.

## 4. Requirement-driven tailoring

- [x] 4.1 Validate `out/coverage.json` in `build` (requirement IDs exist; source IDs exist and are bullets or facts). A missing or broken plan is a `fix` line. Have `score tailored` print `planned, not met:` lines. Verify with tests for the "Plan cites unknown sources" and "Still partial after tailoring" scenarios.
- [x] 4.2 Update `tailor-resume/SKILL.md`:
  - a coverage-plan step after `run terms`
  - revise while `planned, not met` lines remain and builds are left
  - no stopping just for passing 70
  - describe the work in the owner's words

  In `reference/rules.md`, document fact sources (`jN.fK`) with an example, replacing the "TODO(profile-doc)" notes. Verify `tests/test_skill_doc.py` and that the rules.md example still passes `check_content`.

## 5. Service and gate

- [x] 5.1 In `app/tailoring.py`, pass `--profile PROFILE` to `prepare` and `verify`; `verify` builds facts from its own profile copy. Remove the `TODO(profile-doc)` markers this change resolves (tailoring.py, resume_checks.py, SKILL.md). Verify with `tests/test_tailoring.py` (argv includes the profile) and a `tests/test_resume_verify.py` case for "Run adds a profile fact" failing with `missing_source`.
- [x] 5.2 Map a `profile_invalid` prepare failure to a clear `TailoringError` code. Verify with a test using an unknown-employer profile and the fake claude, checking that no Claude run starts.

## 6. Owner's profile and end-to-end check

- [ ] 6.1 Add an "Experience" section to `data/PROFILE.md` with a "### Capital One" draft of the confirmed facts: benchmark evaluations of the agent; comparing different models, reasoning settings and prompt tuning; feedback loops. Update the file's intro text, and have the owner approve the wording before commit. Verify that `prepare` on the real files lists the facts as `j1.f1`… and that the full test suite passes (`pytest`).
- [ ] 6.2 Regenerate the OpenAI application's resume against the running service. Compare the new report with the old one: requirement coverage, `echoed_phrase` gone, judge reasons shown, no posting phrases like "long-horizon workflows" in bullets. Share the result with the owner.

## Workflow follow-up

- Sync specs and archive the change after the owner reviews the regenerated OpenAI resume.
- Push to main (owner's standing preference).
