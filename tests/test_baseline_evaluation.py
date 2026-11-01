"""Baseline post-hoc evaluation and descriptive aggregation on synthetic, non-biometric records."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import pytest

from frp.aggregation import Interval
from frp.baseline.aggregation import aggregate_baseline, summarise_attempt
from frp.baseline.evaluation import evaluate_baseline_results
from frp.baseline.manifest import parse_baseline_manifest
from frp.baseline.planner import BaselinePlan, generate_baseline_plan
from frp.baseline.results import (
    BaselineResultSet,
    BaselineResultValidationError,
    parse_baseline_result_set_json,
)
from frp.results import (
    ArtefactRef,
    FaceEvaluatorInfo,
    FaceStatus,
    FrameEvaluation,
    QualityEvaluation,
    QualityEvaluatorInfo,
)
from frp.review.demo import (
    DemoFaceEvaluator,
    DemoQualityEvaluator,
    demo_manifest,
    demo_unevaluated_results,
)

SHA = "a" * 64
GIT = "b" * 40


@pytest.fixture
def plan() -> BaselinePlan:
    return generate_baseline_plan(demo_manifest())


@pytest.fixture
def unevaluated(plan: BaselinePlan) -> BaselineResultSet:
    return demo_unevaluated_results(plan)


class PatternFace:
    """Synthetic evaluator: one fixed status/similarity pattern for every artefact."""

    def __init__(
        self,
        statuses: Sequence[FaceStatus],
        values: Sequence[float | None],
        *,
        simulated: bool = True,
        raises: bool = False,
    ) -> None:
        self.statuses, self.values, self.raises = statuses, values, raises
        self.info = FaceEvaluatorInfo(
            name="pattern-face", revision="1", settings_sha256=None, simulated=simulated
        )
        self.calls: list[str] = []

    def evaluate(self, artefact: ArtefactRef, pseudonym: str, indices: Sequence[int]) -> Any:
        self.calls.append(artefact.uri)
        if self.raises:
            raise RuntimeError("secret-path-must-not-leak")
        return tuple(
            FrameEvaluation(frame_index=i, face_status=s, similarity=v)
            # Non-strict so a short pattern yields a contract violation rather than an exception.
            for i, s, v in zip(indices, self.statuses, self.values, strict=False)
        )


class FixedQuality:
    def __init__(self, *, simulated: bool = True, raises: bool = False) -> None:
        self.raises = raises
        self.info = QualityEvaluatorInfo(
            name="fixed-q", revision="1", scale_min=1.0, scale_max=5.0, simulated=simulated
        )

    def evaluate(self, artefact: ArtefactRef) -> QualityEvaluation:
        if self.raises:
            raise RuntimeError("boom")
        return QualityEvaluation(status="scored", score=3.0)


VALID5 = PatternFace(("valid",) * 5, (0.9, 0.2, 0.4, 0.6, 0.8))


def evaluate(plan: BaselinePlan, results: BaselineResultSet, face: Any = None, q: Any = None):
    return evaluate_baseline_results(
        results,
        plan,
        face_evaluator=face or DemoFaceEvaluator(),
        quality_evaluator=q or DemoQualityEvaluator(),
        manifest=demo_manifest(),
    )


def test_post_hoc_evaluation_returns_new_record_and_keeps_every_attempt(
    plan: BaselinePlan, unevaluated: BaselineResultSet
) -> None:
    before = unevaluated.model_dump_json()
    evaluated = evaluate(plan, unevaluated)
    assert unevaluated.model_dump_json() == before  # input untouched
    assert unevaluated.face_evaluator is None
    assert evaluated.face_evaluator == DemoFaceEvaluator.info
    assert len(evaluated.attempts) == len(unevaluated.attempts)
    assert evaluated.unexecuted == unevaluated.unexecuted
    assert evaluated.accounting() == unevaluated.accounting()
    for attempt in evaluated.attempts:
        statuses = {f.face_status for f in attempt.frames}
        if attempt.execution.status == "failed":
            assert statuses == {"not_evaluated"}
            assert attempt.quality.status == "not_evaluated"
        else:
            assert "not_evaluated" not in statuses
    assert parse_baseline_result_set_json(evaluated.model_dump_json()) == evaluated


def test_similarity_is_never_generated_for_invalid_faces(
    plan: BaselinePlan, unevaluated: BaselineResultSet
) -> None:
    evaluated = evaluate(plan, unevaluated)
    frames = [f for a in evaluated.attempts for f in a.frames]
    assert {"valid", "absent", "multiple", "low_quality", "error"} <= {
        f.face_status for f in frames
    }
    assert all((f.similarity is not None) == (f.face_status == "valid") for f in frames)


def test_already_evaluated_results_are_not_re_evaluated(
    plan: BaselinePlan, unevaluated: BaselineResultSet
) -> None:
    evaluated = evaluate(plan, unevaluated)
    with pytest.raises(BaselineResultValidationError, match="never re-evaluated"):
        evaluate(plan, evaluated)


def test_mock_evaluators_are_never_applied_to_non_simulated_results(
    plan: BaselinePlan, unevaluated: BaselineResultSet
) -> None:
    data = json.loads(unevaluated.model_dump_json())
    data["executor"]["simulated"] = False
    data.update(
        simulated=False,
        simulation_scenario=None,
        provenance={
            "source_commit": GIT,
            "checkpoint_revision": GIT,
            "weight_files_sha256": SHA,
            "environment_sha256": SHA,
            "verified_before_load": True,
        },
    )
    real = parse_baseline_result_set_json(json.dumps(data))
    face = DemoFaceEvaluator()
    with pytest.raises(BaselineResultValidationError, match="mock scores are never substituted"):
        evaluate_baseline_results(
            real, plan, face_evaluator=face, quality_evaluator=DemoQualityEvaluator()
        )
    with pytest.raises(BaselineResultValidationError, match="simulated flags"):
        evaluate_baseline_results(
            unevaluated,
            plan,
            face_evaluator=PatternFace(("valid",) * 5, (0.5,) * 5, simulated=False),
            quality_evaluator=FixedQuality(simulated=False),
        )


def test_smoke_results_are_never_evaluated() -> None:
    data = demo_manifest().model_dump(mode="json")
    data.update(
        run_role="smoke", identities=[{"pseudonym": "SYN-201", "identity_split": None}], seeds=[11]
    )
    plan = generate_baseline_plan(parse_baseline_manifest(data))
    results = demo_unevaluated_results(plan)
    with pytest.raises(BaselineResultValidationError, match="smoke"):
        evaluate_baseline_results(
            results,
            plan,
            face_evaluator=DemoFaceEvaluator(),
            quality_evaluator=DemoQualityEvaluator(),
        )


def test_evaluator_exceptions_become_error_statuses_without_messages(
    plan: BaselinePlan, unevaluated: BaselineResultSet
) -> None:
    face = PatternFace(("valid",) * 5, (0.5,) * 5, raises=True)
    evaluated = evaluate(plan, unevaluated, face, FixedQuality(raises=True))
    succeeded = [a for a in evaluated.attempts if a.execution.status == "succeeded"]
    assert {f.face_status for a in succeeded for f in a.frames} == {"error"}
    assert {a.quality.status for a in succeeded} == {"error"}
    assert "secret-path" not in evaluated.model_dump_json()
    assert len(face.calls) == len(succeeded)


def test_evaluator_contract_violation_raises(
    plan: BaselinePlan, unevaluated: BaselineResultSet
) -> None:
    with pytest.raises(BaselineResultValidationError, match="one evaluation per requested frame"):
        evaluate(plan, unevaluated, PatternFace(("valid",) * 4, (0.5,) * 4))


# Aggregation ---------------------------------------------------------------------------------


def test_frame_zero_is_separate_and_later_median_uses_valid_frames_only(
    plan: BaselinePlan, unevaluated: BaselineResultSet
) -> None:
    face = PatternFace(("valid", "valid", "absent", "valid", "error"), (0.9, 0.2, None, 0.6, None))
    evaluated = evaluate(plan, unevaluated, face, FixedQuality())
    clip = summarise_attempt(evaluated.attempts[0], min_valid_later_frames=1)
    assert clip.first_frame_similarity == 0.9
    assert clip.valid_later_frames == 2
    assert clip.later_frame_similarity == pytest.approx(0.4)  # median(0.2, 0.6); 0.9 excluded
    assert clip.first_minus_later == pytest.approx(0.5)
    assert clip.trajectory == ((0, 0.9), (4, 0.2), (8, None), (12, 0.6), (16, None))
    assert clip.later_face_status_counts["absent"] == 1
    assert clip.later_frames_sampled == 4


def test_insufficient_valid_later_frames_gives_no_similarity_or_drift(
    plan: BaselinePlan, unevaluated: BaselineResultSet
) -> None:
    face = PatternFace(
        ("valid", "valid", "absent", "multiple", "low_quality"), (0.9, 0.3) + (None,) * 3
    )
    evaluated = evaluate(plan, unevaluated, face, FixedQuality())
    clip = summarise_attempt(evaluated.attempts[0], min_valid_later_frames=2)
    assert clip.later_frame_similarity is None
    assert clip.later_similarity_status == "insufficient_valid_later_frames"
    assert clip.first_minus_later is None
    assert clip.first_frame_similarity == 0.9  # still reported, separately


def test_baseline_aggregation_tracks_coverage_failures_and_unexecuted_runs(
    plan: BaselinePlan, unevaluated: BaselineResultSet
) -> None:
    evaluated = evaluate(plan, unevaluated)
    summary = aggregate_baseline(
        evaluated, plan, min_valid_later_frames=1, attempt_selection="first_attempt"
    )
    assert summary.calibration_status == "uncalibrated"
    assert summary.simulated
    assert summary.runs_planned == len(plan.runs) == len(summary.selected)
    assert len(summary.attempts) == len(evaluated.attempts)  # every attempt summarised
    assert summary.outcome_counts == {"succeeded": 3, "failed": 2, "not_executed": 1}
    assert summary.frames_declared == 5 * len(plan.runs)
    assert sum(summary.face_status_counts.values()) == summary.frames_declared
    assert sum(summary.later_face_status_counts.values()) == summary.later_frames_declared
    assert summary.later_frames_declared == 4 * len(plan.runs)
    assert sum(summary.first_frame_status_counts.values()) == len(plan.runs)
    assert summary.face_status_counts["not_evaluated"] == 5 * 3  # 2 failed + 1 unexecuted
    assert summary.identities_total == 3
    assert summary.identities_with_later_similarity == 2
    assert summary.later_frame_similarity_interval is None
    assert summary.uncertainty_method is None
    unexecuted = [c for c in summary.selected if c.outcome == "not_executed"]
    assert len(unexecuted) == 1
    assert unexecuted[0].unexecuted_reason == "halted_after_failure"
    assert unexecuted[0].later_similarity_status == "not_evaluated"
    third = next(i for i in summary.identities if i.identity_index == 3)
    assert third.median_later_frame_similarity is None
    assert third.outcome_counts == {"succeeded": 0, "failed": 1, "not_executed": 1}


def test_attempt_selection_is_explicit_and_recorded(
    plan: BaselinePlan, unevaluated: BaselineResultSet
) -> None:
    evaluated = evaluate(plan, unevaluated)
    first = aggregate_baseline(
        evaluated, plan, min_valid_later_frames=1, attempt_selection="first_attempt"
    )
    last = aggregate_baseline(
        evaluated, plan, min_valid_later_frames=1, attempt_selection="last_attempt"
    )
    retried = plan.runs[2].run_id
    assert next(c for c in first.selected if c.run_id == retried).outcome == "failed"
    assert next(c for c in last.selected if c.run_id == retried).outcome == "succeeded"
    assert (first.attempt_selection, last.attempt_selection) == ("first_attempt", "last_attempt")
    with pytest.raises(ValueError, match="attempt_selection"):
        aggregate_baseline(evaluated, plan, min_valid_later_frames=1, attempt_selection="best")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        aggregate_baseline(evaluated, plan, attempt_selection="first_attempt")  # type: ignore[call-arg]
    for bad in (0, -1, True):
        with pytest.raises(ValueError, match="min_valid_later_frames"):
            aggregate_baseline(
                evaluated, plan, min_valid_later_frames=bad, attempt_selection="first_attempt"
            )


def test_identity_level_medians_and_independent_quality(
    plan: BaselinePlan, unevaluated: BaselineResultSet
) -> None:
    evaluated = evaluate(plan, unevaluated, VALID5, FixedQuality())
    summary = aggregate_baseline(
        evaluated, plan, min_valid_later_frames=1, attempt_selection="last_attempt"
    )
    # Every evaluated clip has later median 0.5 and frame 0 at 0.9.
    assert summary.median_later_frame_similarity == pytest.approx(0.5)
    assert summary.median_first_frame_similarity == pytest.approx(0.9)
    assert summary.median_first_minus_later == pytest.approx(0.4)
    assert summary.median_quality_score == 3.0
    assert summary.quality_status_counts["scored"] == 4
    assert not hasattr(summary, "combined_score")
    one = next(i for i in summary.identities if i.identity_index == 1)
    assert one.clips_with_later_similarity == 2
    assert one.clips_with_quality == 2


def test_unevaluated_results_aggregate_without_any_similarity(
    plan: BaselinePlan, unevaluated: BaselineResultSet
) -> None:
    summary = aggregate_baseline(
        unevaluated, plan, min_valid_later_frames=1, attempt_selection="first_attempt"
    )
    assert not summary.evaluated
    assert summary.identities_with_later_similarity == 0
    assert summary.median_later_frame_similarity is None
    assert summary.face_status_counts["not_evaluated"] == summary.frames_declared
    assert summary.later_similarity_status_counts["not_evaluated"] == len(plan.runs)


def test_uncertainty_extension_point_receives_identity_values_only(
    plan: BaselinePlan, unevaluated: BaselineResultSet
) -> None:
    seen: list[tuple[float, ...]] = []

    class Recorder:
        name = "recorder"

        def interval(self, values: Sequence[float]) -> Interval | None:
            seen.append(tuple(values))
            return None

    evaluated = evaluate(plan, unevaluated, VALID5, FixedQuality())
    summary = aggregate_baseline(
        evaluated,
        plan,
        min_valid_later_frames=1,
        attempt_selection="first_attempt",
        uncertainty=Recorder(),
    )
    assert seen == [(0.5, 0.5)]  # one value per identity with similarity
    assert summary.uncertainty_method == "recorder"


def test_aggregation_rejects_results_that_do_not_match_the_plan(
    plan: BaselinePlan, unevaluated: BaselineResultSet
) -> None:
    dropped = unevaluated.model_copy(update={"unexecuted": ()})
    with pytest.raises(BaselineResultValidationError, match="neither attempted"):
        aggregate_baseline(
            dropped, plan, min_valid_later_frames=1, attempt_selection="first_attempt"
        )
