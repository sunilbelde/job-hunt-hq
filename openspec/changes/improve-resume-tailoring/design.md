# Design

## Context

See proposal.md (Why). The pieces this change touches:

- **Analysis run.** It writes `out/analysis.json`: keywords, requirements and the base assessment. Only
  `reference/scoring.md` limits what counts as a keyword, so posting phrasing slips in. Half of the score
  is keyword coverage, so those phrases weigh as much as real skills.
- **Judge.** `resume_terms.judge_input` gives it the resume text and the profile skills list.
  `resume_terms.rule` throws away the reason of every rejection (`resume_terms.py:109`).
- **Tailoring run.** It follows SKILL.md steps 4–7: read the terms, write `tailored.json`, build (at most
  5 times), assess, score. Nothing in it looks at requirements until the final assessment.
- **Checks.** `resume_checks.check_content` compares sources, numbers, keywords and bold phrases with the
  base resume only. `TODO(profile-doc)` markers sit where the profile should join in: `SKILL.md`,
  `resume_checks.py`, `app/tailoring.py` and `data/PROFILE.md`.
- **Gate.** `resume_tool verify` rebuilds from the repo's template with the service's copies of the
  analysis and the ruling. It never reads the profile.

## Goals / Non-Goals

**Goals:**
- Requirements move from `partial` to `met` because the bullets show the work, in the owner's words.
- The owner can record true experience that is not on the base resume, and the same guards check it as
  they check base bullets.

**Non-Goals:**
- Changing the score formula, the threshold or the 50/50 split. Better keywords fix the inputs; the
  formula stays.
- Loosening the judge. With phrasing out of the keyword list, the judge rules on real skills only, and
  "When in doubt, reject" stays.
- Free-text projects or roles in the profile. Facts are list items under an existing job, nothing more.
- Running `echoed_phrase` at the gate. It is a soft finding, so the gate would only record it.

## Decisions

### 1. Profile facts are numbered per job: `jN.fK`

An Experience section in `data/PROFILE.md` holds level-3 headings, each naming an employer. A heading
matches the job whose heading starts with that name, ignoring case: "### Capital One" matches "Capital
One, ML Engineer – GenAI/LLM Automation | …". Its list items become `j1.f1`, `j1.f2`, …. `prepare` puts
them into `out/base.json` as each job's `facts`, next to its `bullets`. They stay out of the resume
`text`, because the base assessment quotes only what is on the page.

- **Why per job rather than a flat `p.N`** (the archived design, Decision 13): a fact belongs to one job.
  The existing `foreign_source` check then covers facts with no new rule, and a fact can never sit under
  the wrong employer.
- **A heading that matches no job fails `prepare`** with `profile_invalid` and the employer named. The
  file is the owner's own, and silently dropping facts would hide true experience.

### 2. Facts are sources, like base bullets

`check_content` takes the facts. A bullet's `sources` may hold `jN.bK` and `jN.fK` IDs of its own job.
`unsupported_number` allows the numbers of every cited source. `new_bold_phrase` compares against the
base text plus the facts. `lost_keyword` stays base-only: a keyword only a fact states was never on the
page, so leaving it out loses nothing.

### 3. A keyword in a fact is pre-approved for that fact

A posting keyword absent from the base resume but present in a fact is not sent to the judge. The rule
step adds it to the ruling as approved, with `bullets` set to the fact IDs holding it and the reason "in
the owner's profile facts". The placement check (`misplaced_keyword`) then works unchanged: the keyword
may go in skills lines and in bullets citing those facts. Judge quotes found in a fact map to that fact's
ID in the same way. `Approved.bullets` is renamed `sources`, since it now holds both kinds of ID.

### 4. The judge's reason is kept

`rule` records `verdict["reason"]` for a rejection when it is a non-empty string. Otherwise it records
"rejected by the judge". The ruling, the gate output and the stored report carry it unchanged, and the
viewer already shows `reason`. The text comes from the judge, which never sees the posting, and the
report is never logged, so no logging rule changes.

### 5. Keywords: rules and examples, not a mechanical filter

No script can tell "fine-tuning" from "long-horizon workflows". `reference/scoring.md` changes instead:

- Keywords are terms someone would type into a search box.
- A test to apply: would two unrelated postings in the field use the same term?
- Worked examples from the OpenAI run: `evals`, `fine-tuning` and `latency` are keywords; `long-horizon
  workflows`, `failure modes`, `context construction` and `feedback loops` are requirement text.

The 5–40 bound stays.

### 6. `echoed_phrase` uses word n-grams

- Tokenize the posting and each bullet the same way: normalize, split hyphens and slashes, keep word
  characters.
- Flag a bullet sharing a run of at least 3 consecutive tokens with the posting, with at least 2 of them
  outside a small stopword list, when the cited sources do not contain that run.
- `build` reads `posting.md` from the work folder; with no posting, the check is skipped.
- It is soft (an `aim` line). A hard failure would block common, harmless runs like "end to end
  pipelines".

### 7. Coverage plan: `out/coverage.json`

After `run terms`, the run writes `{"R4": {"sources": ["j1.b1", "j1.b5"], "note": "…"}, …}` for each
requirement the base assessment marks `partial` or `missing`. An empty `sources` means nothing shows it.

- `build` validates the plan: every ID exists and belongs to a job, and every listed requirement exists.
  A broken plan is a `fix` line, so the run cannot skip it.
- `score tailored` prints `planned, not met: R4 (j1.b1, j1.b5)` for each planned requirement with sources
  that is still not `met`.
- SKILL.md tells the run to revise while builds remain and such lines exist. The 5-build limit stays;
  revisions share it.
- The plan never reaches the gate. It steers the run and proves nothing.

### 8. "Met means every part"

`reference/scoring.md` adds the every-part rule for both assessments. The base and tailored statuses then
mean the same thing, and the tailoring run cannot inflate its own grade by loosening the bar. The
evidence quotes still have to be on the page; the gate already enforces that.

### 9. Service wiring

- `_prepare_work` passes `--profile PROFILE` to `prepare`. That replaces the `TODO(profile-doc)` there.
- `_verify` passes `--profile PROFILE` to `verify`.
- `verify` builds the facts from its own copy and never reads `out/base.json` facts. A fact the run
  invents therefore fails `missing_source` at the gate.

## Risks / Trade-offs

- **[Risk] The run grades its own tailored assessment and may call `partial` `met`.** → The every-part
  rule, quotes the gate checks, and the base assessment written before tailoring under the same rule. The
  viewer shows the quotes, so the owner can see a weak `met`.
- **[Risk] Facts are treated as true without checks.** → Same trust as the skills list. `data/PROFILE.md`
  tells the owner to list only what they can discuss in an interview, and each fact can still only appear
  under its own job.
- **[Trade-off] Removing phrasing from keywords lowers the keyword share in every score**, base and
  tailored alike. Scores are not comparable with earlier reports. → Acceptable: reports are regenerated
  per application, and the threshold still compares like with like.
- **[Risk] `echoed_phrase` is noisy on generic runs** such as "machine learning models". → The rule needs
  2 non-stopwords in a run of 3. It is soft, and a run the sources already contain is never flagged.
- **[Trade-off] More facts compete for one page.** → The layout checks already force choices; the coverage
  plan tells the run which bullets matter for this posting.

## Migration Plan

- Deploy by restarting the service; the work folder and judge folder are rebuilt on every run.
- Earlier stored reports keep "rejected by the judge" until their application is regenerated.
- Rollback: revert the commit. A `PROFILE.md` with an Experience section is harmless to the old code,
  because it reads list items only.
  - Caveat: the old code takes every list item as a skills entry, facts included, so roll back
    `PROFILE.md` too, or accept that the judge sees facts as skills.

## Open Questions

- The exact wording of the Capital One facts. The owner confirmed the substance (benchmark evaluations;
  comparing models, reasoning settings and prompt tuning; feedback loops); the tasks write a draft for the
  owner to approve.
- Whether the owner also categorized mapping errors (failure modes), fine-tuned a model, or ran long
  multi-step agent runs. Each answer only adds facts; nothing in this design depends on it.
