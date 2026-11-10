# Proposal

## Why

The owner now trusts the form filler and wants it to finish applications on its own: tick the agreement boxes, review its own work, submit and mark the application applied, instead of waiting for the owner at the end of every run. This is a standing authorization from the owner, so the default for `/job-application-form-filler <id>` changes from review-first to submit-by-default, with firm stop conditions and an opt-out.

## What Changes

- `/job-application-form-filler <id>` submits by default, including when started by the viewer's Fill form button or the apply-from-link handoff. No submit word is needed in the request.
- **BREAKING**: today's Step 5 conditions "no acknowledgments", "simple" (no drafted answer longer than a sentence) and "run asked to submit" no longer gate submission. The form filler ticks the consent, privacy, GDPR, terms and "I certify" boxes the form needs, and submits drafted open-ended answers without the owner's review.
- The run reviews the filled form itself before submitting: every value read back, each drafted answer checked against the sources and style rules.
- Guardrails stay: the run stops and asks with AskUserQuestion, without submitting, for a required answer the sources do not give (salary included), any Step 6 red flag, files not attached for this application ID, sign-in / CAPTCHA / bot check, a validation error that does not clear, or an agreement beyond the standard application terms (costs money, employment contract, non-compete).
- Optional marketing opt-ins (job alerts, newsletters, SMS, talent community, sharing with other employers) stay unticked.
- `/job-application-form-filler <id> review` keeps today's review-first flow (Step 7 questions and "Agree and submit").
- Every drafted open-ended answer is listed in full in the final report.
- The apply-from-link handoff wording changes: it still passes only the ID, but no longer says nothing is submitted unless the owner approves.
- The viewer's Fill form comment, the OpenAPI descriptions of `POST /viewer/application/{id}/fill` and `POST /viewer/apply-from-link`, and the README stop saying the session never submits unless asked.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `application-form-filling`: adds the submit-by-default flow, agreement ticking, self-review, stop conditions, marketing opt-in rule, report of drafted answers and the `review` opt-out.
- `apply-from-link`: the handoff requirement and scenario no longer promise that nothing is submitted without the owner's approval.
- `api-docs`: the Fill form and apply-from-link endpoint descriptions say the session submits on its own unless it stops on a guardrail, instead of "never submits unless asked".

## Impact

- `.claude/skills/job-application-form-filler/SKILL.md` (intro, Step 4 consent row and multi-page stop, Step 5, Step 6 items 8 and 9, Step 7), `.claude/skills/apply-from-link/SKILL.md` (Step 8).
- `app/main.py` (two endpoint descriptions), `app/viewer.py` (comment at `fillForm`), `README.md` (Fill form and apply-from-link paragraphs).
- Tests: `tests/test_form_filler_skill.py`, `tests/test_apply_from_link_skill.py`, `tests/test_docs.py`; the docs smoke count if it is affected.
- Behavior risk: applications are now sent to employers without a human look. Mitigated by the guardrails above and the full report.
