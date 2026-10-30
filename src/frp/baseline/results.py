"""Versioned, strictly validated result records for the Wan 2.1 baseline (``baseline-0.1-draft``).

A **new** result-set type: it does not extend or accept :class:`frp.results.ResultSet`, whose
protocol literal, variant pairing and run ids are specific to the A/B/C/D ablation. Immutable
building blocks that carry no variant semantics are reused unchanged: ``ExecutionRecord``,
``ArtefactRef``, ``FrameEvaluation``, ``QualityEvaluation`` and the component info types.

Accounting rules (see Experiment 003, section 4):

* **Every attempt is recorded**, including failures, and an attempt is never overwritten: a retry
  is a new ``attempt_index`` with a new artefact reference.
* **Attempts, execution failures and unexecuted runs are separate.** An attempt starts when the
  backend is asked to generate; a failed attempt is an execution failure with a category. A run
  that was refused or stopped before any attempt is an ``UnexecutedRun`` with a reason.
* A similarity exists only for a ``valid`` face evaluation, and nothing is ever imputed.
* Records hold ordinal indices, never pseudonyms, prompt text, media, embeddings or paths.

A result set from a mock/CPU backend is marked ``simulated`` and is **not** a Wan 2.1 inference
result; only ``simulated: false`` from a verified, authorised live execution could be one.
"""

from __future__ import annotations

import itertools
from collections import Counter
from collections.abc import Sequence
from typing import Annotated, Final, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

from frp.baseline.manifest import BaselineManifest, format_validation_error
from frp.baseline.planner import BaselinePlan
from frp.baseline.protocol import (
    BASELINE_MODEL_FAMILY,
    BASELINE_SCHEMA_VERSION,
    PROTOCOL_WAN21_I2V_BASELINE,
    ROLE_CLAIMS,
    RunRole,
)
from frp.manifest import ExperimentId, GitSha, Seed, Sha256Hex
from frp.results import (
    ArtefactRef,
    ComponentName,
    ExecutionRecord,
    ExecutorInfo,
    FaceEvaluatorInfo,
    FailureCategory,
    FrameEvaluation,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveInt,
    QualityEvaluation,
    QualityEvaluatorInfo,
    frame_index_problems,
)

BASELINE_RESULT_SCHEMA_VERSION: Final = BASELINE_SCHEMA_VERSION
MAX_BASELINE_RESULTS_BYTES: Final = 16_777_216

BaselineRunId = Annotated[str, StringConstraints(pattern=r"^[A-Z0-9][A-Z0-9-]{2,63}-R[0-9]{4,}$")]

# Finer than FailureCategory (which is reused unchanged); each maps to exactly one category.
FailureDetail = Literal[
    "model_load_error",
    "generation_error",
    "timeout",
    "resource_exhausted",
    "budget_stop",
    "operator_abort",
    "remote_call_blocked",
    "prohibited_module_loaded",
    "conditioning_contract_violation",
    "output_contract_violation",
]
FAILURE_CATEGORY_FOR_DETAIL: Final[dict[str, FailureCategory]] = {
    "model_load_error": "executor_error",
    "generation_error": "executor_error",
    "timeout": "timeout",
    "resource_exhausted": "resource_exhausted",
    "budget_stop": "other",
    "operator_abort": "other",
    "remote_call_blocked": "executor_error",
    "prohibited_module_loaded": "executor_error",
    "conditioning_contract_violation": "executor_error",
    "output_contract_violation": "executor_error",
}
# A retry may help only for transient resource or runtime failures; any other failure halts.
RETRYABLE_DETAILS: Final = frozenset({"timeout", "resource_exhausted", "generation_error"})

# Why a run has no attempt: refused before any model load or generation, or stopped.
RefusalReason = Literal[
    "not_execution_ready",
    "not_authorised",
    "live_execution_disabled",
    "backend_unavailable",
    "provenance_mismatch",
    "weights_verification_failed",
    "prohibited_module_loaded",
    "invalid_input",
]
UnexecutedReason = Literal[
    "not_execution_ready",
    "not_authorised",
    "live_execution_disabled",
    "backend_unavailable",
    "provenance_mismatch",
    "weights_verification_failed",
    "prohibited_module_loaded",
    "invalid_input",
    "budget_stop",
    "operator_abort",
    "cleanup_failed",
    "halted_after_failure",
]
StopReason = UnexecutedReason

_STRICT: Final = ConfigDict(strict=True, extra="forbid", frozen=True)
SimulationLabel = ComponentName


class TensorMeta(BaseModel):
    """Shape, dtype and device of a tensor. Never its contents."""

    model_config = _STRICT

    shape: tuple[NonNegativeInt, ...]
    dtype: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9._]{1,32}$")]
    device: Annotated[str, StringConstraints(pattern=r"^[a-z]{1,16}(:[0-9]{1,3})?$")]


class ConditioningSummary(BaseModel):
    """Branching metadata verified for one successful attempt (no pixels, latents or embeddings).

    The reference token itself is never recorded (it could identify a person); only that both
    routes saw the request's one reference. The record cannot be built unless that holds, the
    CLIP route's output is what the denoiser received, and the positive and negative
    classifier-free-guidance branches received identical image conditioning.
    """

    model_config = _STRICT

    same_reference_on_both_routes: bool
    clip_features: TensorMeta
    vae_first_frame_condition: TensorMeta
    positive_branch_calls: PositiveInt
    negative_branch_calls: PositiveInt
    branches_share_image_conditioning: bool
    clip_route_feeds_denoiser: bool

    @model_validator(mode="after")
    def _consistent(self) -> ConditioningSummary:
        if not self.same_reference_on_both_routes:
            raise ValueError("CLIP and VAE routes must receive the same reference")
        if self.positive_branch_calls != self.negative_branch_calls:
            raise ValueError("positive and negative branch call counts must be equal")
        if not (self.branches_share_image_conditioning and self.clip_route_feeds_denoiser):
            raise ValueError("conditioning checks must all have passed")
        return self


class BaselineAttempt(BaseModel):
    """One attempt to generate one planned run. Immutable; a retry is a new attempt."""

    model_config = _STRICT

    run_id: BaselineRunId
    attempt_index: PositiveInt
    run_role: RunRole
    identity_index: PositiveInt
    prompt_index: PositiveInt
    seed: Seed
    generation_controls_sha256: Sha256Hex
    started_at: AwareDatetime
    finished_at: AwareDatetime
    wall_seconds: NonNegativeFloat
    execution: ExecutionRecord
    failure_detail: FailureDetail | None
    conditioning: ConditioningSummary | None
    cleanup_ok: bool
    frames: Annotated[tuple[FrameEvaluation, ...], Field(min_length=1)]
    quality: QualityEvaluation

    @model_validator(mode="after")
    def _consistent(self) -> BaselineAttempt:
        status = self.execution.status
        if status == "not_executed":
            raise ValueError("an attempt is succeeded or failed; unexecuted runs are separate")
        if (status == "failed") != (self.failure_detail is not None):
            raise ValueError("failure_detail is required for, and only for, failed attempts")
        if (
            self.failure_detail is not None
            and FAILURE_CATEGORY_FOR_DETAIL[self.failure_detail] != self.execution.failure_category
        ):
            raise ValueError("failure_detail does not match failure_category")
        if (status == "succeeded") != (self.conditioning is not None):
            raise ValueError("conditioning metadata is required for, and only for, succeeded runs")
        if self.finished_at < self.started_at:
            raise ValueError("finished_at precedes started_at")
        indices = [frame.frame_index for frame in self.frames]
        if any(b <= a for a, b in itertools.pairwise(indices)):
            raise ValueError("frame indices must be strictly increasing")
        unevaluated = all(f.face_status == "not_evaluated" for f in self.frames) and (
            self.quality.status == "not_evaluated"
        )
        if (status != "succeeded" or self.run_role == "smoke") and not unevaluated:
            raise ValueError(
                "failed attempts, and every smoke attempt, must have face and quality status "
                "not_evaluated"
            )
        return self


class UnexecutedRun(BaseModel):
    """A planned run with no attempt: refused before generation, or not reached after a stop."""

    model_config = _STRICT

    run_id: BaselineRunId
    reason: UnexecutedReason


class ExecutionProvenance(BaseModel):
    """What the executor verified locally before loading anything (no paths, no file names)."""

    model_config = _STRICT

    source_commit: GitSha
    checkpoint_revision: GitSha
    weight_files_sha256: Sha256Hex
    environment_sha256: Sha256Hex
    verified_before_load: bool


class BaselineResultSet(BaseModel):
    """Every planned run's accounting for one baseline experiment: attempts and unexecuted runs."""

    model_config = _STRICT

    result_schema_version: Literal["baseline-0.1-draft"]
    protocol: Literal["wan2.1-i2v-baseline"]
    run_role: RunRole
    claim_scope: str
    simulated: bool
    simulation_scenario: SimulationLabel | None
    experiment_id: ExperimentId
    plan_schema_version: Literal["baseline-0.1-draft"]
    manifest_sha256: Sha256Hex
    generation_controls_sha256: Sha256Hex
    frame_indices: Annotated[tuple[NonNegativeInt, ...], Field(min_length=1)]
    executor: ExecutorInfo
    face_evaluator: FaceEvaluatorInfo | None
    quality_evaluator: QualityEvaluatorInfo | None
    provenance: ExecutionProvenance | None
    stop_reason: StopReason | None
    attempts: tuple[BaselineAttempt, ...]
    unexecuted: tuple[UnexecutedRun, ...]

    @model_validator(mode="after")
    def _consistent(self) -> BaselineResultSet:
        problems = []
        if self.claim_scope != ROLE_CLAIMS[self.run_role].claim_scope:
            problems.append("claim_scope does not match the run role")
        flags = {self.executor.simulated}
        flags |= {e.simulated for e in (self.face_evaluator, self.quality_evaluator) if e}
        if flags != {self.simulated}:
            problems.append("simulated must equal the simulated flag of every component")
        if self.simulated != (self.simulation_scenario is not None):
            problems.append("simulation_scenario is required for, and only for, simulated results")
        if self.executor.model_family != BASELINE_MODEL_FAMILY:
            problems.append(f"executor model_family must be {BASELINE_MODEL_FAMILY}")
        if (
            not self.simulated
            and self.attempts
            and (self.provenance is None or not self.provenance.verified_before_load)
        ):
            problems.append("non-simulated attempts require provenance verified before load")
        if (self.face_evaluator is None) != (self.quality_evaluator is None):
            problems.append("face and quality evaluators are supplied together or not at all")
        scale = (
            (self.quality_evaluator.scale_min, self.quality_evaluator.scale_max)
            if self.quality_evaluator
            else None
        )
        per_run: dict[str, list[BaselineAttempt]] = {}
        for position, attempt in enumerate(self.attempts):
            where = f"attempts.{position}"
            per_run.setdefault(attempt.run_id, []).append(attempt)
            if not attempt.run_id.startswith(f"{self.experiment_id}-R"):
                problems.append(f"{where}: run_id does not belong to experiment_id")
            if attempt.run_role != self.run_role:
                problems.append(f"{where}: run_role differs from the result set")
            if attempt.generation_controls_sha256 != self.generation_controls_sha256:
                problems.append(f"{where}: generation controls differ from the result set")
            if tuple(f.frame_index for f in attempt.frames) != self.frame_indices:
                problems.append(f"{where}: frame indices differ from the declared frame_indices")
            score = attempt.quality.score
            if score is not None and (scale is None or not scale[0] <= score <= scale[1]):
                problems.append(f"{where}: quality score is outside the declared rubric scale")
            if self.face_evaluator is None and (
                any(f.face_status != "not_evaluated" for f in attempt.frames)
                or attempt.quality.status != "not_evaluated"
            ):
                problems.append(f"{where}: evaluated without a declared evaluator")
        for run_id, attempts in per_run.items():
            if [a.attempt_index for a in attempts] != list(range(1, len(attempts) + 1)):
                problems.append(f"run {run_id}: attempt indices must be 1..n in order")
            succeeded = [a for a in attempts if a.execution.status == "succeeded"]
            if len(succeeded) > 1 or (succeeded and attempts[-1] is not succeeded[0]):
                problems.append(f"run {run_id}: a succeeded attempt must be the last and only one")
        uris = [a.execution.artefact.uri for a in self.attempts if a.execution.artefact is not None]
        if len(set(uris)) != len(uris):
            problems.append("two attempts share an artefact reference (overwrite risk)")
        unexecuted_ids = [u.run_id for u in self.unexecuted]
        if duplicates := sorted(r for r, c in Counter(unexecuted_ids).items() if c > 1):
            problems.append(f"duplicate unexecuted record(s): {', '.join(duplicates)}")
        if overlap := sorted(set(unexecuted_ids) & set(per_run)):
            problems.append(f"run(s) both attempted and unexecuted: {', '.join(overlap)}")
        if problems:
            raise ValueError("; ".join(problems))
        return self

    def accounting(self) -> dict[str, int | dict[str, int]]:
        """Counts only: planned attempts, failures by detail and unexecuted runs by reason."""
        runs_with_success = {a.run_id for a in self.attempts if a.execution.status == "succeeded"}
        failures = Counter(a.failure_detail for a in self.attempts if a.failure_detail)
        return {
            "attempts": len(self.attempts),
            "runs_attempted": len({a.run_id for a in self.attempts}),
            "runs_succeeded": len(runs_with_success),
            "failed_attempts": sum(failures.values()),
            "failed_attempts_by_detail": dict(sorted(failures.items())),
            "runs_unexecuted": len(self.unexecuted),
            "runs_unexecuted_by_reason": dict(
                sorted(Counter(u.reason for u in self.unexecuted).items())
            ),
        }


class BaselineResultValidationError(Exception):
    """Raised when baseline results are invalid or do not match their plan (values never echoed)."""

    def __init__(self, problems: Sequence[str]) -> None:
        self.problems = tuple(problems)
        super().__init__("; ".join(self.problems))


def verify_baseline_results_against_plan(
    results: BaselineResultSet, plan: BaselinePlan, manifest: BaselineManifest | None = None
) -> None:
    """Raise unless every planned run is accounted for exactly once and nothing is orphaned.

    Accounted means: attempted (one or more attempts) **or** listed as unexecuted, never both and
    never neither. With ``manifest``, frame indices must be the manifest's and below its frame
    count, and non-simulated results must declare the manifest's evaluator revisions.
    """
    problems: list[str] = []
    for name, got, want in (
        ("experiment_id", results.experiment_id, plan.experiment_id),
        ("run_role", results.run_role, plan.run_role),
        ("manifest_sha256", results.manifest_sha256, plan.manifest_sha256),
        (
            "generation_controls_sha256",
            results.generation_controls_sha256,
            plan.generation_controls_sha256,
        ),
    ):
        if got != want:
            problems.append(f"{name} does not match the plan")
    planned = {run.run_id: run for run in plan.runs}
    attempted = {a.run_id for a in results.attempts}
    listed = {u.run_id for u in results.unexecuted}
    for run_id in sorted((attempted | listed) - planned.keys()):
        problems.append(f"record for {run_id} matches no planned run (orphaned)")
    problems.extend(
        f"planned run {run_id} is neither attempted nor listed as unexecuted"
        for run_id in planned
        if run_id not in attempted and run_id not in listed
    )
    for attempt in results.attempts:
        run = planned.get(attempt.run_id)
        if run is None:
            continue
        expected = (run.identity_index, run.prompt_index, run.seed, run.run_role)
        actual = (attempt.identity_index, attempt.prompt_index, attempt.seed, attempt.run_role)
        if actual != expected:
            problems.append(f"attempt for {attempt.run_id} does not match its planned run")
    if manifest is not None:
        problems.extend(frame_index_problems(results.frame_indices, manifest.frame_count))
        if manifest.frame_indices is not None and results.frame_indices != tuple(
            manifest.frame_indices
        ):
            problems.append("frame_indices differ from the manifest")
        if manifest.frame_indices is None:
            problems.append("results require frame_indices declared in the manifest")
        if (
            not results.simulated
            and results.face_evaluator is not None
            and results.face_evaluator.revision != manifest.face_evaluator_revision
        ):
            problems.append("face evaluator revision differs from the manifest")
    if problems:
        raise BaselineResultValidationError(problems)


_SCHEMA_NAMES: Final = frozenset(
    {
        *BaselineResultSet.model_fields,
        *BaselineAttempt.model_fields,
        *UnexecutedRun.model_fields,
        *ExecutionProvenance.model_fields,
        *ConditioningSummary.model_fields,
        *TensorMeta.model_fields,
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
    return format_validation_error(exc, _SCHEMA_NAMES, root="<results>")


def parse_baseline_result_set_json(text: str | bytes) -> BaselineResultSet:
    """Parse and strictly validate a JSON-serialised :class:`BaselineResultSet`."""
    if len(text) > MAX_BASELINE_RESULTS_BYTES:
        raise BaselineResultValidationError(
            [f"<results>: input exceeds {MAX_BASELINE_RESULTS_BYTES} bytes"]
        )
    try:
        return BaselineResultSet.model_validate_json(text)
    except ValidationError as exc:
        raise BaselineResultValidationError(validation_problems(exc)) from None


__all__ = [
    "BASELINE_RESULT_SCHEMA_VERSION",
    "FAILURE_CATEGORY_FOR_DETAIL",
    "PROTOCOL_WAN21_I2V_BASELINE",
    "RETRYABLE_DETAILS",
    "BaselineAttempt",
    "BaselineResultSet",
    "BaselineResultValidationError",
    "ConditioningSummary",
    "ExecutionProvenance",
    "FailureDetail",
    "RefusalReason",
    "TensorMeta",
    "UnexecutedReason",
    "UnexecutedRun",
    "parse_baseline_result_set_json",
    "verify_baseline_results_against_plan",
]
