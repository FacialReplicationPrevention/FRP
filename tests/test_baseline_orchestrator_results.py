"""Plan-level accounting, retries, stops, result validation and redaction (fake backend only)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from frp.baseline.backend import ConditioningObservation  # noqa: F401
from frp.baseline.executor import Wan21BaselineExecutor
from frp.baseline.manifest import BaselineManifest
from frp.baseline.orchestrator import execute_baseline_plan
from frp.baseline.planner import BaselinePlan, generate_baseline_plan
from frp.baseline.results import (
    BaselineResultSet,
    BaselineResultValidationError,
    parse_baseline_result_set_json,
    verify_baseline_results_against_plan,
)
from frp.baseline.upstream import UpstreamWan21Backend
from frp.results import FaceEvaluatorInfo, FrameEvaluation, QualityEvaluation, QualityEvaluatorInfo
from tests.baseline_support import (
    ARTEFACT_BASE,
    FakeBackend,
    FakeInspector,
    FakeStop,
    FixedReferences,
    RecordingProvider,
    make_checkpoint,
    ready_manifest,
)

INDICES = (0, 4, 8)


class FakeFace:
    info = FaceEvaluatorInfo(
        name="synthetic-face", revision="synthetic-eval-1", settings_sha256=None, simulated=True
    )

    def __init__(self, bad: bool = False) -> None:
        self.bad = bad
        self.calls = 0

    def evaluate(self, artefact: Any, identity_pseudonym: str, frame_indices: Any) -> Any:
        self.calls += 1
        if self.bad:
            return ()
        return tuple(
            FrameEvaluation(frame_index=i, face_status="valid", similarity=0.5)
            for i in frame_indices
        )


class FakeQuality:
    info = QualityEvaluatorInfo(
        name="synthetic-q", revision="synthetic-q-1", scale_min=0.0, scale_max=1.0, simulated=True
    )

    def evaluate(self, artefact: Any) -> QualityEvaluation:
        return QualityEvaluation(status="scored", score=0.5)


def build(
    tmp_path: Path, backend: FakeBackend | None = None, **manifest_overrides: Any
) -> tuple[BaselineManifest, BaselinePlan, Wan21BaselineExecutor, FakeBackend]:
    root = tmp_path / "ckpt"
    root.mkdir()
    expected = make_checkpoint(root)
    manifest = ready_manifest(expected, **manifest_overrides)
    backend = backend or FakeBackend()
    executor = Wan21BaselineExecutor(
        manifest=manifest,
        backend=backend,
        references=FixedReferences(),
        checkpoint_dir=root,
        source_dir=tmp_path,
        artefact_base_uri=ARTEFACT_BASE,
        authorisation=RecordingProvider(),
        source_inspector=FakeInspector(),
    )
    return manifest, generate_baseline_plan(manifest), executor, backend


def run_plan(manifest: BaselineManifest, plan: BaselinePlan, executor: Any, **kw: Any):
    kw.setdefault("simulation_scenario", "synthetic-mock")
    return execute_baseline_plan(
        plan, executor, frame_indices=INDICES, frame_count=9, manifest=manifest, **kw
    )


def test_mock_run_accounts_for_every_run_and_is_marked_simulated(tmp_path: Path) -> None:
    manifest, plan, executor, _ = build(tmp_path)
    results = run_plan(
        manifest, plan, executor, face_evaluator=FakeFace(), quality_evaluator=FakeQuality()
    )
    assert results.simulated
    assert results.simulation_scenario == "synthetic-mock"
    assert results.accounting()["runs_succeeded"] == 4
    assert results.unexecuted == ()
    assert results.claim_scope == "exploratory_uncalibrated_or_calibrated_baseline"
    assert all(a.attempt_index == 1 for a in results.attempts)
    assert results.provenance is not None
    assert results.provenance.verified_before_load


def test_smoke_role_never_gets_similarity(tmp_path: Path) -> None:
    root = tmp_path / "ckpt"
    root.mkdir()
    expected = make_checkpoint(root)
    smoke = ready_manifest(
        expected,
        run_role="smoke",
        identities=[{"pseudonym": "SYN-101", "identity_split": None}],
        seeds=[7],
    )
    plan = generate_baseline_plan(smoke)
    executor = Wan21BaselineExecutor(
        manifest=smoke,
        backend=FakeBackend(),
        references=FixedReferences(),
        checkpoint_dir=root,
        source_dir=tmp_path,
        artefact_base_uri=ARTEFACT_BASE,
        authorisation=RecordingProvider(),
        source_inspector=FakeInspector(),
    )
    face = FakeFace()
    results = run_plan(smoke, plan, executor, face_evaluator=face, quality_evaluator=FakeQuality())
    assert face.calls == 0
    assert {f.face_status for a in results.attempts for f in a.frames} == {"not_evaluated"}
    assert results.claim_scope == "technical_smoke_only"


def test_without_evaluators_nothing_is_imputed(tmp_path: Path) -> None:
    manifest, plan, executor, _ = build(tmp_path)
    results = run_plan(manifest, plan, executor)
    assert all(
        f.similarity is None and f.face_status == "not_evaluated"
        for a in results.attempts
        for f in a.frames
    )


def test_evaluator_contract_violation_raises(tmp_path: Path) -> None:
    manifest, plan, executor, _ = build(tmp_path)
    with pytest.raises(BaselineResultValidationError):
        run_plan(
            manifest,
            plan,
            executor,
            face_evaluator=FakeFace(bad=True),
            quality_evaluator=FakeQuality(),
        )


def test_disabled_live_backend_leaves_every_run_unexecuted(tmp_path: Path) -> None:
    manifest, plan, executor, _ = build(tmp_path, backend=UpstreamWan21Backend())
    results = execute_baseline_plan(
        plan, executor, frame_indices=INDICES, frame_count=9, manifest=manifest
    )
    assert results.simulated is False
    assert results.attempts == ()
    assert results.stop_reason == "live_execution_disabled"
    assert {u.reason for u in results.unexecuted} == {"live_execution_disabled"}
    assert results.provenance is None


def test_non_simulated_attempts_without_verified_provenance_are_invalid(tmp_path: Path) -> None:
    manifest, plan, executor, _ = build(tmp_path)
    data = json.loads(run_plan(manifest, plan, executor).model_dump_json())
    for component in ("executor", "face_evaluator", "quality_evaluator"):
        if data[component]:
            data[component]["simulated"] = False
    data.update(simulated=False, simulation_scenario=None, provenance=None)
    with pytest.raises(BaselineResultValidationError, match="verified before load"):
        parse_baseline_result_set_json(json.dumps(data))


def test_not_authorised_mock_run_records_all_runs_unexecuted(tmp_path: Path) -> None:
    manifest, plan, _, backend = build(tmp_path)
    denied = Wan21BaselineExecutor(
        manifest=manifest,
        backend=backend,
        references=FixedReferences(),
        checkpoint_dir=tmp_path / "ckpt",
        source_dir=tmp_path,
        artefact_base_uri=ARTEFACT_BASE,
    )
    results = run_plan(manifest, plan, denied)
    assert results.attempts == ()
    assert len(results.unexecuted) == 4
    assert results.stop_reason == "not_authorised"
    assert {u.reason for u in results.unexecuted} == {"not_authorised"}
    assert backend.events == []


def test_failure_halts_and_remaining_runs_are_recorded_unexecuted(tmp_path: Path) -> None:
    manifest, plan, executor, _ = build(tmp_path, backend=FakeBackend(mode="load_error"))
    results = run_plan(manifest, plan, executor)
    acc = results.accounting()
    assert acc["failed_attempts"] == 1
    assert acc["runs_unexecuted"] == 3
    assert results.stop_reason == "halted_after_failure"
    assert [u.run_id for u in results.unexecuted] == [r.run_id for r in plan.runs[1:]]
    assert results.attempts[0].execution.artefact is None


def test_transient_failure_retries_as_new_attempt_without_overwriting(tmp_path: Path) -> None:
    manifest, plan, executor, _ = build(tmp_path, backend=FakeBackend(fail_attempts={1}))
    results = run_plan(manifest, plan, executor, max_attempts=2)
    first_run = [a for a in results.attempts if a.run_id == plan.runs[0].run_id]
    assert [a.attempt_index for a in first_run] == [1, 2]
    assert [a.execution.status for a in first_run] == ["failed", "succeeded"]
    uris = [a.execution.artefact.uri for a in first_run if a.execution.artefact]
    assert uris == [f"{ARTEFACT_BASE}/{plan.runs[0].run_id}/attempt-02.mp4"]
    assert results.accounting()["failed_attempts_by_detail"] == {
        "generation_error": 4
    }  # every run's attempt 1


def test_non_transient_failure_is_not_retried(tmp_path: Path) -> None:
    manifest, plan, executor, backend = build(tmp_path, backend=FakeBackend(mode="cfg_order"))
    results = run_plan(manifest, plan, executor, max_attempts=3)
    assert len(results.attempts) == 1
    assert len(backend.requests) == 1


def test_budget_stop_before_a_run_leaves_it_and_later_runs_unexecuted(tmp_path: Path) -> None:
    manifest, plan, executor, _backend = build(tmp_path)
    stop = FakeStop("budget_stop", after_calls=2)
    results = run_plan(manifest, plan, executor, stop=stop)
    assert results.accounting()["runs_succeeded"] == 2
    assert results.stop_reason == "budget_stop"
    assert {u.reason for u in results.unexecuted} == {"budget_stop"}
    assert [u.run_id for u in results.unexecuted] == [r.run_id for r in plan.runs[2:]]


def test_operator_abort_midway_records_the_interrupted_attempt(tmp_path: Path) -> None:
    class Aborting(FakeBackend):
        def generate(self, request, stop):
            if request.run_id.endswith("R0002"):
                raise KeyboardInterrupt
            return super().generate(request, stop)

    manifest, plan, executor, _ = build(tmp_path, backend=Aborting())
    results = run_plan(manifest, plan, executor)
    assert results.stop_reason == "operator_abort"
    assert results.accounting()["failed_attempts_by_detail"] == {"operator_abort": 1}
    assert [u.run_id for u in results.unexecuted] == [r.run_id for r in plan.runs[2:]]


def test_cleanup_failure_halts(tmp_path: Path) -> None:
    manifest, plan, executor, _ = build(tmp_path, backend=FakeBackend(mode="cleanup_error"))
    results = run_plan(manifest, plan, executor)
    assert results.stop_reason == "cleanup_failed"
    assert results.attempts[0].cleanup_ok is False
    assert len(results.attempts) == 1
    assert len(results.unexecuted) == 3


def test_missing_reference_skips_only_that_run(tmp_path: Path) -> None:
    manifest, plan, executor, _ = build(tmp_path)
    executor._references = FixedReferences(missing={"SYN-101"})
    results = run_plan(manifest, plan, executor)
    assert {u.reason for u in results.unexecuted} == {"invalid_input"}
    assert len(results.unexecuted) == 2
    assert results.accounting()["runs_succeeded"] == 2
    assert results.stop_reason is None


def test_results_round_trip_and_redaction(tmp_path: Path) -> None:
    manifest, plan, executor, _backend = build(tmp_path)
    results = run_plan(
        manifest, plan, executor, face_evaluator=FakeFace(), quality_evaluator=FakeQuality()
    )
    text = results.model_dump_json()
    for forbidden in ("SYN-10", "softly lit", "private-ref", "ref-syn", "secret"):
        assert forbidden not in text
    assert parse_baseline_result_set_json(text) == results
    assert "tensor" not in text
    assert "latent" not in text
    summary = results.attempts[0].conditioning
    assert summary is not None
    assert summary.clip_features.shape == (1, 257, 1280)
    assert not any(
        isinstance(v, float) and v > 1
        for v in json.loads(text)["attempts"][0]["conditioning"].values()
    )


def test_results_must_cover_the_plan_exactly(tmp_path: Path) -> None:
    manifest, plan, executor, _ = build(tmp_path)
    results = run_plan(manifest, plan, executor)
    dropped = results.model_copy(update={"attempts": results.attempts[:-1]})
    with pytest.raises(BaselineResultValidationError, match="neither attempted"):
        verify_baseline_results_against_plan(dropped, plan, manifest)
    foreign = results.model_copy(update={"manifest_sha256": "0" * 64})
    with pytest.raises(BaselineResultValidationError, match="manifest_sha256"):
        verify_baseline_results_against_plan(foreign, plan, manifest)


def _mutated(results: BaselineResultSet, **changes: Any) -> dict[str, Any]:
    data = json.loads(results.model_dump_json())
    data.update(changes)
    return data


def test_result_schema_rejects_inconsistent_records(tmp_path: Path) -> None:
    manifest, plan, executor, _ = build(tmp_path)
    results = run_plan(manifest, plan, executor)
    base = json.loads(results.model_dump_json())
    cases: list[dict[str, Any]] = []
    for patch in (
        {"simulated": False},  # mock executor/evaluators flags disagree + no live provenance
        {"claim_scope": "anything"},
        {"run_role": "smoke"},
        {"unexecuted": [{"run_id": results.attempts[0].run_id, "reason": "budget_stop"}]},
        {"attempts": base["attempts"] + [base["attempts"][0]]},
        {"extra_field": 1},
    ):
        data = json.loads(json.dumps(base))
        data.update(patch)
        cases.append(data)
    for data in cases:
        with pytest.raises(BaselineResultValidationError):
            parse_baseline_result_set_json(json.dumps(data))


def test_succeeded_attempt_requires_artefact_and_failed_forbids_one(tmp_path: Path) -> None:
    manifest, plan, executor, _ = build(tmp_path)
    base = json.loads(run_plan(manifest, plan, executor).model_dump_json())
    ok = json.loads(json.dumps(base))
    ok["attempts"][0]["execution"]["artefact"] = None
    with pytest.raises(BaselineResultValidationError):
        parse_baseline_result_set_json(json.dumps(ok))
    bad = json.loads(json.dumps(base))
    bad["attempts"][0]["execution"].update(status="failed", failure_category="timeout")
    with pytest.raises(BaselineResultValidationError):
        parse_baseline_result_set_json(json.dumps(bad))
    unknown = json.loads(json.dumps(base))
    unknown["attempts"][0]["conditioning"]["note"] = "SECRET"
    with pytest.raises(BaselineResultValidationError) as excinfo:
        parse_baseline_result_set_json(json.dumps(unknown))
    assert "SECRET" not in str(excinfo.value)


def test_ablation_result_set_does_not_accept_baseline_results_and_vice_versa(
    tmp_path: Path,
) -> None:
    from frp.results import ResultValidationError, parse_result_set_json

    manifest, plan, executor, _ = build(tmp_path)
    text = run_plan(manifest, plan, executor).model_dump_json()
    with pytest.raises(ResultValidationError):
        parse_result_set_json(text)


def test_max_attempts_bounds() -> None:
    manifest = ready_manifest({"f": "a" * 64})
    plan = generate_baseline_plan(manifest)
    with pytest.raises(ValueError, match="max_attempts"):
        execute_baseline_plan(plan, None, frame_indices=INDICES, max_attempts=0)  # type: ignore[arg-type]
