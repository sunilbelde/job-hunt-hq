# Tasks

## 1. Enable Funnel

- [x] 1.1 Run `sudo tailscale funnel --bg --https=443 http://127.0.0.1:8080` on the Mac mini. Verify that `tailscale funnel status` shows "Funnel on", that public DNS (`dig @1.1.1.1`) resolves the hostname, that `/health` returns 200 and `POST /jobs` without a key returns 401, and that the external client (Muse) can call the API. Done on 2026-10-17.

## 2. Documentation

- [x] 2.1 Update README: change the intro and "Running on the Mac mini" exposure statements, replace the "don't use tailscale funnel" line with the Funnel command, a security note and the revert commands, and change the verify step so it no longer requires a tailnet device. Verify that `grep -n "never exposed\|Don't use .tailscale funnel" README.md` finds nothing.
