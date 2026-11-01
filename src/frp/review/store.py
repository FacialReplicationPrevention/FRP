"""Private review store: an access-controlled directory holding a catalogue, media and records.

Layout (all inside one approved private directory; nothing here belongs in a repository)::

    <store>/catalogue.json                  private catalogue: items, media registry, provenance
    <store>/media/<media_id>/<NNNNNN>.png   one PNG per frame (a still has frame 000000)
    <store>/sessions/<session_id>.json      private session record (Mode B: blinding key)
    <store>/records/<session_id>/<record_id>.json   immutable review records
    <store>/access-log.jsonl                private access log (opaque references only)

Media are addressed only by opaque ids registered in the catalogue (V7). A request can never name
a path: ids are pattern-checked, looked up in the catalogue, and the resulting file must lie inside
``media/``, must not be a symbolic link, must be below a size limit, must match the SHA-256
registered for it and must pass :func:`~frp.review.png.sanitise_png` (V12).

Frame sequences rather than video containers. Each generated clip is held as one PNG per frame so
that the viewer can show *exact* frame indices (browser video seeking is not frame-accurate) and so
that no video container parser is needed. Converting a real Wan output into this form belongs to
the approved private environment and is not implemented here.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Final, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

from frp.baseline.authorisation import RecordRef
from frp.baseline.planner import BaselinePlan
from frp.baseline.results import (
    BaselineResultSet,
    BaselineRunId,
    FailureDetail,
    UnexecutedReason,
    verify_baseline_results_against_plan,
)
from frp.manifest import ExperimentId, Sha256Hex
from frp.results import (
    FaceEvaluatorInfo,
    FrameEvaluation,
    NonNegativeInt,
    PositiveInt,
    QualityEvaluation,
    QualityEvaluatorInfo,
    frames_with_status,
)
from frp.review.png import MAX_PNG_BYTES, MediaRejected, sanitise_png

CATALOGUE_SCHEMA_VERSION: Final = "review-catalogue-0.1-draft"
MAX_CATALOGUE_BYTES: Final = 8 * 1024 * 1024
MAX_RECORD_BYTES: Final = 64 * 1024
MAX_FRAMES: Final = 1024
_DIRECTORY_COMPONENT: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_FILE_NAME: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}\.json$")
_MEDIA_ID: Final = re.compile(r"^m-[0-9a-f]{32}$")

StoreId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{2,63}$")]
MediaId = Annotated[str, StringConstraints(pattern=r"^m-[0-9a-f]{32}$")]
ItemRef = Annotated[str, StringConstraints(pattern=r"^it-[0-9a-f]{16}$")]
ContentClass = Literal["synthetic", "identifiable"]
ItemOutcome = Literal["succeeded", "failed", "not_executed"]

_STRICT: Final = ConfigDict(strict=True, extra="forbid", frozen=True)


class StoreError(Exception):
    """The store is missing, unsafe or inconsistent. ``problems`` never contain paths or values."""

    def __init__(self, problems: list[str] | tuple[str, ...]) -> None:
        self.problems = tuple(problems)
        super().__init__("; ".join(self.problems))


def new_media_id() -> str:
    return f"m-{secrets.token_hex(16)}"


def new_item_ref() -> str:
    return f"it-{secrets.token_hex(8)}"


class MediaEntry(BaseModel):
    """A registered still or frame sequence: dimensions and the SHA-256 of every frame file."""

    model_config = _STRICT

    kind: Literal["still", "frame_sequence"]
    width: Annotated[int, Field(ge=1, le=4096)]
    height: Annotated[int, Field(ge=1, le=4096)]
    frame_sha256: Annotated[tuple[Sha256Hex, ...], Field(min_length=1, max_length=MAX_FRAMES)]

    @model_validator(mode="after")
    def _still_has_one_frame(self) -> MediaEntry:
        if self.kind == "still" and len(self.frame_sha256) != 1:
            raise ValueError("a still has exactly one frame")
        return self

    @property
    def frame_count(self) -> int:
        return len(self.frame_sha256)


class ReviewItem(BaseModel):
    """One attempt, or one unexecuted run, as presented for review. Private."""

    model_config = _STRICT

    item_ref: ItemRef
    run_id: BaselineRunId
    attempt_index: PositiveInt | None
    identity_index: PositiveInt
    outcome: ItemOutcome
    failure_detail: FailureDetail | None
    unexecuted_reason: UnexecutedReason | None
    reference_media: MediaId | None
    output_media: MediaId | None
    frames: Annotated[tuple[FrameEvaluation, ...], Field(min_length=1)]
    quality: QualityEvaluation

    @model_validator(mode="after")
    def _consistent(self) -> ReviewItem:
        if (self.outcome == "failed") != (self.failure_detail is not None):
            raise ValueError("failure_detail is required for, and only for, failed items")
        if (self.outcome == "not_executed") != (self.unexecuted_reason is not None):
            raise ValueError("unexecuted_reason is required for, and only for, unexecuted items")
        if (self.outcome == "not_executed") != (self.attempt_index is None):
            raise ValueError("attempt_index is null for, and only for, unexecuted items")
        if self.outcome != "succeeded" and self.output_media is not None:
            raise ValueError("only succeeded items can have output media")
        return self


class ReviewCatalogue(BaseModel):
    """Everything the viewer may show for one result set, linked to media by opaque ids."""

    model_config = _STRICT

    catalogue_schema_version: Literal["review-catalogue-0.1-draft"]
    store_id: StoreId
    content_class: ContentClass
    storage_approval_reference: RecordRef | None
    simulated: bool
    simulation_scenario: str | None
    experiment_id: ExperimentId
    run_role: Literal["smoke", "calibration", "baseline"]
    manifest_sha256: Sha256Hex
    calibration_status: Literal["uncalibrated"]
    face_evaluator: FaceEvaluatorInfo | None
    quality_evaluator: QualityEvaluatorInfo | None
    frame_indices: Annotated[tuple[NonNegativeInt, ...], Field(min_length=1)]
    playback_fps: Annotated[int, Field(ge=1, le=60)]
    media: dict[MediaId, MediaEntry]
    items: Annotated[tuple[ReviewItem, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def _consistent(self) -> ReviewCatalogue:
        problems = []
        if self.content_class == "identifiable" and self.storage_approval_reference is None:
            problems.append("identifiable content requires a storage approval reference")
        if self.content_class == "synthetic" and not self.simulated:
            problems.append("a synthetic store may hold only simulated results")
        if self.simulated != (self.simulation_scenario is not None):
            problems.append("simulation_scenario is required for, and only for, simulated data")
        refs = [item.item_ref for item in self.items]
        if any(count > 1 for count in Counter(refs).values()):
            problems.append("item references must be unique")
        used: list[str] = []
        for position, item in enumerate(self.items):
            where = f"items.{position}"
            if tuple(f.frame_index for f in item.frames) != self.frame_indices:
                problems.append(f"{where}: frame indices differ from the catalogue")
            for media_id, kind in ((item.reference_media, "still"), (item.output_media, None)):
                if media_id is None:
                    continue
                entry = self.media.get(media_id)
                if entry is None:
                    problems.append(f"{where}: references unregistered media")
                elif kind == "still" and entry.kind != "still":
                    problems.append(f"{where}: a reference must be a still")
                elif kind is None and entry.kind != "frame_sequence":
                    problems.append(f"{where}: an output must be a frame sequence")
                elif kind is None and self.frame_indices[-1] >= entry.frame_count:
                    problems.append(f"{where}: sampled frame indices exceed the output length")
            if item.output_media is not None:
                used.append(item.output_media)
        if any(count > 1 for count in Counter(used).values()):
            problems.append("two items share one output (overwrite risk)")
        if problems:
            raise ValueError("; ".join(problems))
        return self

    def item(self, item_ref: str) -> ReviewItem | None:
        return next((item for item in self.items if item.item_ref == item_ref), None)


def build_catalogue(
    results: BaselineResultSet,
    plan: BaselinePlan,
    *,
    store_id: str,
    content_class: ContentClass,
    storage_approval_reference: str | None,
    reference_media: Mapping[int, str | None],
    output_media: Mapping[str, str | None],
    media: Mapping[str, MediaEntry],
    playback_fps: int,
) -> ReviewCatalogue:
    """One item per attempt and per unexecuted run, in plan order; nothing is dropped.

    ``reference_media`` maps identity ordinals to registered stills; ``output_media`` maps an
    attempt's artefact URI to its registered frame sequence (absent means *media unavailable*).
    """
    verify_baseline_results_against_plan(results, plan)
    unexecuted = {u.run_id: u.reason for u in results.unexecuted}
    by_run: dict[str, list[Any]] = {}
    for attempt in results.attempts:
        by_run.setdefault(attempt.run_id, []).append(attempt)
    items: list[ReviewItem] = []
    for run in plan.runs:
        reference = reference_media.get(run.identity_index)
        for attempt in by_run.get(run.run_id, []):
            artefact = attempt.execution.artefact
            items.append(
                ReviewItem(
                    item_ref=new_item_ref(),
                    run_id=run.run_id,
                    attempt_index=attempt.attempt_index,
                    identity_index=run.identity_index,
                    outcome=attempt.execution.status,
                    failure_detail=attempt.failure_detail,
                    unexecuted_reason=None,
                    reference_media=reference,
                    output_media=output_media.get(artefact.uri) if artefact else None,
                    frames=attempt.frames,
                    quality=attempt.quality,
                )
            )
        if run.run_id in unexecuted:
            items.append(
                ReviewItem(
                    item_ref=new_item_ref(),
                    run_id=run.run_id,
                    attempt_index=None,
                    identity_index=run.identity_index,
                    outcome="not_executed",
                    failure_detail=None,
                    unexecuted_reason=unexecuted[run.run_id],
                    reference_media=reference,
                    output_media=None,
                    frames=frames_with_status(results.frame_indices, "not_evaluated"),
                    quality=QualityEvaluation(status="not_evaluated", score=None),
                )
            )
    return ReviewCatalogue(
        catalogue_schema_version=CATALOGUE_SCHEMA_VERSION,
        store_id=store_id,
        content_class=content_class,
        storage_approval_reference=storage_approval_reference,
        simulated=results.simulated,
        simulation_scenario=results.simulation_scenario,
        experiment_id=results.experiment_id,
        run_role=results.run_role,
        manifest_sha256=results.manifest_sha256,
        calibration_status="uncalibrated",
        face_evaluator=results.face_evaluator,
        quality_evaluator=results.quality_evaluator,
        frame_indices=results.frame_indices,
        playback_fps=playback_fps,
        media=dict(media),
        items=tuple(items),
    )


def _write_exclusive(path: Path, data: bytes, mode: int = 0o600) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, mode)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)


def _read_regular(path: Path, limit: int) -> bytes:
    """Read a regular, non-symlinked file no larger than ``limit`` bytes."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        raise StoreError(["file is missing, unreadable or a symbolic link"]) from None
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not (info.st_mode & 0o170000) == 0o100000:
            raise StoreError(["not a regular file"])
        if info.st_size > limit:
            raise StoreError(["file exceeds the size limit"])
        return handle.read(limit + 1)


class ReviewStore:
    """File-level access to one private review store. Never exposes paths to callers' outputs."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _directory(self, *parts: str) -> Path:
        """Create (or reuse) a directory below the store, validating every component first."""
        if not parts or not all(
            isinstance(part, str) and _DIRECTORY_COMPONENT.fullmatch(part) for part in parts
        ):
            raise StoreError(["invalid store path component"])
        if self.root.is_symlink() or not self.root.is_dir():
            raise StoreError(["the review store directory is missing or a symbolic link"])
        path = self.root
        for part in parts:
            path = path / part
            if path.is_symlink() or (path.exists() and not path.is_dir()):
                raise StoreError(["store directory is a symbolic link or outside the store"])
            path.mkdir(mode=0o700, exist_ok=True)
            os.chmod(path, 0o700)
        if not path.resolve().is_relative_to(self.root.resolve()):
            raise StoreError(["store directory is a symbolic link or outside the store"])
        return path

    def create(self) -> None:
        """Create a new, empty, owner-only store directory; refuses to reuse an existing one."""
        if self.root.is_symlink() or (self.root.exists() and any(self.root.iterdir())):
            raise StoreError(["the store directory already exists and is not empty"])
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)

    def write_catalogue(self, catalogue: ReviewCatalogue) -> None:
        """Write the catalogue once; it is never replaced in place."""
        _write_exclusive(self.root / "catalogue.json", catalogue.model_dump_json().encode())

    def write_media_frame(self, media_id: str, index: int, png: bytes) -> str:
        """Write one frame of new media exclusively and return its SHA-256."""
        if not isinstance(media_id, str) or not _MEDIA_ID.fullmatch(media_id):
            raise StoreError(["invalid media id"])
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < MAX_FRAMES:
            raise StoreError(["invalid frame index"])
        directory = self._directory("media", media_id)
        _write_exclusive(directory / f"{index:06d}.png", png)
        return hashlib.sha256(png).hexdigest()

    def load_catalogue(self) -> ReviewCatalogue:
        if not self.root.is_dir() or self.root.is_symlink():
            raise StoreError(["the review store directory is missing or a symbolic link"])
        data = _read_regular(self.root / "catalogue.json", MAX_CATALOGUE_BYTES)
        try:
            return ReviewCatalogue.model_validate_json(data)
        except ValidationError as exc:
            problems = sorted(
                {
                    ".".join(str(p) for p in e["loc"] if isinstance(p, int) or p.isidentifier())
                    or "<catalogue>"
                    for e in exc.errors(include_url=False, include_input=False)
                }
            )
            raise StoreError([f"invalid catalogue at: {p}" for p in problems]) from None

    def read_frame(self, catalogue: ReviewCatalogue, media_id: str, index: int) -> bytes:
        """Return one sanitised frame of registered media, or raise :class:`StoreError`."""
        entry = catalogue.media.get(media_id)
        if entry is None or isinstance(index, bool) or not 0 <= index < entry.frame_count:
            raise StoreError(["unknown media or frame"])
        media_root = (self.root / "media").resolve()
        path = self.root / "media" / media_id / f"{index:06d}.png"
        if not path.parent.resolve().is_relative_to(media_root) or path.parent.is_symlink():
            raise StoreError(["media directory is outside the store or a symbolic link"])
        data = _read_regular(path, MAX_PNG_BYTES)
        if hashlib.sha256(data).hexdigest() != entry.frame_sha256[index]:
            raise StoreError(["media file does not match its registered digest"])
        try:
            return sanitise_png(data, expected_width=entry.width, expected_height=entry.height)
        except MediaRejected as exc:
            raise StoreError([str(exc)]) from None

    def append_access_event(
        self, *, session_id: str, reviewer_role_code: str, event: str, item: str | None = None
    ) -> None:
        """Private access log (V8): who (role code), when, which opaque reference. No content."""
        line = json.dumps(
            {
                "at": datetime.now(UTC).isoformat(),
                "session_id": session_id,
                "reviewer_role_code": reviewer_role_code,
                "event": event,
                "item": item,
            },
            separators=(",", ":"),
        )
        path = self.root / "access-log.jsonl"
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags, 0o600)
        with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def write_private_json(self, relative: tuple[str, ...], payload: bytes) -> None:
        """Write a new private file under the store exclusively (sessions and records)."""
        if not relative or not _FILE_NAME.fullmatch(relative[-1]):
            raise StoreError(["invalid store file name"])
        directory = self._directory(*relative[:-1])
        _write_exclusive(directory / relative[-1], payload)
        os.chmod(directory / relative[-1], 0o400)

    def read_private_json(self, relative: tuple[str, ...]) -> bytes:
        return _read_regular(self.root.joinpath(*relative), MAX_RECORD_BYTES)

    def list_private(self, *relative: str) -> list[str]:
        directory = self.root.joinpath(*relative)
        if not directory.is_dir() or directory.is_symlink():
            return []
        return sorted(p.name for p in directory.iterdir() if p.is_file() and not p.is_symlink())

    def list_private_dirs(self, *relative: str) -> list[str]:
        directory = self.root.joinpath(*relative)
        if not directory.is_dir() or directory.is_symlink():
            return []
        return sorted(p.name for p in directory.iterdir() if p.is_dir() and not p.is_symlink())


__all__ = [
    "CATALOGUE_SCHEMA_VERSION",
    "ContentClass",
    "ItemRef",
    "MediaEntry",
    "MediaId",
    "ReviewCatalogue",
    "ReviewItem",
    "ReviewStore",
    "StoreError",
    "StoreId",
    "build_catalogue",
    "new_item_ref",
    "new_media_id",
]
