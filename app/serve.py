"""Runs the installed service: the public API on one loopback port and, optionally, the same API plus
its reference pages on a second loopback port that Tailscale publishes to the tailnet only.

Usage: python -m app.serve --port 8080 [--docs-port 8081] [--host 127.0.0.1] [--log-config <path>]
"""
import argparse
import ipaddress
import socket
import sys

import uvicorn

from app.applications import ApplicationStore
from app.main import create_app
from app.settings import get_settings
from app.storage import LocalStorage


def by_local_port(public, routes: dict[int, object]):
    """ASGI app sending each connection to the app for the local port it arrived on.

    scope["server"] is the listening socket's address, which no request header can change
    (uvicorn's proxy header handling rewrites only client and scheme). Anything else, lifespan
    included, goes to the public app, so an unexpected scope never reaches the docs.
    """

    async def app(scope, receive, send):
        target = public
        server = scope.get("server")
        if scope["type"] in ("http", "websocket") and server:
            target = routes.get(server[1], public)
        await target(scope, receive, send)

    return app


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m app.serve", description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1", help="loopback address to listen on")
    parser.add_argument("--port", type=int, required=True, help="public port (the one Funnel publishes)")
    parser.add_argument("--docs-port", type=int, help="port that also serves /docs, /redoc and /openapi.json")
    parser.add_argument("--log-config", help="logging config file, as for uvicorn --log-config")
    args = parser.parse_args(argv)
    try:
        loopback = ipaddress.ip_address(args.host).is_loopback
    except ValueError:
        loopback = False
    if not loopback:
        parser.error(f"--host must be a loopback address, got {args.host}")
    if args.docs_port == args.port:
        parser.error("--docs-port must differ from --port")
    return args


def bind(host: str, port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET6 if ":" in host else socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.set_inheritable(True)
    return sock


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    settings = get_settings()
    # One storage and store for both listeners: a row recorded on one port is seen on the other.
    storage = LocalStorage(settings.output_dir)
    applications = ApplicationStore(settings.output_dir / "applications.sqlite3")
    # Forced in code, not only by the plist's API_DOCS_ENABLED=false: the public port never has docs.
    public = create_app(settings.model_copy(update={"api_docs_enabled": False}), storage, applications)
    routes = {}
    ports = [args.port]
    if args.docs_port is not None:
        routes[args.docs_port] = create_app(settings.model_copy(update={"api_docs_enabled": True}), storage, applications)
        ports.append(args.docs_port)

    options = {"log_config": args.log_config} if args.log_config else {}
    config = uvicorn.Config(by_local_port(public, routes), proxy_headers=True, forwarded_allow_ips="127.0.0.1", **options)
    try:
        sockets = [bind(args.host, port) for port in ports]
    except OSError as exc:
        sys.exit(f"cannot listen on {args.host}: {exc}")
    uvicorn.Server(config).run(sockets=sockets)


if __name__ == "__main__":
    main()
