"""Versioned, strictly validated result records for executed or simulated A/B/C/D runs.

These are *private structured records*. They link each outcome to its planned run id, trial
group, variant and ordinal identity/prompt indices, but never contain identity pseudonyms,
prompt text, images, videos or embeddings. Public outputs are produced only from aggregates
(see :mod:`frp.reporting`).

Missing measurements are explicit: a similarity score exists **only** for a ``valid`` face
evaluation and a quality score **only** for a ``scored`` quality evaluation; every other
status carries ``null`` rather than a placeholder number.
"""

from __future__ import annotations

import itertools
from collections import Counter
from collections.abc import Sequence
from types import MappingProxyType
from typing import Annotated, Final, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)

from frp.manifest import ExperimentId, ExperimentManifest, Seed, Sha256Hex
from frp.planner import RunPlan
from frp.variants import VARIANT_CONDITIONING, Variant

RESULT_SCHEMA_VERSION: Final = "1.0"

# The only protocol supported by result schema 1.0. The fixed A/B/C/D CLIP/VAE design is
# specific to Wan 2.1 I2V; other model families will need their own reviewed protocol id.
PROTOCOL_WAN21_I2V_CLIP_VAE_2X2: Final = "wan2.1-i2v-clip-vae-2x2"
PROTOCOL_MODEL_FAMILY: Final = MappingProxyType({PROTOCOL_WAN21_I2V_CLIP_VAE_2X2: "wan2.1-i2v"})

MAX_RESULTS_BYTES: Final = 16_777_216

FaceStatus = Literal["valid", "absent", "multiple", "low_quality", "error", "not_evaluated"]
FACE_STATUSES: Final[tuple[FaceStatus, ...]] = (
    "valid",
    "absent",
    "multiple",
    "low_quality",
    "error",
    "not_evaluated",
)
ExecutionStatus = Literal["succeeded", "failed", "not_executed"]
EXECUTION_STATUSES: Final[tuple[ExecutionStatus, ...]] = ("succeeded", "failed", "not_executed")
QualityStatus = Literal["scored", "unscorable", "error", "not_evaluated"]
QUALITY_STATUSES: Final[tuple[QualityStatus, ...]] = (
    "scored",
    "unscorable",
    "error",
    "not_evaluated",
)
# Failure categories instead of free-text messages, which could leak paths or private data.
FailureCategory = Literal[
    "executor_error", "timeout", "resource_exhausted", "invalid_input", "other"
]

ComponentName = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")]
ArtefactUri = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9+.-]{0,15}://\S{1,500}$")]
RunId = Annotated[str, StringConstraints(pattern=r"^[A-Z0-9][A-Z0-9-]{2,63}-G[0-9]{4,}-[ABCD]$")]
Similarity = Annotated[float, Field(ge=-1.0, le=1.0, allow_inf_nan=False)]
FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
NonNegativeFloat = Annotated[float, Field(ge=0, allow_inf_nan=False)]
NonNegativeInt = Annotated[int, Field(ge=0)]
PositiveInt = Annotated[int, Field(ge=1)]
ConditioningCode = Literal["original", "altered"]
VariantCode = Literal["A", "B", "C", "D"]

_STRICT: Final = ConfigDict(strict=True, extra="forbid", frozen=True)


class ResultValidationError(Exception):
    """Raised when result records are invalid or do not match their run plan.

    ``problems`` never contains offending input values, so it is safe to print.
    """

    def __init__(self, problems: Sequence[str]) -> None:
        self.problems = tuple(problems)
        super().__init__("; ".join(self.problems))


class ArtefactRef(BaseModel):
    """Opaque reference to a generated artefact held in (private) storage. Never published."""

    model_config = _STRICT

    uri: ArtefactUri


class ExecutionRecord(BaseModel):
    model_config = _STRICT

    status: ExecutionStatus
    artefact: ArtefactRef | None
    failure_category: FailureCategory | None
    gpu_seconds: NonNegativeFloat | None

    @model_validator(mode="after")
    def _consistent(self) -> ExecutionRecord:
        succeeded = self.status == "succeeded"
        if succeeded != (self.artefact is not None):
            raise ValueError("an artefact reference is required for, and only for, succeeded runs")
        if (self.status == "failed") != (self.failure_category is not None):
            raise ValueError("failure_category is required for, and only for, failed runs")
        if self.status == "not_executed" and self.gpu_seconds is not None:
            raise ValueError("a run that was not executed cannot report gpu_seconds")
        return self


class FrameEvaluation(BaseModel):
    model_config = _STRICT

    frame_index: NonNegativeInt
    face_status: FaceStatus
    similarity: Similarity | None

    @model_validator(mode="after")
    def _similarity_only_for_valid_face(self) -> FrameEvaluation:
        if (self.face_status == "valid") != (self.similarity is not None):
            raise ValueError(
                "similarity must be a number for a valid face and null for every other status"
            )
        return self


class QualityEvaluation(BaseModel):
    model_config = _STRICT

    status: QualityStatus
    score: FiniteFloat | None

    @model_validator(mode="after")
    def _score_only_when_scored(self) -> QualityEvaluation:
        if (self.status == "scored") != (self.score is not None):
            raise ValueError("score must be a number when scored and null for every other status")
        return self


NOT_EXECUTED: Final = ExecutionRecord(
    status="not_executed", artefact=None, failure_category=None, gpu_seconds=None
)
QUALITY_NOT_EVALUATED: Final = QualityEvaluation(status="not_evaluated", score=None)


def frames_with_status(
    frame_indices: Sequence[int], status: FaceStatus
) -> tuple[FrameEvaluation, ...]:
    """Frame evaluations for a non-``valid`` status (no similarity) at every declared index."""
    return tuple(
        FrameEvaluation(frame_index=index, face_status=status, similarity=None)
        for index in frame_indices
    )


def _strictly_increasing(values: Sequence[int]) -> bool:
    return all(b > a for a, b in itertools.pairwise(values))


class RunResult(BaseModel):
    """Outcome of one planned run. Linked to the plan by run id, group and ordinal indices."""

    model_config = _STRICT

    run_id: RunId
    group_index: PositiveInt
    identity_index: PositiveInt
    prompt_index: PositiveInt
    seed: Seed
    variant: VariantCode
    clip_conditioning: ConditioningCode
    vae_first_frame_conditioning: ConditioningCode
    execution: ExecutionRecord
    frames: Annotated[tuple[FrameEvaluation, ...], Field(min_length=1)]
    quality: QualityEvaluation

    @model_validator(mode="after")
    def _consistent(self) -> RunResult:
        expected = VARIANT_CONDITIONING[Variant(self.variant)]
        if (self.clip_conditioning, self.vae_first_frame_conditioning) != tuple(expected):
            raise ValueError(f"conditioning does not match the protocol for variant {self.variant}")
        if not self.run_id.endswith(f"-G{self.group_index:04d}-{self.variant}"):
            raise ValueError("run_id does not match group_index and variant")
        if not _strictly_increasing([frame.frame_index for frame in self.frames]):
            raise ValueError("frame indices must be strictly increasing")
        if self.execution.status != "succeeded" and (
            any(frame.face_status != "not_evaluated" for frame in self.frames)
            or self.quality.status != "not_evaluated"
        ):
            raise ValueError(
                "a run that did not succeed must have face and quality status not_evaluated"
            )
        return self


class ExecutorInfo(BaseModel):
    model_config = _STRICT

    name: ComponentName
    revision: ComponentName
    model_family: ComponentName
    simulated: bool


class FaceEvaluatorInfo(BaseModel):
    model_config = _STRICT

    name: ComponentName
    revision: ComponentName
    settings_sha256: Sha256Hex | None
    simulated: bool


class QualityEvaluatorInfo(BaseModel):
    model_config = _STRICT

    name: ComponentName
    revision: ComponentName
    scale_min: FiniteFloat
    scale_max: FiniteFloat
    simulated: bool

    @model_validator(mode="after")
    def _ordered_scale(self) -> QualityEvaluatorInfo:
        if not self.scale_min < self.scale_max:
            raise ValueError("scale_min must be less than scale_max")
        return self


def provenance_problems(
    *,
    protocol: str,
    simulated: bool,
    simulation_scenario: str | None,
    frame_indices_source: str,
    executor: ExecutorInfo,
    face_evaluator: FaceEvaluatorInfo,
    quality_evaluator: QualityEvaluatorInfo,
) -> list[str]:
    """Provenance rules shared by :class:`ResultSet` and the orchestrator's preflight.

    Simulated and real components may never be mixed, and the result-level ``simulated`` flag
    must equal every component's flag in both directions.
    """
    problems = []
    flags = {executor.simulated, face_evaluator.simulated, quality_evaluator.simulated}
    if len(flags) > 1:
        problems.append("simulated and non-simulated components must not be mixed")
    elif flags != {simulated}:
        problems.append("simulated must equal the simulated flag of every component")
    if simulated != (simulation_scenario is not None):
        problems.append("simulation_scenario is required for, and only for, simulated results")
    if frame_indices_source == "simulation_default" and not simulated:
        problems.append("simulation_default frame indices are only allowed for simulated results")
    expected_family = PROTOCOL_MODEL_FAMILY.get(protocol)
    if executor.model_family != expected_family:
        problems.append(f"executor model_family must be {expected_family} for protocol {protocol}")
    return problems


def frame_index_problems(frame_indices: Sequence[int], frame_count: int | None) -> list[str]:
    """Check requested frame indices: non-empty, non-negative, increasing, below frame_count."""
    problems = []
    if not frame_indices:
        problems.append("frame_indices must not be empty")
    if any(not isinstance(i, int) or isinstance(i, bool) or i < 0 for i in frame_indices):
        problems.append("frame_indices must be non-negative integers")
    elif not _strictly_increasing(frame_indices):
        problems.append("frame_indices must be strictly increasing with no duplicates")
    elif frame_count is not None and frame_indices and frame_indices[-1] >= frame_count:
        problems.append(f"frame_indices must be < frame_count ({frame_count})")
    return problems


class ResultSet(BaseModel):
    """Schema version 1.0: every planned run's outcome for one experiment."""

    model_config = _STRICT

    result_schema_version: Literal["1.0"]
    protocol: Literal["wan2.1-i2v-clip-vae-2x2"]
    simulated: bool
    simulation_scenario: ComponentName | None
    experiment_id: ExperimentId
    plan_schema_version: Literal["1.0"]
    manifest_sha256: Sha256Hex
    generation_controls_sha256: Sha256Hex
    frame_indices: Annotated[tuple[NonNegativeInt, ...], Field(min_length=1)]
    frame_indices_source: Literal["manifest", "simulation_default"]
    executor: ExecutorInfo
    face_evaluator: FaceEvaluatorInfo
    quality_evaluator: QualityEvaluatorInfo
    runs: Annotated[tuple[RunResult, ...], Field(min_length=1)]

    @field_validator("frame_indices")
    @classmethod
    def _increasing(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if not _strictly_increasing(value):
            raise ValueError("frame_indices must be strictly increasing with no duplicates")
        return value

    @model_validator(mode="after")
    def _consistent(self) -> ResultSet:
        problems = provenance_problems(
            protocol=self.protocol,
            simulated=self.simulated,
            simulation_scenario=self.simulation_scenario,
            frame_indices_source=self.frame_indices_source,
            executor=self.executor,
            face_evaluator=self.face_evaluator,
            quality_evaluator=self.quality_evaluator,
        )
        run_ids = [run.run_id for run in self.runs]
        duplicates = sorted(run_id for run_id, count in Counter(run_ids).items() if count > 1)
        if duplicates:
            problems.append(f"duplicate result record(s) for run id(s): {', '.join(duplicates)}")
        scale = (self.quality_evaluator.scale_min, self.quality_evaluator.scale_max)
        for position, run in enumerate(self.runs):
            where = f"runs.{position}"
            if not run.run_id.startswith(f"{self.experiment_id}-G"):
                problems.append(f"{where}: run_id does not belong to experiment_id")
            if tuple(frame.frame_index for frame in run.frames) != self.frame_indices:
                problems.append(f"{where}: frame indices differ from the declared frame_indices")
            score = run.quality.score
            if score is not None and not scale[0] <= score <= scale[1]:
                problems.append(f"{where}: quality score is outside the declared rubric scale")
        groups: dict[int, list[RunResult]] = {}
        for run in self.runs:
            groups.setdefault(run.group_index, []).append(run)
        for group_index, members in sorted(groups.items()):
            if sorted(run.variant for run in members) != ["A", "B", "C", "D"]:
                problems.append(f"group {group_index}: must have exactly one record per variant")
            keys = {(run.identity_index, run.prompt_index, run.seed) for run in members}
            if len(keys) > 1:
                problems.append(f"group {group_index}: identity, prompt or seed differ in group")
        if problems:
            raise ValueError("; ".join(problems))
        return self


def verify_results_against_plan(
    results: ResultSet, plan: RunPlan, manifest: ExperimentManifest | None = None
) -> None:
    """Raise :class:`ResultValidationError` unless every planned run has exactly one matching
    result record and no record is orphaned, duplicated or mismatched.

    If ``manifest`` is supplied, frame indices must come from the manifest when it declares
    them. For non-simulated results the evaluator revisions must also equal the manifest's
    declared ``face_evaluator_revision`` and ``quality_rubric_version``.
    """
    problems: list[str] = []
    if results.experiment_id != plan.experiment_id:
        problems.append("experiment_id does not match the plan")
    if results.plan_schema_version != plan.schema_version:
        problems.append("plan_schema_version does not match the plan")
    if results.manifest_sha256 != plan.manifest_sha256:
        problems.append("manifest_sha256 does not match the plan")
    if results.generation_controls_sha256 != plan.generation_controls_sha256:
        problems.append("generation_controls_sha256 does not match the plan")

    planned = {run.run_id: run for run in plan.runs}
    counts = Counter(run.run_id for run in results.runs)
    for run_id, count in sorted(counts.items()):
        if run_id not in planned:
            problems.append(f"result record {run_id} matches no planned run (orphaned)")
        elif count > 1:
            problems.append(f"planned run {run_id} has {count} result records")
    problems.extend(
        f"planned run {run_id} has no result record" for run_id in planned if run_id not in counts
    )
    for result in results.runs:
        run = planned.get(result.run_id)
        if run is None:
            continue
        expected = (
            run.group_index,
            run.identity_index,
            run.prompt_index,
            run.seed,
            run.variant.value,
            run.clip_conditioning.value,
            run.vae_first_frame_conditioning.value,
        )
        actual = (
            result.group_index,
            result.identity_index,
            result.prompt_index,
            result.seed,
            result.variant,
            result.clip_conditioning,
            result.vae_first_frame_conditioning,
        )
        if actual != expected:
            problems.append(f"result record {result.run_id} does not match its planned run")

    if manifest is not None:
        problems.extend(frame_index_problems(results.frame_indices, manifest.frame_count))
        if manifest.frame_indices is not None:
            if results.frame_indices != tuple(manifest.frame_indices):
                problems.append("frame_indices differ from the manifest")
            if results.frame_indices_source != "manifest":
                problems.append("frame_indices_source must be manifest when the manifest sets them")
        elif not results.simulated:
            problems.append("non-simulated results require frame_indices declared in the manifest")
        if not results.simulated:
            if results.face_evaluator.revision != manifest.face_evaluator_revision:
                problems.append("face evaluator revision differs from the manifest")
            if results.quality_evaluator.revision != manifest.quality_rubric_version:
                problems.append("quality evaluator revision differs from quality_rubric_version")

    if problems:
        raise ResultValidationError(problems)


_SCHEMA_NAMES: Final = frozenset(
    {
        *ResultSet.model_fields,
        *RunResult.model_fields,
        *ExecutionRecord.model_fields,
        *FrameEvaluation.model_fields,
        *QualityEvaluation.model_fields,
        *ArtefactRef.model_fields,
        *ExecutorInfo.model_fields,
        *FaceEvaluatorInfo.model_fields,
        *QualityEvaluatorInfo.model_fields,
    }
)


def validation_problems(exc: ValidationError) -> list[str]:
    """Describe result-schema validation errors without echoing input values or unknown keys."""
    problems: list[str] = []
    for error in exc.errors(include_url=False, include_input=False, include_context=False):
        location = ".".join(
            str(part) if isinstance(part, int) or part in _SCHEMA_NAMES else "<key>"
            for part in error["loc"]
        )
        if error["type"] == "extra_forbidden":
            message = "unknown key is not permitted by result schema 1.0 (key name withheld)"
        else:
            message = error["msg"].removeprefix("Value error, ")
        problem = f"{location or '<results>'}: {message}"
        if problem not in problems:
            problems.append(problem)
    return problems


def parse_result_set_json(text: str | bytes) -> ResultSet:
    """Parse and strictly validate a JSON-serialised :class:`ResultSet`."""
    if len(text) > MAX_RESULTS_BYTES:
        raise ResultValidationError([f"<results>: input exceeds {MAX_RESULTS_BYTES} bytes"])
    try:
        return ResultSet.model_validate_json(text)
    except ValidationError as exc:
        raise ResultValidationError(validation_problems(exc)) from None
