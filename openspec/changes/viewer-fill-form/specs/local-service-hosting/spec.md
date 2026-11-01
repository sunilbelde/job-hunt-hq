# Spec Delta

## MODIFIED Requirements

### Requirement: Smoke test checks the docs listener
The smoke test SHALL check that the docs listener serves the reference page, the viewer page and an OpenAPI document with the eighteen documented operations, in addition to its public-address checks.

#### Scenario: Docs listener healthy
- **WHEN** the smoke test runs and the docs listener answers `/docs` and `/viewer` with 200 and `/openapi.json` with the eighteen operations
- **THEN** the docs check passes

#### Scenario: Docs listener missing
- **WHEN** the docs listener does not answer `/docs` with 200
- **THEN** the smoke test fails before creating any application

#### Scenario: Wrong operation count
- **WHEN** the docs listener's OpenAPI document lists any number of operations other than eighteen, such as the seventeen from before the fill endpoint
- **THEN** the smoke test fails before creating any application

## ADDED Requirements

### Requirement: Service finds the Herdr CLI
The install script SHALL put the path of the Herdr CLI it finds on its `PATH` into the launchd job as `HERDR_BIN`, or the bare name `herdr` when none is found, without failing the install.

#### Scenario: Herdr installed
- **WHEN** `herdr` is on the installing shell's `PATH`
- **THEN** the installed plist's `HERDR_BIN` is that path

#### Scenario: Herdr missing
- **WHEN** no `herdr` is found
- **THEN** the install completes and `HERDR_BIN` is `herdr`
