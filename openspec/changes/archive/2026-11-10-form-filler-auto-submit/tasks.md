# Tasks

## 1. Form filler skill

- [x] 1.1 Rewrite the skill description and intro in `.claude/skills/job-application-form-filler/SKILL.md`: submit by default, `review` as the opt-out, no carry-over beyond this default. Verify with a test asserting both phrases.
- [x] 1.2 Step 4: change the consent row and the multi-page "stop at a consent page" bullet to tick needed boxes and read them back, leave marketing opt-ins unticked, and send agreements beyond the standard terms to the guardrail question. Review mode keeps the old rule. Verify with tests for the opt-in list and the beyond-standard-terms list.
- [x] 1.3 Rework Step 5 into review and submit: self-review checklist (every value read back, drafts checked against sources and style), the guardrail list that stops and asks with AskUserQuestion, a single Submit click, and the existing confirmation and mark-applied text. Remove the "no acknowledgments", "simple" and "asked to submit" conditions. Verify with a test per guardrail.
- [x] 1.4 Steps 6 and 7: report every drafted answer in full in the final report, and make the Reviewed / Submitted questions and "Agree and submit" apply only in review mode or after the owner continues by hand. Verify with tests on the report item and the review-only wording.

## 2. Apply-from-link and docs wording

- [x] 2.1 `.claude/skills/apply-from-link/SKILL.md` Step 8: keep "with the ID and nothing else", replace the wording that review and approval apply with the submit-by-default statement. Update `tests/test_apply_from_link_skill.py` (the "submit it" absence check must still hold).
- [x] 2.2 `app/main.py`: change both endpoint descriptions (fill and apply-from-link) to say the session submits on its own unless a guardrail stops it. Update the two assertions in `tests/test_docs.py` to require the new phrase and reject "never submits". Verify with `pytest tests/test_docs.py`.
- [x] 2.3 `app/viewer.py` comment above `fillForm` and the README paragraphs (Fill form, apply-from-link step 6) say the same. Verify with grep for "never submits" and "Nothing is submitted unless" returning nothing outside archived changes.
- [x] 2.4 Check the docs smoke count and any test that counts description text is still right. Verify with the full test run.

## 3. Specs and verification

- [x] 3.1 Run `openspec validate form-filler-auto-submit` and fix any delta errors.
- [x] 3.2 Run the full test suite (`pytest`) and confirm it passes.
- [x] 3.3 Re-read the final form filler skill end to end for contradictions between default and review modes. Open a PR to main from `form-filler-auto-submit`.
