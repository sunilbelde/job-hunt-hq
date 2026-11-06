# Spec Delta

## ADDED Requirements

### Requirement: Easy Apply tag on list entries
A list entry whose `posting_source_type` is `linkedin_easy_apply` SHALL show an **Easy Apply** tag beside its origin tag. Other entries SHALL show no such tag. The tag SHALL be display only.

#### Scenario: Easy Apply application
- **WHEN** an application has `added_via` `link` and `posting_source_type` `linkedin_easy_apply`
- **THEN** its entry shows the tags ByLink and Easy Apply

#### Scenario: Other application
- **WHEN** an application has `posting_source_type` `recruiting_platform` or `employer_site`
- **THEN** its entry shows no Easy Apply tag

## MODIFIED Requirements

### Requirement: Application list
`GET /applications` SHALL return every stored application, most recently generated first and then most recently recorded, each with its ID, company, role, status, recorded time, `added_via`, `posting_source_type`, `jobs` and, when it has a report, the generation time, match status, base score and generated score. `jobs` SHALL hold `resume` and `cover_letter`, each null when that kind has no job, else exactly `status`, `started_at`, `finished_at` and `error`. It SHALL NOT include posting text, nor any job's saved path, match or letter text. It SHALL NOT require the API key, and SHALL ignore an `X-API-Key` header if one is sent.

#### Scenario: Listed with report summary
- **WHEN** the store holds an application with a stored report and one without
- **THEN** both are returned; the first carries its generation time, match status and scores, and the second carries `report` `null`

#### Scenario: Job summaries
- **WHEN** an application has a running resume job and a failed cover letter job, and another has no jobs
- **THEN** the first carries `jobs.resume` with `status` `running`, its `started_at` and null `finished_at` and `error`, and `jobs.cover_letter` with `status` `failed` and its fixed `error`; the second carries `{"resume": null, "cover_letter": null}`

#### Scenario: No job results in the list
- **WHEN** an application's resume and cover letter jobs are `done`
- **THEN** its list entry contains neither job's `saved_path`, `match` nor `text`

#### Scenario: Missing key
- **WHEN** `GET /applications` is sent without `X-API-Key`, or with a wrong one
- **THEN** the response is 200 with the applications

#### Scenario: Store unavailable
- **WHEN** the application store cannot be read
- **THEN** the response is 503 `{"ok": false, "message": "Application store unavailable"}`

#### Scenario: Origin listed
- **WHEN** the store holds an application recorded by link and one with no recorded origin
- **THEN** the first carries `added_via` `link` and the second `manual`

#### Scenario: Source type listed
- **WHEN** the store holds an Easy Apply application and an employer site application
- **THEN** the first carries `posting_source_type` `linkedin_easy_apply` and the second `employer_site`

#### Scenario: Filtered by link
- **WHEN** `GET /applications?job_link=<link>` is sent and a stored application's `job_link` has the same dedupe key
- **THEN** the response holds only that application

#### Scenario: Filter matches nothing
- **WHEN** no stored application has that dedupe key
- **THEN** the response is 200 with an empty `applications` list

#### Scenario: Filter ignores tracking parameters
- **WHEN** the stored link is `https://jobs.ashbyhq.com/acme/1` and the filter value is `https://jobs.ashbyhq.com/acme/1/?utm_source=x`
- **THEN** that application is returned

### Requirement: Fill form from the viewer
The selected application's action bar SHALL offer a **Fill form** button that posts to the fill endpoint for that application, unless its `posting_source_type` is `linkedin_easy_apply`, where no form exists to fill and the button SHALL NOT be offered. While the request is pending the button SHALL be disabled. On success the action bar SHALL show "Opened Herdr tab <label>", or "Already open in Herdr tab <label>"; on failure, "Not opened: <message>". List entries SHALL carry no Fill form button.

#### Scenario: Opened
- **WHEN** the owner clicks Fill form in the action bar
- **THEN** one `POST /viewer/application/<id>/fill` is sent and the action bar shows the tab label

#### Scenario: Herdr not running
- **WHEN** the endpoint answers 503 `Herdr unavailable`
- **THEN** the action bar shows "Not opened: Herdr unavailable"

#### Scenario: Easy Apply application selected
- **WHEN** the selected application has `posting_source_type` `linkedin_easy_apply`
- **THEN** its action bar shows no Fill form button, and still shows the status, resume, cover letter and Delete controls
