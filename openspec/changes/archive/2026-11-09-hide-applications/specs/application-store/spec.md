# Spec Delta

## ADDED Requirements

### Requirement: Application hidden flag stored
Every application row SHALL hold whether it is hidden, defaulting to not hidden. The flag SHALL change only through the viewer hide action, and SHALL be kept across updates through the keyed API, duplicate recordings, email status updates and service restarts.

#### Scenario: New row
- **WHEN** an application is recorded
- **THEN** it is not hidden

#### Scenario: Survives other writes
- **WHEN** a hidden row's status and salary are updated and its link is recorded again
- **THEN** it is still hidden

#### Scenario: Not set by the keyed update
- **WHEN** a keyed `PATCH /application/<id>` body contains `hidden`
- **THEN** the field is ignored and the row's flag is unchanged

### Requirement: Existing stores gain the hidden flag
Initialising a store created before this field SHALL add it in place, with every existing row not hidden, and SHALL keep all other data. Doing so again SHALL change nothing.

#### Scenario: Store from before the field
- **WHEN** the service starts on a store whose rows have no hidden flag
- **THEN** every row is not hidden and its other fields are unchanged

#### Scenario: Restart after the migration
- **WHEN** the service restarts on a store that already has the field
- **THEN** startup succeeds and no value changes
