"""Loopback-only HTTP front end for a :class:`~frp.review.session.ReviewController` (V1, V4, V5).

* Binds only to a literal loopback address; any other host is refused before a socket is opened.
* Every URL is prefixed with an unguessable per-session token (``/s/<token>/``); anything else is
  a bare 404. Tokens are compared in constant time.
* The ``Host`` header must name the loopback interface (DNS-rebinding defence), so the viewer does
  not answer through a hosted port-forwarding domain.
* State-changing requests must be same-origin JSON with a bounded body.
* Every response carries a strict content-security policy (own origin only), ``no-store``
  caching and anti-framing headers. All assets are bundled; nothing is fetched from elsewhere.
* Request paths are matched against fixed patterns; ids are looked up in the catalogue and never
  joined to a filesystem path. Nothing is echoed back from the request.
* The standard request log is disabled (URLs carry the token); the only log is the private access
  log in the store, which holds opaque references and never media, notes or paths.
"""

from __future__ import annotations

import hmac
import json
import re
import secrets
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from typing import Any, Final
from urllib.parse import urlsplit

from frp.review.security import ALLOWED_HOST_NAMES, SECURITY_HEADERS, is_loopback_address
from frp.review.session import ReviewController, SubmissionRejected

MAX_BODY_BYTES: Final = 16 * 1024
_PREFIX: Final = re.compile(r"^/s/(?P<token>[A-Za-z0-9_-]{43})(?P<rest>/[A-Za-z0-9_./-]*)$")
_KEY: Final = r"(?P<key>it-[0-9a-f]{16}|Q-[0-9A-F]{10})"
_ROUTES: Final = (
    ("GET", re.compile(r"^/$"), "index"),
    ("GET", re.compile(r"^/static/app\.js$"), "app.js"),
    ("GET", re.compile(r"^/static/player\.js$"), "player.js"),
    ("GET", re.compile(r"^/static/app\.css$"), "app.css"),
    ("GET", re.compile(r"^/api/session$"), "session"),
    ("GET", re.compile(rf"^/api/items/{_KEY}/measurements$"), "measurements"),
    ("GET", re.compile(rf"^/media/{_KEY}/reference$"), "reference"),
    ("GET", re.compile(rf"^/media/{_KEY}/frame/(?P<index>0|[1-9][0-9]{{0,5}})$"), "frame"),
    ("POST", re.compile(r"^/api/records$"), "records"),
)
_STATIC: Final = {
    "index": ("index.html", "text/html; charset=utf-8"),
    "app.js": ("app.js", "text/javascript; charset=utf-8"),
    "player.js": ("player.js", "text/javascript; charset=utf-8"),
    "app.css": ("app.css", "text/css; charset=utf-8"),
}


@dataclass(frozen=True, slots=True)
class Response:
    status: int
    content_type: str = "text/plain; charset=utf-8"
    body: bytes = b""
    extra_headers: tuple[tuple[str, str], ...] = field(default=())


NOT_FOUND: Final = Response(404, body=b"Not found")


def _json(status: int, payload: Any) -> Response:
    return Response(status, "application/json", json.dumps(payload).encode("utf-8"))


def load_asset(name: str) -> bytes:
    return resources.files("frp.review").joinpath("static", name).read_bytes()


def _host_name(value: str) -> str:
    value = value.strip().lower()
    if value.startswith("["):
        return value[: value.find("]") + 1] if "]" in value else value
    return value.rsplit(":", 1)[0] if value.count(":") == 1 else value


class ReviewApp:
    """Pure request handling: (method, path, headers, body) -> :class:`Response`."""

    def __init__(self, controller: ReviewController, token: str | None = None) -> None:
        self.controller = controller
        self.token = token or secrets.token_urlsafe(32)
        self._assets = {name: load_asset(file) for name, (file, _) in _STATIC.items()}

    def handle(
        self, method: str, raw_path: str, headers: Mapping[str, str], body: bytes = b""
    ) -> Response:
        lowered = {k.lower(): v for k, v in headers.items()}
        if _host_name(lowered.get("host", "")) not in ALLOWED_HOST_NAMES:
            return Response(421, body=b"Misdirected request")
        path = urlsplit(raw_path).path
        match = _PREFIX.match(path)
        if (
            match is None
            or "//" in path
            or any(part in (".", "..") for part in path.split("/"))
            or not hmac.compare_digest(match["token"], self.token)
        ):
            return NOT_FOUND
        rest = match["rest"]
        for route_method, pattern, name in _ROUTES:
            route = pattern.match(rest)
            if route is None:
                continue
            if method != route_method:
                return Response(405, body=b"Method not allowed")
            return self._dispatch(name, route.groupdict(), lowered, body)
        return NOT_FOUND

    def _dispatch(
        self, name: str, params: dict[str, str], headers: Mapping[str, str], body: bytes
    ) -> Response:
        if name in _STATIC:
            return Response(200, _STATIC[name][1], self._assets[name])
        if name == "session":
            return _json(200, self.controller.session_view())
        if name == "measurements":
            payload = self.controller.measurements(params["key"])
            return NOT_FOUND if payload is None else _json(200, payload)
        if name in ("reference", "frame"):
            data = self.controller.media(params["key"], name, int(params.get("index", 0)))
            if data is None:
                return NOT_FOUND
            return Response(
                200, "image/png", data, (("Content-Disposition", 'inline; filename="frame.png"'),)
            )
        return self._submit(headers, body)

    def _submit(self, headers: Mapping[str, str], body: bytes) -> Response:
        origin = headers.get("origin", "")
        parsed = urlsplit(origin)
        if parsed.scheme != "http" or _host_name(parsed.netloc) not in ALLOWED_HOST_NAMES:
            return Response(403, body=b"Cross-origin request refused")
        if headers.get("sec-fetch-site", "same-origin") != "same-origin":
            return Response(403, body=b"Cross-origin request refused")
        if not headers.get("content-type", "").startswith("application/json"):
            return Response(415, body=b"JSON required")
        if len(body) > MAX_BODY_BYTES:
            return Response(413, body=b"Request too large")
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _json(400, {"problems": ["submission is not valid JSON"]})
        try:
            record_id = self.controller.submit(payload)
        except SubmissionRejected as exc:
            return _json(400, {"problems": list(exc.problems)})
        return _json(201, {"record_id": record_id})


def _handler_for(app: ReviewApp) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "frp-review"
        sys_version = ""
        timeout = 30

        def _respond(self, method: str) -> None:
            length = self.headers.get("Content-Length", "0")
            size = int(length) if length.isdigit() else -1
            if size < 0 or size > MAX_BODY_BYTES:
                response = Response(413, body=b"Request too large")
            else:
                body = self.rfile.read(size) if size else b""
                response = app.handle(method, self.path, dict(self.headers.items()), body)
            self.send_response(response.status)
            for name, value in (*SECURITY_HEADERS, *response.extra_headers):
                self.send_header(name, value)
            self.send_header("Content-Type", response.content_type)
            self.send_header("Content-Length", str(len(response.body)))
            self.end_headers()
            if method != "HEAD":
                self.wfile.write(response.body)

        def do_GET(self) -> None:
            self._respond("GET")

        def do_POST(self) -> None:
            self._respond("POST")

        def do_HEAD(self) -> None:
            self._respond("HEAD")

        def do_PUT(self) -> None:
            self._respond("PUT")

        def do_DELETE(self) -> None:
            self._respond("DELETE")

        def log_message(self, format: str, *args: Any) -> None:
            return

    return Handler


class ReviewServer:
    """A loopback-bound server for one :class:`ReviewApp`."""

    def __init__(self, app: ReviewApp, *, host: str = "127.0.0.1", port: int = 0) -> None:
        if not is_loopback_address(host):
            raise ValueError("the review viewer binds only to a loopback address")
        self.app = app
        self._httpd = ThreadingHTTPServer((host, port), _handler_for(app))
        self._httpd.daemon_threads = True
        bound_host = self._httpd.server_address[0]
        if not is_loopback_address(str(bound_host)):
            self._httpd.server_close()
            raise ValueError("the review viewer is not bound to a loopback address")
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return int(self._httpd.server_address[1])

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/s/{self.app.token}/"

    def serve_forever(self) -> None:
        self._httpd.serve_forever(poll_interval=0.2)

    def start_background(self) -> None:
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)
        self._thread.start()

    def shutdown(self) -> None:
        """Stop a server started with :meth:`start_background`."""
        self._httpd.shutdown()
        self.close()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def close(self) -> None:
        self._httpd.server_close()


__all__ = ["MAX_BODY_BYTES", "Response", "ReviewApp", "ReviewServer", "load_asset"]
