# Spec Delta

## ADDED Requirements

### Requirement: Host paths never in responses
No HTTP response body from the service SHALL contain a file-system path on the service host: not the `OUTPUT_DIR` path, not the service user's home directory, and not a company or application folder. This SHALL hold on both listeners, for success and error responses and for 404s. A saved file SHALL be identified to clients only by its file name. Stored reports and job records SHALL keep the absolute path for the service's own use.

#### Scenario: Every JSON and HTML response checked
- **WHEN** a resume and a cover letter have been generated for an application, and every documented JSON or HTML endpoint is called for it, including unknown-ID, wrong-key and no-job 404 and 401 cases
- **THEN** no response body contains the `OUTPUT_DIR` path or the service user's home directory

#### Scenario: Stored path still used to read the file
- **WHEN** an application's resume was saved under its company's folder, and the company was renamed afterwards
- **THEN** the viewer's PDF endpoints still find the resume and the cover letter through the absolute path stored in the report
