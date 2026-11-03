"""Identifiable-review posture: expiry, ownership, platform refusal. Synthetic fixtures only."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from frp.review import security
from frp.review.access import ReviewAccessDenied, ReviewAccessRequest, authorise_review
from frp.review.records import ReviewMode
from frp.review.server import ReviewApp
from frp.review.session import GrantExpired, ReviewController, SubmissionRejected
from tests.review_support import find_item, make_demo_store, open_session, rewrite_catalogue
from tests.test_review_security import NOW, _grant, _make_identifiable, _request


class Granting:
    def __init__(self, expires_at: datetime) -> None:
        self.expires_at = expires_at

    def authorise(self, request: ReviewAccessRequest):  # type: ignore[no-untyped-def]
        return _grant(expires_at=self.expires_at)


def _open(tmp_path: Path, expires_at: datetime, clock: list[datetime]) -> ReviewController:
    store = make_demo_store(tmp_path / "store")
    _make_identifiable(store)
    return open_session(
        store,
        "identity_inspection",
        provider=Granting(expires_at),
        environ={},
        now=NOW,
        clock=lambda: clock[0],
    )


def _item_with_output(controller: ReviewController) -> str:
    return find_item(controller.catalogue, outcome="succeeded", has_output=True).item_ref


def test_authorise_review_returns_the_grant_expiry(tmp_path: Path) -> None:
    store = make_demo_store(tmp_path / "store")
    _make_identifiable(store)
    expiry = NOW + timedelta(hours=1)
    assert (
        authorise_review(
            store, store.load_catalogue(), _request(), Granting(expiry), environ={}, now=NOW
        )
        == expiry
    )


def test_media_and_submissions_stop_at_the_grant_expiry(tmp_path: Path) -> None:
    expiry = NOW + timedelta(hours=1)
    clock = [NOW]
    controller = _open(tmp_path, expiry, clock)
    key = _item_with_output(controller)
    assert controller.media(key, "frame", 0) is not None

    clock[0] = expiry  # at, not after, the expiry
    assert controller.expired()
    with pytest.raises(GrantExpired):
        controller.media(key, "frame", 0)
    with pytest.raises(GrantExpired):
        controller.media(key, "reference")
    with pytest.raises(GrantExpired):
        controller.session_view()
    with pytest.raises(GrantExpired):
        controller.measurements(key)
    with pytest.raises(SubmissionRejected, match="expired"):
        controller.submit({"key": key})


def test_server_stops_every_data_endpoint_at_the_grant_expiry(tmp_path: Path) -> None:
    expiry = NOW + timedelta(hours=1)
    clock = [NOW]
    controller = _open(tmp_path, expiry, clock)
    app = ReviewApp(controller)
    key = _item_with_output(controller)
    host = {"host": "127.0.0.1"}
    base = f"/s/{app.token}"
    paths = (
        "/api/session",
        f"/api/items/{key}/measurements",
        f"/media/{key}/frame/0",
        f"/media/{key}/reference",
    )
    assert all(app.handle("GET", base + p, host).status == 200 for p in paths)

    clock[0] = expiry
    for path in paths:
        response = app.handle("GET", base + path, host)
        assert response.status == 403
        assert b"similarity" not in response.body
    body = json.dumps({"key": key}).encode()
    posted = app.handle(
        "POST",
        base + "/api/records",
        {
            "host": "127.0.0.1",
            "origin": "http://127.0.0.1",
            "content-type": "application/json",
        },
        body,
    )
    assert posted.status == 400
    assert app.handle("GET", base + "/", host).status == 200  # static shell holds no data


def test_server_keeps_serving_a_synthetic_store_without_expiry(tmp_path: Path) -> None:
    app = ReviewApp(open_session(make_demo_store(tmp_path / "store"), "identity_inspection"))
    key = _item_with_output(app.controller)
    host = {"host": "127.0.0.1"}
    clock_far = datetime(2200, 1, 1)
    assert not app.controller.expired(clock_far)
    for path in ("/api/session", f"/api/items/{key}/measurements"):
        assert app.handle("GET", f"/s/{app.token}{path}", host).status == 200


def test_a_submission_dated_at_or_after_expiry_is_refused_even_if_the_clock_is_earlier(
    tmp_path: Path,
) -> None:
    expiry = NOW + timedelta(hours=1)
    controller = _open(tmp_path, expiry, [NOW])
    key = _item_with_output(controller)
    with pytest.raises(SubmissionRejected, match="expired"):
        controller.submit({"key": key}, now=expiry + timedelta(seconds=1))


def test_a_synthetic_store_has_no_expiry(tmp_path: Path) -> None:
    controller = open_session(make_demo_store(tmp_path / "store"), "identity_inspection")
    assert controller.grant_expires_at is None
    assert not controller.expired(NOW + timedelta(days=36500))


def test_no_mode_is_exempt_from_expiry(tmp_path: Path) -> None:
    modes: tuple[ReviewMode, ...] = ("identity_inspection", "blinded_quality")
    for index, mode in enumerate(modes):
        store = make_demo_store(tmp_path / f"s{index}")
        _make_identifiable(store)

        class Both:
            def authorise(self, request: ReviewAccessRequest):  # type: ignore[no-untyped-def]
                return _grant(modes=modes, expires_at=NOW + timedelta(minutes=5))

        controller = open_session(
            store, mode, provider=Both(), environ={}, now=NOW, clock=lambda: NOW
        )
        assert not controller.expired()
        assert controller.expired(NOW + timedelta(minutes=5))


def test_off_posix_identifiable_stores_are_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = make_demo_store(tmp_path / "store")
    _make_identifiable(store)
    monkeypatch.setattr(security.os, "name", "nt")
    assert security.group_or_world_accessible(store.root)  # POSIX mode bits prove nothing on NTFS
    monkeypatch.setattr("frp.private_storage.os.name", "nt")
    with pytest.raises(ReviewAccessDenied) as caught:
        authorise_review(
            store,
            store.load_catalogue(),
            _request(),
            Granting(NOW + timedelta(hours=1)),
            environ={},
            now=NOW,
        )
    assert any("group or others" in problem for problem in caught.value.problems)


def test_synthetic_stores_remain_openable_off_posix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = make_demo_store(tmp_path / "store")
    monkeypatch.setattr(security.os, "name", "nt")
    assert open_session(store, "identity_inspection").grant_expires_at is None


@pytest.mark.skipif(os.name != "posix", reason="POSIX ownership")
def test_a_store_reached_through_a_symlinked_parent_is_refused(tmp_path: Path) -> None:
    from frp.review.store import ReviewStore

    real_parent = tmp_path / "real"
    real_parent.mkdir(mode=0o700)
    _make_identifiable(make_demo_store(real_parent / "store"))
    (tmp_path / "link").symlink_to(real_parent)
    linked = ReviewStore(tmp_path / "link" / "store")
    with pytest.raises(ReviewAccessDenied) as caught:
        authorise_review(
            linked,
            linked.load_catalogue(),
            _request(),
            Granting(NOW + timedelta(hours=1)),
            environ={},
            now=NOW,
        )
    assert any("symlinked" in problem for problem in caught.value.problems)


def test_the_default_provider_still_denies_identifiable_stores(tmp_path: Path) -> None:
    store = make_demo_store(tmp_path / "store")
    rewrite_catalogue(
        store, content_class="identifiable", storage_approval_reference="private:storage/0001"
    )
    with pytest.raises(ReviewAccessDenied, match="no private review-access grant"):
        open_session(store, "identity_inspection", environ={})
