"""Runs a verified baseline plan through a :class:`BaselineExecutor` and accounts for every run.

Every planned run ends up either **attempted** (one or more attempts, each recorded, never
overwritten) or **unexecuted** with a reason; none is dropped. Policy:

* A failed attempt is retried (a new attempt index and artefact) only for transient failures in
  :data:`~frp.baseline.results.RETRYABLE_DETAILS` and only up to ``max_attempts``. Which attempt
  counts for analysis is an open design decision (Experiment 003, section 7); all are kept.
* Any other failure, a stop signal (budget or operator), failed cleanup or a refusal that is not
  specific to one run **halts** the plan: the remaining runs are recorded as unexecuted and the
  result set carries a ``stop_reason``. A per-run ``invalid_input`` refusal skips only that run.
* ``KeyboardInterrupt`` raised inside an attempt is converted to ``operator_abort`` by the
  executor, so the partial accounting is returned rather than lost.
* Optional evaluators run only on succeeded attempts. Without them every evaluation is
  ``not_evaluated``; no score is ever imputed.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import ValidationError

from frp.baseline.backend import StopSignal
from frp.baseline.interfaces import BaselineExecutionOutcome, BaselineExecutor, ExecutionRefused
from frp.baseline.manifest import BaselineManifest
from frp.baseline.planner import BaselinePlan, BaselinePlannedRun, verify_baseline_plan
from frp.baseline.protocol import (
    BASELINE_SCHEMA_VERSION,
    PROTOCOL_WAN21_I2V_BASELINE,
    ROLE_CLAIMS,
)
from frp.baseline.results import (
    RETRYABLE_DETAILS,
    BaselineAttempt,
    BaselineResultSet,
    BaselineResultValidationError,
    StopReason,
    UnexecutedReason,
    UnexecutedRun,
    validation_problems,
    verify_baseline_results_against_plan,
)
from frp.interfaces import FaceIdentityEvaluator, VideoQualityEvaluator
from frp.results import (
    QUALITY_NOT_EVALUATED,
    ArtefactRef,
    FrameEvaluation,
    QualityEvaluation,
    frame_index_problems,
    frames_with_status,
)

DEFAULT_MAX_ATTEMPTS = 1
MAX_ATTEMPTS_LIMIT = 5


def _evaluate(
    attempt_artefact: ArtefactRef,
    run: BaselinePlannedRun,
    frame_indices: tuple[int, ...],
    face_evaluator: FaceIdentityEvaluator | None,
    quality_evaluator: VideoQualityEvaluator | None,
) -> tuple[tuple[FrameEvaluation, ...], QualityEvaluation]:
    if face_evaluator is None or quality_evaluator is None or run.run_role == "smoke":
        return frames_with_status(frame_indices, "not_evaluated"), QUALITY_NOT_EVALUATED
    try:
        frames = tuple(
            face_evaluator.evaluate(attempt_artefact, run.identity_pseudonym, frame_indices)
        )
    except Exception:
        frames = frames_with_status(frame_indices, "error")
    if (
        not all(isinstance(f, FrameEvaluation) for f in frames)
        or tuple(f.frame_index for f in frames) != frame_indices
    ):
        raise BaselineResultValidationError(
            [f"run {run.run_id}: face evaluator must return one evaluation per requested frame"]
        )
    try:
        quality = quality_evaluator.evaluate(attempt_artefact)
    except Exception:
        quality = QualityEvaluation(status="error", score=None)
    if not isinstance(quality, QualityEvaluation):
        raise BaselineResultValidationError(
            [f"run {run.run_id}: quality evaluator must return a QualityEvaluation"]
        )
    return frames, quality


def _attempt_record(
    run: BaselinePlannedRun,
    attempt_index: int,
    outcome: BaselineExecutionOutcome,
    frames: tuple[FrameEvaluation, ...],
    quality: QualityEvaluation,
) -> BaselineAttempt:
    return BaselineAttempt(
        run_id=run.run_id,
        attempt_index=attempt_index,
        run_role=run.run_role,
        identity_index=run.identity_index,
        prompt_index=run.prompt_index,
        seed=run.seed,
        generation_controls_sha256=run.generation_controls_sha256,
        started_at=outcome.started_at,
        finished_at=outcome.finished_at,
        wall_seconds=outcome.wall_seconds,
        execution=outcome.execution,
        failure_detail=outcome.failure_detail,
        conditioning=outcome.conditioning,
        cleanup_ok=outcome.cleanup_ok,
        frames=frames,
        quality=quality,
    )


def _process_run(
    run: BaselinePlannedRun,
    executor: BaselineExecutor,
    indices: tuple[int, ...],
    face_evaluator: FaceIdentityEvaluator | None,
    quality_evaluator: VideoQualityEvaluator | None,
    stop: StopSignal | None,
    max_attempts: int,
) -> tuple[list[BaselineAttempt], UnexecutedRun | None, UnexecutedReason | None]:
    """Attempt one run with bounded retries. Returns (attempts, unexecuted record, halt reason)."""
    attempts: list[BaselineAttempt] = []
    for attempt_index in range(1, max_attempts + 1):
        try:
            outcome = executor.execute(run, attempt_index)
        except ExecutionRefused as refusal:
            unexecuted = None if attempts else UnexecutedRun(run_id=run.run_id, reason=refusal.code)
            run_specific = refusal.code == "invalid_input" and not attempts
            return attempts, unexecuted, None if run_specific else refusal.code
        artefact = outcome.execution.artefact
        if artefact is not None:
            frames, quality = _evaluate(artefact, run, indices, face_evaluator, quality_evaluator)
        else:
            frames, quality = frames_with_status(indices, "not_evaluated"), QUALITY_NOT_EVALUATED
        attempts.append(_attempt_record(run, attempt_index, outcome, frames, quality))
        if not outcome.cleanup_ok:
            return attempts, None, "cleanup_failed"
        if outcome.execution.status == "succeeded":
            return attempts, None, None
        detail = outcome.failure_detail
        if detail not in RETRYABLE_DETAILS:
            halt = detail if detail in ("budget_stop", "operator_abort") else "halted_after_failure"
            return attempts, None, halt
        if stop is not None and (signalled := stop.reason()) is not None:
            return attempts, None, signalled
    return attempts, None, None


def execute_baseline_plan(
    plan: BaselinePlan,
    executor: BaselineExecutor,
    *,
    frame_indices: Sequence[int],
    frame_count: int | None = None,
    manifest: BaselineManifest | None = None,
    face_evaluator: FaceIdentityEvaluator | None = None,
    quality_evaluator: VideoQualityEvaluator | None = None,
    stop: StopSignal | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    simulation_scenario: str | None = None,
) -> BaselineResultSet:
    """Execute ``plan`` in order and return the validated, fully accounted result set.

    Raises :class:`BaselineResultValidationError` on an adapter *contract* violation (for example
    an evaluator returning the wrong frames) or inconsistent provenance. ``simulation_scenario``
    is required for, and only for, a non-live (mock) executor.
    """
    verify_baseline_plan(plan, manifest)
    if not 1 <= max_attempts <= MAX_ATTEMPTS_LIMIT:
        raise ValueError(f"max_attempts must be between 1 and {MAX_ATTEMPTS_LIMIT}")
    indices = tuple(frame_indices)
    if problems := frame_index_problems(indices, frame_count):
        raise BaselineResultValidationError(problems)

    attempts: list[BaselineAttempt] = []
    unexecuted: list[UnexecutedRun] = []
    stop_reason: StopReason | None = None
    for position, run in enumerate(plan.runs):
        halt: UnexecutedReason | None = None
        if stop is not None and (signalled := stop.reason()) is not None:
            halt, run_attempts, skipped = signalled, [], None
        else:
            run_attempts, skipped, halt = _process_run(
                run, executor, indices, face_evaluator, quality_evaluator, stop, max_attempts
            )
        attempts.extend(run_attempts)
        if skipped is not None:
            unexecuted.append(skipped)
        if halt is not None:
            stop_reason = halt
            first_unreached = position + (0 if not run_attempts and skipped is None else 1)
            unexecuted.extend(
                UnexecutedRun(run_id=r.run_id, reason=halt) for r in plan.runs[first_unreached:]
            )
            break

    return _build_result_set(
        plan,
        executor,
        attempts,
        unexecuted,
        stop_reason,
        indices,
        simulation_scenario,
        face_evaluator,
        quality_evaluator,
        manifest,
    )


def _build_result_set(
    plan: BaselinePlan,
    executor: BaselineExecutor,
    attempts: list[BaselineAttempt],
    unexecuted: list[UnexecutedRun],
    stop_reason: StopReason | None,
    indices: tuple[int, ...],
    simulation_scenario: str | None,
    face_evaluator: FaceIdentityEvaluator | None,
    quality_evaluator: VideoQualityEvaluator | None,
    manifest: BaselineManifest | None,
) -> BaselineResultSet:
    try:
        results = BaselineResultSet(
            result_schema_version=BASELINE_SCHEMA_VERSION,
            protocol=PROTOCOL_WAN21_I2V_BASELINE,
            run_role=plan.run_role,
            claim_scope=ROLE_CLAIMS[plan.run_role].claim_scope,
            simulated=executor.info.simulated,
            simulation_scenario=simulation_scenario,
            experiment_id=plan.experiment_id,
            plan_schema_version=plan.schema_version,
            manifest_sha256=plan.manifest_sha256,
            generation_controls_sha256=plan.generation_controls_sha256,
            frame_indices=indices,
            executor=executor.info,
            face_evaluator=face_evaluator.info if face_evaluator and quality_evaluator else None,
            quality_evaluator=(
                quality_evaluator.info if face_evaluator and quality_evaluator else None
            ),
            provenance=executor.verified_provenance,
            stop_reason=stop_reason,
            attempts=tuple(attempts),
            unexecuted=tuple(unexecuted),
        )
    except ValidationError as exc:
        raise BaselineResultValidationError(validation_problems(exc)) from None
    verify_baseline_results_against_plan(results, plan, manifest)
    return results
