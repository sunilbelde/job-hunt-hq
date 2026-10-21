# Spec Delta

## ADDED Requirements

### Requirement: Render tailored resume from the base template
The system SHALL compile a tailored resume's TeX, built from the bundled base template, with the same guarantees as the baseline render: a temporary workspace of its own, removed afterwards, the bundled template files left unchanged, the same time limit, the compiler's untrusted mode, and no network access at request time.

#### Scenario: Offline tailored render
- **WHEN** a tailored resume is rendered on the installed Mac mini with outbound network blocked
- **THEN** the render succeeds using the local TeX cache

#### Scenario: Hung compiler
- **WHEN** compiling a tailored resume does not finish within the time limit
- **THEN** the compiler is killed and the render fails

#### Scenario: Cleanup and unchanged template
- **WHEN** a tailored render finishes, successfully or not
- **THEN** its workspace no longer exists and the bundled template files are unchanged
