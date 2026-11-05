"""Adverse-case matrix for baseline aggregation and the synthetic identity bootstrap."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import pytest

from frp.aggregation import Interval
from frp.baseline.aggregation import aggregate_baseline
from frp.baseline.evaluation import evaluate_baseline_results
from frp.baseline.planner import BaselinePlan, generate_baseline_plan
from frp.baseline.results import BaselineResultSet
from frp.baseline.synthetic_uncertainty import SyntheticIdentityBootstrap
from frp.results import (
    ArtefactRef,
    FaceEvaluatorInfo,
    FaceStatus,
    FrameEvaluation,
    QualityEvaluation,
)
from frp.review.demo import (
    DemoFaceEvaluator,
    DemoQualityEvaluator,
    demo_manifest,
    demo_unevaluated_results,
)

Pattern = tuple[tuple[FaceStatus, ...], tuple[float | None, ...]]


class RunFace:
    """Synthetic evaluator giving each demo run (by number) its own pattern; default: all absent."""

    info = FaceEvaluatorInfo(name="run-face", revision="1", settings_sha256=None, simulated=True)

    def __init__(self, patterns: dict[int, Pattern]) -> None:
        self.patterns = patterns

    def evaluate(self, artefact: ArtefactRef, pseudonym: str, indices: Sequence[int]) -> Any:
        run = int(artefact.uri.split("/")[-2].rsplit("-R", 1)[1])
        statuses, values = self.patterns.get(run, (("absent",) * 5, (None,) * 5))
        return tuple(
            FrameEvaluation(frame_index=i, face_status=s, similarity=v)
            for i, s, v in zip(indices, statuses, values, strict=True)
        )


def valid(first: float, later: float) -> Pattern:
    return ("valid",) * 5, (first, later, later, later, later)


class Scored:
    info = DemoQualityEvaluator.info

    def evaluate(self, artefact: ArtefactRef) -> QualityEvaluation:
        return QualityEvaluation(status="scored", score=3.0)


@pytest.fixture
def plan() -> BaselinePlan:
    return generate_baseline_plan(demo_manifest())


@pytest.fixture
def raw(plan: BaselinePlan) -> BaselineResultSet:
    return demo_unevaluated_results(plan)


def run(plan: BaselinePlan, raw: BaselineResultSet, patterns: dict[int, Pattern], **kw: Any):
    evaluated = evaluate_baseline_results(
        raw,
        plan,
        face_evaluator=RunFace(patterns),
        quality_evaluator=Scored(),
        manifest=demo_manifest(),
    )
    return aggregate_baseline(
        evaluated,
        plan,
        min_valid_later_frames=kw.pop("min_valid", 1),
        attempt_selection=kw.pop("selection", "first_attempt"),
        **kw,
    )


# --- estimator unit behaviour -------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"seed": True, "level": 0.9, "repetitions": 100},
        {"seed": 1.5, "level": 0.9, "repetitions": 100},
        {"seed": 1, "level": True, "repetitions": 100},
        {"seed": 1, "level": 0.0, "repetitions": 100},
        {"seed": 1, "level": 1.0, "repetitions": 100},
        {"seed": 1, "level": float("nan"), "repetitions": 100},
        {"seed": 1, "level": 0.9, "repetitions": 99},
        {"seed": 1, "level": 0.9, "repetitions": True},
        {"seed": 1, "level": 0.9, "repetitions": 100.0},
    ],
)
def test_estimator_requires_valid_explicit_parameters(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match=r"seed|level|repetitions"):
        SyntheticIdentityBootstrap(**kwargs)
    with pytest.raises(TypeError):
        SyntheticIdentityBootstrap(seed=1, level=0.9)  # type: ignore[call-arg]


@pytest.mark.parametrize("bad", [True, float("nan"), float("inf"), 10**400, "0.5", None])
def test_estimator_rejects_non_finite_or_non_numeric_observations(bad: Any) -> None:
    with pytest.raises(ValueError, match="identity value"):
        SyntheticIdentityBootstrap(seed=1, level=0.9, repetitions=100).interval([0.2, bad, 0.4])


@pytest.mark.parametrize("values", [[], [0.5], [0.5, 0.5], [0.3, 0.3, 0.3]])
def test_estimator_withholds_interval_without_identity_variation(values: list[float]) -> None:
    assert SyntheticIdentityBootstrap(seed=1, level=0.9, repetitions=200).interval(values) is None


def test_estimator_is_deterministic_bounded_and_names_its_parameters() -> None:
    values = [0.2, 0.4, 0.5, 0.9]
    a = SyntheticIdentityBootstrap(seed=7, level=0.8, repetitions=500)
    first = a.interval(values)
    assert first == SyntheticIdentityBootstrap(seed=7, level=0.8, repetitions=500).interval(values)
    assert first is not None
    assert first.level == 0.8
    assert min(values) <= first.lower <= first.upper <= max(values)
    other = SyntheticIdentityBootstrap(seed=8, level=0.8, repetitions=500).interval(values)
    assert other is not None
    assert min(values) <= other.lower <= other.upper <= max(values)
    assert "seed=7" in a.name
    assert "unapproved" in a.name


def test_two_identities_resample_identities_only() -> None:
    interval = SyntheticIdentityBootstrap(seed=3, level=0.9, repetitions=400).interval([0.2, 0.8])
    # Medians of resampled pairs can only be 0.2, 0.5 or 0.8.
    assert interval is not None
    assert (interval.lower, interval.upper) == (0.2, 0.8)


# --- aggregation matrix via the real aggregate_baseline ------------------------------------


def test_estimator_receives_one_value_per_identity_despite_unbalanced_clips(
    plan: BaselinePlan, raw: BaselineResultSet
) -> None:
    seen: list[tuple[float, ...]] = []

    class Spy:
        name = "spy"

        def interval(self, values: Sequence[float]) -> Interval | None:
            seen.append(tuple(values))
            return None

    # Identity 1 has two clips (runs 1, 2), identity 2 one succeeded clip (run 3 retried, run 4).
    patterns = {1: valid(0.9, 0.2), 2: valid(0.9, 0.4), 4: valid(0.9, 0.7)}
    summary = run(plan, raw, patterns, selection="last_attempt", uncertainty=Spy())
    assert seen == [(pytest.approx(0.3), pytest.approx(0.7))]
    assert summary.identities_with_later_similarity == 2


def test_interval_and_method_are_recorded_only_when_an_estimator_is_supplied(
    plan: BaselinePlan, raw: BaselineResultSet
) -> None:
    patterns = {1: valid(0.9, 0.2), 2: valid(0.9, 0.2), 4: valid(0.9, 0.8)}
    plain = run(plan, raw, patterns, selection="last_attempt")
    assert plain.later_frame_similarity_interval is None
    assert plain.uncertainty_method is None
    est = SyntheticIdentityBootstrap(seed=5, level=0.9, repetitions=300)
    with_est = run(plan, raw, patterns, selection="last_attempt", uncertainty=est)
    assert with_est.simulated
    assert with_est.calibration_status == "uncalibrated"
    assert with_est.uncertainty_method == est.name
    assert with_est.later_frame_similarity_interval is not None
    assert with_est.median_later_frame_similarity == plain.median_later_frame_similarity
    assert with_est.face_status_counts == plain.face_status_counts


@pytest.mark.parametrize(
    ("patterns", "contributing"),
    [
        ({}, 0),
        ({1: valid(0.9, 0.5)}, 1),
        ({1: valid(0.9, 0.5), 4: valid(0.9, 0.5)}, 2),  # two identities, all equal
    ],
)
def test_zero_one_or_degenerate_identities_get_no_interval(
    plan: BaselinePlan, raw: BaselineResultSet, patterns: dict[int, Pattern], contributing: int
) -> None:
    est = SyntheticIdentityBootstrap(seed=1, level=0.9, repetitions=200)
    summary = run(plan, raw, patterns, selection="last_attempt", uncertainty=est)
    assert summary.later_frame_similarity_interval is None
    assert summary.identities_with_later_similarity == contributing


def test_estimator_is_refused_for_non_simulated_and_smoke_results(
    plan: BaselinePlan, raw: BaselineResultSet
) -> None:
    est = SyntheticIdentityBootstrap(seed=1, level=0.9, repetitions=100)
    for update, match in (
        ({"simulated": False}, "non-simulated"),
        ({"run_role": "smoke"}, "smoke"),
    ):
        with pytest.raises(ValueError, match=match):
            aggregate_baseline(
                raw.model_copy(update=update),
                plan,
                min_valid_later_frames=1,
                attempt_selection="first_attempt",
                uncertainty=est,
            )


def test_no_executed_runs_is_accounted_for_without_values(plan: BaselinePlan) -> None:
    from frp.baseline.results import UnexecutedRun

    empty = demo_unevaluated_results(plan).model_copy(
        update={
            "attempts": (),
            "unexecuted": tuple(
                UnexecutedRun(run_id=r.run_id, reason="halted_after_failure") for r in plan.runs
            ),
        }
    )
    est = SyntheticIdentityBootstrap(seed=1, level=0.9, repetitions=100)
    summary = aggregate_baseline(
        empty, plan, min_valid_later_frames=1, attempt_selection="last_attempt", uncertainty=est
    )
    assert summary.outcome_counts == {"succeeded": 0, "failed": 0, "not_executed": len(plan.runs)}
    assert summary.face_status_counts["not_evaluated"] == summary.frames_declared
    assert summary.identities_with_later_similarity == 0
    assert summary.median_later_frame_similarity is None
    assert summary.later_frame_similarity_interval is None


def test_attempt_selection_changes_identity_values_but_keeps_all_attempts(
    plan: BaselinePlan, raw: BaselineResultSet
) -> None:
    patterns = {1: valid(0.9, 0.2), 3: valid(0.9, 0.7)}
    first = run(plan, raw, patterns, selection="first_attempt")
    last = run(plan, raw, patterns, selection="last_attempt")
    assert len(first.attempts) == len(last.attempts) == len(raw.attempts)
    assert first.identities_with_later_similarity == 1  # retried run 3 failed on its first attempt
    assert last.identities_with_later_similarity == 2


def test_denominators_keep_every_status_and_never_zero_impute(
    plan: BaselinePlan, raw: BaselineResultSet
) -> None:
    mixed: Pattern = (
        ("valid", "absent", "multiple", "low_quality", "error"),
        (0.9, None, None, None, None),
    )
    summary = run(plan, raw, {1: mixed, 2: valid(0.9, 0.6)})
    assert sum(summary.face_status_counts.values()) == summary.frames_declared
    assert summary.later_face_status_counts["valid"] == 4  # run 2 only
    for status in ("absent", "multiple", "low_quality", "error"):
        assert summary.later_face_status_counts[status] >= 1
    # Run 1 has no valid later frame: it is counted as insufficient, not as a zero.
    assert summary.later_similarity_status_counts["insufficient_valid_later_frames"] >= 1
    assert summary.median_later_frame_similarity == pytest.approx(0.6)


def test_isolated_first_frame_success_gives_no_later_similarity(
    plan: BaselinePlan, raw: BaselineResultSet
) -> None:
    isolated: Pattern = (
        ("valid", "absent", "absent", "absent", "absent"),
        (0.95, None, None, None, None),
    )
    est = SyntheticIdentityBootstrap(seed=1, level=0.9, repetitions=100)
    summary = run(plan, raw, {1: isolated, 2: isolated, 4: isolated}, uncertainty=est)
    assert summary.identities_with_later_similarity == 0
    assert summary.median_later_frame_similarity is None
    assert summary.median_first_frame_similarity == pytest.approx(0.95)
    assert summary.median_first_minus_later is None
    assert summary.later_frame_similarity_interval is None
    stricter = run(plan, raw, {1: valid(0.9, 0.5)}, min_valid=5)
    assert stricter.identities_with_later_similarity == 0  # only 4 later frames exist


def test_quality_stays_separate_and_demo_pipeline_is_labelled_simulated(
    plan: BaselinePlan, raw: BaselineResultSet
) -> None:
    evaluated = evaluate_baseline_results(
        raw,
        plan,
        face_evaluator=DemoFaceEvaluator(),
        quality_evaluator=DemoQualityEvaluator(),
        manifest=demo_manifest(),
    )
    est = SyntheticIdentityBootstrap(seed=2, level=0.9, repetitions=100)
    summary = aggregate_baseline(
        evaluated, plan, min_valid_later_frames=1, attempt_selection="last_attempt", uncertainty=est
    )
    assert summary.simulated
    assert summary.claim_scope == evaluated.claim_scope
    assert not hasattr(summary, "combined_score")
    assert "approved" not in summary.uncertainty_method.replace("unapproved", "")  # type: ignore[union-attr]


def test_one_repetition_is_rejected_and_degenerate_resamples_are_withheld() -> None:
    with pytest.raises(ValueError, match="repetitions"):
        SyntheticIdentityBootstrap(seed=1, level=0.9, repetitions=1)
    # Varying values whose resampled medians are all identical give no interval.
    est = SyntheticIdentityBootstrap(seed=1, level=0.9, repetitions=100)
    assert est.interval([0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.9]) is None


def test_extreme_finite_values_never_yield_non_finite_endpoints() -> None:
    big = 1.7e308
    est = SyntheticIdentityBootstrap(seed=1, level=0.9, repetitions=200)
    result = est.interval([-big, big])
    assert result is None or (math.isfinite(result.lower) and math.isfinite(result.upper))
