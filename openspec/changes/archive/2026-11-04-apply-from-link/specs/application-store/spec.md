# Spec Delta

## ADDED Requirements

### Requirement: Application origin stored
Every application row SHALL hold how it was added, `link` or `manual`, and SHALL keep that value unchanged for the life of the row, across updates, duplicate recordings and service restarts.

#### Scenario: New row
- **WHEN** an application is recorded with `added_via` `link`
- **THEN** reading the row returns `added_via` `link`

#### Scenario: Survives an update
- **WHEN** a row's status and salary are updated
- **THEN** its `added_via` is unchanged

### Requirement: Existing stores gain the origin
Initialising a store created before this field SHALL add it in place, with every existing row reading `manual`, and SHALL keep all other data. Doing so again SHALL change nothing.

#### Scenario: Store from before the field
- **WHEN** the service starts on a store whose rows have no `added_via`
- **THEN** every row reads `manual` and its other fields are unchanged

#### Scenario: Restart after the migration
- **WHEN** the service restarts on a store that already has the field
- **THEN** startup succeeds and no value changes

#### Scenario: Store from before UUIDs
- **WHEN** the service starts on a store that still has integer IDs
- **THEN** it ends up with UUIDs and every row reads `manual`
