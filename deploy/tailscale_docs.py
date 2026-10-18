"""Find the tailscale serve mapping for the docs listener in `tailscale serve status --json` (stdin).

Usage: tailscale serve status --json | python deploy/tailscale_docs.py <docs port>

Prints the mapping's HTTPS base URL (https://<host>[:<port>]) and exits 0 when it is tailnet-only,
exits 3 (still printing the URL) when Funnel publishes it, and exits 1 when no mapping proxies the port.
"""
import json
import sys
from urllib.parse import urlsplit

LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def proxies_to(target: str, port: int) -> bool:
    parts = urlsplit(target if "://" in target else f"http://{target}")
    try:
        return parts.hostname in LOOPBACK and parts.port == port
    except ValueError:
        return False


def main() -> int:
    port = int(sys.argv[1])
    try:
        status = json.load(sys.stdin) or {}
    except ValueError:
        return 1
    funnel = status.get("AllowFunnel") or {}
    for host_port, web in (status.get("Web") or {}).items():
        handlers = (web or {}).get("Handlers") or {}
        if any(proxies_to(h.get("Proxy", ""), port) for h in handlers.values() if isinstance(h, dict)):
            print("https://" + host_port.removesuffix(":443"))
            return 3 if funnel.get(host_port) else 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
