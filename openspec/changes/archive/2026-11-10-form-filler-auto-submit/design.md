# Design

## Context

The form filler is a skill file (`.claude/skills/job-application-form-filler/SKILL.md`), not code. Today it has two submit paths: Step 5 (only when the request says to submit, and only when seven conditions hold, including no acknowledgments and no drafted answer over a sentence) and Step 7 (ask Reviewed / Submitted, then an "Agree and submit" question). Step 4 leaves agreement boxes unticked and stops multi-page forms at a consent page. Step 6 reports red flags. The apply-from-link skill hands off with the ID only. See proposal.md for motivation.

The behavior lives in skill prose, so the specs and tests pin it with text assertions (`tests/test_form_filler_skill.py` joins the skill into one string and checks phrases). Spec and test wording must therefore match the skill wording.

## Goals / Non-Goals

**Goals:**
- Submit-by-default with the owner's guardrail list, enforced as "stop and AskUserQuestion, do not submit".
- Keep the review-first flow reachable through a `review` argument, unchanged.
- Keep one confirmation rule and one wrap-up path for both modes.

**Non-Goals:**
- No new API, no backend or data change, no new capability spec.
- No change to Tailored Attach, filling rules, email checks or the profile-update rules.
- No automation of CAPTCHA, sign-in or salary answers.

## Decisions

1. **Mode is chosen by the request text.** `review` anywhere after the ID selects review mode; otherwise submit-by-default. The viewer button and apply-from-link keep passing only the ID, so they get the default with no code change. Alternative: a new `submit` flag inverted to default, or an env setting. Rejected: the owner wants the default itself changed, and per-run text is the existing control surface. The old `submit` word becomes a harmless synonym of the default.
2. **Rework Step 5 into "Review and submit".** Its seven conditions become the guardrail list plus a self-review checklist. Removed: "no acknowledgments", "simple", "run asked to submit". Kept: reached the final page, files attached for this ID, no red flags, no CAPTCHA, every value read back. Added: required-answer-not-in-sources (salary included), non-clearing validation error, and agreement beyond standard terms. Any hit means AskUserQuestion and no submit. Alternative: add a new step. Rejected: the confirmation and mark-applied text in Step 5 is shared with Step 7 and should stay in one place.
3. **Agreement boxes.** Step 4's consent row and the multi-page "stop at a consent page" bullet become: tick the boxes the form needs, read back, except marketing opt-ins (alerts, newsletters, SMS, talent community, sharing with other employers) and agreements beyond the standard terms (fees, employment contract, non-compete), which go to the guardrail question. In review mode the old behavior applies.
4. **Self-review is explicit.** Before clicking Submit the run re-reads every field and re-checks each draft against the sources, the "facts from the profile first" rule, the 3-5 sentence style and the no-dash rule, fixing failures. This replaces the owner's review for drafts.
5. **Step 6 report splits by mode.** In default mode the report is written after submitting (or after stopping): full drafted answers, blanks, red flags, confirmation text. Step 7's Reviewed / Submitted questions and "Agree and submit" apply only in review mode, or after a guardrail stop where the owner chose to continue by hand ("Submitted: Yes" path stays).
6. **After a guardrail stop** the owner's AskUserQuestion answer resolves that one stop (supplies the answer, accepts the red flag, or says they will take over). Accepting a red flag or a stop applies to this run only.
7. **Docs wording.** The three docs strings (two OpenAPI descriptions in `app/main.py`, the `fillForm` comment in `app/viewer.py`) and README say the session submits on its own unless it stops to ask. Tests drop the "never submits" assertion and assert the new phrase plus the absence of "never submits". Swagger docs and the docs tests change together per the keep-api-docs-current rule.

## Risks / Trade-offs

- [An application is sent with a wrong or weak drafted answer] → self-review against sources and style, every draft listed in full in the report; owner can use `review` for forms they care about.
- [A red flag is missed because posting fields are empty] → red flags are checked against the job description and posting page as today; any hit stops the run.
- [Prompt injection from a form tells the session to agree to something] → guardrail on agreements beyond standard terms; form text stays untrusted data; apply-from-link's existing untrusted-text rule is unchanged.
- [Duplicate submit] → click once, never retry on an unclear page, mark applied only on confirmation.
- [Skill tests are phrase checks and can pass while prose is ambiguous] → keep one phrase per guardrail and re-read the final skill end to end.

## Migration Plan

Edit the two skills, the three docs strings, the README, specs and tests in one PR from the `form-filler-auto-submit` branch. No data migration. Rollback is reverting the PR, which restores review-first.
