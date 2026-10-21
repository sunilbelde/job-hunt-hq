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

The posting's hard skills, tools, platforms, methods and domain terms: the words a recruiter or an
applicant-tracking system would search for.

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

- `status`: `met` when the base resume clearly shows it, `partial` for related or partly matching
  experience, `missing` when it does not show it.
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

The same requirement ids with the same rules, quoting the tailored resume instead. `run score tailored`
checks the quotes against the tailored text.

```json
{"R1": {"status": "met", "evidence": ["Built a human-in-the-loop LLM agent using the ReAct agentic AI pattern"]},
 "R2": {"status": "met", "evidence": ["Machine Learning Engineer | Hyderabad, India | Jul 2020 – Jul 2022"]},
 "R3": {"status": "missing", "evidence": []}}
```
