"""Review sessions: what each mode may show, and how submitted judgements become records.

This module is independent of HTTP so that the separation of the two modes can be tested
directly. The browser only ever receives what :meth:`ReviewController.session_view`,
:meth:`ReviewController.measurements` and :meth:`ReviewController.media` return.

**Mode A — identity inspection (unblinded).** Items are keyed by opaque item references and shown
with their reference still, every sampled frame, a later-frame default and, only on request, the
automated detection statuses and *uncalibrated* similarities. Failed, unexecuted,
media-unavailable, output-unreadable (registered frames missing or damaged) and
reference-unavailable (missing or unreadable original) items are shown with their status and can
only be judged ``not_assessable``. Every frame is re-verified when the view is built and again when
a judgement is submitted.

**Mode B — blinded quality.** Only succeeded attempts, keyed by fresh session-specific blinding
codes in a randomised order. No reference, no score, no detection status, no run id, item
reference, attempt, outcome or conditioning information is ever included. A reviewer who has
opened any Mode A session on the store (saved judgement or not) is refused, and a Mode B session
stops accepting ratings if its reviewer opens Mode A concurrently.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Final

from pydantic import ValidationError

from frp import __version__
from frp.review.access import (
    DenyAllReviewAccess,
    ReviewAccessDenied,
    ReviewAccessProvider,
    ReviewAccessRequest,
    authorise_review,
)
from frp.review.records import (
    IDENTITY_INSTRUMENT_VERSION,
    IDENTITY_JUDGEMENTS,
    QUALITY_CRITERIA,
    QUALITY_RUBRIC_VERSION,
    QUALITY_SCALE,
    RECORD_SCHEMA_VERSION,
    SESSION_SCHEMA_VERSION,
    IdentityObservation,
    ItemStatus,
    QualityRating,
    ReviewMode,
    ReviewSession,
    new_blinding_key,
    new_record_id,
    new_session_id,
    prior_unblinded_exposure,
    read_records,
    read_sessions,
    unblinded_sessions,
    write_record,
    write_session,
)
from frp.review.store import ReviewCatalogue, ReviewItem, ReviewStore, StoreError

SIMULATED_BANNER: Final = (
    "SIMULATED DATA — NOT SCIENTIFIC EXPERIMENTAL EVIDENCE. Procedurally generated, "
    "non-biometric demo content; no person, face or model output is shown."
)
PRIVATE_BANNER: Final = (
    "PRIVATE — authorised reviewers only. Do not screenshot, screen-record, copy or review "
    "in shared spaces."
)
SIMILARITY_NOTICE: Final = (
    "UNCALIBRATED evaluator output. A similarity value is not a match decision, not human "
    "recognisability, and not evidence of identity, consent or protection."
)
FIRST_FRAME_NOTE: Final = (
    "conditioned first frame: can look unusually close to the reference; later frames are primary"
)
CRITERION_LABELS: Final = {
    "subject_visibility": "Subject visibility (is the subject clearly visible?)",
    "temporal_continuity": "Temporal continuity (is the scene consistent over time?)",
    "motion_plausibility": "Motion plausibility (is the motion natural and smooth?)",
    "visual_artefacts": "Freedom from visual artefacts (5 = no visible artefacts)",
}
UNSCORABLE_REASONS: Final = ("no_video", "corrupted_or_unplayable", "other")
_IDENTITY_FIELDS: Final = frozenset({"key", "judgement", "frame_index", "notes"})
_QUALITY_FIELDS: Final = frozenset({"key", "status", "scores", "unscorable_reason", "notes"})


class GrantExpired(Exception):
    """The review access grant has expired; no further data may be read or recorded."""


class SubmissionRejected(Exception):
    """A submitted judgement was invalid. ``problems`` are fixed descriptions."""

    def __init__(self, problems: Sequence[str]) -> None:
        self.problems = tuple(problems)
        super().__init__("; ".join(self.problems))


def default_frame_index(sampled: Sequence[int], frame_count: int) -> int:
    """Start on the first sampled *later* frame, never automatically on frame 0."""
    later = [i for i in sampled if 0 < i < frame_count]
    if later:
        return later[0]
    return frame_count - 1 if frame_count > 1 else 0


def sampled_frames(sampled: Sequence[int], frame_count: int) -> list[dict[str, Any]]:
    """Thumbnail descriptors for the manifest's frame indices that exist in the output."""
    return [
        {
            "index": index,
            "first_frame": index == 0,
            "label": f"Frame {index}" + (f" ({FIRST_FRAME_NOTE})" if index == 0 else ""),
        }
        for index in sampled
        if index < frame_count
    ]


def item_status(item: ReviewItem) -> ItemStatus:
    """Status from the catalogue alone; the controller also checks that the media are readable."""
    if item.outcome != "succeeded":
        return "output_absent"
    if item.output_media is None:
        return "media_unavailable"
    return "available" if item.reference_media is not None else "reference_unavailable"


def _status_note(item: ReviewItem, status: ItemStatus) -> str:
    if item.outcome == "failed":
        return f"Generation failed ({item.failure_detail}). No output exists; nothing is scored."
    if item.outcome == "not_executed":
        return f"Run not executed ({item.unexecuted_reason}). No output exists."
    if status == "media_unavailable":
        return "Output media unavailable in this store. Nothing is substituted."
    if status == "output_unreadable":
        return (
            "Output media missing or damaged (frames do not match their registered digests). "
            "Nothing is substituted; only not assessable can be recorded."
        )
    if status == "reference_unavailable":
        return (
            "Original reference unavailable or unreadable. Identity cannot be compared; "
            "only not assessable can be recorded."
        )
    return "Output available."


class ReviewController:
    """One open review session over one store."""

    def __init__(
        self,
        store: ReviewStore,
        catalogue: ReviewCatalogue,
        session: ReviewSession,
        clock: Callable[[], datetime] | None = None,
    ):
        self._clock = clock or (lambda: datetime.now(UTC))
        self.store = store
        self.catalogue = catalogue
        self.session = session
        self.grant_expires_at: datetime | None = None
        self._revealed: set[str] = set()
        self._viewed: set[tuple[str, str]] = set()
        self._lock = threading.Lock()

    @classmethod
    def open(
        cls,
        store: ReviewStore,
        *,
        mode: ReviewMode,
        reviewer_role_code: str,
        provider: ReviewAccessProvider | None = None,
        environ: Mapping[str, str] | None = None,
        now: datetime | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> ReviewController:
        """Authorise, create the private session record and log the opening, or raise."""
        catalogue = store.load_catalogue()
        session_id = new_session_id()
        request = ReviewAccessRequest(
            store_id=catalogue.store_id,
            content_class=catalogue.content_class,
            storage_approval_reference=catalogue.storage_approval_reference,
            mode=mode,
            reviewer_role_code=reviewer_role_code,
            session_id=session_id,
        )
        expires_at = authorise_review(
            store, catalogue, request, provider or DenyAllReviewAccess(), environ=environ, now=now
        )
        blinding = None
        if mode == "blinded_quality":
            refs = [i.item_ref for i in catalogue.items if i.outcome == "succeeded"]
            if not refs:
                raise ReviewAccessDenied(["there are no generated clips to rate"])
            if prior_unblinded_exposure(
                read_records(store), reviewer_role_code, refs
            ) or unblinded_sessions(read_sessions(store), reviewer_role_code):
                raise ReviewAccessDenied(
                    [
                        "this reviewer has opened an unblinded (Mode A) session or judged these "
                        "clips unblinded; a different reviewer must do the blinded rating"
                    ]
                )
            blinding = new_blinding_key(refs)
        try:
            session = ReviewSession(
                session_schema_version=SESSION_SCHEMA_VERSION,
                session_id=session_id,
                store_id=catalogue.store_id,
                mode=mode,
                reviewer_role_code=reviewer_role_code,
                viewer_version=__version__,
                created_at=now or datetime.now(UTC),
                instrument_version=(
                    IDENTITY_INSTRUMENT_VERSION
                    if mode == "identity_inspection"
                    else QUALITY_RUBRIC_VERSION
                ),
                blinding=blinding,
            )
        except ValidationError:
            raise ReviewAccessDenied(["invalid reviewer role code or review mode"]) from None
        write_session(store, session)
        store.append_access_event(
            session_id=session_id, reviewer_role_code=reviewer_role_code, event="session_open"
        )
        controller = cls(store, catalogue, session, clock)
        controller.grant_expires_at = expires_at
        return controller

    def expired(self, now: datetime | None = None) -> bool:
        """True once the grant has expired; media and records must then stop."""
        return self.grant_expires_at is not None and (now or self._clock()) >= (
            self.grant_expires_at
        )

    @property
    def mode(self) -> ReviewMode:
        return self.session.mode

    def close(self) -> None:
        self.store.append_access_event(
            session_id=self.session.session_id,
            reviewer_role_code=self.session.reviewer_role_code,
            event="session_close",
        )

    def _item_for_key(self, key: str) -> ReviewItem | None:
        if self.mode == "blinded_quality":
            ref = self.session.item_for_code(key)
            return self.catalogue.item(ref) if ref is not None else None
        return self.catalogue.item(key)

    def _output_shape(self, item: ReviewItem) -> tuple[int, int, int]:
        entry = self.catalogue.media.get(item.output_media) if item.output_media else None
        return (entry.frame_count, entry.width, entry.height) if entry else (0, 0, 0)

    def _readable(self, media_id: str | None) -> bool:
        """Every frame exists, matches its registered digest and passes sanitising (fail closed)."""
        entry = self.catalogue.media.get(media_id) if media_id is not None else None
        if entry is None:
            return False
        try:
            for index in range(entry.frame_count):
                self.store.read_frame(self.catalogue, media_id, index)
        except StoreError:
            return False
        return True

    def _reference_readable(self, item: ReviewItem) -> bool:
        return self._readable(item.reference_media)

    def _output_readable(self, item: ReviewItem) -> bool:
        return self._readable(item.output_media)

    def _status(
        self,
        item: ReviewItem,
        *,
        output_readable: bool | None = None,
        reference_readable: bool | None = None,
    ) -> ItemStatus:
        status = item_status(item)
        if status in ("output_absent", "media_unavailable"):
            return status
        if not (self._output_readable(item) if output_readable is None else output_readable):
            return "output_unreadable"
        if not (
            self._reference_readable(item) if reference_readable is None else reference_readable
        ):
            return "reference_unavailable"
        return "available"

    def _blinding_compromised(self) -> bool:
        """Whether this reviewer has opened Mode A on the store, even concurrently with this one."""
        try:
            sessions = read_sessions(self.store)
        except StoreError:
            return True
        return bool(unblinded_sessions(sessions, self.session.reviewer_role_code))

    def _banners(self) -> list[str]:
        return [SIMULATED_BANNER if self.catalogue.simulated else PRIVATE_BANNER]

    def require_unexpired(self) -> None:
        if self.expired():
            raise GrantExpired("the review access grant has expired")

    def session_view(self) -> dict[str, Any]:
        self.require_unexpired()
        if self.mode == "blinded_quality":
            return self._quality_view()
        items = []
        for position, item in enumerate(self.catalogue.items, 1):
            frame_count, width, height = self._output_shape(item)
            readable = self._reference_readable(item)
            output_readable = frame_count > 0 and self._output_readable(item)
            if not output_readable:
                frame_count = 0
            status = self._status(
                item, output_readable=output_readable, reference_readable=readable
            )
            items.append(
                {
                    "key": item.item_ref,
                    "label": f"Item {position} of {len(self.catalogue.items)}",
                    "outcome": item.outcome,
                    "item_status": status,
                    "status_note": _status_note(item, status),
                    "reference_available": readable,
                    "frame_count": frame_count,
                    "width": width,
                    "height": height,
                    "sampled_frames": sampled_frames(self.catalogue.frame_indices, frame_count),
                    "default_frame": default_frame_index(self.catalogue.frame_indices, frame_count),
                }
            )
        return {
            "mode": "identity_inspection",
            "mode_label": "Mode A — identity inspection (unblinded)",
            "banners": self._banners(),
            "simulated": self.catalogue.simulated,
            "reviewer_role_code": self.session.reviewer_role_code,
            "instrument_version": IDENTITY_INSTRUMENT_VERSION,
            "judgements": list(IDENTITY_JUDGEMENTS),
            "playback_fps": self.catalogue.playback_fps,
            "similarity_notice": SIMILARITY_NOTICE,
            "items": items,
        }

    def _quality_view(self) -> dict[str, Any]:
        items = []
        blinding = self.session.blinding or ()
        for position, entry in enumerate(blinding, 1):
            item = self.catalogue.item(entry.item_ref)
            frame_count, width, height = self._output_shape(item) if item else (0, 0, 0)
            available = item is not None and frame_count > 0 and self._output_readable(item)
            items.append(
                {
                    "key": entry.blinding_code,
                    "label": f"Clip {position} of {len(blinding)}",
                    "media_available": available,
                    "frame_count": frame_count if available else 0,
                    "width": width,
                    "height": height,
                    "default_frame": 0,
                }
            )
        return {
            "mode": "blinded_quality",
            "mode_label": "Mode B — blinded video-quality review",
            "banners": self._banners(),
            "simulated": self.catalogue.simulated,
            "reviewer_role_code": self.session.reviewer_role_code,
            "rubric": {
                "version": QUALITY_RUBRIC_VERSION,
                "scale": list(QUALITY_SCALE),
                "criteria": [{"id": c, "label": CRITERION_LABELS[c]} for c in QUALITY_CRITERIA],
                "unscorable_reasons": list(UNSCORABLE_REASONS),
            },
            "playback_fps": self.catalogue.playback_fps,
            "items": items,
        }

    def measurements(self, key: str) -> dict[str, Any] | None:
        """Mode A only: automated detection statuses and uncalibrated similarities, on request."""
        self.require_unexpired()
        if self.mode != "identity_inspection":
            return None
        item = self.catalogue.item(key)
        if item is None:
            return None
        with self._lock:
            self._revealed.add(item.item_ref)
        self.store.append_access_event(
            session_id=self.session.session_id,
            reviewer_role_code=self.session.reviewer_role_code,
            event="measurements_revealed",
            item=item.item_ref,
        )
        evaluator = self.catalogue.face_evaluator
        return {
            "calibration_status": self.catalogue.calibration_status,
            "notice": SIMILARITY_NOTICE,
            "simulated": self.catalogue.simulated,
            "face_evaluator": (
                None
                if evaluator is None
                else {
                    "name": evaluator.name,
                    "revision": evaluator.revision,
                    "simulated": evaluator.simulated,
                }
            ),
            "frames": [
                {
                    "index": f.frame_index,
                    "first_frame": f.frame_index == 0,
                    "face_status": f.face_status,
                    "similarity": f.similarity,
                }
                for f in item.frames
            ],
        }

    def media(self, key: str, kind: str, index: int = 0) -> bytes | None:
        """Sanitised PNG bytes for a reference (Mode A only) or an output frame, else ``None``."""
        self.require_unexpired()
        item = self._item_for_key(key)
        if item is None:
            return None
        if kind == "reference":
            if self.mode != "identity_inspection" or item.reference_media is None:
                return None
            media_id, index = item.reference_media, 0
        elif kind == "frame" and item.output_media is not None:
            media_id = item.output_media
        else:
            return None
        try:
            data = self.store.read_frame(self.catalogue, media_id, index)
        except StoreError:
            return None
        with self._lock:
            first_view = (key, kind) not in self._viewed
            self._viewed.add((key, kind))
        if first_view:
            self.store.append_access_event(
                session_id=self.session.session_id,
                reviewer_role_code=self.session.reviewer_role_code,
                event="reference_viewed" if kind == "reference" else "output_viewed",
                item=key,
            )
        return data

    def submit(self, payload: Any, now: datetime | None = None) -> str:
        """Validate a browser submission, write a new immutable record and return its id."""
        if self.expired(now):
            raise SubmissionRejected(["the review access grant has expired"])
        if not isinstance(payload, dict):
            raise SubmissionRejected(["submission must be a JSON object"])
        allowed = _IDENTITY_FIELDS if self.mode == "identity_inspection" else _QUALITY_FIELDS
        if set(payload) - allowed or "key" not in payload:
            raise SubmissionRejected(["submission has missing or unexpected fields"])
        key = payload["key"]
        item = self._item_for_key(key) if isinstance(key, str) else None
        if item is None:
            raise SubmissionRejected(["unknown item"])
        common: dict[str, Any] = {
            "record_schema_version": RECORD_SCHEMA_VERSION,
            "record_id": new_record_id(),
            "session_id": self.session.session_id,
            "reviewer_role_code": self.session.reviewer_role_code,
            "viewer_version": __version__,
            "created_at": now or datetime.now(UTC),
            "notes": payload.get("notes"),
        }
        try:
            if self.mode == "identity_inspection":
                frame_index = payload.get("frame_index")
                frame_count = self._output_shape(item)[0]
                if frame_index is not None and (
                    not isinstance(frame_index, int)
                    or isinstance(frame_index, bool)
                    or not 0 <= frame_index < frame_count
                ):
                    raise SubmissionRejected(["frame_index is not a frame of this output"])
                with self._lock:
                    revealed = item.item_ref in self._revealed
                record: IdentityObservation | QualityRating = IdentityObservation(
                    **common,
                    record_kind="identity_observation",
                    instrument_version=IDENTITY_INSTRUMENT_VERSION,
                    item_ref=item.item_ref,
                    item_status=self._status(item),
                    frame_index=frame_index,
                    judgement=payload.get("judgement"),
                    measurements_revealed=revealed,
                )
            else:
                if self._blinding_compromised():
                    raise SubmissionRejected(
                        [
                            "this reviewer has opened an unblinded (Mode A) session on this "
                            "store; blinded ratings are no longer accepted from them"
                        ]
                    )
                record = QualityRating(
                    **common,
                    record_kind="blinded_quality_rating",
                    rubric_version=QUALITY_RUBRIC_VERSION,
                    blinding_code=key,
                    status=payload.get("status"),
                    scores=payload.get("scores"),
                    unscorable_reason=payload.get("unscorable_reason"),
                )
                if record.status == "scored" and not self._output_readable(item):
                    raise SubmissionRejected(
                        ["a clip without viewable media can only be unscorable"]
                    )
        except ValidationError as exc:
            fields = sorted(
                {
                    str(e["loc"][0])
                    for e in exc.errors(include_url=False, include_input=False)
                    if e["loc"] and str(e["loc"][0]) in allowed | {"judgement", "status"}
                }
            )
            raise SubmissionRejected(
                [f"invalid value for: {', '.join(fields) or 'submission'}"]
            ) from None
        write_record(self.store, record)
        self.store.append_access_event(
            session_id=self.session.session_id,
            reviewer_role_code=self.session.reviewer_role_code,
            event="record_saved",
            item=key,
        )
        return record.record_id


__all__ = [
    "FIRST_FRAME_NOTE",
    "PRIVATE_BANNER",
    "SIMILARITY_NOTICE",
    "SIMULATED_BANNER",
    "ReviewController",
    "SubmissionRejected",
    "default_frame_index",
    "item_status",
    "sampled_frames",
]
