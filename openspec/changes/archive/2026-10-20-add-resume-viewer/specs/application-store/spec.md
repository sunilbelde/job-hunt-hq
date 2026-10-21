# Spec Delta

## ADDED Requirements

### Requirement: One generation report per application
The store SHALL hold at most one generation report per application, in the same private SQLite file as the applications, created on startup in a store that lacks it without changing any application row.

#### Scenario: Existing store upgraded
- **WHEN** the service starts against a store created before reports existed
- **THEN** it starts normally, every application row is unchanged, and no application has a report

#### Scenario: Regenerated
- **WHEN** a report is stored for an application that already has one
- **THEN** only the new report remains for it

### Requirement: Report removed with its application
Deleting an application SHALL also delete its report, in the same transaction, so no report remains for an ID that no longer names an application.

#### Scenario: Application deleted
- **WHEN** an application with a report is deleted
- **THEN** the store holds no report for its ID, and its saved resume file is kept

### Requirement: Report kept across application updates
Updating an application's fields SHALL NOT change or remove its report.

#### Scenario: Company renamed
- **WHEN** an application with a report has its company changed
- **THEN** its report, including the saved path, is unchanged
