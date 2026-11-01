# Spec Delta

## ADDED Requirements

### Requirement: Status endpoints on the local listener only
Both status endpoints SHALL be served on the docs port, the loopback-only local listener, and SHALL NOT be served on the public port, where they are handled as unknown paths. They SHALL return only the fields listed above: no posting text, application fields other than the ID, scores breakdown, added-term evidence or full report.

#### Scenario: Local listener
- **WHEN** an authenticated client on the Mac calls `GET /resume/<id>/status` on the docs port after `POST /resume` for `<id>` was sent to the public port
- **THEN** it gets that job's status

#### Scenario: Public listener
- **WHEN** an authenticated client calls `GET /resume/<id>/status` or `GET /cover-letter/<id>/status` on the public port for an application with a job
- **THEN** it gets 404, as for an unknown path, and no job state

## REMOVED Requirements

### Requirement: Status endpoints on the public port
**Reason**: Muse does not poll job status, so the public Funnel address no longer serves the status endpoints. Replaced by "Status endpoints on the local listener only".
**Migration**: Poll `GET /resume/{id}/status` and `GET /cover-letter/{id}/status` on `http://127.0.0.1:8081` from the Mac, or watch the result in the viewer.
