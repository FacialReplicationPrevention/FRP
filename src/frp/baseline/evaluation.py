"""Post-hoc evaluation of a baseline result set with the reusable evaluator contracts.

Generation (on an approved GPU) and evaluation (in an approved private environment) need not
happen in the same process. :func:`evaluate_baseline_results` takes an **unevaluated**
:class:`~frp.baseline.results.BaselineResultSet` and returns a *new*, validated result set in
which every succeeded attempt carries the evaluators' outputs. The input is immutable and is never
modified, so the unevaluated record remains available alongside the evaluated one.

Rules (Experiment 003, sections 4-5):

* Only succeeded attempts are evaluated. Failed attempts and unexecuted runs are carried over
  unchanged with ``not_evaluated`` statuses; nothing is dropped.
* ``smoke`` results are never evaluated (technical claims only).
* A result set that already declares evaluators is refused rather than overwritten.
* Simulated evaluators can never be applied to non-simulated results, nor the reverse, so a mock
  score is never substituted for a real evaluator's result.
* Evaluator exceptions become ``error`` statuses without their messages; a contract violation
  (wrong frames, wrong type) raises.
"""

from __future__ import annotations

from pydantic import ValidationError

from frp.baseline.manifest import BaselineManifest
from frp.baseline.orchestrator import _evaluate
from frp.baseline.planner import BaselinePlan
from frp.baseline.results import (
    BaselineAttempt,
    BaselineResultSet,
    BaselineResultValidationError,
    validation_problems,
    verify_baseline_results_against_plan,
)
from frp.interfaces import FaceIdentityEvaluator, VideoQualityEvaluator


def evaluate_baseline_results(
    results: BaselineResultSet,
    plan: BaselinePlan,
    *,
    face_evaluator: FaceIdentityEvaluator,
    quality_evaluator: VideoQualityEvaluator,
    manifest: BaselineManifest | None = None,
) -> BaselineResultSet:
    """Evaluate every succeeded attempt of ``results`` and return a new validated result set."""
    verify_baseline_results_against_plan(results, plan, manifest)
    problems = []
    if results.face_evaluator is not None or results.quality_evaluator is not None:
        problems.append("results already carry evaluations and are never re-evaluated in place")
    if results.run_role == "smoke":
        problems.append("smoke results are never evaluated for similarity or quality")
    if {face_evaluator.info.simulated, quality_evaluator.info.simulated} != {results.simulated}:
        problems.append(
            "evaluator simulated flags must equal the results' simulated flag "
            "(mock scores are never substituted for real evaluator results)"
        )
    if problems:
        raise BaselineResultValidationError(problems)

    planned = {run.run_id: run for run in plan.runs}
    attempts = []
    for attempt in results.attempts:
        artefact = attempt.execution.artefact
        if attempt.execution.status == "succeeded" and artefact is not None:
            frames, quality = _evaluate(
                artefact,
                planned[attempt.run_id],
                results.frame_indices,
                face_evaluator,
                quality_evaluator,
            )
            attempt = BaselineAttempt(**{**dict(attempt), "frames": frames, "quality": quality})
        attempts.append(attempt)
    try:
        evaluated = BaselineResultSet(
            **{
                **dict(results),
                "face_evaluator": face_evaluator.info,
                "quality_evaluator": quality_evaluator.info,
                "attempts": tuple(attempts),
            }
        )
    except ValidationError as exc:
        raise BaselineResultValidationError(validation_problems(exc)) from None
    verify_baseline_results_against_plan(evaluated, plan, manifest)
    return evaluated


__all__ = ["evaluate_baseline_results"]
