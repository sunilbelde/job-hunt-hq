# Writing out/letter.json

```json
{"paragraphs": [
  {"role": "opening", "text": "I am applying for the Applied AI Engineer role at Acme Corp. For the last two years at Capital One I have built agents that turn scattered enterprise knowledge into working data software."},
  {"role": "body", "text": "At Capital One I developed a human-in-the-loop Conversion Mapping Engine using the ReAct pattern. ... the assistant reached 75% source-field recall across domains.", "sources": ["j1.b1", "j1.b3", "j1.f1"], "requirements": ["R1"]},
  {"role": "body", "text": "I also designed a GenAI ETL platform that turns plain-language mapping instructions into PySpark code that runs as AWS Glue jobs. ...", "sources": ["j1.b4", "j1.b5"], "requirements": ["R2", "R3"]},
  {"role": "closing", "text": "I would welcome the chance to talk about how this work could help your team. Thank you for your time and consideration."}
]}
```

The scripts add everything else: the resume's name and contact header, the date, the greeting ("Dear
Acme Corp Hiring Team," or, in base mode, "Dear Hiring Manager,") and "Sincerely," with the owner's name.
Do not write any of them.

## Structure

- One `opening`, two or three `body` paragraphs, one `closing`, in that order (`structure_mismatch`).
- Between 250 and 400 words in all (`word_count`). The letter must fit on one page (`one_page`).
- **Opening**: in tailored mode, name the role and the company exactly as `job.json` has them
  (`missing_role`, `missing_company`), then say why this role: the one or two things the job most needs
  and the owner's work that answers them. A reader should learn from the opening alone why this
  candidate fits this job. At most one sentence about the company itself, drawn from the posting or the
  application notes. In base mode, say who the owner is and what their systems accomplish. Lead with the
  result of the work, not a general description ("pipelines that turn mapping instructions into
  production code", not "systems that do real work").
- **Body**: each paragraph connects one need of the employer to one achievement of the owner, in
  that order:
  1. **The need**: what the job requires, said in the owner's own words (never the posting's phrasing).
  2. **The achievement**: the work that meets it: what the owner built and how, in enough detail to be
     believable.
  3. **The improvement**: the measured result that work produced, exactly as a cited source states it
     ("reduced engineering effort by over 70%", "cut delivery time from about 5 months to 4 weeks"). When
     the cited sources state a result and the paragraph gives none, `run build` warns `no_result`. When
     no source states a result, say plainly what the work made possible and never invent a figure.

  The first two body paragraphs carry the owner's two strongest achievements: those with the best
  measured results among the work that meets the posting's required requirements. A third body
  paragraph, if any, is shorter. `sources` lists every bullet and fact (`jN.bK`, `jN.fK`) it draws
  on, from any job (`missing_source`, `unknown_source`). In tailored mode `requirements` lists the
  requirement IDs from `out/analysis.json` it shows (`requirements_not_addressed`, `unknown_requirement`),
  and together the body paragraphs must address the number of required requirements `run analyze`
  names.
- **Closing**: two sentences at most: an invitation to talk and a thank-you. No new claims.
- **Weight**: give most of the space to the one or two pieces of work that match the job best.
  Compress older or less relevant jobs into one sentence, or leave them out. Aim near the low end of
  the word range; every sentence should earn its place.

## Facts and numbers

- Every number in a body paragraph must appear in a source that paragraph cites, written the same way
  (`unsupported_number`). The opening and closing hold no numbers, except one that is part of the role
  or company name; write "two years", not "2 years", when a source does not state it.
- Name only tools and skills the owner's record states. A posting keyword the record lacks is rejected
  (`unsupported_keyword`), wherever it appears.
- Stay inside what the source says: "contributed to" stays "contributed to", "evaluated" does not become
  "led the evaluation".
- Ownership: use "I" for what the sources say the owner did ("developed", "architected", "led"). State
  results that a whole team or system produced as the system's ("the platform reduced effort by over
  70%") or the team's ("we"), not as the owner's alone.
- Tools: name only the two or three tools per paragraph that matter most to this job, preferring the
  posting's keywords. A list of tools, products and model names competes with the work itself; describe
  what the work did instead.

## Text

- Plain text: no Markdown, no backslashes, no line breaks inside a paragraph, at most 1,200 characters a
  paragraph (`invalid_text`). `%`, `&` and `$` print as written.
- No run of three or more posting words that the paragraph's sources do not also contain
  (`echoed_phrase`); the role and company names are exempt.

## Examples

- Source `j3.f4`: "Designed an automated NER data extraction and auto-labeling pipeline with Prodigy, cutting
  manual annotation effort by 60%."
  - Good: "I built an auto-labeling pipeline with Prodigy that cut manual annotation effort by 60%."
  - Rejected: "...cut annotation effort by 65%" (`unsupported_number`), or "...with Prodigy and Label Studio"
    when Label Studio is a posting keyword the record lacks (`unsupported_keyword`).
- Posting: "We value people who thrive in ambiguity."
  - Rejected: "I thrive in ambiguity" (`echoed_phrase`). Show it instead with work from the sources, such
    as the migration the mapping engine handled.
