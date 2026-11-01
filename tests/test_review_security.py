"""Access control, restricted storage, path safety, media sanitising and outbound-network guard."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import struct
import zlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from frp.review.access import (
    DenyAllReviewAccess,
    ReviewAccessDenied,
    ReviewAccessGrant,
    ReviewAccessRequest,
    authorise_review,
    grant_problems,
)
from frp.review.png import PNG_SIGNATURE, MediaRejected, encode_png_rgb, sanitise_png
from frp.review.security import (
    OutboundNetworkBlocked,
    group_or_world_accessible,
    inside_git_worktree,
    is_loopback_address,
    loopback_only_network,
    remote_environment_indicators,
)
from frp.review.store import ReviewStore, StoreError
from tests.review_support import make_demo_store, open_session, rewrite_catalogue

NOW = datetime(2026, 6, 1, tzinfo=UTC)


@pytest.fixture
def store(tmp_path: Path) -> ReviewStore:
    return make_demo_store(tmp_path / "store")


def _make_identifiable(store: ReviewStore) -> None:
    rewrite_catalogue(
        store, content_class="identifiable", storage_approval_reference="private:storage/0001"
    )


def _request(**overrides: object) -> ReviewAccessRequest:
    values: dict[str, object] = {
        "store_id": "synthetic-review-demo",
        "content_class": "identifiable",
        "storage_approval_reference": "private:storage/0001",
        "mode": "identity_inspection",
        "reviewer_role_code": "RV-01",
        "session_id": "0" * 32,
    }
    values.update(overrides)
    return ReviewAccessRequest(**values)  # type: ignore[arg-type]


def _grant(**overrides: object) -> ReviewAccessGrant:
    values: dict[str, object] = {
        "grant_id": "private:grant/0001",
        "store_id": "synthetic-review-demo",
        "storage_approval_reference": "private:storage/0001",
        "modes": ("identity_inspection",),
        "reviewer_role_codes": ("RV-01",),
        "gates": {
            "consent_and_data_processing": "private:consent/0001",
            "restricted_storage_retention_deletion": "private:storage/0001",
        },
        "expires_at": NOW + timedelta(days=1),
    }
    values.update(overrides)
    return ReviewAccessGrant(**values)  # type: ignore[arg-type]


# Access ---------------------------------------------------------------------------------------


def test_identifiable_store_is_refused_by_the_only_shipped_provider(store: ReviewStore) -> None:
    _make_identifiable(store)
    with pytest.raises(ReviewAccessDenied, match="no private review-access grant") as caught:
        open_session(store, "identity_inspection", environ={})
    assert str(store.root) not in str(caught.value)
    assert not (store.root / "sessions").exists()  # nothing recorded for a refused session


def test_identifiable_store_is_refused_in_remote_environments_even_with_a_grant(
    store: ReviewStore,
) -> None:
    _make_identifiable(store)

    class Granting:
        def authorise(self, request: ReviewAccessRequest) -> ReviewAccessGrant:
            return _grant()

    for variable in ("CODESPACES", "SSH_CONNECTION", "GITHUB_ACTIONS", "CI"):
        with pytest.raises(ReviewAccessDenied, match=variable) as caught:
            open_session(
                store,
                "identity_inspection",
                provider=Granting(),
                environ={variable: "secret-v"},
                now=NOW,
            )
        assert "secret-v" not in str(caught.value)


def test_identifiable_store_in_a_git_worktree_or_shared_directory_is_refused(
    tmp_path: Path,
) -> None:
    (tmp_path / "repo" / ".git").mkdir(parents=True)
    store = make_demo_store(tmp_path / "repo" / "store")
    _make_identifiable(store)
    os.chmod(store.root, 0o750)  # noqa: S103 - deliberately too permissive
    with pytest.raises(ReviewAccessDenied) as caught:
        authorise_review(
            store, store.load_catalogue(), _request(), DenyAllReviewAccess(), environ={}, now=NOW
        )
    problems = " ".join(caught.value.problems)
    assert "git working tree" in problems
    if os.name == "posix":
        assert "group or others" in problems


def test_grant_problems_cover_every_mismatch() -> None:
    assert grant_problems(_grant(), _request(), NOW) == []
    assert grant_problems(None, _request(), NOW)
    cases = {
        "different store": _grant(store_id="other-store"),
        "different storage approval": _grant(storage_approval_reference="private:storage/9"),
        "review mode": _grant(modes=("blinded_quality",)),
        "reviewer role code": _grant(reviewer_role_codes=("RV-02",)),
        "lacks approval": _grant(gates={"consent_and_data_processing": "private:c/1"}),
        "expired": _grant(expires_at=NOW - timedelta(seconds=1)),
    }
    for expected, grant in cases.items():
        assert any(expected in p for p in grant_problems(grant, _request(), NOW)), expected


def test_synthetic_label_cannot_be_used_for_non_demo_media(store: ReviewStore) -> None:
    catalogue = json.loads(store.load_catalogue().model_dump_json())
    media_id = next(iter(catalogue["media"]))
    frames = catalogue["media"][media_id]["frame_sha256"]
    frames[0] = hashlib.sha256(b"not a demo frame").hexdigest()
    rewrite_catalogue(store, media=catalogue["media"])
    with pytest.raises(ReviewAccessDenied, match="not procedurally generated"):
        open_session(store, "identity_inspection")


def test_synthetic_store_must_hold_simulated_results(store: ReviewStore) -> None:
    rewrite_catalogue(store, simulated=False, simulation_scenario=None)
    with pytest.raises(StoreError, match="invalid catalogue"):
        store.load_catalogue()


def test_remote_environment_indicators_report_names_only() -> None:
    assert remote_environment_indicators({}) == []
    assert remote_environment_indicators({"CODESPACES": "true", "HOME": "/x"}) == ["CODESPACES"]
    assert remote_environment_indicators({"CODESPACES": ""}) == []


def test_filesystem_checks(tmp_path: Path) -> None:
    assert not inside_git_worktree(tmp_path)
    (tmp_path / ".git").mkdir()
    assert inside_git_worktree(tmp_path / "nested")
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    os.chmod(private, 0o700)
    assert not group_or_world_accessible(private)
    if os.name == "posix":
        os.chmod(private, 0o704)
        assert group_or_world_accessible(private)


# Store ----------------------------------------------------------------------------------------


def test_store_is_owner_only_and_never_reused(tmp_path: Path) -> None:
    store = make_demo_store(tmp_path / "store")
    if os.name == "posix":
        for path in (store.root, store.root / "media", store.root / "catalogue.json"):
            assert path.stat().st_mode & 0o077 == 0, path
    with pytest.raises(StoreError, match="already exists"):
        make_demo_store(tmp_path / "store")
    with pytest.raises(FileExistsError):
        store.write_catalogue(store.load_catalogue())


def test_frames_must_match_registered_digests(store: ReviewStore) -> None:
    catalogue = store.load_catalogue()
    media_id, entry = next(iter(catalogue.media.items()))
    assert store.read_frame(catalogue, media_id, 0).startswith(PNG_SIGNATURE)
    path = store.root / "media" / media_id / "000000.png"
    os.chmod(path, 0o600)
    path.write_bytes(
        encode_png_rgb(entry.width, entry.height, [b"\x00" * entry.width * 3] * entry.height)
    )
    with pytest.raises(StoreError, match="registered digest"):
        store.read_frame(catalogue, media_id, 0)


def test_symlinked_media_and_catalogue_are_refused(store: ReviewStore, tmp_path: Path) -> None:
    catalogue = store.load_catalogue()
    media_id = next(iter(catalogue.media))
    outside = tmp_path / "outside.png"
    frame = store.root / "media" / media_id / "000000.png"
    outside.write_bytes(frame.read_bytes())
    frame.unlink()
    frame.symlink_to(outside)
    with pytest.raises(StoreError, match="symbolic link"):
        store.read_frame(catalogue, media_id, 0)

    directory = store.root / "media" / media_id
    moved = tmp_path / "moved"
    directory.rename(moved)
    directory.symlink_to(moved)
    with pytest.raises(StoreError, match=r"symbolic link|outside"):
        store.read_frame(catalogue, media_id, 0)

    cat = store.root / "catalogue.json"
    copy = tmp_path / "catalogue.json"
    copy.write_bytes(cat.read_bytes())
    cat.unlink()
    cat.symlink_to(copy)
    with pytest.raises(StoreError, match="symbolic link"):
        store.load_catalogue()


@pytest.mark.parametrize(
    ("media_id", "index"),
    [
        ("../catalogue", 0),
        ("m-" + "0" * 32, 0),
        ("/etc/passwd", 0),
        (None, -1),
        (None, 10_000),
        (None, True),
    ],
)
def test_unregistered_media_and_indices_are_refused(
    store: ReviewStore, media_id: str | None, index: int
) -> None:
    catalogue = store.load_catalogue()
    with pytest.raises(StoreError, match="unknown media or frame"):
        store.read_frame(catalogue, media_id or next(iter(catalogue.media)), index)


def test_catalogue_rejects_path_like_media_ids(store: ReviewStore) -> None:
    catalogue = json.loads(store.load_catalogue().model_dump_json())
    media = catalogue["media"]
    media["../../etc"] = media.pop(next(iter(media)))
    rewrite_catalogue(store, media=media)
    with pytest.raises(StoreError) as caught:
        store.load_catalogue()
    assert "etc" not in str(caught.value)


def test_store_errors_do_not_reveal_paths(tmp_path: Path) -> None:
    secret = tmp_path / "participant-SYN-201-private"
    with pytest.raises(StoreError) as caught:
        ReviewStore(secret).load_catalogue()
    assert "participant" not in str(caught.value)


# PNG sanitising -------------------------------------------------------------------------------


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def _png(width: int = 2, height: int = 2) -> bytes:
    return encode_png_rgb(width, height, [b"\x10\x20\x30" * width] * height)


def test_sanitiser_drops_metadata_chunks() -> None:
    clean = _png()
    text = _chunk(b"tEXt", b"Author\x00Someone private")
    exif = _chunk(b"eXIf", b"MM\x00*GPS")
    head = clean[: len(PNG_SIGNATURE) + 25]
    tainted = head + text + exif + clean[len(head) :]
    result = sanitise_png(tainted)
    assert result == clean
    assert b"Someone" not in result
    assert b"GPS" not in result


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"GIF89a....", "not a PNG"),
        (_png()[:-4] + b"\x00\x00\x00\x00", "checksum"),
        (_png() + _chunk(b"tEXt", b"x"), "after the PNG end"),
        (PNG_SIGNATURE + _chunk(b"IDAT", b""), "header chunk"),
        (_png()[:30], "truncated"),
        (PNG_SIGNATURE + _png()[8:33] + _chunk(b"IEND", b""), "missing required"),
        (_png()[:33] + _chunk(b"XXXX", b"") + _png()[33:], "unknown critical"),
    ],
)
def test_sanitiser_rejects_malformed_png(data: bytes, message: str) -> None:
    with pytest.raises(MediaRejected, match=message):
        sanitise_png(data)


def test_sanitiser_enforces_catalogue_dimensions() -> None:
    with pytest.raises(MediaRejected, match="dimensions differ"):
        sanitise_png(_png(2, 2), expected_width=3, expected_height=2)
    assert sanitise_png(_png(3, 1), expected_width=3, expected_height=1)


# Network --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("host", "loopback"),
    [
        ("127.0.0.1", True),
        ("127.5.6.7", True),
        ("::1", True),
        ("0.0.0.0", False),  # noqa: S104 - must be rejected
        ("::", False),
        ("192.168.1.10", False),
        ("localhost", False),  # names are never resolved
        ("127.0.0.1.nip.io", False),
    ],
)
def test_loopback_detection(host: str, loopback: bool) -> None:
    assert is_loopback_address(host) is loopback


def test_outbound_network_is_blocked_and_restored() -> None:
    original = socket.getaddrinfo
    with loopback_only_network() as guard:
        with pytest.raises(OutboundNetworkBlocked):
            socket.getaddrinfo("example.org", 443)
        with pytest.raises(OutboundNetworkBlocked):
            socket.create_connection(("192.0.2.1", 80), timeout=0.1)
        with (
            socket.socket(socket.AF_INET, socket.SOCK_STREAM) as raw,
            pytest.raises(OutboundNetworkBlocked),
        ):
            raw.connect(("192.0.2.1", 80))
        with pytest.raises(OutboundNetworkBlocked):
            socket.gethostbyname("example.org")
        assert socket.getaddrinfo("127.0.0.1", 80)
        assert guard.blocked_calls == 4
    assert socket.getaddrinfo is original
    assert "connect" not in vars(socket.socket)
