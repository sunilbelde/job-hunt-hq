# email-status-updates Specification

## Purpose

Lets an outside email classifier, such as the owner's n8n workflow, move a recorded application's status after a job email arrives. The classifier gives a company, a role and an email outcome rather than an application ID, and the service updates only an application it can identify without guessing.

## Requirements

### Requirement: Email status endpoint authentication
`POST /application/email-status` SHALL require the `X-API-Key` header to equal the configured API key, and SHALL respond 401 with `{"ok": false, "message": ...}` otherwise. It SHALL check the key before it reads the body or touches the application store.

#### Scenario: Missing key
- **WHEN** a client sends a valid body without `X-API-Key`
- **THEN** the system responds 401 with `ok` false and a `message`, and no application changes

#### Scenario: Wrong key with malformed body
- **WHEN** a client sends a wrong `X-API-Key` and a body that is not JSON
- **THEN** the system responds 401, not 422

#### Scenario: No match information without key
- **WHEN** a client without a valid key sends a company and role that match no application
- **THEN** the system responds 401, not 404

### Requirement: Email status request body
The body SHALL be a JSON object with `company` and `role` as non-empty strings and `status` as `Applied`, `Rejected` or `Response`. The `status` value SHALL be matched ignoring letter case and surrounding whitespace. `job_link`, `received_at` and `note` SHALL be optional strings or null. Unknown fields SHALL be ignored. An invalid body SHALL get 422 with a `message` that names the failing fields but never echoes their values, and nothing SHALL change.

#### Scenario: n8n summary accepted
- **WHEN** an authenticated client sends `{"company": "Ramp", "role": "Applied AI Engineer", "status": "Rejected", "received_at": "Nov 7, 2026 9:21 PM", "note": "..."}`
- **THEN** the body is accepted

#### Scenario: Status case ignored
- **WHEN** `status` is `rejected` or ` RESPONSE `
- **THEN** it is accepted as `Rejected` or `Response`

#### Scenario: Unknown email status
- **WHEN** `status` is `Interview` or `Offer`
- **THEN** the system responds 422 naming `status`, does not echo the value, and no application changes

#### Scenario: Missing company or role
- **WHEN** `company` or `role` is absent, empty, null or not a string
- **THEN** the system responds 422 naming that field

#### Scenario: Malformed body
- **WHEN** the body is not valid JSON, or is a JSON array, string, number or null
- **THEN** the system responds 422 with `ok` false and a `message`

#### Scenario: Note not stored
- **WHEN** a body carries a `note` and `received_at`
- **THEN** neither value is stored on the application or written to any log

### Requirement: Tolerant name comparison
Company and role SHALL be compared after normalization. Normalization ignores letter case, accents, punctuation and repeated whitespace, and treats `&` as `and`. For companies, it also drops a leading `The` and trailing legal suffixes such as `Inc`, `LLC`, `Ltd`, `Corp`, `Co`, `PLC` and `GmbH`. For roles, it treats `Sr` as `Senior` and `Jr` as `Junior`. Two names that are still not equal SHALL match only when their normalized similarity is at least 0.9.

#### Scenario: Company suffix and case
- **WHEN** the stored company is `Ramp Business Corporation, Inc.` and the request says `ramp business corporation`
- **THEN** the companies match

#### Scenario: Punctuation and abbreviation in role
- **WHEN** the stored role is `Sr. Software Engineer - Payments` and the request says `Senior Software Engineer, Payments`
- **THEN** the roles match

#### Scenario: Small typo
- **WHEN** the stored role is `Applied AI Engineer` and the request says `Applied AI Enginer`
- **THEN** the roles match

#### Scenario: Different role at the same company
- **WHEN** the stored role is `Applied AI Engineer` and the request says `Product Designer`
- **THEN** the roles do not match

### Requirement: Single-application matching
The system SHALL pick an application only when exactly one candidate matches. If `job_link` is present and has the same dedupe key as a stored application, that application is the only candidate. Otherwise the candidates are applications whose company and role both match. When some candidates match a name exactly after normalization and others only by similarity, only the exact matches SHALL count.

#### Scenario: One application matches
- **WHEN** one stored application is `Ramp` / `Applied AI Engineer` and the request names `Ramp` / `Applied AI Engineer`
- **THEN** that application is selected

#### Scenario: Link decides
- **WHEN** the request's `job_link` has the dedupe key of a stored application, and two applications match the company and role
- **THEN** the application with that link is selected

#### Scenario: Unknown link falls back to names
- **WHEN** the request's `job_link` matches no stored application and exactly one application matches the company and role
- **THEN** that application is selected

#### Scenario: Exact match beats a near match
- **WHEN** the stored roles at `Ramp` are `Applied AI Engineer` and `Applied AI Engineers`, and the request says `Applied AI Engineer`
- **THEN** the `Applied AI Engineer` application is selected

#### Scenario: Company matches but role does not
- **WHEN** the only application at `Ramp` is `Product Designer` and the request says `Applied AI Engineer`
- **THEN** no application is selected

### Requirement: No match reported without change
When no application matches, the system SHALL respond 404 with `{"ok": false, "reason": "no_match", "message": ...}` and SHALL change nothing.

#### Scenario: Unknown company
- **WHEN** an authenticated client sends a company that no stored application has
- **THEN** the system responds 404 with `reason` `no_match`, and no application changes

### Requirement: Ambiguous match reported without change
When more than one application matches, the system SHALL respond 409 with `{"ok": false, "reason": "ambiguous", "message": ..., "match_count": <n>}` and SHALL change nothing. The response SHALL NOT include the IDs or fields of the matching applications.

#### Scenario: Same role posted twice
- **WHEN** two applications have company `Ramp` and role `Applied AI Engineer` with different job links, and the request carries no `job_link`
- **THEN** the system responds 409 with `reason` `ambiguous` and `match_count` 2, and neither application changes

### Requirement: Email status mapping
`Applied` SHALL never change an application. `Rejected` SHALL set status `rejected`. `Response` SHALL set status `interviewing`. A status SHALL NOT move backwards: `Response` leaves `interviewing`, `offer`, `rejected` and `withdrawn` unchanged, and `Rejected` leaves `withdrawn` unchanged. An unchanged application keeps its `updated_at`.

#### Scenario: Applied confirms only
- **WHEN** the matched application's status is `verified` or `applied` and the email status is `Applied`
- **THEN** the status is unchanged and the response reports `changed` false

#### Scenario: Rejection recorded
- **WHEN** the matched application's status is `applied`, `interviewing` or `offer` and the email status is `Rejected`
- **THEN** its status becomes `rejected`

#### Scenario: Response moves to interviewing
- **WHEN** the matched application's status is `verified` or `applied` and the email status is `Response`
- **THEN** its status becomes `interviewing`

#### Scenario: Response after rejection
- **WHEN** the matched application's status is `rejected` and the email status is `Response`
- **THEN** the status stays `rejected` and the response reports `changed` false

#### Scenario: Withdrawn kept
- **WHEN** the matched application's status is `withdrawn` and the email status is `Rejected`
- **THEN** the status stays `withdrawn`

#### Scenario: Repeated rejection
- **WHEN** the same `Rejected` email is sent twice
- **THEN** both responses are 200, the first with `changed` true and the second with `changed` false

### Requirement: Email status success response
When exactly one application matches, the system SHALL respond 200 with exactly `{"ok": true, "application_id": "<uuid>", "company": ..., "role": ..., "previous_status": ..., "status": ..., "changed": <bool>}`. `company` and `role` SHALL be the stored values. `application_id` SHALL be lowercase.

#### Scenario: Response shape
- **WHEN** an application `<id>` stored as `Ramp` / `Applied AI Engineer` with status `applied` is matched by a `Rejected` email
- **THEN** the response is 200 with body `{"ok": true, "application_id": "<id>", "company": "Ramp", "role": "Applied AI Engineer", "previous_status": "applied", "status": "rejected", "changed": true}` and no other keys

### Requirement: Email status update changes only status
A matched update SHALL change only the application's `status` and `updated_at`. The match and the update SHALL happen as one atomic step, so a concurrent change to the application cannot be overwritten with a status based on a stale read.

#### Scenario: Other fields untouched
- **WHEN** a `Response` email updates an application
- **THEN** every stored field other than `status` and `updated_at` is unchanged

#### Scenario: Concurrent emails
- **WHEN** a `Rejected` email and a `Response` email for the same `applied` application arrive at the same time
- **THEN** the final status is `rejected` whichever is applied first

### Requirement: Email status store failure handling
When the application store cannot be read or written, the endpoint SHALL respond 503 with `{"ok": false, "message": ...}`. The message SHALL be generic and expose no path or exception text. The details SHALL be logged server-side.

#### Scenario: Store unavailable
- **WHEN** an authenticated request with a valid body hits a database error
- **THEN** the system responds 503 with a generic `message` and no path or exception text

### Requirement: Email status request logging
Each request SHALL emit exactly one `application_request` log line. The line SHALL carry method `POST`, the HTTP status, the duration and, when one application matched, its `application_id`. It SHALL NOT log the API key, `company`, `role`, `note`, `received_at`, `job_link` or either status value.

#### Scenario: Successful update log
- **WHEN** a `Rejected` email updates application `<id>`
- **THEN** one log line records method `POST`, status 200, `application_id` `<id>` and the duration
- **AND** the line does not contain the company, role, `Rejected` or `rejected`

#### Scenario: Ambiguous log
- **WHEN** a request matches two applications
- **THEN** one log line records status 409 and no `application_id`
