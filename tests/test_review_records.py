"""Review records: append-only, tamper-evident, attributable; disagreement is kept, never merged."""

from __future__ import annotations

import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from frp.review.records import (
    RECORD_SCHEMA_VERSION,
    Adjudication,
    IdentityObservation,
    RecordIntegrityError,
    check_adjudication,
    disagreements,
    new_record_id,
    read_records,
    read_sessions,
    withdrawal_remaining,
    withdrawal_scope,
    write_record,
)
from frp.review.store import ReviewStore, StoreError
from tests.review_support import find_item, make_demo_store, open_session


@pytest.fixture
def store(tmp_path: Path) -> ReviewStore:
    return make_demo_store(tmp_path / "store")


def _observe(store: ReviewStore, reviewer: str, judgement: str) -> tuple[str, str]:
    controller = open_session(store, "identity_inspection", reviewer)
    item = find_item(controller.catalogue, outcome="succeeded", has_output=True)
    return item.item_ref, controller.submit({"key": item.item_ref, "judgement": judgement})


def _record_path(store: ReviewStore, record_id: str) -> Path:
    (path,) = store.root.glob(f"records/*/{record_id}.json")
    return path


def test_records_are_frozen_read_only_and_never_rewritten(store: ReviewStore) -> None:
    _, record_id = _observe(store, "RV-01", "uncertain")
    (record,) = read_records(store)
    with pytest.raises(ValidationError):
        record.judgement = "same_person"  # type: ignore[misc]
    path = _record_path(store, record_id)
    if os.name == "posix":
        assert path.stat().st_mode & 0o777 == 0o400
    with pytest.raises(FileExistsError):
        write_record(store, record)


def test_tampering_is_detected(store: ReviewStore) -> None:
    _, record_id = _observe(store, "RV-01", "uncertain")
    path = _record_path(store, record_id)
    os.chmod(path, 0o600)
    path.write_text(path.read_text().replace('"uncertain"', '"same_person"'))
    with pytest.raises(RecordIntegrityError, match="digest"):
        read_records(store)
    path.write_text("{not json")
    with pytest.raises(RecordIntegrityError, match="invalid"):
        read_records(store)


def test_moved_record_is_detected(store: ReviewStore) -> None:
    _, record_id = _observe(store, "RV-01", "uncertain")
    path = _record_path(store, record_id)
    path.rename(path.with_name(f"{new_record_id()}.json"))
    with pytest.raises(RecordIntegrityError):
        read_records(store)


def test_disagreement_is_reported_and_every_record_kept(store: ReviewStore) -> None:
    item_ref, first = _observe(store, "RV-01", "same_person")
    _, second = _observe(store, "RV-02", "different_person")
    _, third = _observe(store, "RV-03", "same_person")
    records = read_records(store)
    assert {r.record_id for r in records} == {first, second, third}
    assert disagreements(records) == {
        item_ref: {
            "RV-01": ("same_person",),
            "RV-02": ("different_person",),
            "RV-03": ("same_person",),
        }
    }


def test_agreement_and_single_reviewer_changes_are_not_disagreements(store: ReviewStore) -> None:
    _observe(store, "RV-01", "uncertain")
    _observe(store, "RV-01", "same_person")  # one reviewer revising is kept as two records
    _observe(store, "RV-02", "same_person")
    records = read_records(store)
    assert len(records) == 3
    item_ref = records[0].item_ref
    assert disagreements(records) == {
        item_ref: {"RV-01": ("uncertain", "same_person"), "RV-02": ("same_person",)}
    }
    agreed = [r for r in records if r.judgement == "same_person"]
    assert disagreements(agreed) == {}


def test_adjudication_is_a_new_linked_record(store: ReviewStore) -> None:
    item_ref, first = _observe(store, "RV-01", "same_person")
    _, second = _observe(store, "RV-02", "different_person")
    session_id = read_sessions(store)[0].session_id
    common = {
        "record_schema_version": RECORD_SCHEMA_VERSION,
        "session_id": session_id,
        "reviewer_role_code": "ADJ-01",
        "viewer_version": "0.4.0",
        "created_at": datetime.now(UTC),
        "notes": None,
        "record_kind": "adjudication",
        "instrument_version": "frp-identity-observation-0.1-draft",
        "judgement": "uncertain",
    }
    adjudication = Adjudication(
        **common, record_id=new_record_id(), item_ref=item_ref, adjudicates=(first, second)
    )
    write_record(store, adjudication)
    records = read_records(store)
    assert len(records) == 3  # originals retained
    bogus = Adjudication(
        **common,
        record_id=new_record_id(),
        item_ref=item_ref,
        adjudicates=(first, new_record_id()),
    )
    assert check_adjudication(records, bogus)
    with pytest.raises(StoreError, match="missing"):
        write_record(store, bogus)
    other = find_item(store.load_catalogue(), outcome="failed").item_ref
    wrong_item = Adjudication(
        **common, record_id=new_record_id(), item_ref=other, adjudicates=(first, second)
    )
    with pytest.raises(StoreError, match="different item"):
        write_record(store, wrong_item)


def test_records_identify_reviewers_by_role_code_only() -> None:
    base = {
        "record_schema_version": RECORD_SCHEMA_VERSION,
        "record_id": new_record_id(),
        "session_id": new_record_id(),
        "viewer_version": "0.4.0",
        "created_at": datetime.now(UTC),
        "notes": None,
        "record_kind": "identity_observation",
        "instrument_version": "frp-identity-observation-0.1-draft",
        "item_ref": "it-0123456789abcdef",
        "item_status": "available",
        "frame_index": None,
        "judgement": "uncertain",
        "measurements_revealed": False,
    }
    IdentityObservation(**base, reviewer_role_code="RV-01")
    for bad in ("Jane Doe", "jane@example.org", "RV01"):
        with pytest.raises(ValidationError):
            IdentityObservation(**base, reviewer_role_code=bad)
    with pytest.raises(ValidationError):
        IdentityObservation(
            **{**base, "created_at": datetime(2026, 1, 1)}, reviewer_role_code="RV-01"
        )


def test_withdrawal_scope_locates_and_verifies_deletion_of_one_identity(store: ReviewStore) -> None:
    item_ref, _ = _observe(store, "RV-01", "same_person")
    quality = open_session(store, "blinded_quality", "RV-02")
    for entry in quality.session.blinding or ():
        quality.submit(
            {"key": entry.blinding_code, "status": "unscorable", "unscorable_reason": "other"}
        )
    catalogue = store.load_catalogue()
    identity = next(i.identity_index for i in catalogue.items if i.item_ref == item_ref)
    scope = withdrawal_scope(catalogue, read_records(store), read_sessions(store), identity)
    own = [i for i in catalogue.items if i.identity_index == identity]
    assert set(scope.item_refs) == {i.item_ref for i in own}
    assert {i.reference_media for i in own} <= set(scope.media_ids)
    assert len(scope.record_ids) == 1 + len(own)  # one Mode A + one rating per own clip
    assert scope.session_ids_with_blinding_entries == (quality.session.session_id,)
    assert withdrawal_remaining(store, scope) == ["media", "records"]

    for media_id in scope.media_ids:
        shutil.rmtree(store.root / "media" / media_id)
    for record_id in scope.record_ids:
        path = _record_path(store, record_id)
        os.chmod(path, 0o600)
        path.unlink()
    assert withdrawal_remaining(store, scope) == []
    assert len(read_records(store)) == 4 - len(own)  # other identities' ratings remain
