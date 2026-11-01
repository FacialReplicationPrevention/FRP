"""Review sessions: frame selection, Mode A inspection, Mode B blinding and their separation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from frp.review.access import ReviewAccessDenied
from frp.review.demo import FRAME_COUNT, FRAME_INDICES
from frp.review.png import PNG_SIGNATURE
from frp.review.records import IdentityObservation, QualityRating, read_records, read_sessions
from frp.review.session import (
    SIMILARITY_NOTICE,
    SIMULATED_BANNER,
    SubmissionRejected,
    default_frame_index,
    sampled_frames,
)
from frp.review.store import ReviewStore
from tests.review_support import edit_catalogue, find_item, make_demo_store, open_session


@pytest.fixture
def store(tmp_path: Path) -> ReviewStore:
    return make_demo_store(tmp_path / "store")


# Frame selection ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("sampled", "count", "expected"),
    [
        ((0, 4, 8), 17, 4),  # first sampled later frame, never frame 0
        ((0,), 17, 16),  # only frame 0 sampled: fall back to the last frame
        ((0,), 1, 0),  # a single-frame output has nothing later
        ((0, 20), 10, 9),  # sampled index beyond the output is ignored
        ((8, 4), 17, 8),  # manifest order is respected
        ((), 0, 0),
    ],
)
def test_default_frame_is_a_later_frame(
    sampled: tuple[int, ...], count: int, expected: int
) -> None:
    assert default_frame_index(sampled, count) == expected


def test_sampled_frames_follow_manifest_indices_and_flag_frame_zero() -> None:
    frames = sampled_frames((0, 4, 20), 10)
    assert [f["index"] for f in frames] == [0, 4]
    assert frames[0]["first_frame"]
    assert "conditioned first frame" in frames[0]["label"]
    assert not frames[1]["first_frame"]


# Mode A ---------------------------------------------------------------------------------------


def test_identity_view_shows_every_item_with_status_and_later_default(store: ReviewStore) -> None:
    controller = open_session(store, "identity_inspection")
    view = controller.session_view()
    assert view["mode"] == "identity_inspection"
    assert view["banners"] == [SIMULATED_BANNER]
    assert view["similarity_notice"] == SIMILARITY_NOTICE
    assert view["judgements"] == ["same_person", "different_person", "uncertain", "not_assessable"]
    items = view["items"]
    assert len(items) == len(controller.catalogue.items) == 7  # 6 runs, one retried
    outcomes = [i["outcome"] for i in items]
    assert outcomes.count("failed") == 2
    assert outcomes.count("not_executed") == 1
    statuses = {i["item_status"] for i in items}
    assert statuses == {"available", "output_absent", "media_unavailable"}
    for item in items:
        if item["item_status"] == "available":
            assert item["frame_count"] == FRAME_COUNT
            assert item["default_frame"] == 4
            assert [f["index"] for f in item["sampled_frames"]] == list(FRAME_INDICES)
        else:
            assert item["frame_count"] == 0
            assert item["sampled_frames"] == []
        assert item["reference_available"]
        assert item["key"].startswith("it-")
    serialised = json.dumps(view)
    assert "private://" not in serialised
    assert str(store.root) not in serialised
    assert "SYN-" not in serialised
    assert "FRP-REVIEW-DEMO" not in serialised


def test_measurements_are_on_request_uncalibrated_and_missing_for_invalid_faces(
    store: ReviewStore,
) -> None:
    controller = open_session(store, "identity_inspection")
    catalogue = controller.catalogue
    succeeded = find_item(catalogue, outcome="succeeded", has_output=True)
    data = controller.measurements(succeeded.item_ref)
    assert data is not None
    assert data["calibration_status"] == "uncalibrated"
    assert data["simulated"]
    assert data["face_evaluator"]["simulated"]
    assert data["frames"][0]["first_frame"]
    for frame in data["frames"]:
        assert (frame["similarity"] is not None) == (frame["face_status"] == "valid")
    every = [f for i in catalogue.items for f in controller.measurements(i.item_ref)["frames"]]
    assert {"valid", "absent", "multiple", "low_quality", "error", "not_evaluated"} <= {
        f["face_status"] for f in every
    }
    failed = find_item(catalogue, outcome="failed")
    assert {f["face_status"] for f in controller.measurements(failed.item_ref)["frames"]} == {
        "not_evaluated"
    }
    assert controller.measurements("it-0000000000000000") is None


def test_media_is_served_only_for_registered_items(store: ReviewStore) -> None:
    controller = open_session(store, "identity_inspection")
    catalogue = controller.catalogue
    available = find_item(catalogue, outcome="succeeded", has_output=True)
    assert controller.media(available.item_ref, "reference").startswith(PNG_SIGNATURE)
    assert controller.media(available.item_ref, "frame", FRAME_COUNT - 1).startswith(PNG_SIGNATURE)
    assert controller.media(available.item_ref, "frame", FRAME_COUNT) is None
    assert controller.media(available.item_ref, "catalogue") is None
    unimported = find_item(catalogue, outcome="succeeded", has_output=False)
    assert controller.media(unimported.item_ref, "frame", 0) is None
    assert controller.media(find_item(catalogue, outcome="failed").item_ref, "frame", 0) is None
    assert controller.media("it-0000000000000000", "reference") is None


def test_identity_submission_records_judgement_and_reveal_state(store: ReviewStore) -> None:
    controller = open_session(store, "identity_inspection")
    item = find_item(controller.catalogue, outcome="succeeded", has_output=True)
    first = controller.submit({"key": item.item_ref, "judgement": "uncertain", "frame_index": 8})
    controller.measurements(item.item_ref)
    second = controller.submit({"key": item.item_ref, "judgement": "same_person", "notes": "n"})
    records = {r.record_id: r for r in read_records(store)}
    assert isinstance(records[first], IdentityObservation)
    assert not records[first].measurements_revealed
    assert records[first].frame_index == 8
    assert records[second].measurements_revealed
    assert records[second].frame_index is None
    assert records[first].reviewer_role_code == "RV-01"
    assert len(records) == 2  # a second judgement is a new record, not an overwrite


@pytest.mark.parametrize(
    ("payload", "problem"),
    [
        ([], "JSON object"),
        ({"judgement": "same_person"}, "missing or unexpected"),
        ({"key": "it-0000000000000000", "judgement": "same_person"}, "unknown item"),
        ({"key": "../catalogue.json", "judgement": "same_person"}, "unknown item"),
        ({"key": 7, "judgement": "same_person"}, "unknown item"),
        ({"key": "@", "judgement": "same_person", "score": 1}, "missing or unexpected"),
        ({"key": "@", "judgement": "maybe"}, "invalid value for: judgement"),
        ({"key": "@", "judgement": "uncertain", "frame_index": FRAME_COUNT}, "frame_index"),
        ({"key": "@", "judgement": "uncertain", "frame_index": True}, "frame_index"),
        ({"key": "@", "judgement": "uncertain", "frame_index": "4"}, "frame_index"),
        ({"key": "@", "judgement": "uncertain", "notes": "x" * 2001}, "notes"),
        ({"key": "@", "judgement": "uncertain", "notes": "a\x00b"}, "notes"),
    ],
)
def test_invalid_identity_submissions_are_rejected(
    store: ReviewStore, payload: object, problem: str
) -> None:
    controller = open_session(store, "identity_inspection")
    item = find_item(controller.catalogue, outcome="succeeded", has_output=True)
    if isinstance(payload, dict) and payload.get("key") == "@":
        payload = {**payload, "key": item.item_ref}
    with pytest.raises(SubmissionRejected, match=problem):
        controller.submit(payload)
    assert read_records(store) == []


@pytest.mark.parametrize("outcome", ["failed", "not_executed"])
def test_items_without_output_can_only_be_not_assessable(store: ReviewStore, outcome: str) -> None:
    controller = open_session(store, "identity_inspection")
    item = find_item(controller.catalogue, outcome=outcome)
    with pytest.raises(SubmissionRejected):
        controller.submit({"key": item.item_ref, "judgement": "same_person"})
    with pytest.raises(SubmissionRejected):
        controller.submit({"key": item.item_ref, "judgement": "not_assessable", "frame_index": 0})
    record_id = controller.submit({"key": item.item_ref, "judgement": "not_assessable"})
    (record,) = read_records(store)
    assert record.record_id == record_id
    assert record.item_status == "output_absent"


def test_missing_media_is_marked_and_not_substituted(store: ReviewStore) -> None:
    controller = open_session(store, "identity_inspection")
    item = find_item(controller.catalogue, outcome="succeeded", has_output=False)
    with pytest.raises(SubmissionRejected):
        controller.submit({"key": item.item_ref, "judgement": "different_person"})
    controller.submit({"key": item.item_ref, "judgement": "not_assessable"})
    assert read_records(store)[0].item_status == "media_unavailable"


# Mode B ---------------------------------------------------------------------------------------


def test_blinded_view_hides_reference_scores_ids_and_conditioning(store: ReviewStore) -> None:
    controller = open_session(store, "blinded_quality", "RV-02")
    view = controller.session_view()
    assert view["mode"] == "blinded_quality"
    assert set(view) == {
        "mode",
        "mode_label",
        "banners",
        "simulated",
        "reviewer_role_code",
        "rubric",
        "playback_fps",
        "items",
    }
    items = view["items"]
    assert len(items) == 4  # succeeded attempts only
    for item in items:
        assert set(item) == {
            "key",
            "label",
            "media_available",
            "frame_count",
            "width",
            "height",
            "default_frame",
        }
        assert item["key"].startswith("Q-")
    assert [i["media_available"] for i in items].count(False) == 1
    serialised = json.dumps(view)
    for forbidden in (
        "it-",
        "FRP-REVIEW",
        "-R000",
        "SYN-",
        "similarity",
        "face_status",
        "reference",
        "attempt",
        "outcome",
        "conditioning",
        "original",
        "private://",
        "identity",
    ):
        assert forbidden not in serialised, forbidden
    assert view["rubric"]["version"] == "frp-blinded-quality-rubric-0.1-draft"


def test_blinded_mode_refuses_references_measurements_and_item_refs(store: ReviewStore) -> None:
    controller = open_session(store, "blinded_quality", "RV-02")
    code = controller.session_view()["items"][0]["key"]
    item_ref = controller.session.item_for_code(code)
    assert controller.measurements(code) is None
    assert controller.measurements(item_ref) is None
    assert controller.media(code, "reference") is None
    assert controller.media(item_ref, "frame", 0) is None
    with pytest.raises(SubmissionRejected, match="unknown item"):
        controller.submit({"key": item_ref, "status": "unscorable", "unscorable_reason": "other"})
    with pytest.raises(SubmissionRejected, match="unexpected"):
        controller.submit({"key": code, "judgement": "same_person"})


def test_blinding_codes_are_session_specific_and_order_is_randomised(store: ReviewStore) -> None:
    orders = set()
    codes: list[set[str]] = []
    for n in range(12):
        session = open_session(store, "blinded_quality", f"RV-{10 + n}").session
        assert session.blinding is not None
        codes.append({e.blinding_code for e in session.blinding})
        orders.add(tuple(e.item_ref for e in session.blinding))
    assert all(a.isdisjoint(b) for i, a in enumerate(codes) for b in codes[i + 1 :])
    assert len(orders) > 1
    assert all(s.blinding is not None for s in read_sessions(store))


def test_blinded_ratings_record_scores_or_unscorable_outcomes(store: ReviewStore) -> None:
    controller = open_session(store, "blinded_quality", "RV-02")
    items = controller.session_view()["items"]
    viewable = next(i for i in items if i["media_available"])
    missing = next(i for i in items if not i["media_available"])
    scores = dict.fromkeys(
        ("subject_visibility", "temporal_continuity", "motion_plausibility", "visual_artefacts"), 4
    )
    controller.submit({"key": viewable["key"], "status": "scored", "scores": scores})
    controller.submit(
        {"key": viewable["key"], "status": "unscorable", "unscorable_reason": "other"}
    )
    with pytest.raises(SubmissionRejected, match="only be unscorable"):
        controller.submit({"key": missing["key"], "status": "scored", "scores": scores})
    controller.submit(
        {"key": missing["key"], "status": "unscorable", "unscorable_reason": "no_video"}
    )
    for bad in (
        {"status": "scored", "scores": {**scores, "visual_artefacts": 6}},
        {"status": "scored", "scores": {"subject_visibility": 3}},
        {"status": "scored", "scores": scores, "unscorable_reason": "other"},
        {"status": "unscorable"},
        {"status": "great"},
    ):
        with pytest.raises(SubmissionRejected):
            controller.submit({"key": viewable["key"], **bad})
    records = read_records(store)
    assert all(isinstance(r, QualityRating) for r in records)
    assert [r.status for r in records].count("unscorable") == 2
    assert all(r.blinding_code.startswith("Q-") for r in records)
    assert "item_ref" not in records[0].model_dump()


def test_unblinded_reviewer_cannot_rate_the_same_clips_blinded(store: ReviewStore) -> None:
    identity = open_session(store, "identity_inspection", "RV-01")
    item = find_item(identity.catalogue, outcome="succeeded", has_output=True)
    identity.submit({"key": item.item_ref, "judgement": "uncertain"})
    with pytest.raises(ReviewAccessDenied, match="different reviewer"):
        open_session(store, "blinded_quality", "RV-01")
    assert open_session(store, "blinded_quality", "RV-02").mode == "blinded_quality"


def test_viewing_mode_a_without_saving_still_blocks_blinded_rating(store: ReviewStore) -> None:
    identity = open_session(store, "identity_inspection", "RV-01")
    item = find_item(identity.catalogue, outcome="succeeded", has_output=True)
    assert identity.media(item.item_ref, "reference") is not None
    assert identity.media(item.item_ref, "frame", 4) is not None
    identity.close()
    assert read_records(store) == []  # nothing saved, but the session is durable evidence
    with pytest.raises(ReviewAccessDenied, match="different reviewer"):
        open_session(store, "blinded_quality", "RV-01")


def test_concurrent_mode_a_session_stops_blinded_ratings(store: ReviewStore) -> None:
    quality = open_session(store, "blinded_quality", "RV-01")
    code = quality.session_view()["items"][0]["key"]
    unscorable = {"key": code, "status": "unscorable", "unscorable_reason": "other"}
    quality.submit(unscorable)
    open_session(store, "identity_inspection", "RV-01")
    with pytest.raises(SubmissionRejected, match="unblinded"):
        quality.submit(unscorable)
    assert len(read_records(store)) == 1  # the rating made before exposure is kept
    other = open_session(store, "blinded_quality", "RV-02")
    other.submit({**unscorable, "key": other.session_view()["items"][0]["key"]})


def _first_viewable(store: ReviewStore) -> str:
    return find_item(store.load_catalogue(), outcome="succeeded", has_output=True).item_ref


def _assert_reference_unavailable(store: ReviewStore, item_ref: str) -> None:
    controller = open_session(store, "identity_inspection")
    view = next(i for i in controller.session_view()["items"] if i["key"] == item_ref)
    assert view["item_status"] == "reference_unavailable"
    assert not view["reference_available"]
    assert "reference unavailable" in view["status_note"].lower()
    assert view["frame_count"] == FRAME_COUNT  # the output itself is still shown
    assert controller.media(item_ref, "reference") is None
    for judgement in ("same_person", "different_person", "uncertain"):
        with pytest.raises(SubmissionRejected):
            controller.submit({"key": item_ref, "judgement": judgement})
    with pytest.raises(SubmissionRejected):
        controller.submit({"key": item_ref, "judgement": "not_assessable", "frame_index": 4})
    controller.submit({"key": item_ref, "judgement": "not_assessable"})
    (record,) = read_records(store)
    assert record.item_status == "reference_unavailable"


def test_identity_judgement_needs_a_registered_reference(store: ReviewStore) -> None:
    item_ref = _first_viewable(store)

    def drop_reference(data: dict[str, Any]) -> None:
        for item in data["items"]:
            if item["item_ref"] == item_ref:
                item["reference_media"] = None

    edit_catalogue(store, drop_reference)
    _assert_reference_unavailable(store, item_ref)


@pytest.mark.parametrize("damage", ["corrupt", "delete"])
def test_identity_judgement_needs_a_readable_reference(store: ReviewStore, damage: str) -> None:
    item_ref = _first_viewable(store)
    reference = store.load_catalogue().item(item_ref).reference_media
    path = store.root / "media" / reference / "000000.png"
    if damage == "corrupt":
        path.write_bytes(b"not the registered image")
    else:
        path.unlink()
    _assert_reference_unavailable(store, item_ref)


def test_invalid_reviewer_role_codes_are_refused(store: ReviewStore) -> None:
    for code in ("alice", "rv-01", "RV-1", "RV-01; drop", ""):
        with pytest.raises(ReviewAccessDenied, match="reviewer role code"):
            open_session(store, "identity_inspection", code)
