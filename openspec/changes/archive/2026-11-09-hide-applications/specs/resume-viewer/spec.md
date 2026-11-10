# Spec Delta

## ADDED Requirements

### Requirement: Hidden flag in the application list
Each entry of `GET /applications` SHALL carry `hidden`, true when the application is hidden and false otherwise. The list SHALL still return hidden applications.

#### Scenario: Flag listed
- **WHEN** the store holds one hidden and one visible application
- **THEN** the first entry has `hidden` true and the second false, and both are returned

### Requirement: Viewer hide endpoint
Where the viewer is served, `PUT /viewer/application/{application_id}/hidden` SHALL set whether the application is hidden from a JSON object body `{"hidden": <boolean>}`, without requiring the API key, and change no other field except the update time. It SHALL respond 200 with exactly `{"ok": true, "application_id": "<uuid>", "hidden": <boolean>}`. Setting the value it already has SHALL succeed.

#### Scenario: Hidden
- **WHEN** the viewer sends `{"hidden": true}` without `X-API-Key` for a visible application
- **THEN** the response is 200 `{"ok": true, "application_id": "<id>", "hidden": true}`, `GET /applications` lists it with `hidden` true, and its status, report and files are unchanged

#### Scenario: Unhidden
- **WHEN** the viewer sends `{"hidden": false}` for a hidden application
- **THEN** the response is 200 with `hidden` false and the list shows it not hidden

#### Scenario: Same value again
- **WHEN** the body sets the value the application already has
- **THEN** the response is 200

### Requirement: Viewer hide validation
The hide endpoint SHALL reject with 422 `{"ok": false, "message": ...}`, changing nothing, a body that is not a JSON object, has no `hidden`, or has a `hidden` that is not a boolean. The message SHALL name `hidden` and SHALL NOT echo the value sent.

#### Scenario: Not a boolean
- **WHEN** the body is `{"hidden": "yes"}`, `{"hidden": 1}` or `{"hidden": null}`
- **THEN** the response is 422 naming `hidden`, not containing the value, and the row is unchanged

#### Scenario: Missing or not an object
- **WHEN** the body is `{}`, a JSON array or not JSON
- **THEN** the response is 422 and the row is unchanged

### Requirement: Viewer hide guarded like other viewer writes
The hide endpoint SHALL respond 403 `{"ok": false, "message": "Cross-site request refused"}` for cross-site requests before the body is read, 404 `{"ok": false, "message": "Application not found"}` for an unknown or non-UUID ID even when the body is invalid, and 503 when the store is unavailable. It SHALL exist only when API docs are enabled.

#### Scenario: Cross-site
- **WHEN** the request carries `Sec-Fetch-Site: cross-site`
- **THEN** the response is 403 and the row is unchanged

#### Scenario: Unknown application
- **WHEN** the ID is not a UUID or identifies no row, whatever the body
- **THEN** the response is 404

#### Scenario: Docs disabled
- **WHEN** API docs are disabled and a client sends the request
- **THEN** the response is 404 and the row is unchanged

### Requirement: Hidden applications left out of the list
The viewer list SHALL leave out hidden applications unless "Show hidden" is on. It is off when the page loads. Toggling it SHALL happen in the page and send no request, and it SHALL combine with the search, status and date filters.

#### Scenario: Default
- **WHEN** the page loads with 2 hidden and 5 visible applications
- **THEN** only the 5 visible entries are listed

#### Scenario: Show hidden on
- **WHEN** the owner turns on "Show hidden"
- **THEN** all 7 are listed, the hidden ones in their normal list order, and no request is sent

#### Scenario: Combined with status
- **WHEN** "Show hidden" is on and the status filter is `rejected`
- **THEN** both visible and hidden `rejected` applications are listed

### Requirement: Show hidden control
Below the status filter the viewer SHALL show a "Show hidden (N)" checkbox, N being the number of hidden applications, whenever N is above zero. It SHALL stay shown while on, even if the owner unhides the last one, until the owner turns it off or reloads. Clearing filters SHALL NOT change it.

#### Scenario: Count shown
- **WHEN** 3 applications are hidden
- **THEN** the checkbox reads "Show hidden (3)"

#### Scenario: None hidden
- **WHEN** no application is hidden and the checkbox has not been turned on
- **THEN** no checkbox is shown

#### Scenario: Clear filters
- **WHEN** "Show hidden" is on and the owner chooses Clear
- **THEN** the search, status and date filters are reset and "Show hidden" stays on

### Requirement: Hidden entries marked
When shown, a hidden application's list entry SHALL be visually muted and carry a "Hidden" tag, so it cannot be mistaken for a visible one.

#### Scenario: Marked
- **WHEN** "Show hidden" is on
- **THEN** each hidden entry shows the "Hidden" tag and visible entries do not

### Requirement: Hide and unhide from the action bar
The selected application's action bar SHALL offer a Hide action immediately before Delete, labelled Unhide when the application is hidden, styled as a normal (not destructive) button and asking for no confirmation. List entries SHALL carry no Hide action.

#### Scenario: Hide
- **WHEN** the owner selects a visible application and chooses Hide
- **THEN** one `PUT /viewer/application/<id>/hidden` with `{"hidden": true}` is sent, the entry leaves the list while "Show hidden" is off, the details stay shown, and the button now reads Unhide

#### Scenario: Unhide
- **WHEN** the selected application is hidden (opened via "Show hidden" or its link) and the owner chooses Unhide
- **THEN** `{"hidden": false}` is sent and the entry is listed as visible with no "Hidden" tag

### Requirement: Hide result shown without reloading
Choosing Hide or Unhide SHALL send one hide request, then update the list, counts and action bar without reloading, show "Hidden" or "Unhidden" in the action bar, and keep the application selected with its details shown. If the request fails, the action bar SHALL show the error and keep the previous state.

#### Scenario: Stays selected
- **WHEN** the owner hides the selected application
- **THEN** its details remain shown

#### Scenario: Fails
- **WHEN** the request responds with an error
- **THEN** the action bar shows "Not saved: <message>" and the button and list are unchanged

#### Scenario: Busy
- **WHEN** a write for the application is in flight
- **THEN** the Hide/Unhide button is disabled

### Requirement: Counts and empty state with hidden applications
With "Show hidden" off, the header count SHALL count only visible applications and, when any are hidden, end with " · N hidden" (for example "17 applications · 3 hidden"). With it on, hidden applications SHALL be included in the count and no suffix shown. When applications exist but all are hidden and "Show hidden" is off, the list SHALL say all applications are hidden.

#### Scenario: Count with hidden
- **WHEN** 20 applications exist, 3 hidden, and "Show hidden" is off
- **THEN** the header shows "17 applications · 3 hidden"

#### Scenario: Count with hidden shown
- **WHEN** "Show hidden" is turned on
- **THEN** the header shows "20 applications"

#### Scenario: Filtered count
- **WHEN** "Show hidden" is off and 5 of the 17 visible applications match the filters
- **THEN** the header shows "5 of 17 applications · 3 hidden"

#### Scenario: Everything hidden
- **WHEN** every application is hidden and "Show hidden" is off
- **THEN** the list says all applications are hidden, and the "Show hidden" checkbox is shown

#### Scenario: Selected application hidden
- **WHEN** the selected application becomes hidden while "Show hidden" is off
- **THEN** its details stay shown although its entry has left the list

### Requirement: Hidden applications stay usable
A hidden application SHALL keep every behavior it had: it can be opened by its link, its generation and form fill work, emails still match it, and recording its link again returns the existing ID and leaves it hidden.

#### Scenario: Re-recorded
- **WHEN** a hidden application's link is recorded again
- **THEN** the response is the existing ID as a duplicate and the application is still hidden
