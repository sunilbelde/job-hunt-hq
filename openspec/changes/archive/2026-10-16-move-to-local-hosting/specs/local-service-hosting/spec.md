# Spec Delta

## Purpose

Defines how the service runs as an always-on process on the owner's Mac mini: how it is started, kept alive, logged, installed and removed, and how it is reached privately from the owner's devices without any cloud hosting.

## ADDED Requirements

### Requirement: Starts at boot without login
The service SHALL be installed as a system launchd job that starts automatically when the Mac boots, without requiring any user to log in, and runs as the owner's non-root user account.

#### Scenario: Reboot
- **WHEN** the Mac mini restarts and nobody logs in
- **THEN** `GET /health` on the service responds 200 within two minutes of boot

#### Scenario: Not root
- **WHEN** the service process is running
- **THEN** its effective user is the owner's account, not root

### Requirement: Restarts after failure
The service SHALL be restarted automatically if its process exits unexpectedly, with a throttle that prevents a tight crash loop.

#### Scenario: Process killed
- **WHEN** the running service process is killed
- **THEN** a new process is serving `GET /health` within 30 seconds

### Requirement: Loopback-only listener
The service process SHALL listen only on the loopback interface, so it is not reachable directly from the LAN or the internet.

#### Scenario: LAN access refused
- **WHEN** another device on the local network connects to the Mac's LAN address on the service port
- **THEN** the connection is refused

### Requirement: Private remote access over Tailscale
The service SHALL be reachable from the owner's tailnet devices over HTTPS at the Mac's Tailscale hostname, and SHALL NOT be published to the public internet.

#### Scenario: Tailnet device
- **WHEN** a device signed into the owner's tailnet requests `https://<mac-tailscale-name>/health`
- **THEN** it receives 200 `{"status": "ok"}`

#### Scenario: Not on tailnet
- **WHEN** a device outside the tailnet tries to reach the Tailscale hostname
- **THEN** it cannot connect

### Requirement: Persistent log files
The service SHALL write its logs, including startup errors and crash output, to files under the owner's `~/Library/Logs/job-hunt-hq/` directory. The main service log SHALL be rotated by size so it does not grow without bound.

#### Scenario: Request logged
- **WHEN** a `POST /jobs` request completes
- **THEN** its structured log line appears in the service log file

#### Scenario: Rotation
- **WHEN** the main service log exceeds its configured size limit
- **THEN** it is rotated and older rotations beyond the kept count are removed

### Requirement: Install, uninstall and status scripts
The repository SHALL provide idempotent scripts to install the service, uninstall it, and report its status, so setup on a fresh Mac needs no hand-edited system files.

#### Scenario: Fresh install
- **WHEN** the owner runs the install script after completing the README prerequisites and filling in `.env`
- **THEN** the service is loaded into launchd and `GET /health` responds 200

#### Scenario: Reinstall
- **WHEN** the install script is run again on an already-installed service
- **THEN** it replaces the job definition, restarts the service, and does not fail

#### Scenario: Uninstall
- **WHEN** the owner runs the uninstall script
- **THEN** the service stops, will not start at the next boot, and stored output files are left in place

#### Scenario: Status
- **WHEN** the owner runs the status script
- **THEN** it reports whether the launchd job is loaded, the process id if running, and the result of a health check

### Requirement: Install refuses unsafe configuration
The install script SHALL refuse to install when `.env` is missing, readable by users other than its owner, or rejected by the service's startup validation, and SHALL name the problem without printing secret values.

#### Scenario: World-readable env file
- **WHEN** `.env` has permissions that let other users read it
- **THEN** the install script exits non-zero, explains how to fix the permissions, and installs nothing
