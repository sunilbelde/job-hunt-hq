# Writing out/analysis.json

```json
{
  "keywords": [
    {"term": "Kubernetes", "aliases": ["k8s"], "importance": "required"},
    {"term": "large language models", "aliases": ["LLM", "LLMs"], "importance": "required"},
    {"term": "Airflow", "aliases": [], "importance": "preferred"}
  ],
  "requirements": [
    {"id": "R1", "text": "Builds LLM-based agents used in production", "importance": "required"},
    {"id": "R2", "text": "Three or more years of machine learning engineering", "importance": "required"},
    {"id": "R3", "text": "Experience with workflow orchestrators", "importance": "preferred"}
  ],
  "assessment": {
    "R1": {"status": "met", "evidence": ["ReAct agentic AI pattern to propose, critique, and refine"]},
    "R2": {"status": "met", "evidence": ["ML Engineer – GenAI/LLM Automation | Chicago, IL | Jul 2024 – Present",
                                         "Machine Learning Engineer | Hyderabad, India | Jul 2020 – Jul 2022"]},
    "R3": {"status": "missing", "evidence": []}
  }
}
```

## Keywords: 5 to 40

The posting's hard skills, tools, languages, platforms, methods and standard terms of the field: the words
a recruiter or an applicant-tracking system would type into a search box.

- Test each candidate: would two unrelated postings in the field use the same term for the same thing? If
  so, it is a keyword. If it is this posting's own way of describing its work, it is not.
- Phrasing that is not a keyword goes into a requirement's `text`, where the assessment can judge it by
  the work the resume shows. A missing keyword pushes tailoring to paste the phrase into a bullet, which
  reads as copied from the posting.
- Example, for an applied AI posting about coding agents: `Python`, `evals`, `fine-tuning`,
  `prompt engineering` and `latency` are keywords. "long-horizon workflows", "failure modes", "context
  construction", "feedback loops" and "real-world coding tasks" are the posting's phrasing: they belong in
  requirements such as "Designs and iterates on agent behaviors across real-world coding tasks and
  long-horizon workflows".

- `importance`: `required` for what the posting requires (requirements, must have, minimum
  qualifications); `preferred` for nice to have, bonus or preferred qualifications.
- `aliases`: other ways to write the same thing, such as abbreviations (`k8s`), plurals (`LLMs`), long
  and short forms (`retrieval-augmented generation` and `RAG`) and spellings (`scikit-learn` and
  `sklearn`). Matching is by whole words and ignores case, so `LLM` does not match `LLMs`: list every
  form the posting or the resume uses. Never list a different skill as an alias.
- One concept per keyword, no duplicates. Terms and aliases are at most 60 characters each.

## Requirements: 3 to 15

The posting's qualifications and responsibilities beyond single keywords: kinds of experience, scope,
seniority, domain, years, education. Give each a short `text` and an `id` (`R1`, `R2`, …).

## Assessment: one entry per requirement

- `status`: `met` when the quoted passages together show every part of the requirement, `partial` when
  they show some parts or related experience, `missing` when the resume does not show it. A requirement
  such as "Develops evals measuring performance and regressions" needs both parts for `met`: benchmark
  evaluation alone is `partial`.
- Judge by the work, not the wording. A passage that describes the work the requirement asks for counts,
  whatever words it uses: "Evaluated the assistant on cross-domain benchmarks" shows running evals.
- `evidence`: quotes copied exactly from `out/base.json` `text`, each at least 3 words. Case and spacing
  do not matter, but every quote must appear in the text; otherwise the requirement counts as missing.
  For experience, quote the bullet that proves it, not only a skills line.
- Years: compute them from the dates in job headings and quote the headings.
- Judge honestly. The score decides whether the resume gets reworked, and an inflated score only hides
  gaps.

## The score

`run score base` computes it: half from keyword coverage and half from requirement coverage, with
required items weighing twice as much as preferred ones, and `met` 1, `partial` 0.5, `missing` 0. At 70
or more the base resume is kept.

## out/assessment_tailored.json

The same requirement ids with the same rules, including the every-part rule for `met`, quoting the
tailored resume instead. `run score tailored`
checks the quotes against the tailored text.

```json
{"R1": {"status": "met", "evidence": ["Built a human-in-the-loop LLM agent using the ReAct agentic AI pattern"]},
 "R2": {"status": "met", "evidence": ["Machine Learning Engineer | Hyderabad, India | Jul 2020 – Jul 2022"]},
 "R3": {"status": "missing", "evidence": []}}
```
