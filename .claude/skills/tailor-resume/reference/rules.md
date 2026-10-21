# Writing out/tailored.json

```json
{
  "skills": [
    {"label": "Machine Learning & GenAI", "items": ["LLMs (Llama, Mistral)", "RAG", "PyTorch", "Transformers"]},
    {"label": "Cloud & DevOps", "items": ["Kubernetes", "Docker", "AWS (EC2, S3, Lambda, SageMaker, Glue, CloudWatch)"]}
  ],
  "jobs": [
    {"id": "j1", "bullets": [
      {"text": "Built a human-in-the-loop LLM agent using the **ReAct agentic AI pattern** to propose, critique, and refine source-to-target mappings.", "sources": ["j1.b1"]}
    ]},
    {"id": "j2", "bullets": [
      {"text": "Built end-to-end **NLP pipelines** using **HuggingFace Transformers** to analyze political trends from **10M+ tweets**.", "sources": ["j2.b1"]}
    ]}
  ]
}
```

The example shows two skills lines and two jobs. Start from a copy of the skills and bullets in
`out/base.json`, then edit. Every job `j1`, `j2`, … must be listed, in the base order, with at least one
bullet.

## What stays fixed

The name and contact line, education, job headings (employer, title, location, dates), certifications,
section order and job order come from the base resume. They are not in this file, so they cannot change.

## Skills lines

- Use only the base labels. Lines may be reordered or dropped, and items reordered, moved between lines
  or dropped.
- Every item must appear in the base resume, or be a keyword the judge approved, written as `run terms`
  shows it (`unknown_skill`). A grouped item may be split when its parts appear there, for example
  `Llama` from `LLMs (Llama, Mistral)`.
- Put what the posting asks for first.

## Bullets

- `sources` lists the base bullets a bullet comes from, all of the same job (`missing_source`,
  `foreign_source`). A merged bullet cites both of its sources; a split bullet cites its one source in
  both halves.
- Allowed: rewording with the posting's terms when they name the same thing; reordering bullets by
  relevance; merging, splitting and dropping bullets.
- Never: adding a tool, skill, metric, scope, team size, customer or outcome that the sources do not
  state, or moving a bullet to another job.
- Numbers: every number must appear in the bullet's sources, written the same way (`unsupported_number`).
- Keywords: never mention a posting keyword that the base resume lacks (`unsupported_keyword`) unless
  `run terms` lists it as approved. Then use it only where it says: in a skills line, or in a bullet
  that cites one of the base bullets it names (`misplaced_keyword`), and only for what its evidence
  shows. Keep at least one mention of each posting keyword the base resume has (`lost_keyword`).
- Text: plain text with `**bold**` and `*italic*` only. No backslashes and no TeX; `%`, `&` and `$` print
  as written. At most 400 characters, ending with a period like the base bullets.
- Bold the terms the posting cares about, using phrases from the base resume (`new_bold_phrase` warns
  otherwise).

## Examples from this resume

- Allowed: the posting asks for "LLM agents" and j1.b1 says "using the **ReAct agentic AI pattern**". The
  same work may be called an LLM agent. List `agentic AI` as an alias of the keyword in `analysis.json`,
  so the scripts can see the base resume already has it.
- Allowed: the posting stresses document AI. Move j3.b1 ("Built **document intelligence pipelines** …")
  to the top of its job, and drop j3.b3 to make room.
- Allowed: the judge approved `testing` with the evidence "automated code validation", from j1.b5. The
  bullet citing j1.b5 may say "automated code validation and testing", and `Testing` may join a skills
  line.
- Not allowed: the judge approved `post-training` from the owner's profile alone, so `run terms` says
  "skills lines only". It may join a skills line, but no bullet may claim it.
- Not allowed: the posting asks for Kafka, the base resume never mentions it, and the judge rejected
  it. It appears nowhere, not even as "familiar with Kafka".
- Not allowed: "cut engineering effort by 80%" when j1.b4 says "over **70%**".
- Not allowed: putting the Kubernetes migration (j4.b4, Acheron) under Capital One.
