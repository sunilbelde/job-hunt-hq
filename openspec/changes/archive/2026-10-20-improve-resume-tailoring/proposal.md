# Proposal

## Why

The OpenAI (Codex Core Agent) run scored 54 → 77, but almost all of the gain came from keyword coverage
(36% → 76%). Requirement coverage barely moved (74% → 79%), and five required requirements stayed
`partial` although the owner's work does show them. Three causes:

- The analysis lists the posting's own phrasing ("long-horizon workflows", "failure modes", "context
  construction") as keywords. Tailoring then has to paste those phrases into bullets, which reads as
  copied from the posting: "developer tooling for code generation that translates…".
- Nothing asks the tailoring run to lift `partial` requirements. It inserts approved keywords, fixes the
  layout and stops once the score passes 70.
- Some of the owner's experience is written down nowhere the run may use. Examples are the benchmark
  evaluations comparing models, reasoning settings and prompts, and the feedback loops. `data/PROFILE.md`
  is a skills list that reaches the resume only through the judge, and only in the skills section.

The report also hides why the judge rejected a keyword: every rejection reads "rejected by the judge".

## What Changes

- **Keywords are searchable terms only.** The posting analysis lists only terms a recruiter or an
  applicant-tracking system would search for: tools, skills, methods and standard field vocabulary (for
  example evals, fine-tuning, Python). Phrasing particular to the posting goes into requirements instead.
- **No echoed posting phrasing.** A new soft check, `echoed_phrase`, flags a tailored bullet that copies a
  run of three or more words from the posting which the owner's sources do not already use. The skill
  revises until the flag clears. Requirements are met by describing the work plainly, in the owner's
  words.
- **Tailoring works requirement by requirement.** Before writing bullets, the run maps each `partial` or
  `missing` requirement to the base bullets and profile facts that show it. It then reframes those
  bullets around that work, and checks its tailored assessment against the map before it finishes. The
  aim is the best honest requirement coverage the page allows, not merely clearing 70.
- **Profile document with experience facts.** `data/PROFILE.md` gains an Experience section: facts about
  each job, under the employer's name. A tailored bullet may cite a fact of its own job as a source, as it
  cites a base bullet, with the same rules for numbers and keywords. A keyword that a fact states needs no
  judge, but it may appear only in skills lines and in bullets citing that fact. The facts the owner
  confirmed for Capital One are added: benchmark evaluations comparing models, reasoning settings and
  prompt tuning, and feedback loops.
- **The judge's rejection reasons are kept** in the ruling, the stored report and the viewer, in place of
  the fixed text "rejected by the judge".

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `resume-tailoring`: the posting analysis keeps phrasing out of keywords; a new requirement-by-requirement
  tailoring step; a new `echoed_phrase` check; the profile list becomes a profile document whose
  experience facts are bullet sources; the judge's input includes those facts; rejected keywords keep the
  judge's reason; the gate re-checks with the service's copy of the profile.

## Impact

- Skills: `.claude/skills/tailor-resume/SKILL.md`, `reference/scoring.md`, `reference/rules.md`,
  `reference/layout.md`; `.claude/skills/judge-resume-terms/SKILL.md`.
- Scripts: `resume_model.py` (profile facts), `resume_terms.py` (fact keywords, rejection reasons),
  `resume_checks.py` (fact sources, `echoed_phrase`), `resume_tool.py` (`prepare`, `build` and `verify`
  read the profile and the posting).
- Service: `app/tailoring.py` passes the profile to the work folder and to the gate.
- Data: `data/PROFILE.md` gains an Experience section.
- No API, response or report shape changes. The `reason` of a rejected keyword only carries different
  text, so the OpenAPI docs are unaffected.
- Tests: `test_resume_terms.py`, `test_resume_checks.py`, `test_resume_verify.py`, `test_tailoring.py`,
  `test_skill_doc.py` and the fixtures.
