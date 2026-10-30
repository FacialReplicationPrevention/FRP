"""Executor boundary tests with a fake backend: gates, conditioning contract, failures, cleanup."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from frp.baseline.authorisation import DenyAllAuthorisation, authorisation_problems
from frp.baseline.backend import GenerationRequest
from frp.baseline.executor import Wan21BaselineExecutor
from frp.baseline.interfaces import ExecutionRefused
from frp.baseline.manifest import parse_baseline_manifest
from frp.baseline.planner import generate_baseline_plan
from frp.baseline.upstream import UpstreamWan21Backend
from tests.baseline_support import (
    ARTEFACT_BASE,
    SOURCE_COMMIT,
    FakeBackend,
    FakeInspector,
    FakeStop,
    FixedReferences,
    RecordingProvider,
    example_data,
    make_checkpoint,
    ready_manifest,
)


class Setup:
    def __init__(self, tmp_path: Path, **kwargs: Any) -> None:
        self.root = tmp_path / "ckpt"
        self.root.mkdir()
        self.expected = make_checkpoint(self.root)
        self.manifest = ready_manifest(self.expected)
        self.plan = generate_baseline_plan(self.manifest)
        self.backend = kwargs.pop("backend", FakeBackend())
        self.provider = kwargs.pop("provider", RecordingProvider())
        self.executor = Wan21BaselineExecutor(
            manifest=kwargs.pop("manifest", self.manifest),
            backend=self.backend,
            references=kwargs.pop("references", FixedReferences()),
            checkpoint_dir=self.root,
            source_dir=tmp_path / "src",
            artefact_base_uri=ARTEFACT_BASE,
            authorisation=self.provider,
            source_inspector=kwargs.pop("inspector", FakeInspector()),
            stop=kwargs.pop("stop", None),
        )
        assert not kwargs

    @property
    def run(self):
        return self.plan.runs[0]


def refusal(setup: Setup) -> str:
    with pytest.raises(ExecutionRefused) as excinfo:
        setup.executor.execute(setup.run, 1)
    return excinfo.value.code


def test_mock_success_is_simulated_and_records_private_metadata(tmp_path: Path) -> None:
    s = Setup(tmp_path)
    outcome = s.executor.execute(s.run, 1)
    assert outcome.execution.status == "succeeded"
    assert outcome.execution.artefact is not None
    assert outcome.execution.artefact.uri.startswith(ARTEFACT_BASE)
    assert outcome.conditioning is not None
    assert outcome.cleanup_ok
    assert s.executor.info.simulated is True  # a mock success is NOT a Wan 2.1 inference
    assert s.executor.verified_provenance is not None
    assert s.executor.verified_provenance.verified_before_load


def test_gate_order_verifies_everything_before_load(tmp_path: Path) -> None:
    s = Setup(tmp_path)
    s.executor.execute(s.run, 1)
    events = s.backend.events
    assert events.index("check_available") < events.index("environment") < events.index("load")
    assert events.index("load") < events.index("generate") < events.index("cleanup")


def test_fails_closed_by_default_without_private_authorisation(tmp_path: Path) -> None:
    s = Setup(tmp_path, provider=DenyAllAuthorisation())
    assert refusal(s) == "not_authorised"
    assert s.backend.events == []  # nothing was checked, loaded or generated


def test_executor_defaults_to_deny_all(tmp_path: Path) -> None:
    s = Setup(tmp_path)
    executor = Wan21BaselineExecutor(
        manifest=s.manifest,
        backend=s.backend,
        references=FixedReferences(),
        checkpoint_dir=s.root,
        source_dir=tmp_path,
        artefact_base_uri=ARTEFACT_BASE,
    )
    with pytest.raises(ExecutionRefused) as excinfo:
        executor.execute(s.run, 1)
    assert excinfo.value.code == "not_authorised"
    assert s.backend.events == []


@pytest.mark.parametrize(
    "override",
    [
        {"run_ids": ("FRP-BASELINE-SYNTHETIC-EXAMPLE-R0099",)},
        {"manifest_sha256": "1" * 64},
        {"generation_controls_sha256": "1" * 64},
        {"source_commit": "1" * 40},
        {"checkpoint_revision": "1" * 40},
        {"environment_sha256": "1" * 64},
        {"expected_files": {"weights/a.bin": "1" * 64}},
        {"executor_mode": "live"},
    ],
)
def test_authorisation_must_match_this_run_and_plan(tmp_path: Path, override: dict) -> None:
    s = Setup(tmp_path, provider=RecordingProvider(**override))
    assert refusal(s) == "not_authorised"
    assert s.backend.events == []


def test_grant_without_every_gate_is_not_constructible() -> None:
    with pytest.raises(ValueError, match="missing gate"):
        RecordingProvider(gates={"licence_and_intended_use": "private-record-1"}).authorise(
            _request()
        )


def _request():
    from frp.baseline.authorisation import AuthorisationRequest

    return AuthorisationRequest(
        run_id="FRP-BASELINE-SYNTHETIC-EXAMPLE-R0001",
        run_role="baseline",
        executor_mode="mock",
        manifest_sha256="1" * 64,
        generation_controls_sha256="2" * 64,
        source_commit="3" * 40,
        checkpoint_revision="4" * 40,
        environment_sha256="5" * 64,
        expected_files={"a": "6" * 64},
    )


def test_authorisation_problems_never_echo_values() -> None:
    problems = authorisation_problems(None, _request())
    assert problems
    assert "1" * 10 not in "".join(problems)


def test_provider_exception_is_a_refusal_not_a_crash(tmp_path: Path) -> None:
    class Exploding:
        def authorise(self, request: Any) -> None:
            raise RuntimeError("secret")

    s = Setup(tmp_path, provider=Exploding())
    assert refusal(s) == "not_authorised"


def test_incomplete_manifest_is_not_execution_ready(tmp_path: Path) -> None:
    incomplete = parse_baseline_manifest(example_data())
    s = Setup(tmp_path, manifest=incomplete)
    s.plan = generate_baseline_plan(incomplete)
    assert refusal(s) == "not_execution_ready"
    assert s.backend.events == []
    assert s.provider.requests == []


def test_run_from_another_plan_is_rejected(tmp_path: Path) -> None:
    other = example_data()
    other["sampling_steps"] = 3
    foreign = generate_baseline_plan(parse_baseline_manifest(other)).runs[0]
    s = Setup(tmp_path)
    with pytest.raises(ExecutionRefused) as excinfo:
        s.executor.execute(foreign, 1)
    assert excinfo.value.code == "invalid_input"


def test_live_upstream_backend_is_disabled(tmp_path: Path) -> None:
    s = Setup(tmp_path, backend=UpstreamWan21Backend())
    assert refusal(s) == "live_execution_disabled"
    assert s.executor.info.simulated is False


def test_missing_dependencies_refuse(tmp_path: Path) -> None:
    s = Setup(tmp_path, backend=FakeBackend(mode="unavailable"))
    assert refusal(s) == "backend_unavailable"
    assert "load" not in s.backend.events


@pytest.mark.parametrize(
    "inspector", [FakeInspector(commit="1" * 40), FakeInspector(clean=False), FakeInspector(None)]
)
def test_source_commit_mismatch_or_dirty_checkout_refuses(tmp_path: Path, inspector) -> None:
    s = Setup(tmp_path, inspector=inspector)
    assert refusal(s) == "provenance_mismatch"
    assert "load" not in s.backend.events


def test_environment_digest_mismatch_refuses(tmp_path: Path) -> None:
    s = Setup(tmp_path, backend=FakeBackend(env_sha="9" * 64))
    assert refusal(s) == "provenance_mismatch"
    assert "load" not in s.backend.events


@pytest.mark.parametrize("case", ["tampered", "missing", "extra"])
def test_weight_hash_discrepancy_refuses_before_load(tmp_path: Path, case: str) -> None:
    s = Setup(tmp_path)
    if case == "tampered":
        (s.root / "weights/a.bin").write_bytes(b"tampered")
    elif case == "missing":
        (s.root / "weights/b.bin").unlink()
    else:
        (s.root / "extra.pth").write_bytes(b"x")
    assert refusal(s) == "weights_verification_failed"
    assert "load" not in s.backend.events
    assert "generate" not in s.backend.events
    assert refusal(s) == "weights_verification_failed"  # remembered, still refuses


def test_prohibited_prompt_extension_module_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import types

    monkeypatch.setitem(sys.modules, "dashscope", types.ModuleType("dashscope"))
    s = Setup(tmp_path)
    assert refusal(s) == "prohibited_module_loaded"
    assert s.backend.events == []


def test_backend_importing_a_remote_service_module_fails_the_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delitem(sys.modules, "dashscope", raising=False)
    s = Setup(tmp_path, backend=FakeBackend(mode="dashscope"))
    try:
        outcome = s.executor.execute(s.run, 1)
    finally:
        sys.modules.pop("dashscope", None)
    assert outcome.execution.status == "failed"
    assert outcome.failure_detail == "prohibited_module_loaded"
    assert outcome.execution.artefact is None


def test_remote_calls_are_blocked_and_recorded(tmp_path: Path) -> None:
    s = Setup(tmp_path, backend=FakeBackend(mode="remote_call"))
    outcome = s.executor.execute(s.run, 1)
    assert outcome.failure_detail == "remote_call_blocked"
    assert outcome.execution.artefact is None


def test_clip_and_vae_receive_the_same_reference_and_request_has_no_extension_switch(
    tmp_path: Path,
) -> None:
    s = Setup(tmp_path)
    s.executor.execute(s.run, 1)
    request = s.backend.requests[0]
    assert isinstance(request, GenerationRequest)
    assert not any("extend" in name for name in GenerationRequest.__dataclass_fields__)
    refs = [n for n in GenerationRequest.__dataclass_fields__ if "reference" in n or n == "img"]
    assert refs == ["reference"]  # a single reference field feeds both routes
    assert request.reference == FixedReferences().reference_for("SYN-101")
    outcome = s.executor.execute(s.plan.runs[1], 1)
    assert outcome.conditioning is not None
    assert outcome.conditioning.same_reference_on_both_routes
    assert "ref-syn" not in repr(outcome)  # the token itself is never recorded


def test_generation_settings_are_passed_through_unchanged(tmp_path: Path) -> None:
    s = Setup(tmp_path)
    run = s.plan.runs[1]
    s.executor.execute(run, 1)
    request = s.backend.requests[0]
    m = s.manifest
    assert (request.seed, request.frame_count, request.sample_shift) == (run.seed, 9, 3.0)
    assert (request.sample_solver, request.sampling_steps, request.guide_scale) == ("unipc", 2, 5.0)
    assert request.max_area == 480 * 832
    assert request.offload_model is m.offload_model
    assert request.deadline_seconds == 60.0
    assert request.output_uri == f"{ARTEFACT_BASE}/{run.run_id}/attempt-01.mp4"


@pytest.mark.parametrize(
    "mode",
    ["vae_other_reference", "cfg_y_differs", "cfg_clip_differs", "cfg_order"],
)
def test_conditioning_violations_fail_the_attempt_without_an_artefact(
    tmp_path: Path, mode: str
) -> None:
    s = Setup(tmp_path, backend=FakeBackend(mode=mode))
    outcome = s.executor.execute(s.run, 1)
    assert outcome.execution.status == "failed"
    assert outcome.failure_detail == "conditioning_contract_violation"
    assert outcome.execution.artefact is None
    assert outcome.conditioning is None
    assert outcome.cleanup_ok


@pytest.mark.parametrize(
    ("mode", "detail", "category"),
    [
        ("load_error", "model_load_error", "executor_error"),
        ("error", "generation_error", "executor_error"),
        ("timeout", "timeout", "timeout"),
        ("oom", "resource_exhausted", "resource_exhausted"),
    ],
)
def test_failures_are_categorised_without_messages(
    tmp_path: Path, mode: str, detail: str, category: str
) -> None:
    s = Setup(tmp_path, backend=FakeBackend(mode=mode))
    outcome = s.executor.execute(s.run, 1)
    assert outcome.execution.status == "failed"
    assert (outcome.failure_detail, outcome.execution.failure_category) == (detail, category)
    assert outcome.execution.artefact is None
    assert outcome.conditioning is None
    assert "cleanup" in s.backend.events
    assert "secret" not in repr(outcome)


@pytest.mark.parametrize("reason", ["budget_stop", "operator_abort"])
def test_stop_signal_interrupts_the_attempt(tmp_path: Path, reason: str) -> None:
    s = Setup(tmp_path, stop=FakeStop(reason))  # type: ignore[arg-type]
    outcome = s.executor.execute(s.run, 1)
    assert outcome.failure_detail == reason
    assert outcome.execution.artefact is None
    assert "cleanup" in s.backend.events


def test_keyboard_interrupt_is_recorded_and_cleanup_runs(tmp_path: Path) -> None:
    class Interrupting(FakeBackend):
        def generate(self, request, stop):
            raise KeyboardInterrupt

    s = Setup(tmp_path, backend=Interrupting())
    outcome = s.executor.execute(s.run, 1)
    assert outcome.failure_detail == "operator_abort"
    assert "cleanup" in s.backend.events


def test_cleanup_failure_is_reported_not_swallowed(tmp_path: Path) -> None:
    s = Setup(tmp_path, backend=FakeBackend(mode="cleanup_error"))
    outcome = s.executor.execute(s.run, 1)
    assert outcome.cleanup_ok is False


def test_attempts_are_never_reused(tmp_path: Path) -> None:
    s = Setup(tmp_path)
    s.executor.execute(s.run, 1)
    with pytest.raises(ValueError, match="never overwritten"):
        s.executor.execute(s.run, 1)
    outcome = s.executor.execute(s.run, 2)
    assert outcome.execution.artefact is not None
    assert outcome.execution.artefact.uri.endswith("attempt-02.mp4")


def test_missing_reference_refuses_that_run_only(tmp_path: Path) -> None:
    s = Setup(tmp_path, references=FixedReferences(missing={"SYN-101"}))
    assert refusal(s) == "invalid_input"
    assert s.executor.execute(s.plan.runs[2], 1).execution.status == "succeeded"


def test_close_unloads_once_and_is_a_context_manager(tmp_path: Path) -> None:
    s = Setup(tmp_path)
    with s.executor:
        s.executor.execute(s.run, 1)
    s.executor.close()
    assert s.backend.events.count("close") == 1


def test_weights_are_hashed_once_and_load_gets_the_verified_token(tmp_path: Path) -> None:
    s = Setup(tmp_path)
    s.executor.execute(s.plan.runs[0], 1)
    s.executor.execute(s.plan.runs[1], 1)
    assert s.backend.events.count("load") == 1
    assert len(s.backend.loaded_with) == 1
    assert s.backend.loaded_with[0].files_sha256


def test_importing_the_baseline_package_loads_no_ml_or_network_modules() -> None:
    import subprocess

    code = (
        "import sys, frp.baseline.executor, frp.baseline.upstream, frp.baseline.orchestrator;"
        "bad = [m for m in ('torch','wan','dashscope','cv2','PIL','huggingface_hub','requests',"
        "'transformers','numpy') if m in sys.modules];"
        "print(bad)"
    )
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert done.stdout.strip() == "[]"


def test_source_commit_constant_is_the_reviewed_pin() -> None:
    assert SOURCE_COMMIT == "9737cba9c1c3c4d04b33fcad41c111989865d315"
