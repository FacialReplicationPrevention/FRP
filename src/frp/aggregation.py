"""Identity-first, descriptive aggregation of result records: frame -> clip -> identity -> variant.

Frames of one clip and clips of one identity are not independent observations, so similarity
and quality are summarised per clip, then per identity, and only then across identities.
Missing measurements are counted, never imputed. Paired contrasts are formed within trial
groups (same identity, prompt and seed) and summarised at identity level.

This module computes no thresholds, calibration, confidence intervals or hypothesis tests.
:class:`UncertaintyEstimator` is the extension point for future identity-clustered uncertainty.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from statistics import median
from typing import Final, Literal, Protocol, TypeVar

from frp.results import (
    EXECUTION_STATUSES,
    FACE_STATUSES,
    QUALITY_STATUSES,
    ExecutionStatus,
    ExecutorInfo,
    FaceEvaluatorInfo,
    FaceStatus,
    QualityEvaluatorInfo,
    QualityStatus,
    ResultSet,
    RunResult,
)
from frp.variants import VARIANT_CONDITIONING, VARIANT_ORDER, Variant

# Experiment 002 separates the anchored first frame from later frames.
FIRST_FRAME_INDEX: Final = 0
PRIMARY_CONTRASTS: Final = ((Variant.B, Variant.A), (Variant.C, Variant.A), (Variant.D, Variant.A))

Metric = Literal["later_frame_similarity", "quality_score"]
METRICS: Final[tuple[Metric, ...]] = ("later_frame_similarity", "quality_score")

_K = TypeVar("_K")


@dataclass(frozen=True, slots=True)
class Interval:
    lower: float
    upper: float
    level: float


class UncertaintyEstimator(Protocol):
    """Future identity-clustered uncertainty method (e.g. an identity-level bootstrap).

    Receives one unlabelled value per identity and returns an interval, or ``None`` when the
    observations are insufficient. None is implemented in this milestone.
    """

    @property
    def name(self) -> str: ...

    def interval(self, identity_values: Sequence[float]) -> Interval | None: ...


@dataclass(frozen=True, slots=True)
class ClipSummary:
    group_index: int
    identity_index: int
    variant: Variant
    execution_status: ExecutionStatus
    face_status_counts: Mapping[FaceStatus, int]
    valid_later_frames: int
    later_frame_similarity: float | None
    first_frame_similarity: float | None
    quality_status: QualityStatus
    quality_score: float | None


@dataclass(frozen=True, slots=True)
class VariantSummary:
    variant: Variant
    clip_conditioning: str
    vae_first_frame_conditioning: str
    execution_counts: Mapping[ExecutionStatus, int]
    frames_declared: int
    face_status_counts: Mapping[FaceStatus, int]
    clips_planned: int
    clips_with_similarity: int
    identities_total: int
    identities_with_similarity: int
    median_later_frame_similarity: float | None
    identities_with_first_frame: int
    median_first_frame_similarity: float | None
    quality_status_counts: Mapping[QualityStatus, int]
    identities_with_quality: int
    median_quality_score: float | None


@dataclass(frozen=True, slots=True)
class ContrastSummary:
    """Paired ``variant - baseline`` differences, matched within trial groups.

    ``identity_differences`` holds one unlabelled value per identity with at least one
    complete pair (median of that identity's group differences). It is retained for future
    uncertainty estimation and must not be published per identity.
    """

    variant: Variant
    baseline: Variant
    metric: Metric
    groups_total: int
    groups_complete: int
    groups_missing_baseline_only: int
    groups_missing_variant_only: int
    groups_missing_both: int
    identities_total: int
    identities_with_complete_pair: int
    identity_differences: tuple[float, ...]
    median_difference: float | None
    interval: Interval | None

    @property
    def label(self) -> str:
        return f"{self.variant.value} - {self.baseline.value}"


@dataclass(frozen=True, slots=True)
class ExperimentSummary:
    experiment_id: str
    protocol: str
    result_schema_version: str
    simulated: bool
    simulation_scenario: str | None
    manifest_sha256: str
    generation_controls_sha256: str
    frame_indices: tuple[int, ...]
    frame_indices_source: str
    later_frame_indices: tuple[int, ...]
    min_valid_later_frames: int
    executor: ExecutorInfo
    face_evaluator: FaceEvaluatorInfo
    quality_evaluator: QualityEvaluatorInfo
    identities: int
    trial_groups: int
    planned_runs: int
    groups_with_all_variants_similarity: int
    variants: tuple[VariantSummary, ...]
    contrasts: tuple[ContrastSummary, ...]
    uncertainty_method: str | None


def _counts(values: Iterable[_K], keys: Sequence[_K]) -> dict[_K, int]:
    counter = Counter(values)
    return {key: counter.get(key, 0) for key in keys}


def summarise_clip(run: RunResult, min_valid_later_frames: int = 1) -> ClipSummary:
    """Clip-level summary; later-frame similarity is the median over valid later frames, or
    ``None`` when fewer than ``min_valid_later_frames`` valid later frames exist."""
    later = [
        frame.similarity
        for frame in run.frames
        if frame.frame_index != FIRST_FRAME_INDEX and frame.similarity is not None
    ]
    first = next(
        (frame.similarity for frame in run.frames if frame.frame_index == FIRST_FRAME_INDEX),
        None,
    )
    return ClipSummary(
        group_index=run.group_index,
        identity_index=run.identity_index,
        variant=Variant(run.variant),
        execution_status=run.execution.status,
        face_status_counts=_counts((f.face_status for f in run.frames), FACE_STATUSES),
        valid_later_frames=len(later),
        later_frame_similarity=median(later) if len(later) >= min_valid_later_frames else None,
        first_frame_similarity=first,
        quality_status=run.quality.status,
        quality_score=run.quality.score,
    )


def _identity_medians(
    clips: Iterable[ClipSummary], value: Callable[[ClipSummary], float | None]
) -> list[float]:
    per_identity: dict[int, list[float]] = defaultdict(list)
    for clip in clips:
        if (observed := value(clip)) is not None:
            per_identity[clip.identity_index].append(observed)
    return [median(values) for _, values in sorted(per_identity.items())]


def _median_or_none(values: Sequence[float]) -> float | None:
    return median(values) if values else None


def _later(clip: ClipSummary) -> float | None:
    return clip.later_frame_similarity


def _first(clip: ClipSummary) -> float | None:
    return clip.first_frame_similarity


def _quality(clip: ClipSummary) -> float | None:
    return clip.quality_score


_METRIC_VALUE: Final = {"later_frame_similarity": _later, "quality_score": _quality}


def _variant_summary(variant: Variant, clips: list[ClipSummary], frames: int) -> VariantSummary:
    later = _identity_medians(clips, _later)
    first = _identity_medians(clips, _first)
    quality = _identity_medians(clips, _quality)
    face_counts: Counter[FaceStatus] = Counter()
    for clip in clips:
        face_counts.update(clip.face_status_counts)
    conditioning = VARIANT_CONDITIONING[variant]
    return VariantSummary(
        variant=variant,
        clip_conditioning=conditioning.clip.value,
        vae_first_frame_conditioning=conditioning.vae_first_frame.value,
        execution_counts=_counts((c.execution_status for c in clips), EXECUTION_STATUSES),
        frames_declared=frames * len(clips),
        face_status_counts={status: face_counts[status] for status in FACE_STATUSES},
        clips_planned=len(clips),
        clips_with_similarity=sum(c.later_frame_similarity is not None for c in clips),
        identities_total=len({c.identity_index for c in clips}),
        identities_with_similarity=len(later),
        median_later_frame_similarity=_median_or_none(later),
        identities_with_first_frame=len(first),
        median_first_frame_similarity=_median_or_none(first),
        quality_status_counts=_counts((c.quality_status for c in clips), QUALITY_STATUSES),
        identities_with_quality=len(quality),
        median_quality_score=_median_or_none(quality),
    )


def _contrast(
    clips: Mapping[tuple[int, Variant], ClipSummary],
    groups: Mapping[int, int],
    variant: Variant,
    baseline: Variant,
    metric: Metric,
    uncertainty: UncertaintyEstimator | None,
) -> ContrastSummary:
    value = _METRIC_VALUE[metric]
    differences: dict[int, list[float]] = defaultdict(list)
    missing = Counter[str]()
    for group_index, identity_index in groups.items():
        x = value(clips[(group_index, variant)])
        a = value(clips[(group_index, baseline)])
        if x is not None and a is not None:
            differences[identity_index].append(x - a)
        elif x is None and a is None:
            missing["both"] += 1
        elif a is None:
            missing["baseline"] += 1
        else:
            missing["variant"] += 1
    identity_values = tuple(sorted(median(values) for values in differences.values()))
    interval = uncertainty.interval(identity_values) if uncertainty and identity_values else None
    return ContrastSummary(
        variant=variant,
        baseline=baseline,
        metric=metric,
        groups_total=len(groups),
        groups_complete=sum(len(values) for values in differences.values()),
        groups_missing_baseline_only=missing["baseline"],
        groups_missing_variant_only=missing["variant"],
        groups_missing_both=missing["both"],
        identities_total=len(set(groups.values())),
        identities_with_complete_pair=len(identity_values),
        identity_differences=identity_values,
        median_difference=_median_or_none(identity_values),
        interval=interval,
    )


def aggregate(
    results: ResultSet,
    *,
    min_valid_later_frames: int = 1,
    uncertainty: UncertaintyEstimator | None = None,
) -> ExperimentSummary:
    """Summarise a validated :class:`ResultSet` identity-first, without imputation."""
    if min_valid_later_frames < 1:
        raise ValueError("min_valid_later_frames must be >= 1")
    clip_list = [summarise_clip(run, min_valid_later_frames) for run in results.runs]
    clips = {(clip.group_index, clip.variant): clip for clip in clip_list}
    groups = dict(sorted({(c.group_index, c.identity_index) for c in clip_list}))
    frames = len(results.frame_indices)
    variants = tuple(
        _variant_summary(variant, [c for c in clip_list if c.variant is variant], frames)
        for variant in VARIANT_ORDER
    )
    contrasts = tuple(
        _contrast(clips, groups, variant, baseline, metric, uncertainty)
        for variant, baseline in PRIMARY_CONTRASTS
        for metric in METRICS
    )
    return ExperimentSummary(
        experiment_id=results.experiment_id,
        protocol=results.protocol,
        result_schema_version=results.result_schema_version,
        simulated=results.simulated,
        simulation_scenario=results.simulation_scenario,
        manifest_sha256=results.manifest_sha256,
        generation_controls_sha256=results.generation_controls_sha256,
        frame_indices=results.frame_indices,
        frame_indices_source=results.frame_indices_source,
        later_frame_indices=tuple(i for i in results.frame_indices if i != FIRST_FRAME_INDEX),
        min_valid_later_frames=min_valid_later_frames,
        executor=results.executor,
        face_evaluator=results.face_evaluator,
        quality_evaluator=results.quality_evaluator,
        identities=len(set(groups.values())),
        trial_groups=len(groups),
        planned_runs=len(results.runs),
        groups_with_all_variants_similarity=sum(
            all(clips[(g, v)].later_frame_similarity is not None for v in VARIANT_ORDER)
            for g in groups
        ),
        variants=variants,
        contrasts=contrasts,
        uncertainty_method=uncertainty.name if uncertainty else None,
    )
