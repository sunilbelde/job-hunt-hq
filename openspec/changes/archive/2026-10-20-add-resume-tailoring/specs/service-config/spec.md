# Spec Delta

## ADDED Requirements

### Requirement: Claude credential for tailoring
The system SHALL read an optional `CLAUDE_CODE_OAUTH_TOKEN` and the optional `ANTHROPIC_API_KEY`. It SHALL give each Claude run exactly one of them, the API key when both are set. With neither set, the service SHALL still start, and any resume that needs scoring SHALL fail generation. Neither value SHALL appear in logs, error messages or files the service writes.

#### Scenario: Subscription token only
- **WHEN** `.env` sets `CLAUDE_CODE_OAUTH_TOKEN` and not `ANTHROPIC_API_KEY`
- **THEN** Claude runs authenticate with the token

#### Scenario: Both set
- **WHEN** both `CLAUDE_CODE_OAUTH_TOKEN` and `ANTHROPIC_API_KEY` are set
- **THEN** Claude runs receive only `ANTHROPIC_API_KEY`

#### Scenario: Neither set
- **WHEN** the service starts with no Claude credential
- **THEN** it starts normally, resumes for applications without usable posting text are still generated, and resumes that need scoring fail with the generic 500

#### Scenario: Credential kept secret
- **WHEN** a Claude run fails for any reason
- **THEN** neither credential value appears in the log or the response

### Requirement: Tailoring run settings
The system SHALL read four optional settings:
- `TAILORING_MODEL`, default `claude-opus-5-5`
- `TAILORING_TIMEOUT_SECONDS`, an integer from 60 to 480, default 420
- `TAILORING_MAX_BUDGET_USD`, a number above 0, default 3
- `CLAUDE_BIN`, default `claude`

The time limit and the spend cap SHALL apply to all the Claude runs for one resume together. An invalid value SHALL fail startup with an error naming the variable, without printing secret values.

#### Scenario: Defaults
- **WHEN** none of these variables is set
- **THEN** Claude runs use `claude-opus-5-5`, the runs for one resume stop after 420 seconds or an estimated 3 USD in total, and they use the `claude` command found on the service's `PATH`

#### Scenario: Invalid timeout
- **WHEN** `TAILORING_TIMEOUT_SECONDS` is `30` or `abc`
- **THEN** startup fails and the error identifies `TAILORING_TIMEOUT_SECONDS`

#### Scenario: Invalid budget
- **WHEN** `TAILORING_MAX_BUDGET_USD` is `0`
- **THEN** startup fails and the error identifies `TAILORING_MAX_BUDGET_USD`

#### Scenario: Documented in example file
- **WHEN** a developer opens `.env.example`
- **THEN** `CLAUDE_CODE_OAUTH_TOKEN`, `TAILORING_MODEL`, `TAILORING_TIMEOUT_SECONDS`, `TAILORING_MAX_BUDGET_USD` and `CLAUDE_BIN` appear with placeholder or default values, and `ANTHROPIC_API_KEY` is described as a tailoring credential rather than reserved
