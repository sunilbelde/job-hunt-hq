# Spec Delta

## MODIFIED Requirements

### Requirement: Application details shown
For the selected application, the viewer SHALL show its company, role, status, location, work type, salary, posting date, sponsorship, why it fits, the job link and careers URL as links, when it was recorded and last updated, and the posting text, which SHALL be collapsed until the owner expands it. Empty fields SHALL be omitted. The status SHALL be shown as text; the detail pane SHALL NOT offer a status control or a Delete action.

#### Scenario: Details present
- **WHEN** the owner selects an application with a location, salary and posting text
- **THEN** the page shows them, with the posting text collapsed

#### Scenario: Posting text shown as text
- **WHEN** the stored posting text contains HTML markup or script
- **THEN** the page shows it as literal text and runs nothing from it

#### Scenario: No write controls in the details
- **WHEN** the owner selects an application
- **THEN** the detail pane shows its status as text and has no status control and no Delete button

#### Scenario: Status text follows a change from the list
- **WHEN** the selected application's status is changed to `applied` from its list entry
- **THEN** the detail pane shows `applied` without reloading the application

### Requirement: Status changed from the viewer
Every entry in the application list SHALL show its application's status as a control listing the six application statuses, with the current one selected. Choosing a different status SHALL save it at once, update that entry (and the details, when that application is selected) without reloading the page, and show that it was saved. If the save fails, the viewer SHALL show the error message on that entry and put the control back to the stored status. Using the control SHALL NOT select the application.

#### Scenario: Changing status
- **WHEN** the owner selects `applied` in the list entry of an application whose status is `verified`
- **THEN** one `PATCH /viewer/application/<id>` is sent and the entry shows `applied`

#### Scenario: Changing status of an unopened application
- **WHEN** application A is selected and the owner changes application B's status from B's list entry
- **THEN** B's status is saved, A stays selected and its details stay shown, and B's details and PDFs are not loaded

#### Scenario: Save fails
- **WHEN** the save responds with an error
- **THEN** the entry shows the error message and its control shows the previous status

#### Scenario: No write on selection
- **WHEN** the owner selects an application and does not change its status
- **THEN** no write request is sent

### Requirement: Application deleted from the viewer
Every entry in the application list SHALL offer a Delete action that first asks for confirmation naming the company and role and saying it cannot be undone. Only after the owner confirms SHALL it send the delete. On success it SHALL remove the entry from the list and update the count, and, if that application was selected, clear the detail pane. On failure it SHALL show the error on that entry and leave it listed. Using Delete SHALL NOT select the application.

#### Scenario: Confirmed
- **WHEN** the owner chooses Delete on the "Acme – Data Engineer" list entry and confirms
- **THEN** one `DELETE /viewer/application/<id>` is sent, the entry leaves the list and the count drops by one

#### Scenario: Selected application deleted
- **WHEN** the deleted application was the selected one
- **THEN** the detail pane says to select an application

#### Scenario: Other application deleted
- **WHEN** application A is selected and the owner deletes application B from its list entry
- **THEN** A stays selected and its details stay shown

#### Scenario: Cancelled
- **WHEN** the owner chooses Delete and then cancels
- **THEN** no request is sent, the entry stays listed and the selection is unchanged

#### Scenario: Delete fails
- **WHEN** the delete responds with an error
- **THEN** the entry shows the error message and is still listed

#### Scenario: Deleted application in the URL
- **WHEN** the deleted application's ID is still in the page's URL fragment
- **THEN** the fragment is cleared, and a reload shows the list with nothing selected

## ADDED Requirements

### Requirement: List filtered by status
Above the application list, the viewer SHALL offer a status filter with "All statuses" (the default) and each of the six application statuses. Choosing a status SHALL show only applications with that status. Filtering SHALL happen in the page and SHALL NOT send a request.

#### Scenario: Filter by status
- **WHEN** the list holds 3 `applied` and 2 `verified` applications and the owner filters by `applied`
- **THEN** only the 3 `applied` entries are listed and no request is sent

#### Scenario: Back to all
- **WHEN** the owner chooses "All statuses" again
- **THEN** all 5 entries are listed

#### Scenario: Status changed out of the filter
- **WHEN** the list is filtered by `verified` and the owner changes an entry's status to `applied`
- **THEN** after the save succeeds the entry leaves the filtered list and the counts update

### Requirement: List filtered by recorded date
Above the application list, the viewer SHALL offer an optional "Recorded from" and "Recorded to" date. They SHALL filter on when the application was recorded in the store, not on the posting date, both ends inclusive, by calendar day in the browser's time zone. An empty end SHALL be unbounded. Both filters SHALL combine with the status filter.

#### Scenario: Date range
- **WHEN** applications were recorded on Oct 20, Oct 25 and Oct 30 and the owner sets from Oct 25 to Oct 30
- **THEN** the Oct 25 and Oct 30 applications are listed

#### Scenario: Posting date ignored
- **WHEN** an application was recorded on Oct 30 for a posting dated Sep 1 and the range is Oct 25 to Oct 30
- **THEN** it is listed

#### Scenario: Only a start date
- **WHEN** only "Recorded from" Oct 25 is set
- **THEN** every application recorded on or after Oct 25 is listed

#### Scenario: Combined with status
- **WHEN** the status filter is `applied` and the range is Oct 25 to Oct 30
- **THEN** only `applied` applications recorded in that range are listed

### Requirement: Filtered count and empty result
When any filter is set, the header count SHALL show how many applications match out of the total (for example "5 of 20 applications"); with no filter it SHALL show the total as before. When no application matches, the list SHALL say so and offer to clear the filters. The selected application's details SHALL stay shown when a filter hides its entry.

#### Scenario: Count while filtered
- **WHEN** 5 of 20 applications match the filters
- **THEN** the header shows "5 of 20 applications"

#### Scenario: Nothing matches
- **WHEN** no application matches
- **THEN** the list says no applications match and offers a control that clears every filter and lists all applications

#### Scenario: Selected application filtered out
- **WHEN** the selected application's entry is hidden by a filter
- **THEN** its details stay shown
