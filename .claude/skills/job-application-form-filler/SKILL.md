---
name: "job-application-form-filler"
description: "Fill a job application form in Chrome for a job-hunt-hq application ID, from the owner's profile document, PROFILE.md and the application's tailored resume; attach the tailored files with the Tailored Attach button; after the user reviews it, tick the agreement boxes and submit only on their approval, mark it applied, and close the form and Herdr tabs."
---

# Job application form filler

Invoked with a job-hunt-hq **application ID** (`/job-application-form-filler <application id>`). Fill that
application's form in Chrome (Greenhouse, Ashby, Lever, Workday, a company careers page and similar), attach its
tailored resume and cover letter, report, then ask whether the user reviewed and submitted it (Step 7).

**Submitting:** only when this run's request explicitly asks for it (`/job-application-form-filler <id> submit`,
or "…and submit it if it's simple"), and only when every condition in Step 5 holds; or, after the user has
reviewed the form, when they approve "agree and submit" in Step 7. Otherwise never submit. Permission to submit,
and to tick agreement boxes, never carries over from an earlier run, form or conversation.

Runs in Claude Code on the owner's Mac: it reads local files and the local backend. If no ID is given, ask for it.
If only a form URL is given, find the ID by listing `GET /applications` and reading `GET /application/{id}` until
`job_link` matches the URL (ignore case, `#…`, trailing `/`, tracking parameters, and an `apply` or `application`
path segment). If none matches, say so and ask for the ID.

## Asking the user: always with AskUserQuestion

Every question to the user during a run goes through the **AskUserQuestion** tool (selectable options, so the
user picks instead of typing), never as a plain-text question. This covers missing answers, follow-ups, setup
steps the user must do and the final review. Moving to the next page of a multi-page form is never asked about
(see "Multi-page forms" in Step 4).

- **Batch:** collect what you need, then ask up to 4 questions in one call (one tab each). Ask again for the rest.
  Prefer one batch after reading the whole form over one question at a time.
- **Options come from the sources and the form:** 2 to 4 per question. For a form's dropdown or radio, use the
  form's own choices; for a fact, offer the candidates the sources suggest; put the most likely one first with
  "(Recommended)" when a source supports it. Never add an "Other" option: the tool adds a free-text one.
- **multiSelect** for "which of these" questions (skills used, locations, tools), single-select otherwise.
- **Self-contained:** each question names the form field it fills and the company, e.g. "Rula form: years of
  Python experience?". Header (12 characters at most) names the field.
- **Short descriptions** say what each option means or where it came from ("from your resume", "posting asks
  for this").
- Never ask something the sources already answer, and never ask for a password, ID number or other credential.
- If AskUserQuestion is not available in this environment, ask the same questions as a short numbered list.

## Step 1: Read the sources

All of these, before touching the form. The backend is `http://127.0.0.1:8081` (the docs listener; no key needed).

| Source | How | Use it for |
| --- | --- | --- |
| **Application** | `curl -s http://127.0.0.1:8081/application/<id>` | `company`, `role`, `official_apply_url`, `job_link`, `full_job_description`; the `report`'s `added_terms` and `rejected_terms`. `salary`, `sponsorship`, `work_type` and `why_it_fits` are often empty: read those from the job description instead. |
| **Profile document** | Read the Markdown file matching `data/*Profile.md`, not `data/PROFILE.md` | **Every form answer**: contact, the Reusable Answers table, EEO table, visa status, job preferences, drafting style |
| **Tailored resume** | Read the resume PDF in `outputs/<company>/<id>/`, and the `* - Cover Letter.pdf` beside it if present | What this application claims: open-ended answers must agree with it |
| **Experience facts** | `data/PROFILE.md`, `data/BASE.tex` | Detail behind open-ended answers |

Paths are relative to the root of the job-hunt-hq repo, where this session runs.

- The profile document wins over everything else for form answers. Match questions to its rows by meaning, not
  wording.
- A term in the report's `rejected_terms` was judged unsupported: never claim it in any answer.
- Read the contact email shown in the header of the tailored resume, and of the cover letter if there is one, and
  compare each with the profile document's `Email` row. Keep any mismatch, or any document whose email can't be read,
  for the red flags in Step 6.
- If the backend is unreachable or has no such ID, say so, continue from the profile document only, and expect
  the file attach to fail.
- If the profile document cannot be read, stop and say so: do not fill from memory.

## Step 2: Open the form

- Open `official_apply_url` (it is often empty: then `job_link`) in a new tab in Claude's tab group; Claude cannot
  reach the user's other tabs. Go on to the application form if the posting has an Apply tab or link that only
  navigates.
- Check the page's company and role match the application's. If they don't, stop and report.

## Step 3: Attach the files (Tailored Attach button)

The **Attach tailored files** button (`[data-testid=tailored-attach-button]`) sits under the Resume/CV field.
Click it once, wait until its `data-state` is not `working`, then read the status
(`[data-testid=tailored-attach-status]`) and the application shown beside it
(`[data-testid=tailored-attach-application]`, ID in `data-application-id`).

| Status | Do |
| --- | --- |
| `Attached: …` or `Attached resume only: …` | Done, **if** `data-application-id` is this application's ID. If it is a different ID, stop: the wrong resume is on the form. Tell the user to remove it from the form. |
| `No recorded application for this URL: enter its application ID and click again` | Click the **Application ID** box (`[data-testid=tailored-attach-app-id]`), **type** the ID (real key input, not a scripted value), click the button. |
| `No recorded application for this URL` (nothing after it) and no Application ID box | An old Tailored Attach build is loaded. Ask with AskUserQuestion: "Reload the extension at chrome://extensions (Tailored Attach should show version 1.2.0 or later), then reload this tab", options "Reloaded, try again" / "Skip attaching". Filled answers are lost on a tab reload, so do this before filling. |
| `Found by ID: click again to attach its files` | Check the company and role shown match this application, then click the button again. |
| `Already attached: …` | Files are already on the form. Report it. |
| `No application with ID …`, `Backend unreachable`, `Attach failed: …` | Attach nothing more. Report the status as written. |

- **No button on the form:**
  - On Greenhouse, Ashby, Lever, Workday, SmartRecruiters, Workable, iCIMS or Jobvite: ask the user to reload
    the tab (AskUserQuestion: "Reloaded, try again" / "Skip attaching, I'll attach by hand"), then click again.
  - On any other site: ask the user to open the Tailored Attach toolbar popup and click **Enable on this site**
    (Claude cannot click the toolbar or Chrome's permission prompt). Ask with AskUserQuestion ("Enabled, try
    again" / "Skip attaching"). The button appears without a reload.
- Once the click finds the application, Tailored Attach (1.3.0 or later) names this session's Chrome tab group
  after the company. Nothing to do for it; if the group keeps its old name, mention that the extension needs a
  reload.
- Never use the OS file picker or the form's own Upload button.
- If the form has a cover letter field but no cover letter was attached, report it: the profile says to attach
  one whenever a form has the field.

## Step 4: Fill the form

**Read the whole form first.** Some questions appear only after another answer (Race after Hispanic/Latino; visa
details after sponsorship), so re-scan after each section.

**Answers** come only from the Step 1 sources. Never invent experience, numbers, employers, skills or ratings.

| Question type | Answer |
| --- | --- |
| Contact, name, links, location | Profile document. A "preferred" and a "legal" name field both get the full name there. Every email field gets the profile document's `Email` row, even when an attached document shows another address. |
| Work authorization, sponsorship | The profile document's visa status section and Reusable Answers table. |
| Visa type lists | The option the profile document's visa status section names, and no other. |
| Self-ratings, yes/no screening questions | The profile document's Reusable Answers table, matched by meaning. |
| EEO (gender, Hispanic/Latino, race, veteran) | The profile document's EEO table. |
| Disability | Leave blank; report it. |
| Salary expectations | Leave blank; report it with the posting's range. |
| Consent, privacy, GDPR, terms, "I certify" | Leave unticked while filling, and list each one with its text. Tick them only in Step 7, after the user has reviewed the form and approved ticking those exact boxes. |
| Anything the sources don't answer | Ask the user with AskUserQuestion (see "Asking the user"), batched after reading the whole form, then fill in the answers. Follow a form's own fallback instruction (such as "write N/A if none") only when the sources confirm the fact. |

**Open-ended questions** ("Why us?", "Tell us about a project"), and questions about skills, experience or
knowledge ("Describe your experience with RAG", "How have you evaluated LLM output?", "How would you design…"):
- **Facts come from the profile document first:** its Capital One Work Summary (ETL automation, Enterprise Data
  Quality, Conversion Mapping Engine and their results), technical stack and supporting stack. Add detail from
  the tailored resume and `PROFILE.md`. Never use a fact that none of these state.
- **Meet what the company is looking for:** read the job description first and answer the question it is really
  asking. Lead with the experience closest to the role's stated requirements, use the posting's own terms where
  they truthfully describe the owner's work, and say what the work achieved (the profile's results). For a design or
  knowledge question, answer the approach directly, then ground it in work the owner has done.
- **Style** (the profile document's drafting style): concise and specific to the question, 3–5 sentences unless
  the field asks for more or sets a limit; "we" for team work while making the owner's own part clear; never invent
  metrics, fine-tuning experience or testing practices; never claim a `rejected_terms` term.
- **No dashes as punctuation:** no em dashes (—), no en dashes used as dashes (–), and no double hyphens (--).
  Use a comma, colon, period or parentheses instead. Hyphenated words ("human-in-the-loop", "source-to-target")
  are fine. Check every draft for these characters before typing it in.
- Type each draft in and list it in the report for review. If the sources don't support an answer, leave it blank.

**Mechanics:**
- **Text fields:** click and type. Keep the field's format (phone with country code if the field shows one).
- **Dropdowns and comboboxes:** click, type the option, pick it, then read the value back.
- **Radios, checkboxes, Yes/No toggle buttons:** click, then read the state back. A first click sometimes does
  not register (seen on Ashby's toggles); click again if needed.
- **Before reporting,** read every field's final value:
  - A value already present that did not come from the sources (seen: an Ashby dropdown pre-set to an unrelated
    option): clear it or set it from the sources, and report it.
  - A value the user changed in the tab during the session: keep the user's value, and mention it.

**Do not** click Submit, Apply, Send or any button that sends the application, except as Step 5 and Step 7
allow.

**Multi-page forms** (Workday, iCIMS, SmartRecruiters, some Ashby and Lever forms, careers sites with steps):
go through every page to the end without stopping to ask whether to continue. Next, Continue and Save and
Continue only move between pages (or save a draft); they do not send the application, so click them without
asking. On each page:
1. Read the whole page, fill it as above, and read every value back.
2. Ask, in one batch, only for what this page needs and the sources don't answer, if it is **required** (the
   page won't go on without it). Leave an optional unanswered question blank, note it for the report, and carry
   on.
3. Note every value entered on this page (earlier pages can't be seen later, so the report is built from these
   notes).
4. Click Next / Continue once, and read the new page. If the page shows a validation error, fix it from the
   sources (or ask, if it is a required answer the sources don't give), then click again. If the same error
   comes back a second time, stop and report it.

Stop going forward only at:
- **the final page:** a Review / Summary page, or the page whose button is Submit / Apply / Send Application.
  Fill it, then go to Step 5 or Step 6. This is where the user reviews the whole application.
- **a page that won't go on without a consent, terms, certification or "I agree" box ticked** (seen on Workday's
  Voluntary Disclosures and Self Identify pages). Do not tick it: report it with its exact text and go to Step 6,
  and Step 7 asks to tick it.
- **a sign-in, account creation, password, email code, CAPTCHA or bot check.** Never fill or solve one; ask the
  user with AskUserQuestion to do it in the tab ("Done, carry on" / "Stop here, I'll take over"), then carry on.
- **a page for a different company or role** than the application's: stop and report.

**New answers from the user.** When the user answers a question the sources didn't cover (through
AskUserQuestion or typed), fill it in and add it as
a row to the profile document's "Application Profile — Reusable Answers" table: a Markdown table row
`| <question> | <answer> |` in the same style as the rows around it, placed with related rows, and set
"Last updated: <Month D, YYYY>" near the top to today. Edit only that table and that date; keep every other line
as it is. If it is also a capability a resume could use, add it to `data/PROFILE.md` as a "- " skill line. The
profile document is gitignored on purpose (personal details): never commit it, and keep personal details out of this file.

## Step 5: Submit (only when this run asked for it)

Skip this step unless the request for this run explicitly said to submit. Then submit only if **every** one of
these holds; if any fails, do not submit, and say which one in the report:

1. **Reached the final page:** a single-page form, or a multi-page form gone through to its final page with
   every page meeting the conditions below.
2. **Everything answered from the sources:** no question left blank, except an optional voluntary
   self-identification question the skill leaves blank by rule (disability). No question was answered from a guess.
3. **Simple:** no free-text answer longer than one sentence was drafted (an essay or "Why us?" waits for the
   user's review), and no salary question.
4. **No acknowledgments:** no consent, privacy, terms, certification or "I agree" checkbox. The user accepts
   those personally, so a form that requires one is left for the user.
5. **Files attached** with status `Attached: …` or `Attached resume only: …`, and `data-application-id` is this
   application's ID. If the form has a cover letter field, a cover letter was attached.
6. **No red flags** (Step 6, item 7) and no CAPTCHA or bot check (never solve one).
7. **Every value read back** and correct, with nothing pre-filled or changed by the user left unexplained.

Then:

- Click Submit once. Do not click it again if nothing seems to happen; read the page.
- **Confirm it went through:** the page shows a confirmation ("Thank you for applying", "Application submitted",
  "We've received your application"), or the form is replaced by one. If the page shows an error, a validation
  message, or nothing clear, do not retry and do not mark it applied: report what the page shows.
- **Mark it applied** in job-hunt-hq, only after a confirmation. The key is `API_KEY` in the repo's `.env`; read
  it into a variable and never print it:

  ```bash
  KEY=$(grep '^API_KEY=' .env | cut -d= -f2- | tr -d "\"'")
  curl -s -X PATCH -H "X-API-Key: $KEY" -H 'Content-Type: application/json' \
    -d '{"status":"applied"}' http://127.0.0.1:8081/application/<id>
  ```

  Expect `{"ok":true,"application_id":"<id>","status":"applied"}`. Report any other answer as written.

## Step 6: Report back

Briefly:

1. Company, role and application ID; the form's URL.
2. Which sources loaded (application, profile document, tailored resume, cover letter).
3. The file status line and the application the button showed.
4. What was filled in, page by page for a multi-page form.
5. Each drafted open-ended answer, in full.
6. Everything left blank, and why.
7. Red flags, from the profile document's hard filters, checked against the application's fields, the job
   description and the posting page (the fields are often empty):
   - base pay below the profile document's pay floor,
   - sponsorship explicitly refused (silence is fine),
   - the form is not on the company's own careers site or its ATS,
   - no full job description,
   - contract-only or unpaid,
   - an attached resume or cover letter shows a contact email other than the profile document's: name the
     document and suggest generating it again from the viewer before submitting (say so instead if no email could
     be read from it),
   - a cover letter field with no generated cover letter.
8. Submitted or not:
   - submitted: the confirmation text the page showed, and the status update's response;
   - not submitted: whether this run asked to submit, and if it did, which Step 5 condition failed.
9. Anything waiting on the user: enabling the site, consent boxes (listed with their text), salary, essay answers
   to review. Then go on to Step 7.

## Step 7: Review, submit, and wrap up

Skip the questions if Step 5 already submitted the form in this run, and go straight to "Wrap up". Otherwise,
right after the report, call AskUserQuestion once with two questions:

1. **Reviewed** (header "Reviewed"): "Have you reviewed the filled <Company> form?" Options: "Yes, reviewed" /
   "No, not yet".
2. **Submitted** (header "Submitted"): "Have you submitted the <Company> application?" Options: "Yes, I
   submitted it" / "No, not submitted".

| Answers | Do |
| --- | --- |
| Submitted: Yes | Read the form tab. If it shows a confirmation, go to "Wrap up". If it doesn't, say so and ask with AskUserQuestion whether to mark it applied anyway ("Yes, it went through" / "No, leave it"); on Yes go to "Wrap up", on No stop. |
| Reviewed: Yes, Submitted: No | Go to "Agree and submit". |
| Reviewed: No | Change nothing. Say what is still waiting for the user (Step 6, item 9) and offer to ask again later. Do not wrap up. |

### Agree and submit (after the user's review)

1. Re-read the whole form. Note every unticked consent, privacy, terms, certification or "I agree" box, with its
   exact label text, and anything the user changed since the report (keep the user's values).
2. Check what still blocks submitting: a required field still empty, files not attached for this application
   ID, a CAPTCHA or bot check (never solve one), or a validation error on the page. If any is present, say what,
   and stop: do not submit.
3. Ask with AskUserQuestion (header "Submit"): "Tick these boxes on the <Company> form and submit: <each box's
   label, shortened>?" with any red flags from Step 6 named in the question. Options: "Yes, agree and submit" /
   "Submit, but leave the boxes to me" (only offered when no box is required) / "No, I'll do it myself". This
   answer is the user's approval for those exact boxes and this one submission; it does not carry over to
   another form or run.
4. On "Yes, agree and submit": tick exactly the listed boxes (click, then read each state back). Do not tick any
   box that was not in the question; if a new one appears, ask again.
5. Click Submit (or Apply / Send Application) once. On a multi-page form this is only the final page's button.
   If ticked boxes were on an earlier page (a consent page that stopped Step 4), tick them there, carry on
   through the remaining pages as in Step 4's "Multi-page forms", and click Submit on the final page.
6. Confirm it went through (Step 5's confirmation rule). If the page shows an error or nothing clear, report
   what it shows, do not retry, and do not wrap up.
7. On a confirmation, go to "Wrap up".

### Wrap up (only after a confirmed or user-confirmed submission)

Do these in order, and stop at the first one that fails (report it and leave both tabs open):

1. **Mark it applied** with Step 5's status update; expect `"status":"applied"`.
2. **Profile document:** make sure every new answer the user gave in this run is in the Reusable Answers table
   of the profile document (and `data/PROFILE.md` where it belongs), with "Last updated" set to today.
   Re-read the file to check.
3. **Close the Chrome tab** with the application form (the one this run opened in Claude's tab group, using the
   tab close tool). Close no other tab.
4. **Final report** in one short message: company, role, ID, the confirmation text, the status response, what
   was added to the profile document, and that the tabs are being closed.
5. **Close this Herdr tab**, last of all, only when everything above succeeded and this session is claimed for
   this application, whether Fill form opened it or the apply-from-link workflow renamed it. Check with Bash:

   ```bash
   [ "${HERDR_ENV:-}" = 1 ] && herdr tab get "$HERDR_TAB_ID"
   ```

   Close it only if that tab's `label` ends with this application's ID (both workflows label tabs
   `<Company>-<Role>-<id>`); otherwise leave it open and say so. Then run, as the final command of the run:

   ```bash
   herdr tab close "$HERDR_TAB_ID"
   ```

   This ends this session, so nothing may come after it.

Never mark an application applied unless the user answered Submitted: Yes (and the page or the user confirmed
it) or a submission in this run saw a confirmation.
