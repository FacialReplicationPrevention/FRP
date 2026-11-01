"""Private, immutable, individually attributable review records and review sessions.

* Records are **append-only**: each is written once to its own file with an exclusive create, made
  read-only, and stored with a SHA-256 of its canonical content so modification is detectable. No
  API updates a record. A second opinion, or an adjudication, is a *new* record; disagreement is
  retained, never overwritten.
* Records identify the reviewer by a private **role code** (e.g. ``RV-01``), never a name.
* Mode A (identity inspection) records reference an opaque item reference. Mode B (blinded
  quality) records reference only a session-specific **blinding code**; the key that maps codes
  to items is kept in the private session record and never served to the browser.
* Free-text notes may accidentally contain personal information. They are stored only here, never
  logged or exported, and follow the media's retention and deletion.
* A per-file hash was chosen over a hash chain on purpose: withdrawal of a participant must be able
  to delete that participant's records without invalidating everyone else's.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Final, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)

from frp.review.store import ItemRef, MediaId, ReviewCatalogue, ReviewStore, StoreError

RECORD_SCHEMA_VERSION: Final = "review-record-0.1-draft"
SESSION_SCHEMA_VERSION: Final = "review-session-0.1-draft"
IDENTITY_INSTRUMENT_VERSION: Final = "frp-identity-observation-0.1-draft"
QUALITY_RUBRIC_VERSION: Final = "frp-blinded-quality-rubric-0.1-draft"
MAX_NOTES_CHARS: Final = 2000

ReviewMode = Literal["identity_inspection", "blinded_quality"]
REVIEW_MODES: Final[tuple[ReviewMode, ...]] = ("identity_inspection", "blinded_quality")
IdentityJudgement = Literal["same_person", "different_person", "uncertain", "not_assessable"]
IDENTITY_JUDGEMENTS: Final[tuple[IdentityJudgement, ...]] = (
    "same_person",
    "different_person",
    "uncertain",
    "not_assessable",
)
ItemStatus = Literal[
    "available", "output_absent", "media_unavailable", "output_unreadable", "reference_unavailable"
]
QualityCriterion = Literal[
    "subject_visibility", "temporal_continuity", "motion_plausibility", "visual_artefacts"
]
# Draft rubric, not validated: each criterion on a 1-5 ordinal scale (5 = best), or the whole
# clip unscorable. Prompt adherence is excluded so no prompt text reaches the blinded viewer.
QUALITY_CRITERIA: Final[tuple[QualityCriterion, ...]] = (
    "subject_visibility",
    "temporal_continuity",
    "motion_plausibility",
    "visual_artefacts",
)
QUALITY_SCALE: Final = (1, 5)
UnscorableReason = Literal["no_video", "corrupted_or_unplayable", "other"]

ReviewerRoleCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{2,4}-[0-9]{2,4}$")]
SessionId = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{32}$")]
RecordId = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{32}$")]
BlindingCode = Annotated[str, StringConstraints(pattern=r"^Q-[0-9A-F]{10}$")]
ViewerVersion = Annotated[str, StringConstraints(pattern=r"^[0-9A-Za-z.+-]{1,32}$")]

_STRICT: Final = ConfigDict(strict=True, extra="forbid", frozen=True)


def _clean_notes(value: str | None) -> str | None:
    if value is None:
        return None
    if len(value) > MAX_NOTES_CHARS:
        raise ValueError(f"notes are limited to {MAX_NOTES_CHARS} characters")
    if any(ord(c) < 32 and c not in "\n\t" for c in value) or "\x7f" in value:
        raise ValueError("notes must not contain control characters")
    return value if value.strip() else None


class _RecordBase(BaseModel):
    model_config = _STRICT

    record_schema_version: Literal["review-record-0.1-draft"]
    record_id: RecordId
    session_id: SessionId
    reviewer_role_code: ReviewerRoleCode
    viewer_version: ViewerVersion
    created_at: AwareDatetime
    notes: str | None

    @field_validator("notes")
    @classmethod
    def _notes(cls, value: str | None) -> str | None:
        return _clean_notes(value)


class IdentityObservation(_RecordBase):
    """Mode A: one reviewer's judgement of one item (optionally of one frame)."""

    record_kind: Literal["identity_observation"]
    instrument_version: Literal["frp-identity-observation-0.1-draft"]
    item_ref: ItemRef
    item_status: ItemStatus
    frame_index: Annotated[int, Field(ge=0)] | None
    judgement: IdentityJudgement
    measurements_revealed: bool

    @model_validator(mode="after")
    def _unviewable_item_is_not_assessable(self) -> IdentityObservation:
        if self.item_status != "available" and self.judgement != "not_assessable":
            raise ValueError("an item without a viewable output and reference is not_assessable")
        if self.item_status != "available" and self.frame_index is not None:
            raise ValueError("an item without a viewable output and reference has no frame")
        return self


class QualityRating(_RecordBase):
    """Mode B: one blinded rating of one clip on the versioned rubric, or ``unscorable``."""

    record_kind: Literal["blinded_quality_rating"]
    rubric_version: Literal["frp-blinded-quality-rubric-0.1-draft"]
    blinding_code: BlindingCode
    status: Literal["scored", "unscorable"]
    scores: dict[QualityCriterion, Annotated[int, Field(ge=1, le=5)]] | None
    unscorable_reason: UnscorableReason | None

    @model_validator(mode="after")
    def _scores_only_when_scored(self) -> QualityRating:
        if self.status == "scored":
            if self.scores is None or set(self.scores) != set(QUALITY_CRITERIA):
                raise ValueError("a scored rating needs a score for every rubric criterion")
            if self.unscorable_reason is not None:
                raise ValueError("a scored rating has no unscorable_reason")
        elif self.scores is not None or self.unscorable_reason is None:
            raise ValueError("an unscorable rating has a reason and no scores")
        return self


class Adjudication(_RecordBase):
    """A new record that resolves disagreement between earlier Mode A records; they are kept."""

    record_kind: Literal["adjudication"]
    instrument_version: Literal["frp-identity-observation-0.1-draft"]
    item_ref: ItemRef
    adjudicates: Annotated[tuple[RecordId, ...], Field(min_length=2)]
    judgement: IdentityJudgement


ReviewRecord = IdentityObservation | QualityRating | Adjudication


class StoredRecord(BaseModel):
    """On-disk envelope: the record plus the SHA-256 of its canonical JSON."""

    model_config = _STRICT

    record: Annotated[ReviewRecord, Field(discriminator="record_kind")]
    sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class BlindingEntry(BaseModel):
    model_config = _STRICT

    blinding_code: BlindingCode
    item_ref: ItemRef


class ReviewSession(BaseModel):
    """Private session record. For Mode B it holds the blinding key in presentation order."""

    model_config = _STRICT

    session_schema_version: Literal["review-session-0.1-draft"]
    session_id: SessionId
    store_id: str
    mode: ReviewMode
    reviewer_role_code: ReviewerRoleCode
    viewer_version: ViewerVersion
    created_at: AwareDatetime
    instrument_version: str
    blinding: tuple[BlindingEntry, ...] | None

    @model_validator(mode="after")
    def _blinding_only_for_mode_b(self) -> ReviewSession:
        if (self.mode == "blinded_quality") != (self.blinding is not None):
            raise ValueError("a blinding key is required for, and only for, blinded sessions")
        if self.blinding is not None:
            codes = [entry.blinding_code for entry in self.blinding]
            refs = [entry.item_ref for entry in self.blinding]
            if len(set(codes)) != len(codes) or len(set(refs)) != len(refs):
                raise ValueError("blinding codes and items must be unique")
        return self

    def item_for_code(self, code: str) -> str | None:
        return next((e.item_ref for e in self.blinding or () if e.blinding_code == code), None)


class RecordIntegrityError(StoreError):
    """A stored record is unreadable, invalid or does not match its digest."""


def new_record_id() -> str:
    return secrets.token_hex(16)


def new_session_id() -> str:
    return secrets.token_hex(16)


def _canonical(record: ReviewRecord) -> bytes:
    return json.dumps(
        record.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")


def write_record(store: ReviewStore, record: ReviewRecord) -> None:
    """Persist ``record`` once. A record id can never be written twice (exclusive create)."""
    if isinstance(record, Adjudication) and (
        problems := check_adjudication(read_records(store), record)
    ):
        raise StoreError(problems)
    envelope = StoredRecord(record=record, sha256=hashlib.sha256(_canonical(record)).hexdigest())
    store.write_private_json(
        ("records", record.session_id, f"{record.record_id}.json"),
        envelope.model_dump_json().encode(),
    )


def read_records(store: ReviewStore) -> list[ReviewRecord]:
    """Every stored record, each verified against its digest; raises on any inconsistency."""
    records: list[ReviewRecord] = []
    for session_id in store.list_private_dirs("records"):
        for name in store.list_private("records", session_id):
            try:
                envelope = StoredRecord.model_validate_json(
                    store.read_private_json(("records", session_id, name))
                )
            except (ValidationError, StoreError):
                raise RecordIntegrityError(["a stored review record is invalid"]) from None
            record = envelope.record
            if (
                hashlib.sha256(_canonical(record)).hexdigest() != envelope.sha256
                or name != f"{record.record_id}.json"
                or record.session_id != session_id
            ):
                raise RecordIntegrityError(["a stored review record does not match its digest"])
            records.append(record)
    return sorted(records, key=lambda r: (r.created_at, r.record_id))


def write_session(store: ReviewStore, session: ReviewSession) -> None:
    store.write_private_json(
        ("sessions", f"{session.session_id}.json"), session.model_dump_json().encode()
    )


def read_sessions(store: ReviewStore) -> list[ReviewSession]:
    sessions = []
    for name in store.list_private("sessions"):
        try:
            sessions.append(
                ReviewSession.model_validate_json(store.read_private_json(("sessions", name)))
            )
        except (ValidationError, StoreError):
            raise RecordIntegrityError(["a stored review session is invalid"]) from None
    return sessions


def new_blinding_key(item_refs: Sequence[str]) -> tuple[BlindingEntry, ...]:
    """Fresh, unguessable, session-specific codes in a randomised presentation order."""
    shuffled = list(item_refs)
    secrets.SystemRandom().shuffle(shuffled)
    codes: set[str] = set()
    entries = []
    for item_ref in shuffled:
        while (code := f"Q-{secrets.token_hex(5).upper()}") in codes:
            continue
        codes.add(code)
        entries.append(BlindingEntry(blinding_code=code, item_ref=item_ref))
    return tuple(entries)


def prior_unblinded_exposure(
    records: Iterable[ReviewRecord], reviewer_role_code: str, item_refs: Iterable[str]
) -> list[str]:
    """Items this reviewer has already judged unblinded (Mode A or adjudication)."""
    wanted = set(item_refs)
    return sorted(
        {
            r.item_ref
            for r in records
            if isinstance(r, IdentityObservation | Adjudication)
            and r.reviewer_role_code == reviewer_role_code
            and r.item_ref in wanted
        }
    )


def unblinded_sessions(sessions: Iterable[ReviewSession], reviewer_role_code: str) -> list[str]:
    """Mode A sessions this reviewer has opened on the store, whether or not anything was saved.

    The session file is written before any media is served, so it is durable evidence of possible
    unblinded exposure to every item in the store, including views that left no record.
    """
    return sorted(
        s.session_id
        for s in sessions
        if s.mode == "identity_inspection" and s.reviewer_role_code == reviewer_role_code
    )


def disagreements(records: Iterable[ReviewRecord]) -> dict[str, dict[str, tuple[str, ...]]]:
    """Items whose clip-level Mode A judgements differ between reviewers.

    Returns ``{item_ref: {reviewer_role_code: (judgements in time order)}}``. Every record is
    kept; this only reports, it never chooses a winner.
    """
    per_item: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for record in records:
        if isinstance(record, IdentityObservation) and record.frame_index is None:
            per_item[record.item_ref][record.reviewer_role_code].append(record.judgement)
    return {
        item: {reviewer: tuple(js) for reviewer, js in sorted(by_reviewer.items())}
        for item, by_reviewer in sorted(per_item.items())
        if len(by_reviewer) > 1 and len({j for js in by_reviewer.values() for j in js}) > 1
    }


def check_adjudication(records: Sequence[ReviewRecord], adjudication: Adjudication) -> list[str]:
    """Why ``adjudication`` does not validly link to existing Mode A records of its item."""
    by_id = {r.record_id: r for r in records}
    problems = []
    for record_id in adjudication.adjudicates:
        original = by_id.get(record_id)
        if not isinstance(original, IdentityObservation):
            problems.append("an adjudicated record is missing or not an identity observation")
        elif original.item_ref != adjudication.item_ref:
            problems.append("an adjudicated record refers to a different item")
    if len(set(adjudication.adjudicates)) != len(adjudication.adjudicates):
        problems.append("an adjudication lists a record more than once")
    return problems


@dataclass(frozen=True, slots=True)
class WithdrawalScope:
    """Everything in one store that derives from one identity (for withdrawal and deletion)."""

    identity_index: int
    item_refs: tuple[str, ...]
    media_ids: tuple[str, ...]
    record_ids: tuple[str, ...]
    session_ids_with_blinding_entries: tuple[str, ...]
    blinding_codes: tuple[str, ...]


def withdrawal_scope(
    catalogue: ReviewCatalogue,
    records: Iterable[ReviewRecord],
    sessions: Iterable[ReviewSession],
    identity_index: int,
) -> WithdrawalScope:
    """Locate (not delete) every item, media file, record and blinding entry of one identity.

    Deletion itself must run under the approved storage procedure (readiness gate 3), because
    copies outside this store (backups, provider snapshots) are beyond this software's reach.
    """
    items = [i for i in catalogue.items if i.identity_index == identity_index]
    refs = {i.item_ref for i in items}
    media: set[MediaId] = set()
    for item in items:
        media.update(m for m in (item.reference_media, item.output_media) if m is not None)
    session_list = list(sessions)
    codes = {e.blinding_code for s in session_list for e in s.blinding or () if e.item_ref in refs}
    record_ids = sorted(
        r.record_id
        for r in records
        if (isinstance(r, IdentityObservation | Adjudication) and r.item_ref in refs)
        or (isinstance(r, QualityRating) and r.blinding_code in codes)
    )
    return WithdrawalScope(
        identity_index=identity_index,
        item_refs=tuple(sorted(refs)),
        media_ids=tuple(sorted(media)),
        record_ids=tuple(record_ids),
        session_ids_with_blinding_entries=tuple(
            sorted(
                s.session_id
                for s in session_list
                if any(e.item_ref in refs for e in s.blinding or ())
            )
        ),
        blinding_codes=tuple(sorted(codes)),
    )


def withdrawal_remaining(store: ReviewStore, scope: WithdrawalScope) -> list[str]:
    """Verification step after deletion: which classes of withdrawn material the store still holds.

    An empty list means nothing in *this store* still refers to the identity: no media, records,
    catalogue items or media entries, session blinding entries or access-log lines. Anything that
    cannot be read is reported as remaining, never as deleted. Copies outside the store are not
    checked.
    """
    remaining = []
    if any((store.root / "media" / media_id).exists() for media_id in scope.media_ids):
        remaining.append("media")
    stored = {
        name.removesuffix(".json")
        for s in store.list_private_dirs("records")
        for name in store.list_private("records", s)
    }
    if stored & set(scope.record_ids):
        remaining.append("records")
    refs = set(scope.item_refs)
    if (store.root / "catalogue.json").exists() or (store.root / "catalogue.json").is_symlink():
        try:
            catalogue = store.load_catalogue()
        except StoreError:
            remaining.append("catalogue")
        else:
            if refs & {i.item_ref for i in catalogue.items} or set(scope.media_ids) & set(
                catalogue.media
            ):
                remaining.append("catalogue")
    try:
        sessions = read_sessions(store)
    except StoreError:
        remaining.append("session_blinding")
    else:
        if any(e.item_ref in refs for s in sessions for e in s.blinding or ()):
            remaining.append("session_blinding")
    log = store.root / "access-log.jsonl"
    if (log.exists() or log.is_symlink()) and _log_mentions(log, refs | set(scope.blinding_codes)):
        remaining.append("access_log")
    return remaining


def _log_mentions(path: Path, markers: set[str]) -> bool:
    """True if any access-log line names a marker, or the log cannot be read and checked."""
    if path.is_symlink():
        return True
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line and json.loads(line).get("item") in markers:
                return True
    except (OSError, ValueError, AttributeError):
        return True
    return False


__all__ = [
    "IDENTITY_INSTRUMENT_VERSION",
    "IDENTITY_JUDGEMENTS",
    "QUALITY_CRITERIA",
    "QUALITY_RUBRIC_VERSION",
    "QUALITY_SCALE",
    "RECORD_SCHEMA_VERSION",
    "REVIEW_MODES",
    "SESSION_SCHEMA_VERSION",
    "Adjudication",
    "BlindingEntry",
    "IdentityObservation",
    "QualityRating",
    "RecordIntegrityError",
    "ReviewMode",
    "ReviewRecord",
    "ReviewSession",
    "WithdrawalScope",
    "check_adjudication",
    "disagreements",
    "new_blinding_key",
    "new_record_id",
    "new_session_id",
    "prior_unblinded_exposure",
    "read_records",
    "read_sessions",
    "unblinded_sessions",
    "withdrawal_remaining",
    "withdrawal_scope",
    "write_record",
    "write_session",
]
