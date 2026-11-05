"""Descriptive clip -> identity -> role aggregation for the single-condition baseline.

Separate from :func:`frp.aggregation.aggregate`, whose variant summaries and paired contrasts are
specific to the A/B/C/D ablation and are unchanged. The baseline has no variants and no pairs, so
this module reports **descriptive** quantities only:

* **Coverage first.** Face-status counts per sampled frame with explicit denominators, including
  frames of failed and unexecuted runs (``not_evaluated``), so every similarity summary is read
  with its coverage.
* **Frame 0 is separate.** The conditioned first frame can be unusually close to the reference;
  later frames (index != 0) are primary.
* **Per clip:** the later-frame similarity is the median over ``valid`` later frames, available
  only when at least ``min_valid_later_frames`` exist. That minimum is **not** preregistered
  (Experiment 003, decision 2), so callers must pass it explicitly; it is recorded in the summary.
* **Temporal drift** is the sampled-frame similarity trajectory and, when both exist, frame-0
  similarity minus the later-frame median. No trend model is fitted.
* **Identity first.** Clips of one identity are not independent: clip values are summarised per
  identity (median), then across identities (median), with the number of contributing identities.
* **Identity and quality stay independent.** Quality is summarised separately and never combined
  with similarity into one score.
* **Attempts.** Every attempt is summarised. Which attempt represents a planned run in the
  identity-level summary is an open decision (Experiment 003, decision 4), so the caller chooses
  ``first_attempt`` or ``last_attempt`` explicitly and the choice is recorded.

No calibration, threshold, interval or test is computed. Similarities are **uncalibrated**
evaluator outputs, not match decisions, and say nothing about consent or protection. The optional
:class:`~frp.aggregation.UncertaintyEstimator` is accepted **only for simulated, non-smoke** result
sets; the sole estimator shipped is the synthetic demonstration in
:mod:`frp.baseline.synthetic_uncertainty` (decisions D14/D15 remain pending).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from statistics import median
from typing import Final, Literal, TypeVar

from frp.aggregation import FIRST_FRAME_INDEX, Interval, UncertaintyEstimator
from frp.baseline.planner import BaselinePlan
from frp.baseline.results import (
    BaselineAttempt,
    BaselineResultSet,
    FailureDetail,
    UnexecutedReason,
    verify_baseline_results_against_plan,
)
from frp.results import FACE_STATUSES, QUALITY_STATUSES, FaceStatus, QualityStatus

AttemptSelection = Literal["first_attempt", "last_attempt"]
ATTEMPT_SELECTIONS: Final[tuple[AttemptSelection, ...]] = ("first_attempt", "last_attempt")
ClipOutcome = Literal["succeeded", "failed", "not_executed"]
CLIP_OUTCOMES: Final[tuple[ClipOutcome, ...]] = ("succeeded", "failed", "not_executed")
LaterSimilarityStatus = Literal[
    "available", "not_evaluated", "insufficient_valid_later_frames", "no_later_frames_sampled"
]
CALIBRATION_STATUS: Final = "uncalibrated"

_K = TypeVar("_K")


@dataclass(frozen=True, slots=True)
class BaselineClipSummary:
    """One attempt (or one unexecuted run) of one planned run. Private: holds ordinals only."""

    run_id: str
    attempt_index: int | None
    identity_index: int
    prompt_index: int
    seed: int
    outcome: ClipOutcome
    failure_detail: FailureDetail | None
    unexecuted_reason: UnexecutedReason | None
    frames_sampled: int
    face_status_counts: Mapping[FaceStatus, int]
    later_frames_sampled: int
    later_face_status_counts: Mapping[FaceStatus, int]
    first_frame_status: FaceStatus | None
    first_frame_similarity: float | None
    valid_later_frames: int
    later_frame_similarity: float | None
    later_similarity_status: LaterSimilarityStatus
    trajectory: tuple[tuple[int, float | None], ...]
    first_minus_later: float | None
    quality_status: QualityStatus
    quality_score: float | None


@dataclass(frozen=True, slots=True)
class BaselineIdentitySummary:
    identity_index: int
    runs_planned: int
    outcome_counts: Mapping[ClipOutcome, int]
    clips_with_later_similarity: int
    median_later_frame_similarity: float | None
    clips_with_first_frame_similarity: int
    median_first_frame_similarity: float | None
    clips_with_drift: int
    median_first_minus_later: float | None
    quality_status_counts: Mapping[QualityStatus, int]
    clips_with_quality: int
    median_quality_score: float | None


@dataclass(frozen=True, slots=True)
class BaselineSummary:
    experiment_id: str
    protocol: str
    run_role: str
    claim_scope: str
    simulated: bool
    simulation_scenario: str | None
    calibration_status: str
    evaluated: bool
    frame_indices: tuple[int, ...]
    later_frame_indices: tuple[int, ...]
    first_frame_sampled: bool
    min_valid_later_frames: int
    attempt_selection: AttemptSelection
    accounting: Mapping[str, object]
    runs_planned: int
    outcome_counts: Mapping[ClipOutcome, int]
    frames_declared: int
    face_status_counts: Mapping[FaceStatus, int]
    first_frame_status_counts: Mapping[FaceStatus, int]
    later_frames_declared: int
    later_face_status_counts: Mapping[FaceStatus, int]
    later_similarity_status_counts: Mapping[LaterSimilarityStatus, int]
    identities_total: int
    identities_with_later_similarity: int
    median_later_frame_similarity: float | None
    later_frame_similarity_interval: Interval | None
    identities_with_first_frame_similarity: int
    median_first_frame_similarity: float | None
    identities_with_drift: int
    median_first_minus_later: float | None
    quality_status_counts: Mapping[QualityStatus, int]
    identities_with_quality: int
    median_quality_score: float | None
    uncertainty_method: str | None
    attempts: tuple[BaselineClipSummary, ...]
    selected: tuple[BaselineClipSummary, ...]
    identities: tuple[BaselineIdentitySummary, ...]


def _counts(values: Iterable[_K], keys: Sequence[_K]) -> dict[_K, int]:
    counter = Counter(values)
    return {key: counter.get(key, 0) for key in keys}


def _median_or_none(values: Sequence[float]) -> float | None:
    return median(values) if values else None


def summarise_attempt(
    attempt: BaselineAttempt, *, min_valid_later_frames: int
) -> BaselineClipSummary:
    """Clip-level summary of one attempt. Similarity is used only where the face is ``valid``."""
    frames = attempt.frames
    later = [f for f in frames if f.frame_index != FIRST_FRAME_INDEX]
    first = next((f for f in frames if f.frame_index == FIRST_FRAME_INDEX), None)
    later_values = [f.similarity for f in later if f.similarity is not None]
    status: LaterSimilarityStatus
    if not later:
        status = "no_later_frames_sampled"
    elif all(f.face_status == "not_evaluated" for f in later):
        status = "not_evaluated"
    elif len(later_values) < min_valid_later_frames:
        status = "insufficient_valid_later_frames"
    else:
        status = "available"
    later_similarity = median(later_values) if status == "available" else None
    first_similarity = first.similarity if first is not None else None
    drift = (
        first_similarity - later_similarity
        if first_similarity is not None and later_similarity is not None
        else None
    )
    return BaselineClipSummary(
        run_id=attempt.run_id,
        attempt_index=attempt.attempt_index,
        identity_index=attempt.identity_index,
        prompt_index=attempt.prompt_index,
        seed=attempt.seed,
        outcome=attempt.execution.status,  # type: ignore[arg-type]
        failure_detail=attempt.failure_detail,
        unexecuted_reason=None,
        frames_sampled=len(frames),
        face_status_counts=_counts((f.face_status for f in frames), FACE_STATUSES),
        later_frames_sampled=len(later),
        later_face_status_counts=_counts((f.face_status for f in later), FACE_STATUSES),
        first_frame_status=first.face_status if first is not None else None,
        first_frame_similarity=first_similarity,
        valid_later_frames=len(later_values),
        later_frame_similarity=later_similarity,
        later_similarity_status=status,
        trajectory=tuple((f.frame_index, f.similarity) for f in frames),
        first_minus_later=drift,
        quality_status=attempt.quality.status,
        quality_score=attempt.quality.score,
    )


def _unexecuted_summary(
    run_id: str,
    reason: UnexecutedReason,
    identity_index: int,
    prompt_index: int,
    seed: int,
    frame_indices: tuple[int, ...],
) -> BaselineClipSummary:
    later = [i for i in frame_indices if i != FIRST_FRAME_INDEX]
    first_sampled = FIRST_FRAME_INDEX in frame_indices
    return BaselineClipSummary(
        run_id=run_id,
        attempt_index=None,
        identity_index=identity_index,
        prompt_index=prompt_index,
        seed=seed,
        outcome="not_executed",
        failure_detail=None,
        unexecuted_reason=reason,
        frames_sampled=len(frame_indices),
        face_status_counts=_counts(["not_evaluated"] * len(frame_indices), FACE_STATUSES),
        later_frames_sampled=len(later),
        later_face_status_counts=_counts(["not_evaluated"] * len(later), FACE_STATUSES),
        first_frame_status="not_evaluated" if first_sampled else None,
        first_frame_similarity=None,
        valid_later_frames=0,
        later_frame_similarity=None,
        later_similarity_status="not_evaluated" if later else "no_later_frames_sampled",
        trajectory=tuple((i, None) for i in frame_indices),
        first_minus_later=None,
        quality_status="not_evaluated",
        quality_score=None,
    )


def _identity_medians(
    clips: Iterable[BaselineClipSummary], value: Callable[[BaselineClipSummary], float | None]
) -> dict[int, float]:
    per_identity: dict[int, list[float]] = defaultdict(list)
    for clip in clips:
        if (observed := value(clip)) is not None:
            per_identity[clip.identity_index].append(observed)
    return {identity: median(values) for identity, values in sorted(per_identity.items())}


def _later(clip: BaselineClipSummary) -> float | None:
    return clip.later_frame_similarity


def _first(clip: BaselineClipSummary) -> float | None:
    return clip.first_frame_similarity


def _drift(clip: BaselineClipSummary) -> float | None:
    return clip.first_minus_later


def _quality(clip: BaselineClipSummary) -> float | None:
    return clip.quality_score


def _identity_summary(identity: int, clips: list[BaselineClipSummary]) -> BaselineIdentitySummary:
    later = [v for c in clips if (v := _later(c)) is not None]
    first = [v for c in clips if (v := _first(c)) is not None]
    drift = [v for c in clips if (v := _drift(c)) is not None]
    quality = [v for c in clips if (v := _quality(c)) is not None]
    return BaselineIdentitySummary(
        identity_index=identity,
        runs_planned=len(clips),
        outcome_counts=_counts((c.outcome for c in clips), CLIP_OUTCOMES),
        clips_with_later_similarity=len(later),
        median_later_frame_similarity=_median_or_none(later),
        clips_with_first_frame_similarity=len(first),
        median_first_frame_similarity=_median_or_none(first),
        clips_with_drift=len(drift),
        median_first_minus_later=_median_or_none(drift),
        quality_status_counts=_counts((c.quality_status for c in clips), QUALITY_STATUSES),
        clips_with_quality=len(quality),
        median_quality_score=_median_or_none(quality),
    )


def aggregate_baseline(
    results: BaselineResultSet,
    plan: BaselinePlan,
    *,
    min_valid_later_frames: int,
    attempt_selection: AttemptSelection,
    uncertainty: UncertaintyEstimator | None = None,
) -> BaselineSummary:
    """Summarise a plan-verified baseline result set descriptively, without imputation."""
    if isinstance(min_valid_later_frames, bool) or min_valid_later_frames < 1:
        raise ValueError("min_valid_later_frames must be an integer >= 1")
    if attempt_selection not in ATTEMPT_SELECTIONS:
        raise ValueError("attempt_selection must be first_attempt or last_attempt")
    if uncertainty is not None:
        if not results.simulated:
            raise ValueError(
                "uncertainty estimators are not scientifically authorised for non-simulated "
                "results (D14/D15 pending review)"
            )
        if results.run_role == "smoke":
            raise ValueError("a smoke run supports no uncertainty interval")
    verify_baseline_results_against_plan(results, plan)

    attempts = tuple(
        summarise_attempt(a, min_valid_later_frames=min_valid_later_frames)
        for a in results.attempts
    )
    by_run: dict[str, list[BaselineClipSummary]] = defaultdict(list)
    for clip in attempts:
        by_run[clip.run_id].append(clip)
    unexecuted = {u.run_id: u.reason for u in results.unexecuted}
    selected = []
    for run in plan.runs:
        if run.run_id in by_run:
            run_attempts = by_run[run.run_id]
            selected.append(run_attempts[0 if attempt_selection == "first_attempt" else -1])
        else:
            selected.append(
                _unexecuted_summary(
                    run.run_id,
                    unexecuted[run.run_id],
                    run.identity_index,
                    run.prompt_index,
                    run.seed,
                    results.frame_indices,
                )
            )

    per_identity: dict[int, list[BaselineClipSummary]] = defaultdict(list)
    for clip in selected:
        per_identity[clip.identity_index].append(clip)
    identities = tuple(
        _identity_summary(identity, clips) for identity, clips in sorted(per_identity.items())
    )
    later = list(_identity_medians(selected, _later).values())
    first = list(_identity_medians(selected, _first).values())
    drift = list(_identity_medians(selected, _drift).values())
    quality = list(_identity_medians(selected, _quality).values())

    face_counts: Counter[FaceStatus] = Counter()
    later_counts: Counter[FaceStatus] = Counter()
    for clip in selected:
        face_counts.update(clip.face_status_counts)
        later_counts.update(clip.later_face_status_counts)
    later_indices = tuple(i for i in results.frame_indices if i != FIRST_FRAME_INDEX)
    interval = uncertainty.interval(later) if uncertainty is not None and later else None
    return BaselineSummary(
        experiment_id=results.experiment_id,
        protocol=results.protocol,
        run_role=results.run_role,
        claim_scope=results.claim_scope,
        simulated=results.simulated,
        simulation_scenario=results.simulation_scenario,
        calibration_status=CALIBRATION_STATUS,
        evaluated=results.face_evaluator is not None,
        frame_indices=results.frame_indices,
        later_frame_indices=later_indices,
        first_frame_sampled=FIRST_FRAME_INDEX in results.frame_indices,
        min_valid_later_frames=min_valid_later_frames,
        attempt_selection=attempt_selection,
        accounting=results.accounting(),
        runs_planned=len(plan.runs),
        outcome_counts=_counts((c.outcome for c in selected), CLIP_OUTCOMES),
        frames_declared=len(results.frame_indices) * len(selected),
        face_status_counts={s: face_counts[s] for s in FACE_STATUSES},
        first_frame_status_counts=_counts(
            (c.first_frame_status for c in selected if c.first_frame_status is not None),
            FACE_STATUSES,
        ),
        later_frames_declared=len(later_indices) * len(selected),
        later_face_status_counts={s: later_counts[s] for s in FACE_STATUSES},
        later_similarity_status_counts=_counts(
            (c.later_similarity_status for c in selected),
            (
                "available",
                "not_evaluated",
                "insufficient_valid_later_frames",
                "no_later_frames_sampled",
            ),
        ),
        identities_total=len(identities),
        identities_with_later_similarity=len(later),
        median_later_frame_similarity=_median_or_none(later),
        later_frame_similarity_interval=interval,
        identities_with_first_frame_similarity=len(first),
        median_first_frame_similarity=_median_or_none(first),
        identities_with_drift=len(drift),
        median_first_minus_later=_median_or_none(drift),
        quality_status_counts=_counts((c.quality_status for c in selected), QUALITY_STATUSES),
        identities_with_quality=len(quality),
        median_quality_score=_median_or_none(quality),
        uncertainty_method=uncertainty.name if uncertainty is not None else None,
        attempts=attempts,
        selected=tuple(selected),
        identities=identities,
    )


__all__ = [
    "ATTEMPT_SELECTIONS",
    "CALIBRATION_STATUS",
    "AttemptSelection",
    "BaselineClipSummary",
    "BaselineIdentitySummary",
    "BaselineSummary",
    "aggregate_baseline",
    "summarise_attempt",
]
