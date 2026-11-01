# Spec Delta

## ADDED Requirements

### Requirement: Viewer fill endpoint
Where the viewer is served, `POST /viewer/application/{application_id}/fill` SHALL, without requiring the API key, open a tab in the Herdr workspace named by `FILL_WORKSPACE` (default `Claude-Jobs-Automation`), labelled `<company>-<role>-<application id>`, starting in the repository, that runs `claude --chrome "/job-application-form-filler <application id>"`. It SHALL change no stored data and ignore any request body.

#### Scenario: Tab opened
- **WHEN** the viewer posts to the fill endpoint for application `<id>` of "Rula – Staff Forward Deployed Engineer"
- **THEN** a tab labelled `Rula-Staff Forward Deployed Engineer-<id>` opens in `Claude-Jobs-Automation` running `claude --chrome "/job-application-form-filler <id>"`
- **AND** the response is 200 with exactly `{"ok": true, "application_id": "<id>", "tab_id": "<herdr tab id>", "tab_label": "Rula-Staff Forward Deployed Engineer-<id>", "already_open": false}`, the ID in lowercase

#### Scenario: Workspace missing
- **WHEN** no Herdr workspace is labelled `Claude-Jobs-Automation`
- **THEN** one is created with that label and its first tab is used, labelled as above

#### Scenario: Already open
- **WHEN** a tab whose label ends with the application's ID is open in the workspace
- **THEN** no tab is opened and nothing is run, and the response is 200 with that tab and `already_open` true

#### Scenario: Only the ID reaches the command
- **WHEN** the company or role contains shell syntax or control characters
- **THEN** the command run is still exactly the fixed command with the application ID, and the label has the control characters removed

#### Scenario: Herdr unavailable
- **WHEN** the Herdr CLI is missing, the Herdr server is not running, or Herdr returns an error or an unexpected reply
- **THEN** the response is 503 `{"ok": false, "message": "Herdr unavailable"}` and the log records a `herdr_error` without Herdr's output

#### Scenario: Unknown application
- **WHEN** the ID is not a UUID or not stored
- **THEN** the response is 404 `Application not found` and Herdr is not called

#### Scenario: Cross-site or docs off
- **WHEN** the request is cross-site under the rule for viewer writes, or API docs are disabled
- **THEN** the response is 403 `Cross-site request refused`, or 404 as for an unknown path, and Herdr is not called

### Requirement: Fill form from the viewer
Every entry in the application list SHALL offer a **Fill form** button that posts to the fill endpoint for that application. While the request is pending the entry's controls SHALL be disabled. On success the entry SHALL show "Opened Herdr tab <label>", or "Already open in Herdr tab <label>"; on failure, "Not opened: <message>". Using it SHALL NOT select the application.

#### Scenario: Opened
- **WHEN** the owner clicks Fill form on an entry
- **THEN** one `POST /viewer/application/<id>/fill` is sent and the entry shows the tab label

#### Scenario: Herdr not running
- **WHEN** the endpoint answers 503 `Herdr unavailable`
- **THEN** the entry shows "Not opened: Herdr unavailable"
