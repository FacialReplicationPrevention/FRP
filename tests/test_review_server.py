"""Loopback HTTP front end: token, host, routing, headers, same-origin writes, no leakage."""

from __future__ import annotations

import http.client
import json
import logging
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from frp.cli import EXIT_INVALID, EXIT_OK, EXIT_OUTPUT, EXIT_USAGE, main
from frp.review.demo import SIMULATED_NOTICE as DEMO_NOTICE
from frp.review.png import PNG_SIGNATURE
from frp.review.security import CONTENT_SECURITY_POLICY, loopback_only_network
from frp.review.server import ReviewApp, ReviewServer, load_asset
from frp.review.store import ReviewStore
from tests.review_support import find_item, make_demo_store, open_session, rewrite_catalogue

HOST = {"Host": "127.0.0.1:8765"}
POST = {
    **HOST,
    "Origin": "http://127.0.0.1:8765",
    "Content-Type": "application/json",
    "Sec-Fetch-Site": "same-origin",
}
STATIC = Path(__file__).resolve().parents[1] / "src" / "frp" / "review" / "static"


@pytest.fixture
def store(tmp_path: Path) -> ReviewStore:
    return make_demo_store(tmp_path / "store")


@pytest.fixture
def app(store: ReviewStore) -> ReviewApp:
    return ReviewApp(open_session(store, "identity_inspection"))


def _url(app: ReviewApp, rest: str) -> str:
    return f"/s/{app.token}{rest}"


def test_index_assets_and_session_are_served_under_the_token(app: ReviewApp) -> None:
    for rest, kind in (
        ("/", "text/html"),
        ("/static/app.js", "text/javascript"),
        ("/static/player.js", "text/javascript"),
        ("/static/app.css", "text/css"),
        ("/api/session", "application/json"),
    ):
        response = app.handle("GET", _url(app, rest), HOST)
        assert response.status == 200, rest
        assert response.content_type.startswith(kind)


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/api/session",
        "/s/short/",
        "/s/" + "A" * 43 + "/api/session",
        "/static/app.js",
    ],
)
def test_requests_without_the_session_token_are_not_found(app: ReviewApp, path: str) -> None:
    assert app.handle("GET", path, HOST).status == 404


@pytest.mark.parametrize(
    "rest",
    [
        "/../catalogue.json",
        "/static/../catalogue.json",
        "/media/../../catalogue.json",
        "/static/%2e%2e/catalogue.json",
        "//api/session",
        "/catalogue.json",
        "/media/m-00000000000000000000000000000000/frame/0",
        "/media/it-0123/frame/0",
        "/media/it-0123456789abcdef/frame/-1",
        "/media/it-0123456789abcdef/frame/01",
        "/access-log.jsonl",
        "/records",
    ],
)
def test_path_traversal_and_unknown_routes_are_not_found(app: ReviewApp, rest: str) -> None:
    assert app.handle("GET", _url(app, rest), HOST).status == 404


@pytest.mark.parametrize(
    "host",
    ["", "evil.example", "127.0.0.1.nip.io", "abc-8765.app.github.dev", "0.0.0.0:8765"],
)
def test_non_loopback_host_headers_are_refused(app: ReviewApp, host: str) -> None:
    response = app.handle("GET", _url(app, "/api/session"), {"Host": host})
    assert response.status == 421


def test_loopback_host_spellings_are_accepted(app: ReviewApp) -> None:
    for host in ("127.0.0.1", "localhost:9", "[::1]:9", "LOCALHOST"):
        assert app.handle("GET", _url(app, "/api/session"), {"Host": host}).status == 200


def test_wrong_methods_are_refused(app: ReviewApp) -> None:
    assert app.handle("POST", _url(app, "/api/session"), POST).status == 405
    assert app.handle("DELETE", _url(app, "/api/records"), POST).status == 405


def test_media_and_measurements_routes(app: ReviewApp) -> None:
    item = find_item(app.controller.catalogue, outcome="succeeded", has_output=True)
    frame = app.handle("GET", _url(app, f"/media/{item.item_ref}/frame/4"), HOST)
    assert frame.status == 200
    assert frame.content_type == "image/png"
    assert frame.body.startswith(PNG_SIGNATURE)
    reference = app.handle("GET", _url(app, f"/media/{item.item_ref}/reference"), HOST)
    assert reference.status == 200
    measured = app.handle("GET", _url(app, f"/api/items/{item.item_ref}/measurements"), HOST)
    assert json.loads(measured.body)["calibration_status"] == "uncalibrated"


def test_blinded_app_never_serves_references_or_measurements(store: ReviewStore) -> None:
    app = ReviewApp(open_session(store, "blinded_quality", "RV-02"))
    session = json.loads(app.handle("GET", _url(app, "/api/session"), HOST).body)
    code = next(i["key"] for i in session["items"] if i["media_available"])
    item_ref = app.controller.session.item_for_code(code)
    assert app.handle("GET", _url(app, f"/media/{code}/frame/0"), HOST).status == 200
    for rest in (
        f"/media/{code}/reference",
        f"/api/items/{code}/measurements",
        f"/media/{item_ref}/frame/0",
        f"/media/{item_ref}/reference",
        f"/api/items/{item_ref}/measurements",
    ):
        assert app.handle("GET", _url(app, rest), HOST).status == 404, rest


def test_record_submission_requires_same_origin_json(app: ReviewApp) -> None:
    item = find_item(app.controller.catalogue, outcome="succeeded", has_output=True)
    body = json.dumps({"key": item.item_ref, "judgement": "uncertain"}).encode()
    path = _url(app, "/api/records")
    assert app.handle("POST", path, {**POST, "Origin": "http://evil.example"}, body).status == 403
    assert app.handle("POST", path, {**POST, "Origin": "null"}, body).status == 403
    assert (
        app.handle("POST", path, {k: v for k, v in POST.items() if k != "Origin"}, body).status
        == 403
    )
    assert app.handle("POST", path, {**POST, "Sec-Fetch-Site": "cross-site"}, body).status == 403
    assert app.handle("POST", path, {**POST, "Content-Type": "text/plain"}, body).status == 415
    assert app.handle("POST", path, POST, b"x" * 20_000).status == 413
    assert app.handle("POST", path, POST, b"{not json").status == 400
    rejected = app.handle("POST", path, POST, json.dumps({"key": item.item_ref}).encode())
    assert rejected.status == 400
    assert "problems" in json.loads(rejected.body)
    created = app.handle("POST", path, POST, body)
    assert created.status == 201
    assert len(json.loads(created.body)["record_id"]) == 32


def test_responses_echo_nothing_from_the_request(app: ReviewApp) -> None:
    marker = "ZZ-ECHO-MARKER"
    path = _url(app, "/api/records")
    payload = json.dumps({"key": "it-0123456789abcdef", "judgement": marker}).encode()
    assert marker.encode() not in app.handle("POST", path, POST, payload).body
    assert marker.encode() not in app.handle("GET", f"/s/{marker}/", HOST).body


def test_live_server_binds_loopback_only_and_sets_security_headers(
    app: ReviewApp,
    store: ReviewStore,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for host in ("0.0.0.0", "192.168.1.1", "localhost", "::"):  # noqa: S104 - must be rejected
        with pytest.raises(ValueError, match="loopback"):
            ReviewServer(app, host=host)
    caplog.set_level(logging.DEBUG)
    server = ReviewServer(app)
    assert server.url.startswith("http://127.0.0.1:")
    with loopback_only_network() as guard:
        server.start_background()
        try:
            item = find_item(app.controller.catalogue, outcome="succeeded", has_output=True)
            results = {}
            for rest in ("/", f"/media/{item.item_ref}/frame/4", "/nope"):
                connection = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
                connection.request("GET", _url(app, rest))
                response = connection.getresponse()
                results[rest] = (response.status, dict(response.getheaders()), response.read())
                connection.close()
            connection = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
            connection.request(
                "POST",
                _url(app, "/api/records"),
                body=json.dumps(
                    {"key": item.item_ref, "judgement": "uncertain", "notes": "PRIVATE-NOTE"}
                ),
                headers={
                    "Origin": f"http://127.0.0.1:{server.port}",
                    "Content-Type": "application/json",
                },
            )
            assert connection.getresponse().status == 201
            connection.close()
        finally:
            server.shutdown()
        assert guard.blocked_calls == 0
    assert results["/"][0] == 200
    assert results["/nope"][0] == 404
    for _status, headers, _ in results.values():
        assert headers["Content-Security-Policy"] == CONTENT_SECURITY_POLICY
        assert "no-store" in headers["Cache-Control"]
        assert headers["X-Frame-Options"] == "DENY"
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["Referrer-Policy"] == "no-referrer"
        assert headers["Server"].startswith("frp-review")
        assert "Python" not in headers["Server"]
    captured = capsys.readouterr()
    logged = captured.out + captured.err + caplog.text
    assert app.token not in logged
    assert "PRIVATE-NOTE" not in logged
    assert item.item_ref not in logged
    access_log = (store.root / "access-log.jsonl").read_text()
    assert "PRIVATE-NOTE" not in access_log
    assert str(store.root) not in access_log
    assert app.token not in access_log
    events = [json.loads(line)["event"] for line in access_log.splitlines()]
    assert {"session_open", "output_viewed", "record_saved"} <= set(events)


# Bundled assets -------------------------------------------------------------------------------


def test_assets_load_nothing_from_elsewhere_and_avoid_unsafe_apis() -> None:
    html = load_asset("index.html").decode()
    scripts = re.findall(r"<script\b[^>]*>", html)
    assert scripts
    assert all('src="static/' in s for s in scripts)
    assert "<style" not in html
    assert not re.search(r"\son[a-z]+\s*=", html, re.I)
    for name in ("index.html", "app.js", "player.js", "app.css"):
        text = load_asset(name).decode()
        assert not re.search(r"(https?:)?//[a-z0-9.-]+\.[a-z]{2,}", text, re.I), name
        assert "@import" not in text
    for name in ("app.js", "player.js"):
        code = re.sub(r"^\s*//.*$", "", load_asset(name).decode(), flags=re.M)
        for unsafe in (
            "innerHTML",
            "outerHTML",
            "insertAdjacentHTML",
            "document.write",
            "eval(",
            "new Function",
            "localStorage",
            "sessionStorage",
            "indexedDB",
            "navigator.sendBeacon",
            "WebSocket",
            "XMLHttpRequest",
            "serviceWorker",
        ):
            assert unsafe not in code, (name, unsafe)


# Frame navigation (player.js) under Node ------------------------------------------------------

NODE_SCRIPT = r"""
const assert = require('assert');
const p = require(process.argv[1]);
assert.strictEqual(p.clampFrame(-3, 17), 0);
assert.strictEqual(p.clampFrame(99, 17), 16);
assert.strictEqual(p.clampFrame(4.7, 17), 4);
assert.strictEqual(p.clampFrame(NaN, 17), 0);
assert.strictEqual(p.clampFrame(3, 0), 0);
assert.ok(p.frameLabel(0, 17).includes('conditioned first frame'));
assert.ok(!p.frameLabel(4, 17).includes('first frame'));

const s = p.createFrameState(17, 4);
assert.strictEqual(s.frame(), 4);
assert.strictEqual(s.step(1), 5);
assert.strictEqual(s.step(-10), 0);
assert.strictEqual(s.select(16), 16);
assert.strictEqual(s.select(40), 16);
assert.ok(s.play());                 // play from the end restarts at 0
assert.strictEqual(s.frame(), 0);
assert.ok(s.playing());
for (let i = 0; i < 16; i += 1) s.tick();
assert.strictEqual(s.frame(), 16);
assert.ok(!s.playing());             // stops on the last frame
assert.strictEqual(s.tick(), 16);
s.select(8); s.play(); s.tick();
assert.strictEqual(s.frame(), 9);
s.step(1);                           // manual navigation pauses playback
assert.ok(!s.playing());
s.play(); s.pause(); s.tick();
assert.strictEqual(s.frame(), 10);

const single = p.createFrameState(1, 0);
assert.ok(!single.play());
assert.strictEqual(single.step(1), 0);
console.log('player-ok');
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_player_navigation_logic_under_node() -> None:
    node = shutil.which("node")
    assert node is not None
    result = subprocess.run(
        [node, "-e", NODE_SCRIPT, str(STATIC / "player.js")],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "player-ok"


# CLI ------------------------------------------------------------------------------------------


def _cli(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str, str]:
    code = main(list(args))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_cli_review_demo_creates_a_labelled_synthetic_store(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    root = tmp_path / "demo"
    code, out, err = _cli(capsys, "review-demo", str(root))
    assert code == EXIT_OK, err
    assert out.startswith(DEMO_NOTICE)
    assert str(root) not in out
    assert ReviewStore(root).load_catalogue().simulated

    code, out, err = _cli(capsys, "review-demo", str(root))
    assert code == EXIT_OUTPUT
    assert out == ""
    assert "not empty" in err
    assert str(root) not in err


def test_cli_review_demo_accepts_a_relative_store_path(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    code, _, err = _cli(capsys, "review-demo", "relative-demo")
    assert code == EXIT_OK, err
    assert ReviewStore(Path("relative-demo")).load_catalogue().simulated
    assert not (tmp_path / "relative-demo" / "relative-demo").exists()


def test_cli_review_refuses_identifiable_stores_missing_stores_and_bad_ports(
    capsys: pytest.CaptureFixture[str], store: ReviewStore, tmp_path: Path
) -> None:
    base = ("--mode", "identity", "--reviewer", "RV-01")
    assert _cli(capsys, "review", str(store.root), *base, "--port", "70000")[0] == EXIT_USAGE

    missing = tmp_path / "missing"
    code, out, err = _cli(capsys, "review", str(missing), *base)
    assert code == EXIT_INVALID
    assert out == ""
    assert str(missing) not in err

    rewrite_catalogue(
        store, content_class="identifiable", storage_approval_reference="private:storage/0001"
    )
    code, out, err = _cli(capsys, "review", str(store.root), *base)
    assert code == EXIT_INVALID
    assert out == ""
    assert "review access refused" in err
    assert str(store.root) not in err
    assert not (store.root / "sessions").exists()
