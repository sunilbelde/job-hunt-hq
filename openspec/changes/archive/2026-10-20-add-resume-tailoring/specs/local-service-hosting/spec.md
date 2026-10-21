# Spec Delta

## ADDED Requirements

### Requirement: Service runs Claude with its own configuration
The installed service SHALL run the Claude Code CLI found when it was installed. It SHALL give Claude runs a private configuration of the service's own, so the owner's personal Claude Code settings, login, plugins, hooks, MCP servers, memory and shell startup files are never used by service runs.

#### Scenario: CLI outside the service PATH
- **WHEN** the owner's Claude Code CLI is installed in `~/.local/bin`, which the launchd job's default `PATH` does not include
- **THEN** the installed service still finds and runs it

#### Scenario: Personal hooks not run
- **WHEN** the owner's own Claude Code configuration defines a hook or an MCP server
- **THEN** service Claude runs neither execute the hook nor connect to the server

#### Scenario: Shell profile not loaded
- **WHEN** the owner's `~/.zshrc` defines an alias or exports a variable
- **THEN** commands in service Claude runs see neither

### Requirement: Install checks tailoring prerequisites
The install script SHALL warn, without failing, when the Claude Code CLI cannot be found, when `.env` sets no Claude credential, or when one minimal live request shows the credential is rejected. Each warning SHALL say how to fix it and SHALL never print a credential.

#### Scenario: CLI missing
- **WHEN** the install script runs and no `claude` command is found
- **THEN** it completes the install, warns that resumes needing tailoring will fail, and says how to install Claude Code

#### Scenario: No credential
- **WHEN** `.env` sets neither `CLAUDE_CODE_OAUTH_TOKEN` nor `ANTHROPIC_API_KEY`
- **THEN** the install script warns and names `claude setup-token` and `ANTHROPIC_API_KEY` as the two ways to configure one

#### Scenario: Credential rejected
- **WHEN** `.env` sets a `CLAUDE_CODE_OAUTH_TOKEN` that the API rejects, such as one pasted across two lines
- **THEN** the install completes, warns that the credential was rejected, and says to paste the token from `claude setup-token` as one line

### Requirement: Status reports tailoring readiness
The status script SHALL report whether tailoring is ready: the Claude CLI path and version, which kind of credential is configured (subscription token or API key) and the model, without printing the credential.

#### Scenario: Ready
- **WHEN** the CLI is installed and `.env` sets `CLAUDE_CODE_OAUTH_TOKEN`
- **THEN** the status output shows tailoring as ready with a subscription token and the configured model

#### Scenario: Not configured
- **WHEN** no Claude credential is configured
- **THEN** the status output shows tailoring as not configured

### Requirement: Smoke test never starts a Claude run
The smoke test SHALL generate its resume for an application with no posting text and check that `match.status` is `no_job_description`. If it reuses a leftover application that has posting text, it SHALL clear that text before generating, so it never starts a Claude run.

#### Scenario: Fresh smoke test
- **WHEN** the smoke test runs against a service with no leftover smoke-test application
- **THEN** the resume is generated without a Claude run and `match.status` is `no_job_description`

#### Scenario: Leftover application with posting text
- **WHEN** an earlier version of the smoke test left its application with posting text
- **THEN** the smoke test clears that text before requesting the resume
