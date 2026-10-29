"""Simulated executor/evaluators and the orchestrator: determinism, pairing and failure paths."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace

import pytest

from frp.manifest import load_manifest, parse_manifest
from frp.pipeline import execute_plan
from frp.planner import PlanInvariantError, generate_run_plan
from frp.results import (
    EXECUTION_STATUSES,
    FACE_STATUSES,
    QUALITY_STATUSES,
    ExecutionRecord,
    FrameEvaluation,
    ResultValidationError,
    verify_results_against_plan,
)
from frp.simulation import (
    SCENARIOS,
    SIMULATION_DEFAULT_FRAME_INDICES,
    SimulatedExecutor,
    SimulatedFaceEvaluator,
    SimulatedQualityEvaluator,
    simulate_experiment,
)
from tests.conftest import EXAMPLE_MANIFEST


@pytest.fixture
def example():
    return load_manifest(EXAMPLE_MANIFEST)


@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_every_scenario_is_deterministic_and_matches_plan(example, scenario):
    first = simulate_experiment(example, scenario)
    second = simulate_experiment(example, scenario)
    assert first.model_dump_json() == second.model_dump_json()
    plan = generate_run_plan(example)
    verify_results_against_plan(first, plan, example)
    assert [r.run_id for r in first.runs] == [r.run_id for r in plan.runs]
    assert first.simulated is True
    assert first.simulation_scenario == scenario
    assert all(c.simulated for c in (first.executor, first.face_evaluator, first.quality_evaluator))


def test_simulation_preserves_abcd_pairing(example):
    results = simulate_experiment(example)
    plan = generate_run_plan(example)
    record_groups = [results.runs[i : i + 4] for i in range(0, len(results.runs), 4)]
    for group, (record_group, plan_group) in enumerate(
        zip(record_groups, (g.runs for g in plan.groups), strict=True), 1
    ):
        assert [r.variant for r in record_group] == ["A", "B", "C", "D"]
        assert {(r.identity_index, r.prompt_index, r.seed) for r in record_group} == {
            (p.identity_index, p.prompt_index, p.seed) for p in plan_group
        }
        assert {r.group_index for r in record_group} == {group}


def test_mixed_scenario_covers_every_status(example):
    results = simulate_experiment(example, "mixed")
    assert {r.execution.status for r in results.runs} == set(EXECUTION_STATUSES)
    assert {f.face_status for r in results.runs for f in r.frames} == set(FACE_STATUSES)
    assert {r.quality.status for r in results.runs} == set(QUALITY_STATUSES)


def test_all_valid_has_no_missing_values(example):
    results = simulate_experiment(example, "all-valid")
    assert all(r.execution.status == "succeeded" for r in results.runs)
    assert all(f.similarity is not None for r in results.runs for f in r.frames)
    assert all(r.quality.score is not None for r in results.runs)


def test_failed_runs_are_preserved_and_unevaluated(example):
    results = simulate_experiment(example, "failed-run")
    failed = [r for r in results.runs if r.execution.status == "failed"]
    assert failed
    assert len(results.runs) == 24
    for run in failed:
        assert run.execution.artefact is None
        assert run.execution.failure_category is not None
        assert {f.face_status for f in run.frames} == {"not_evaluated"}
        assert all(f.similarity is None for f in run.frames)
        assert run.quality.status == "not_evaluated"


def test_incomplete_experiment_records_unexecuted_runs(example):
    results = simulate_experiment(example, "incomplete")
    statuses = [r.execution.status for r in results.runs]
    assert statuses == ["succeeded"] * 18 + ["not_executed"] * 6


@pytest.mark.parametrize(
    ("scenario", "status"),
    [("absent-face", "absent"), ("multiple-faces", "multiple"), ("evaluator-error", "error")],
)
def test_face_scenarios_produce_null_similarity(example, scenario, status):
    frames = [f for r in simulate_experiment(example, scenario).runs for f in r.frames]
    hit = [f for f in frames if f.face_status == status]
    assert hit
    assert all(f.similarity is None for f in hit)


def test_missing_quality_scenario(example):
    statuses = Counter(
        r.quality.status for r in simulate_experiment(example, "missing-quality").runs
    )
    assert statuses["not_evaluated"] > 0
    assert statuses["unscorable"] > 0


def test_fixture_values_are_plain_and_bounded(example):
    results = simulate_experiment(example, "all-valid")
    for run in results.runs:
        assert run.execution.gpu_seconds is None
        assert run.execution.artefact.uri.startswith("simulated://artefact/")
        assert run.run_id not in run.execution.artefact.uri
        assert all(0.1 <= f.similarity <= 0.9 for f in run.frames)
        assert run.quality.score in {1.0, 2.0, 3.0, 4.0, 5.0}


def test_frame_indices_from_manifest_or_simulation_default(manifest_data, example):
    default = simulate_experiment(example)
    assert default.frame_indices == SIMULATION_DEFAULT_FRAME_INDICES
    assert default.frame_indices_source == "simulation_default"
    manifest = parse_manifest(manifest_data | {"frame_indices": [0, 40, 80]})
    declared = simulate_experiment(manifest)
    assert declared.frame_indices == (0, 40, 80)
    assert declared.frame_indices_source == "manifest"


def test_unknown_scenario_rejected(example):
    with pytest.raises(ResultValidationError, match="unknown simulation scenario"):
        simulate_experiment(example, "no-such-scenario")


# --- Orchestrator behaviour with misbehaving adapters --------------------------------------


class _Raising:
    def __init__(self, inner):
        self._inner = inner

    @property
    def info(self):
        return self._inner.info

    def execute(self, run):
        raise RuntimeError("/private/path/should/not/leak")

    def evaluate(self, *args):
        raise RuntimeError("/private/path/should/not/leak")


def _adapters():
    scenario = SCENARIOS["all-valid"]
    executor = SimulatedExecutor(scenario)
    return (
        executor,
        SimulatedFaceEvaluator(scenario, executor),
        SimulatedQualityEvaluator(scenario, executor),
    )


def _run(manifest, executor, face, quality, **kwargs):
    return execute_plan(
        generate_run_plan(manifest),
        executor,
        face,
        quality,
        frame_indices=(0, 20),
        frame_indices_source="simulation_default",
        simulation_scenario="all-valid",
        **kwargs,
    )


def test_executor_exception_becomes_failed_run(example):
    executor, face, quality = _adapters()
    results = _run(example, _Raising(executor), face, quality)
    assert {r.execution.status for r in results.runs} == {"failed"}
    assert {r.execution.failure_category for r in results.runs} == {"executor_error"}
    assert "/private/path" not in results.model_dump_json()


def test_evaluator_exceptions_become_error_statuses(example):
    executor, face, quality = _adapters()
    results = _run(example, executor, _Raising(face), _Raising(quality))
    assert {f.face_status for r in results.runs for f in r.frames} == {"error"}
    assert {r.quality.status for r in results.runs} == {"error"}
    assert all(f.similarity is None for r in results.runs for f in r.frames)


def test_face_evaluator_contract_violation_raises(example):
    executor, face, quality = _adapters()

    class _WrongFrames:
        info = face.info

        def evaluate(self, artefact, pseudonym, frame_indices):
            return (FrameEvaluation(frame_index=0, face_status="absent", similarity=None),)

    with pytest.raises(ResultValidationError, match="one evaluation per requested frame"):
        _run(example, executor, _WrongFrames(), quality)


def test_executor_may_not_claim_not_executed(example):
    executor, face, quality = _adapters()

    class _Liar:
        info = executor.info

        def execute(self, run):
            return ExecutionRecord(
                status="not_executed", artefact=None, failure_category=None, gpu_seconds=None
            )

    with pytest.raises(ResultValidationError, match="succeeded or failed"):
        _run(example, _Liar(), face, quality)


def test_max_runs_marks_remaining_runs_not_executed(example):
    results = _run(example, *_adapters(), max_runs=5)
    assert [r.execution.status for r in results.runs].count("not_executed") == 19
    with pytest.raises(ValueError, match="max_runs"):
        _run(example, *_adapters(), max_runs=-1)


def test_orchestrator_rejects_tampered_plan(example):
    plan = generate_run_plan(example)
    tampered = replace(plan, groups=(replace(plan.groups[0], seed=999), *plan.groups[1:]))
    with pytest.raises(PlanInvariantError):
        execute_plan(
            tampered,
            *_adapters(),
            frame_indices=(0,),
            frame_indices_source="simulation_default",
            simulation_scenario="all-valid",
        )
