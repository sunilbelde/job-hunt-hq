## MODIFIED Requirements

### Requirement: Persistent log files
The service SHALL write its logs, including startup errors and crash output, to files under the owner's `~/Library/Logs/job-hunt-hq/` directory. The main service log SHALL be rotated by size so it does not grow without bound.

#### Scenario: Request logged
- **WHEN** a `POST /resume` request completes
- **THEN** its structured log line appears in the service log file

#### Scenario: Rotation
- **WHEN** the main service log exceeds its configured size limit
- **THEN** it is rotated and older rotations beyond the kept count are removed

### Requirement: Public HTTPS access through Tailscale Funnel
The service SHALL be reachable over HTTPS at the Mac's Tailscale hostname from both tailnet devices and the public internet, through Tailscale Funnel, while the process itself keeps listening only on loopback. Resume generation and the application endpoints SHALL still require the API key, and generated files SHALL NOT be retrievable over this public address.

#### Scenario: Tailnet device
- **WHEN** a device signed into the owner's tailnet requests `https://<mac-tailscale-name>/health`
- **THEN** it receives 200 `{"status": "ok"}`

#### Scenario: Internet client
- **WHEN** a client outside the tailnet requests `https://<mac-tailscale-name>/health`
- **THEN** it receives 200 `{"status": "ok"}`

#### Scenario: Internet client without API key
- **WHEN** a client outside the tailnet sends `POST /resume` without a valid `X-API-Key`
- **THEN** it receives 401 and nothing is generated or stored

#### Scenario: LAN still refused
- **WHEN** another device on the local network connects to the Mac's LAN address on the service port
- **THEN** the connection is refused
