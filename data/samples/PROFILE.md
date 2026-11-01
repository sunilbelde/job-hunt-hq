# Profile

What you have done and can do beyond what `BASE.tex` states. Resume tailoring treats every entry here as
true, so leave out anything you could not discuss in an interview. Write one entry per line, starting with
"- ". Headings and other text are ignored.

This sample belongs to the made-up resume in `BASE.tex` beside it. Copy both to `data/` and replace them
with your own.

## Experience

Facts about each job that `BASE.tex` does not say. Put them under a `###` heading naming the employer as
its job heading in `BASE.tex` starts ("Northwind Bank", "Contoso Documents"). A tailored bullet of that job
may use them like its base bullets, numbers included, and a posting keyword a fact states may appear in the
bullets that use it. A heading that names no job fails resume generation.

### Northwind Bank
- Ran benchmark evaluations of the mapping agent, comparing different models, reasoning settings and prompt versions.
- Tuned prompts based on the benchmark results.
- Built feedback loops that fed evaluation results back into the agent's prompts and configuration.

### Lakeside University
- Built a user influence model from graph embeddings (node2vec) and centrality features on a large social network.

### Contoso Documents
- Built a layout detection model with Faster-RCNN that finds headers, tables and signature blocks in scanned invoices.
- Added morphology filters to the OCR preprocessing to clean up faint scans.
- Scored extracted clauses for compliance risk.
- Designed an automated NER data extraction and auto-labeling pipeline with Prodigy, cutting manual annotation effort by 60%.

### Fabrikam Software
- Built an internal timesheet app with Spring Boot, Angular 8 and MySQL.

## Skills and abilities

Skills you have beyond the resume. When a job posting asks for a keyword your base resume lacks, a
separate Claude judge decides whether you genuinely have it. A keyword it approves from this list alone can
appear in the resume's skills section, never inside an experience bullet. Name the tools you have used
rather than only the area: an entry "Browser automation" does not tell the judge you have used Playwright.

- Agent harnesses
- Testing
- Code quality
- Context engineering
- Post-training (supervised fine-tuning)
- Playwright
- TypeScript
- FastAPI
- LangGraph
- LLM-as-a-judge evaluation
- Tool calling / function calling
- Structured outputs (JSON schema)
