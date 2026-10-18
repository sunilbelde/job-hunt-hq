# Proposal

## Why

An external tool the owner uses (Muse) needs to call `POST /jobs`, and it runs outside the owner's tailnet, so the tailnet-only Tailscale Serve setup couldn't reach it. On 2026-10-17 the owner enabled Tailscale Funnel on the Mac mini, which publishes the same HTTPS hostname to the public internet. The spec and README still say the service is never public, so they no longer describe what is running.

## What Changes

- **BREAKING** (exposure): the service is reachable from the public internet at `https://<machine>.<tailnet>.ts.net` through Tailscale Funnel. Before this change it was reachable only from tailnet devices.
- Access control moves entirely to the application. `POST /jobs` requires the API key, and `/files/{key}` requires a valid, unexpired signed link. `/health` is public but reveals nothing.
- Unchanged: the process still binds only to `127.0.0.1:8080` and stays unreachable on the LAN; the hostname and `PUBLIC_BASE_URL` are the same; there is no change to code or configuration.
- README: replace the "don't use Funnel" guidance with the Funnel setup, a security note, and how to go back to tailnet-only.

## Capabilities

### New Capabilities

### Modified Capabilities
- `local-service-hosting`: the "Private remote access over Tailscale" requirement is replaced by "Public HTTPS access through Tailscale Funnel".

## Impact

- **Ops**: Funnel is turned on with `sudo tailscale funnel --bg --https=443 http://127.0.0.1:8080`, and the tailnet's policy must allow Funnel for this machine. It persists across reboots.
- **Security**: the API key and link-signing secret are now the only barrier against internet clients. There is no rate limiting yet; that is a possible follow-up.
- **Code**: none.
