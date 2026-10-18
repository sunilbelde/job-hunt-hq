# Spec Delta

## REMOVED Requirements

### Requirement: Private remote access over Tailscale
**Reason**: An external client outside the owner's tailnet (Muse) must call the API, so the service is now published with Tailscale Funnel instead of tailnet-only Serve.
**Migration**: Replaced by "Public HTTPS access through Tailscale Funnel". The hostname is unchanged. To restore tailnet-only access, turn Funnel off and re-enable Serve, as the README describes.

## ADDED Requirements

### Requirement: Public HTTPS access through Tailscale Funnel
The service SHALL be reachable over HTTPS at the Mac's Tailscale hostname from both tailnet devices and the public internet, through Tailscale Funnel, while the process itself keeps listening only on loopback. Job creation SHALL still require the API key and downloads SHALL still require a valid signed link.

#### Scenario: Tailnet device
- **WHEN** a device signed into the owner's tailnet requests `https://<mac-tailscale-name>/health`
- **THEN** it receives 200 `{"status": "ok"}`

#### Scenario: Internet client
- **WHEN** a client outside the tailnet requests `https://<mac-tailscale-name>/health`
- **THEN** it receives 200 `{"status": "ok"}`

#### Scenario: Internet client without API key
- **WHEN** a client outside the tailnet sends `POST /jobs` without a valid `X-API-Key`
- **THEN** it receives 401 and nothing is generated or stored

#### Scenario: LAN still refused
- **WHEN** another device on the local network connects to the Mac's LAN address on the service port
- **THEN** the connection is refused
