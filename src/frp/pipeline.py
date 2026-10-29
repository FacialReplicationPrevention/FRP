"""Orchestrates a verified run plan through executor and evaluator adapters into a ResultSet.

Every planned run receives exactly one result record. Adapter exceptions are recorded as
``failed`` runs or ``error`` evaluations without their messages (which could contain paths or
private data); adapter *contract* violations raise :class:`ResultValidationError`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from pydantic import ValidationError

from frp.interfaces import FaceIdentityEvaluator, RunExecutor, VideoQualityEvaluator
from frp.planner import PlannedRun, RunPlan, verify_run_plan
from frp.results import (
    NOT_EXECUTED,
    PROTOCOL_WAN21_I2V_CLIP_VAE_2X2,
    QUALITY_NOT_EVALUATED,
    RESULT_SCHEMA_VERSION,
    ArtefactRef,
    ExecutionRecord,
    FrameEvaluation,
    QualityEvaluation,
    ResultSet,
    ResultValidationError,
    RunResult,
    frames_with_status,
    validation_problems,
    verify_results_against_plan,
)


def _execute(executor: RunExecutor, run: PlannedRun) -> ExecutionRecord:
    try:
        record = executor.execute(run)
    except Exception:
        return ExecutionRecord(
            status="failed", artefact=None, failure_category="executor_error", gpu_seconds=None
        )
    if not isinstance(record, ExecutionRecord) or record.status == "not_executed":
        raise ResultValidationError(
            [f"run {run.run_id}: executor must return a succeeded or failed ExecutionRecord"]
        )
    return record


def _evaluate_faces(
    evaluator: FaceIdentityEvaluator,
    artefact: ArtefactRef,
    run: PlannedRun,
    frame_indices: tuple[int, ...],
) -> tuple[FrameEvaluation, ...]:
    try:
        frames = tuple(evaluator.evaluate(artefact, run.identity_pseudonym, frame_indices))
    except Exception:
        return frames_with_status(frame_indices, "error")
    if (
        not all(isinstance(frame, FrameEvaluation) for frame in frames)
        or tuple(frame.frame_index for frame in frames) != frame_indices
    ):
        raise ResultValidationError(
            [f"run {run.run_id}: face evaluator must return one evaluation per requested frame"]
        )
    return frames


def _evaluate_quality(
    evaluator: VideoQualityEvaluator, artefact: ArtefactRef, run: PlannedRun
) -> QualityEvaluation:
    try:
        quality = evaluator.evaluate(artefact)
    except Exception:
        return QualityEvaluation(status="error", score=None)
    if not isinstance(quality, QualityEvaluation):
        raise ResultValidationError(
            [f"run {run.run_id}: quality evaluator must return a QualityEvaluation"]
        )
    return quality


def execute_plan(
    plan: RunPlan,
    executor: RunExecutor,
    face_evaluator: FaceIdentityEvaluator,
    quality_evaluator: VideoQualityEvaluator,
    *,
    frame_indices: Sequence[int],
    frame_indices_source: Literal["manifest", "simulation_default"],
    simulation_scenario: str | None = None,
    max_runs: int | None = None,
) -> ResultSet:
    """Run every planned run in plan order and return validated result records.

    ``max_runs`` stops execution after that many runs (simulating an interrupted experiment);
    the remaining runs are recorded as ``not_executed`` rather than dropped.
    """
    verify_run_plan(plan)
    if max_runs is not None and max_runs < 0:
        raise ValueError("max_runs must be >= 0")
    indices = tuple(frame_indices)
    results = []
    for position, run in enumerate(plan.runs):
        if max_runs is not None and position >= max_runs:
            execution = NOT_EXECUTED
        else:
            execution = _execute(executor, run)
        if execution.artefact is not None:
            frames = _evaluate_faces(face_evaluator, execution.artefact, run, indices)
            quality = _evaluate_quality(quality_evaluator, execution.artefact, run)
        else:
            frames = frames_with_status(indices, "not_evaluated")
            quality = QUALITY_NOT_EVALUATED
        results.append(
            RunResult(
                run_id=run.run_id,
                group_index=run.group_index,
                identity_index=run.identity_index,
                prompt_index=run.prompt_index,
                seed=run.seed,
                variant=run.variant.value,
                clip_conditioning=run.clip_conditioning.value,
                vae_first_frame_conditioning=run.vae_first_frame_conditioning.value,
                execution=execution,
                frames=frames,
                quality=quality,
            )
        )
    components = (executor.info, face_evaluator.info, quality_evaluator.info)
    try:
        result_set = _build_result_set(
            plan,
            executor,
            face_evaluator,
            quality_evaluator,
            results,
            simulated=any(component.simulated for component in components),
            simulation_scenario=simulation_scenario,
            frame_indices=indices,
            frame_indices_source=frame_indices_source,
        )
    except ValidationError as exc:
        raise ResultValidationError(validation_problems(exc)) from None
    verify_results_against_plan(result_set, plan)
    return result_set


def _build_result_set(
    plan: RunPlan,
    executor: RunExecutor,
    face_evaluator: FaceIdentityEvaluator,
    quality_evaluator: VideoQualityEvaluator,
    results: list[RunResult],
    *,
    simulated: bool,
    simulation_scenario: str | None,
    frame_indices: tuple[int, ...],
    frame_indices_source: Literal["manifest", "simulation_default"],
) -> ResultSet:
    return ResultSet(
        result_schema_version=RESULT_SCHEMA_VERSION,
        protocol=PROTOCOL_WAN21_I2V_CLIP_VAE_2X2,
        simulated=simulated,
        simulation_scenario=simulation_scenario,
        experiment_id=plan.experiment_id,
        plan_schema_version=plan.schema_version,
        manifest_sha256=plan.manifest_sha256,
        generation_controls_sha256=plan.generation_controls_sha256,
        frame_indices=frame_indices,
        frame_indices_source=frame_indices_source,
        executor=executor.info,
        face_evaluator=face_evaluator.info,
        quality_evaluator=quality_evaluator.info,
        runs=tuple(results),
    )
