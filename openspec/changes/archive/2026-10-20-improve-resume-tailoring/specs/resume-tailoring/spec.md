## ADDED Requirements

### Requirement: Keywords are searchable terms
The posting analysis SHALL list as keywords only terms a recruiter or applicant-tracking system would search for: tools, languages, platforms, methods and standard field vocabulary. Phrasing particular to the posting, such as how it describes its own work, SHALL go into requirements instead, so that it is never counted as a missing keyword.

#### Scenario: Standard term
- **WHEN** a posting asks for "evals" and "fine-tuning"
- **THEN** both are listed as keywords

#### Scenario: Posting phrasing
- **WHEN** a posting says "iterate on agent behaviors across long-horizon workflows" and "measure failure modes"
- **THEN** "long-horizon workflows" and "failure modes" are not keywords, and the work they describe is part of a requirement

### Requirement: Posting phrasing is not echoed
The bullet checks SHALL flag, as a soft `echoed_phrase` finding, a tailored bullet that contains a run of three or more consecutive words from the posting, with at least two words that are not stopwords, when the bullet's sources do not contain that run. The skill SHALL revise such a bullet into the owner's own wording before finishing.

#### Scenario: Copied phrase
- **WHEN** the posting says "failure modes and edge cases" and a tailored bullet citing j1.b3 says "measuring failure modes and edge cases", which j1.b3 does not say
- **THEN** the build reports `echoed_phrase` for that bullet

#### Scenario: Phrase the owner already uses
- **WHEN** the posting and base bullet j1.b4 both say "PySpark code deployable as AWS Glue jobs" and the tailored bullet citing j1.b4 keeps it
- **THEN** no `echoed_phrase` is reported

#### Scenario: Soft finding
- **WHEN** the only finding left on a build is `echoed_phrase`
- **THEN** the build passes its hard checks, and the gate does not fail on it

### Requirement: Tailoring targets weak requirements
Before writing tailored content, the tailoring run SHALL record, for each requirement the base resume assesses as `partial` or `missing`, the base bullets and profile facts that show it, or that none do. It SHALL rework those bullets so the tailored resume shows that work plainly. When finishing, it SHALL report every planned requirement that is still not `met`. It SHALL NOT stop revising only because the score has reached the threshold.

#### Scenario: Plan written
- **WHEN** the base assessment marks R5 `partial`
- **THEN** the run's coverage plan names R5 with the bullet or fact IDs that show it, or with none

#### Scenario: Plan cites unknown sources
- **WHEN** the coverage plan cites `j1.b9`, which does not exist
- **THEN** the plan is rejected with a message naming `j1.b9`

#### Scenario: Still partial after tailoring
- **WHEN** the plan maps R5 to j1.b3 and j1.f1, and the tailored assessment still marks R5 `partial`
- **THEN** `run score tailored` lists R5 as planned but not met, so the run revises again if builds remain

### Requirement: Met means every part is shown
An assessment SHALL mark a requirement `met` only when its quoted passages together show every part of the requirement, and `partial` when they show some parts. The same rule SHALL apply to the base and the tailored assessment.

#### Scenario: One part missing
- **WHEN** R5 asks for evals measuring performance and regressions, and the quotes show benchmark evaluation but nothing about comparing versions
- **THEN** R5 is assessed `partial`

#### Scenario: Every part shown
- **WHEN** the tailored quotes show benchmark evaluation and comparisons between models and prompt versions
- **THEN** R5 may be assessed `met`

### Requirement: Keywords stated in profile facts
A posting keyword absent from the base resume but stated in a profile fact SHALL need no judge, and SHALL appear in a tailored resume only in the skills section or in a bullet citing that fact.

#### Scenario: Keyword stated in a fact
- **WHEN** the posting asks for "evals", the base resume lacks it, profile fact j1.f1 says "ran evals", and a tailored bullet citing j1.f1 says evals
- **THEN** the content is accepted without a judge ruling on evals

#### Scenario: Fact keyword elsewhere
- **WHEN** the same "evals" appears in a bullet that cites only j1.b2
- **THEN** the content is rejected

## MODIFIED Requirements

### Requirement: Bullets trace to the same job
Every experience bullet in a tailored resume SHALL cite one or more sources of the same job: base resume bullets, profile facts of that job, or both. Bullets MAY be reworded, merged, split, reordered or dropped. A bullet without sources, or citing a bullet or fact of another job, SHALL be rejected.

#### Scenario: Merged bullets
- **WHEN** a tailored bullet combines two base bullets of the same job and cites both
- **THEN** it is accepted

#### Scenario: Bullet moved to another job
- **WHEN** a bullet under Capital One cites a Dockskiff bullet
- **THEN** the content is rejected

#### Scenario: Invented bullet
- **WHEN** a tailored bullet cites no source
- **THEN** the content is rejected

#### Scenario: Bullet from a profile fact
- **WHEN** a tailored bullet under Capital One cites only `j1.f1`, a profile fact listed under Capital One
- **THEN** it is accepted

#### Scenario: Fact of another job
- **WHEN** a bullet under Dockskiff cites `j1.f1`
- **THEN** the content is rejected

### Requirement: Numbers come from the cited bullets
Every number in a tailored bullet, such as a percentage, count, size or duration, SHALL appear in the base bullets or profile facts it cites.

#### Scenario: Number kept
- **WHEN** a tailored bullet says "75% source-field recall" and cites the base bullet with that figure
- **THEN** it is accepted

#### Scenario: Number changed
- **WHEN** a tailored bullet says "80%" and no cited bullet contains 80
- **THEN** the content is rejected

#### Scenario: Number from a fact
- **WHEN** a tailored bullet says "3 model families" and cites a profile fact that says "3 model families"
- **THEN** it is accepted

### Requirement: New posting keywords need the judge's approval
A posting keyword whose term and aliases are all absent from the base resume and from the profile facts SHALL appear in a tailored resume only when the judge approved it, and then only in the skills section or in a bullet that cites a base bullet or profile fact holding the judge's evidence for it. A keyword approved from the profile skills list alone SHALL appear only in the skills section.

#### Scenario: Keyword the candidate lacks
- **WHEN** the posting asks for Kafka, the base resume never mentions it, the judge rejected it, and tailored content mentions Kafka
- **THEN** the content is rejected

#### Scenario: Approved keyword where its evidence is
- **WHEN** the judge approved "testing" with the quote "automated code validation", which is in base bullet j1.b5, and the tailored bullet citing j1.b5 mentions testing
- **THEN** the content is accepted

#### Scenario: Approved keyword in another bullet
- **WHEN** the same approved "testing" appears in a bullet that cites only j4.b2
- **THEN** the content is rejected

#### Scenario: Approved from the profile alone
- **WHEN** the judge approved "post-training" from a profile skills entry only, and a tailored bullet mentions post-training
- **THEN** the content is rejected, while the same keyword in a skills line is accepted

### Requirement: Judge for keywords the base resume lacks
When the base resume scores below 70 and the posting analysis lists keywords absent from both the base resume and the profile facts, the service SHALL have a separate Claude run, the judge, rule on each of them before tailoring. The judge SHALL receive only the base resume's text, the owner's profile document (skills list and experience facts) and those keywords, without their importance and never the posting text. When no keyword is missing, no judge run SHALL start.

#### Scenario: Judge never sees the posting
- **WHEN** the judge runs for any posting
- **THEN** its folder holds no posting text, and its input holds the resume, the profile skills, the profile facts and the missing keywords only

#### Scenario: Nothing missing
- **WHEN** the base resume scores below 70 but every posting keyword is in the base resume or the profile facts
- **THEN** no judge run starts, and the resume is tailored

#### Scenario: Unusable judge output
- **WHEN** the judge's output is missing or is not a verdicts file
- **THEN** generation fails

### Requirement: Judge approvals need evidence
A script SHALL accept the judge's approval of a keyword only when the judge quotes a passage found in the base resume, in a profile fact, or in a part of a profile skills entry, and SHALL record which base bullets and profile facts hold the quotes. A keyword the judge rejects, or approves without such evidence, SHALL be left out without failing generation, and its recorded reason SHALL be the judge's own reason when the judge gave one.

#### Scenario: Approval without evidence
- **WHEN** the judge approves "Airflow" quoting "scheduled Airflow DAGs", which is in neither the base resume nor the profile
- **THEN** Airflow is rejected, and generation goes on without it

#### Scenario: Rejections do not fail generation
- **WHEN** the judge rejects every missing keyword
- **THEN** the resume is tailored from the base resume's facts and the profile facts alone

#### Scenario: Judge's reason kept
- **WHEN** the judge rejects "latency" with the reason "Nothing shows latency work."
- **THEN** the ruling records "latency" with the reason "Nothing shows latency work."

#### Scenario: No reason given
- **WHEN** the judge rejects a keyword with no reason
- **THEN** the ruling records the reason "rejected by the judge"

#### Scenario: Quote from a fact
- **WHEN** the judge approves "A/B testing" quoting profile fact j1.f2
- **THEN** the approval is accepted, and the keyword may go in skills lines and in bullets citing j1.f2

### Requirement: Owner's profile list
The repository SHALL hold the owner's profile document, `data/PROFILE.md`. Its "Experience" section lists facts under level-3 headings naming a base resume employer; each list item is a fact of that job, numbered `jN.f1`, `jN.f2`, … in order. Every other list item is a skill beyond the base resume, which only the judge reads. Every entry SHALL be treated as true. Other text SHALL be ignored. A missing file SHALL mean no skills and no facts.

#### Scenario: Listed skill
- **WHEN** the profile skills list has the entry "Post-training" and the posting asks for post-training, which the base resume lacks
- **THEN** the judge may approve it by quoting that entry, and the tailored resume may list it in the skills section

#### Scenario: Prose is not an entry
- **WHEN** the judge quotes a sentence of the file's introduction as evidence
- **THEN** the quote counts for nothing

#### Scenario: Facts numbered by job
- **WHEN** the Experience section has a "### Capital One" heading with two list items, and Capital One is the base resume's first job
- **THEN** the work folder's base resume lists them as facts `j1.f1` and `j1.f2` of job j1

#### Scenario: Unknown employer
- **WHEN** the Experience section has a "### Globex" heading and no base resume job is at Globex
- **THEN** preparing the work folder fails with a message naming "Globex", and no Claude run starts

### Requirement: Final gate re-checks the run's output
Before saving a tailored resume, the service SHALL use its own unmodified copy of the scripts, base template and profile document to recompute the scores, re-run every check and re-render the PDF from the run's content. It SHALL score against its own copy of the posting analysis, taken after the analysis run, and allow only the keywords of its own copy of the judge's ruling. It SHALL save only the PDF it rendered and checked. Any failed check SHALL fail generation.

#### Scenario: Run alters its copy of the template
- **WHEN** a Claude run edits the template or script files in its work folder
- **THEN** the saved resume is built from the unmodified base template and checked by the unmodified script

#### Scenario: Run's own PDF ignored
- **WHEN** a Claude run leaves a PDF in its work folder
- **THEN** that file is never saved as the resume

#### Scenario: Failed check at the gate
- **WHEN** the gate finds a two-page result or an unsupported keyword
- **THEN** generation fails and no resume file is written

#### Scenario: Tailoring run edits the analysis or the ruling
- **WHEN** the tailoring run drops a keyword from its copy of the analysis, or marks a keyword approved in its copy of the ruling
- **THEN** the gate scores and checks with the service's copies, so neither change has any effect

#### Scenario: Run adds a profile fact
- **WHEN** the tailoring run adds a fact to the base resume JSON in its work folder and cites it from a bullet
- **THEN** the gate checks against the service's profile document, finds no such fact and fails generation
