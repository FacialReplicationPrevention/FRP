"""CPU-only tests of the gated Wan 2.1 upstream adapter with a fake upstream runtime.

No torch, wan, image, weight, GPU or network is used. The fake upstream follows the pinned call
order so the adapter's wiring, refusals and cleanup can be checked; **none of these tests shows
how the real Wan 2.1 model behaves**, and every success here is labelled simulated.
"""

from __future__ import annotations

import dataclasses
import itertools
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from frp.baseline.authorisation import DenyAllAuthorisation
from frp.baseline.backend import ConditioningContractViolation, GenerationRequest, ModelLoadError
from frp.baseline.evaluation import evaluate_baseline_results
from frp.baseline.executor import Wan21BaselineExecutor
from frp.baseline.interfaces import ExecutionRefused
from frp.baseline.orchestrator import execute_baseline_plan
from frp.baseline.planner import generate_baseline_plan
from frp.baseline.results import BaselineResultValidationError
from frp.baseline.wan21_adapter import (
    WAN21_I2V_REQUIRED_FILES,
    UnsupportedConfiguration,
    Wan21UpstreamAdapter,
    configuration_problems,
    expected_geometry,
    map_request,
    reference_geometry_problem,
)
from frp.baseline.wan21_probe import ConditioningProbe
from frp.baseline.wan21_runtime import (
    RuntimeUnavailable,
    TorchWanRuntime,
    runtime_environment_problems,
    torch_version_problem,
)
from tests.baseline_support import (
    ARTEFACT_BASE,
    FakeInspector,
    FakeStop,
    FixedReferences,
    RecordingProvider,
)
from tests.test_baseline_evaluation import FixedQuality, PatternFace
from tests.wan21_support import (
    GPU,
    NEGATIVE_PROMPT,
    UPSTREAM_GENERATE_KEYWORDS,
    FakeImage,
    FakeRuntime,
    FakeTextEncoder,
    FakeWanI2V,
    StoreLocator,
    adapter_manifest,
    make_wan_checkpoint,
)

_DEFAULT: Any = object()


class Setup:
    def __init__(
        self,
        tmp_path: Path,
        *,
        runtime: Any = None,
        provider: Any = _DEFAULT,
        stop: Any = None,
        inspector: Any = None,
        timer: Any = None,
        manifest_overrides: dict[str, Any] | None = None,
        adapter_manifest_overrides: dict[str, Any] | None = None,
        extra_files: dict[str, bytes] | None = None,
    ) -> None:
        self.root = tmp_path / "ckpt"
        self.root.mkdir()
        for name, content in (extra_files or {}).items():
            (self.root / name).write_bytes(content)
        self.expected = make_wan_checkpoint(self.root)
        self.manifest = adapter_manifest(self.expected, **(manifest_overrides or {}))
        bound = self.manifest
        if adapter_manifest_overrides:
            bound = adapter_manifest(self.expected, **adapter_manifest_overrides)
        self.plan = generate_baseline_plan(self.manifest)
        self.store = tmp_path / "private-store"
        self.runtime = runtime if runtime is not None else FakeRuntime()
        self.adapter = Wan21UpstreamAdapter(
            manifest=bound,
            runtime=self.runtime,
            artefacts=StoreLocator(self.store),
            **({"timer": timer} if timer is not None else {}),
        )
        self.provider = RecordingProvider() if provider is _DEFAULT else provider
        self.executor = Wan21BaselineExecutor(
            manifest=self.manifest,
            backend=self.adapter,
            references=FixedReferences(),
            checkpoint_dir=self.root,
            source_dir=tmp_path / "src",
            artefact_base_uri=ARTEFACT_BASE,
            authorisation=self.provider,
            source_inspector=inspector or FakeInspector(),
            stop=stop,
        )

    @property
    def run(self):
        return self.plan.runs[0]

    @property
    def pipeline(self) -> FakeWanI2V:
        (pipeline,) = self.runtime.pipelines
        return pipeline

    def files(self) -> list[Path]:
        return (
            sorted(p for p in self.store.rglob("*") if not p.is_dir())
            if self.store.exists()
            else []
        )

    def refusal(self) -> str:
        with pytest.raises(ExecutionRefused) as excinfo:
            self.executor.execute(self.run, 1)
        return excinfo.value.code

    def assert_nothing_loaded_or_generated(self) -> None:
        assert "build" not in self.runtime.events  # no model load (and so no download)
        assert self.runtime.pipelines == []  # no generate call can have happened
        assert "open_reference" not in self.runtime.events  # the reference was never opened
        assert self.files() == []

    def assert_failed_without_artefact(self, outcome: Any, detail: str) -> None:
        assert outcome.execution.status == "failed"
        assert outcome.failure_detail == detail
        assert outcome.execution.artefact is None
        assert outcome.conditioning is None
        assert self.files() == []  # no video, reservation or partial file is left behind
        assert outcome.cleanup_ok
        assert "release" in self.runtime.events
        for pipeline in self.runtime.pipelines:  # instrumentation always removed
            assert isinstance(pipeline.text_encoder, FakeTextEncoder)
            assert pipeline.components() == tuple(
                getattr(pipeline, n) for n in ("text_encoder", "clip", "vae", "model")
            )


# -- success path and control mapping ----------------------------------------------------------


def test_fake_upstream_success_is_simulated_and_writes_one_private_artefact(tmp_path: Path) -> None:
    s = Setup(tmp_path)
    outcome = s.executor.execute(s.run, 1)
    assert outcome.execution.status == "succeeded", outcome.failure_detail
    assert s.adapter.info.live is False
    assert s.executor.info.simulated is True  # a fake upstream is NOT a Wan 2.1 inference
    assert s.provider.requests[0].executor_mode == "mock"
    final = s.store / s.run.run_id / "attempt-01.mp4"
    assert s.files() == [final]
    assert final.stat().st_mode & 0o777 == 0o600
    assert outcome.execution.artefact is not None
    assert outcome.execution.artefact.uri == f"{ARTEFACT_BASE}/{s.run.run_id}/attempt-01.mp4"
    assert outcome.execution.gpu_seconds is not None
    assert s.runtime.saved_fps == [16]  # cfg.sample_fps, as upstream generate.py writes it
    assert s.runtime.events.index("check_available") < s.runtime.events.index("build")
    assert s.runtime.events.index("device_name") < s.runtime.events.index("build")


def test_every_upstream_generate_argument_is_passed_explicitly_from_the_manifest(
    tmp_path: Path,
) -> None:
    s = Setup(tmp_path)
    run = s.plan.runs[1]
    s.executor.execute(run, 1)
    (call,) = s.pipeline.generate_calls
    assert set(call) == {"input_prompt", "img", *UPSTREAM_GENERATE_KEYWORDS}
    m = s.manifest
    assert call["input_prompt"] == m.prompts[run.prompt_index - 1].text
    assert call["img"] is s.runtime.image  # the single opened original reference
    assert call == call | {
        "max_area": 480 * 832,
        "frame_num": m.frame_count,
        "shift": m.sample_shift,
        "sample_solver": m.sampler,
        "sampling_steps": m.sampling_steps,
        "guide_scale": m.guidance_scale,
        "n_prompt": "",  # upstream substitutes its config default (negative_prompt_policy)
        "seed": run.seed,
        "offload_model": m.offload_model,
    }
    assert call["seed"] >= 0  # a negative seed would be replaced by a random one upstream


def test_map_request_keywords_match_the_pinned_generate_signature(tmp_path: Path) -> None:
    s = Setup(tmp_path)
    s.executor.execute(s.run, 1)
    request = _request_for(s)
    assert tuple(map_request(request, s.manifest).kwargs()) == UPSTREAM_GENERATE_KEYWORDS


def _request_for(s: Setup) -> GenerationRequest:
    return GenerationRequest(
        run_id=s.run.run_id,
        attempt_index=1,
        reference=FixedReferences().reference_for(s.run.identity_pseudonym),
        prompt_text=s.manifest.prompts[0].text,
        seed=s.run.seed,
        max_area=480 * 832,
        frame_count=9,
        sample_shift=3.0,
        sample_solver="unipc",
        sampling_steps=2,
        guide_scale=5.0,
        offload_model=False,
        output_uri=f"{ARTEFACT_BASE}/{s.run.run_id}/attempt-09.mp4",
        deadline_seconds=60.0,
    )


@pytest.mark.parametrize(
    "change",
    [
        {"max_area": 832 * 480 + 16},
        {"frame_count": 13},
        {"sample_shift": 5.0},
        {"sample_solver": "dpm++"},
        {"sampling_steps": 40},
        {"guide_scale": 6.0},
        {"offload_model": True},
        {"seed": 7},
        {"prompt_text": "an unplanned prompt"},
        {"deadline_seconds": float("inf")},
        {"deadline_seconds": 0.0},
    ],
)
def test_requests_that_differ_from_the_frozen_manifest_are_refused(
    tmp_path: Path, change: dict[str, Any]
) -> None:
    s = Setup(tmp_path)
    request = dataclasses.replace(_request_for(s), **change)
    with pytest.raises(UnsupportedConfiguration) as excinfo:
        map_request(request, s.manifest)
    assert "an unplanned prompt" not in str(excinfo.value)


def test_adapter_bound_to_another_manifest_never_calls_upstream_generate(tmp_path: Path) -> None:
    s = Setup(tmp_path, adapter_manifest_overrides={"sampling_steps": 3})
    outcome = s.executor.execute(s.run, 1)
    s.assert_failed_without_artefact(outcome, "generation_error")
    assert s.pipeline.generate_calls == []


# -- unsupported configuration: refused before anything is loaded --------------------------------


@pytest.mark.parametrize(
    "update",
    [
        {"precision": "bf16"},
        {"precision": None},
        {"use_prompt_extend": True},
        {"clip_conditioning": "altered"},
        {"vae_first_frame_conditioning": "altered"},
        {"adapters": "lora"},
        {"remote_inference_services": "dashscope"},
        {"negative_prompt_policy": "custom"},
        {"generator": "cpu"},
        {"resolution": "720*1280"},
        {"sampler": "euler"},
        {"frame_count": 8},
        {"seeds": [-1]},
        {"upstream_commit_sha": "1" * 40},
        {"checkpoint_revision": "1" * 40},
    ],
)
def test_configuration_problems_reject_unsupported_controls(
    tmp_path: Path, update: dict[str, Any]
) -> None:
    s = Setup(tmp_path)
    assert configuration_problems(s.manifest) == []
    # model_copy skips validation, modelling a manifest the schema itself would already reject.
    assert configuration_problems(s.manifest.model_copy(update=update))


def test_checkpoint_manifest_must_name_every_file_the_pinned_loaders_open(tmp_path: Path) -> None:
    s = Setup(tmp_path)
    for name in WAN21_I2V_REQUIRED_FILES:
        files = {k: v for k, v in s.expected.items() if k != name}
        assert configuration_problems(s.manifest.model_copy(update={"checkpoint_hashes": files}))


@pytest.mark.parametrize("extra", ["extra.bin", "lora/adapter.pt", "x.PKL", "m.ckpt", "y.pth"])
def test_unexpected_pickle_format_files_are_refused(tmp_path: Path, extra: str) -> None:
    s = Setup(tmp_path)
    files = {**s.expected, extra: "0" * 64}
    problems = configuration_problems(s.manifest.model_copy(update={"checkpoint_hashes": files}))
    assert problems == ["1 pickle-format file(s) beyond the three upstream .pth files"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"precision": "bf16"},
        {"precision": "fp16"},
    ],
)
def test_unsupported_precision_is_refused_before_load(
    tmp_path: Path, overrides: dict[str, Any]
) -> None:
    s = Setup(tmp_path, manifest_overrides=overrides)
    assert s.refusal() == "backend_unavailable"
    s.assert_nothing_loaded_or_generated()


def test_checkpoint_with_an_extra_pickle_is_refused_before_hashing_or_load(tmp_path: Path) -> None:
    s = Setup(tmp_path, extra_files={"extra.bin": b"synthetic"})
    assert "extra.bin" in s.manifest.checkpoint_hashes  # approved list matches the directory
    assert s.refusal() == "backend_unavailable"
    s.assert_nothing_loaded_or_generated()


# -- refusals: nothing is downloaded, loaded or generated ----------------------------------------


def test_default_executor_denies_the_adapter_without_any_runtime_activity(tmp_path: Path) -> None:
    s = Setup(tmp_path, provider=None)  # executor default: DenyAllAuthorisation
    assert s.refusal() == "not_authorised"
    assert s.runtime.events == []
    s.assert_nothing_loaded_or_generated()


@pytest.mark.parametrize(
    "override",
    [
        {"source_commit": "1" * 40},
        {"checkpoint_revision": "1" * 40},
        {"environment_sha256": "1" * 64},
        {"expected_files": {"config.json": "1" * 64}},
        {"executor_mode": "live"},
        {"run_ids": ("FRP-BASELINE-SYNTHETIC-EXAMPLE-R0099",)},
    ],
)
def test_mismatched_authorisation_refuses_before_any_runtime_activity(
    tmp_path: Path, override: dict[str, Any]
) -> None:
    s = Setup(tmp_path, provider=RecordingProvider(**override))
    assert s.refusal() == "not_authorised"
    assert s.runtime.events == []
    s.assert_nothing_loaded_or_generated()


def test_deny_all_provider_refuses(tmp_path: Path) -> None:
    s = Setup(tmp_path, provider=DenyAllAuthorisation())
    assert s.refusal() == "not_authorised"
    s.assert_nothing_loaded_or_generated()


@pytest.mark.parametrize(
    "inspector", [FakeInspector(commit="1" * 40), FakeInspector(clean=False), FakeInspector(None)]
)
def test_unpinned_or_dirty_source_refuses(tmp_path: Path, inspector: FakeInspector) -> None:
    s = Setup(tmp_path, inspector=inspector)
    assert s.refusal() == "provenance_mismatch"
    s.assert_nothing_loaded_or_generated()


def test_environment_digest_mismatch_refuses(tmp_path: Path) -> None:
    s = Setup(tmp_path, runtime=FakeRuntime(env_sha="9" * 64))
    assert s.refusal() == "provenance_mismatch"
    s.assert_nothing_loaded_or_generated()


@pytest.mark.parametrize("case", ["tampered", "missing", "extra"])
def test_weight_hash_discrepancy_refuses_before_load(tmp_path: Path, case: str) -> None:
    s = Setup(tmp_path)
    if case == "tampered":
        (s.root / "Wan2.1_VAE.pth").write_bytes(b"tampered synthetic bytes")
    elif case == "missing":
        (s.root / "config.json").unlink()
    else:
        (s.root / "unlisted.safetensors").write_bytes(b"x")
    assert s.refusal() == "weights_verification_failed"
    s.assert_nothing_loaded_or_generated()


def test_missing_optional_dependencies_refuse(tmp_path: Path) -> None:
    s = Setup(tmp_path, runtime=FakeRuntime(mode="unavailable"))
    assert s.refusal() == "backend_unavailable"
    s.assert_nothing_loaded_or_generated()


def test_prohibited_module_refuses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import types

    monkeypatch.setitem(sys.modules, "wan.utils.prompt_extend", types.ModuleType("x"))
    s = Setup(tmp_path)
    assert s.refusal() == "prohibited_module_loaded"
    assert s.runtime.events == []
    s.assert_nothing_loaded_or_generated()


def test_incomplete_manifest_refuses(tmp_path: Path) -> None:
    s = Setup(tmp_path, manifest_overrides={"precision": None})
    assert s.refusal() == "not_execution_ready"
    assert s.runtime.events == []
    s.assert_nothing_loaded_or_generated()


# -- conditioning routes --------------------------------------------------------------------------


def test_same_original_reference_reaches_clip_vae_and_both_cfg_branches(tmp_path: Path) -> None:
    s = Setup(tmp_path)
    outcome = s.executor.execute(s.run, 1)
    p = s.pipeline
    (clip_in,) = p.clip.inputs
    (vae_in,) = p.vae.inputs
    assert clip_in[0].tag == ("img", s.runtime.image.content)
    assert vae_in[0].tag == ("vae_in", s.runtime.image.content, "zeros")
    assert p.text_encoder.calls == [[s.manifest.prompts[0].text], [NEGATIVE_PROMPT]]
    calls = p.model.calls
    assert len(calls) == 2 * s.manifest.sampling_steps
    assert len({id(c["clip_fea"]) for c in calls}) == 1
    assert len({id(c["y"][0]) for c in calls}) == 1
    summary = outcome.conditioning
    assert summary is not None
    assert summary.same_reference_on_both_routes
    assert summary.branches_share_image_conditioning
    assert summary.clip_route_feeds_denoiser
    assert summary.positive_branch_calls == summary.negative_branch_calls == 2
    assert summary.clip_features.shape == (1, 257, 1280)
    assert summary.vae_first_frame_condition.shape == (20, 3, 100, 60)


@pytest.mark.parametrize(
    ("mode", "aborts_early"),
    [
        ("clip_other_image", True),
        ("vae_other_image", True),
        ("vae_nonzero_tail", True),
        ("clip_twice", True),
        ("other_prompt", True),
        ("custom_negative", True),
        ("extra_text_call", True),
        ("missing_clip", True),
        ("unknown_context", True),
        ("swap_branches", False),
        ("negative_other_y", False),
        ("negative_other_clip", False),
        ("y_not_from_vae", False),
        ("skip_negative", False),
        ("extra_step", False),
    ],
)
def test_conditioning_deviations_fail_without_writing_a_video(
    tmp_path: Path, mode: str, aborts_early: bool
) -> None:
    s = Setup(tmp_path, runtime=FakeRuntime(pipeline_mode=mode))
    outcome = s.executor.execute(s.run, 1)
    s.assert_failed_without_artefact(outcome, "conditioning_contract_violation")
    assert "save" not in s.runtime.events
    if aborts_early:  # stopped before or at the first denoiser call: no further GPU time
        assert len(s.pipeline.model.calls) <= 1


# -- geometry and output contract ----------------------------------------------------------------


def test_expected_geometry_follows_the_pinned_formula() -> None:
    area = 480 * 832
    assert expected_geometry(832, 480, area) == (832, 480)
    # Not (480, 832): in upstream's float arithmetic 399360 * (480 / 832) is 230399.99999999997,
    # so the height floors to 464. Mirrored, not corrected; unverified on real hardware.
    assert expected_geometry(480, 832, area) == (464, 832)
    assert expected_geometry(1000, 600, area) == (800, 480)
    assert expected_geometry(600, 1000, area) == (480, 800)
    for h, w in [(1000, 600), (1234, 567), (2000, 1999)]:
        out_h, out_w = expected_geometry(h, w, area)
        assert out_h * out_w <= area
        assert out_h % 16 == 0
        assert out_w % 16 == 0


@pytest.mark.parametrize(
    ("resolution", "size", "ok"),
    [
        ("480*832", (1000, 600), True),
        ("832*480", (600, 1000), True),
        ("480*832", (600, 1000), False),
        ("832*480", (1000, 600), False),
        ("480*832", (700, 700), False),
        ("480*832", (100_000, 10), False),
        ("480*832", (0, 10), False),
    ],
)
def test_reference_orientation_must_match_the_width_by_height_label(
    resolution: str, size: tuple[int, int], ok: bool
) -> None:
    problem = reference_geometry_problem(resolution, *size, 480 * 832)
    assert (problem is None) is ok


@pytest.mark.parametrize("image", [FakeImage(600, 1000), FakeImage(700, 700)])
def test_mismatched_reference_never_reaches_upstream(tmp_path: Path, image: FakeImage) -> None:
    s = Setup(tmp_path, runtime=FakeRuntime(image=image))
    outcome = s.executor.execute(s.run, 1)
    s.assert_failed_without_artefact(outcome, "generation_error")
    assert s.pipeline.generate_calls == []


@pytest.mark.parametrize("mode", ["wrong_geometry", "wrong_frames", "wrong_channels"])
def test_output_shape_violations_are_never_written(tmp_path: Path, mode: str) -> None:
    s = Setup(tmp_path, runtime=FakeRuntime(pipeline_mode=mode))
    outcome = s.executor.execute(s.run, 1)
    s.assert_failed_without_artefact(outcome, "output_contract_violation")
    assert "save" not in s.runtime.events


def test_existing_artefact_is_never_overwritten(tmp_path: Path) -> None:
    s = Setup(tmp_path)
    final = s.store / s.run.run_id / "attempt-01.mp4"
    final.parent.mkdir(parents=True)
    final.write_bytes(b"earlier synthetic attempt")
    outcome = s.executor.execute(s.run, 1)
    assert outcome.failure_detail == "generation_error"
    assert outcome.execution.artefact is None
    assert final.read_bytes() == b"earlier synthetic attempt"
    assert s.pipeline.generate_calls == []


def test_stale_partial_file_blocks_the_attempt_and_is_kept(tmp_path: Path) -> None:
    s = Setup(tmp_path)
    stale = s.store / s.run.run_id / ".attempt-01.partial.mp4"
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"left by a killed synthetic run")
    outcome = s.executor.execute(s.run, 1)
    assert outcome.failure_detail == "generation_error"
    assert s.files() == [stale]  # the reservation was removed; the stale file is untouched
    assert stale.read_bytes() == b"left by a killed synthetic run"


def test_symlinked_artefact_location_is_refused(tmp_path: Path) -> None:
    s = Setup(tmp_path)
    target = tmp_path / "elsewhere.mp4"
    final = s.store / s.run.run_id / "attempt-01.mp4"
    final.parent.mkdir(parents=True)
    final.symlink_to(target)
    outcome = s.executor.execute(s.run, 1)
    assert outcome.failure_detail == "generation_error"
    assert not target.exists()


def test_unreadable_reference_fails_without_leaking_its_location(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    s = Setup(tmp_path, runtime=FakeRuntime(mode="unreadable"))
    with caplog.at_level(logging.DEBUG):
        outcome = s.executor.execute(s.run, 1)
    s.assert_failed_without_artefact(outcome, "generation_error")
    captured = capsys.readouterr()
    for text in (repr(outcome), caplog.text, captured.out, captured.err):
        assert "secret" not in text
        assert "private-ref" not in text


def test_save_failure_leaves_no_partial_file(tmp_path: Path) -> None:
    s = Setup(tmp_path, runtime=FakeRuntime(mode="save_error"))
    outcome = s.executor.execute(s.run, 1)
    s.assert_failed_without_artefact(outcome, "generation_error")
    assert "secret" not in repr(outcome)


# -- load lifecycle ------------------------------------------------------------------------------


def test_load_accepts_only_a_verified_checkpoint_and_loads_once(tmp_path: Path) -> None:
    s = Setup(tmp_path)
    with pytest.raises(ModelLoadError):
        s.adapter.load(s.root)  # type: ignore[arg-type]
    assert "build" not in s.runtime.events
    s.executor.execute(s.plan.runs[0], 1)
    s.executor.execute(s.plan.runs[1], 1)
    assert s.runtime.events.count("build") == 1
    assert s.runtime.loaded_from[0].root == s.root
    with pytest.raises(ModelLoadError):
        s.adapter.load(s.runtime.loaded_from[0])  # already loaded


def test_gpu_model_mismatch_fails_before_building_the_pipeline(tmp_path: Path) -> None:
    s = Setup(tmp_path, runtime=FakeRuntime(device="another-synthetic-gpu"))
    outcome = s.executor.execute(s.run, 1)
    assert outcome.failure_detail == "model_load_error"
    assert "build" not in s.runtime.events
    assert s.files() == []


@pytest.mark.parametrize(
    "facts",
    [
        {"clip_dtype": "torch.float32"},
        {"param_dtype": "torch.float16"},
        {"vae_dtype": "torch.bfloat16"},
        {"t5_dtype": "torch.float32"},
        {"sample_fps": 24},
        {"vae_stride": (4, 16, 16)},
        {"patch_size": (1, 1, 1)},
        {"model_type": "t2v"},
        {"config_name": "Config: Wan FLF2V 14B"},
        {"negative_prompt": ""},
    ],
)
def test_loaded_config_differing_from_the_pinned_source_is_unloaded(
    tmp_path: Path, facts: dict[str, Any]
) -> None:
    s = Setup(tmp_path, runtime=FakeRuntime(facts=facts))
    outcome = s.executor.execute(s.run, 1)
    assert outcome.failure_detail == "model_load_error"
    assert s.pipeline.generate_calls == []
    assert s.adapter._pipeline is None
    assert "release" in s.runtime.events
    assert s.files() == []


@pytest.mark.parametrize(
    ("mode", "detail"), [("load_error", "model_load_error"), ("load_oom", "resource_exhausted")]
)
def test_load_failures_are_typed_and_message_free(tmp_path: Path, mode: str, detail: str) -> None:
    s = Setup(tmp_path, runtime=FakeRuntime(mode=mode))
    outcome = s.executor.execute(s.run, 1)
    assert outcome.failure_detail == detail
    assert outcome.execution.artefact is None
    assert "secret" not in repr(outcome)
    assert "release" in s.runtime.events
    assert s.adapter._pipeline is None


# -- generation failures, stops and cleanup ------------------------------------------------------


@pytest.mark.parametrize(
    ("mode", "detail"),
    [
        ("error", "generation_error"),
        ("oom", "resource_exhausted"),
        ("keyboard", "operator_abort"),
        ("remote_call", "remote_call_blocked"),
        ("swallowed_remote_call", "remote_call_blocked"),
    ],
)
def test_upstream_failures_are_typed_cleaned_up_and_message_free(
    tmp_path: Path,
    mode: str,
    detail: str,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    s = Setup(tmp_path, runtime=FakeRuntime(pipeline_mode=mode))
    with caplog.at_level(logging.DEBUG):
        outcome = s.executor.execute(s.run, 1)
    s.assert_failed_without_artefact(outcome, detail)
    captured = capsys.readouterr()
    for text in (repr(outcome), caplog.text, captured.out, captured.err):
        assert "secret" not in text
        assert s.manifest.prompts[0].text not in text
        assert "ref-syn" not in text


def test_remote_service_import_during_generation_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delitem(sys.modules, "dashscope", raising=False)
    s = Setup(tmp_path, runtime=FakeRuntime(pipeline_mode="dashscope"))
    try:
        outcome = s.executor.execute(s.run, 1)
    finally:
        sys.modules.pop("dashscope", None)
    s.assert_failed_without_artefact(outcome, "prohibited_module_loaded")
    assert "save" not in s.runtime.events


@pytest.mark.parametrize("reason", ["budget_stop", "operator_abort"])
def test_stop_signal_interrupts_between_denoiser_calls(tmp_path: Path, reason: str) -> None:
    # Polls: before reserving output, after opening the reference, then before each model call.
    s = Setup(tmp_path, stop=FakeStop(reason, after_calls=3))  # type: ignore[arg-type]
    outcome = s.executor.execute(s.run, 1)
    s.assert_failed_without_artefact(outcome, reason)
    assert len(s.pipeline.model.calls) == 1  # stopped mid-denoising, not after the whole run


def test_stop_before_generation_never_opens_the_reference(tmp_path: Path) -> None:
    s = Setup(tmp_path, stop=FakeStop("operator_abort"))  # type: ignore[arg-type]
    outcome = s.executor.execute(s.run, 1)
    s.assert_failed_without_artefact(outcome, "operator_abort")
    assert "open_reference" not in s.runtime.events


def test_deadline_is_enforced_inside_the_denoising_loop(tmp_path: Path) -> None:
    ticks = itertools.count(0.0, 25.0)  # 25 synthetic seconds per timer read; deadline is 60
    s = Setup(tmp_path, timer=lambda: next(ticks))
    outcome = s.executor.execute(s.run, 1)
    s.assert_failed_without_artefact(outcome, "timeout")
    assert len(s.pipeline.model.calls) < 2 * s.manifest.sampling_steps


def test_cleanup_failure_is_reported(tmp_path: Path) -> None:
    s = Setup(tmp_path, runtime=FakeRuntime(mode="release_error"))
    outcome = s.executor.execute(s.run, 1)
    assert outcome.execution.status == "succeeded"
    assert outcome.cleanup_ok is False


def test_close_releases_the_pipeline(tmp_path: Path) -> None:
    s = Setup(tmp_path)
    with s.executor:
        s.executor.execute(s.run, 1)
    assert s.adapter._pipeline is None
    assert s.runtime.events[-1] == "release"


# -- simulated labelling and the PR 3A evaluation contracts --------------------------------------


def test_results_through_a_fake_runtime_stay_simulated_for_evaluation(tmp_path: Path) -> None:
    s = Setup(tmp_path)
    results = execute_baseline_plan(
        s.plan,
        s.executor,
        frame_indices=[0, 4, 8],
        frame_count=9,
        manifest=s.manifest,
        simulation_scenario="wan21-adapter-fake-upstream",
    )
    assert results.simulated is True
    assert results.executor.simulated is True
    assert {a.execution.status for a in results.attempts} == {"succeeded"}
    face = PatternFace(("valid",) * 3, (0.5,) * 3)
    evaluated = evaluate_baseline_results(
        results, s.plan, face_evaluator=face, quality_evaluator=FixedQuality(), manifest=s.manifest
    )
    assert evaluated.simulated is True
    with pytest.raises(BaselineResultValidationError, match="simulated flags"):
        evaluate_baseline_results(
            results,
            s.plan,
            face_evaluator=PatternFace(("valid",) * 3, (0.5,) * 3, simulated=False),
            quality_evaluator=FixedQuality(simulated=False),
        )


def test_only_the_real_runtime_class_is_labelled_live(tmp_path: Path) -> None:
    class Imitation(TorchWanRuntime):
        pass

    s = Setup(tmp_path)
    real = Wan21UpstreamAdapter(
        manifest=s.manifest,
        runtime=TorchWanRuntime(source_dir=tmp_path),
        artefacts=StoreLocator(s.store),
    )
    imitation = Wan21UpstreamAdapter(
        manifest=s.manifest,
        runtime=Imitation(source_dir=tmp_path),
        artefacts=StoreLocator(s.store),
    )
    assert real.info.live is True
    assert imitation.info.live is False
    assert s.adapter.info.live is False


# -- the real runtime stays closed on CPU, in CI and in Codespaces --------------------------------


def test_real_runtime_is_refused_by_default_and_imports_nothing(tmp_path: Path) -> None:
    s = Setup(tmp_path, runtime=FakeRuntime())
    adapter = Wan21UpstreamAdapter(
        manifest=s.manifest,
        runtime=TorchWanRuntime(source_dir=tmp_path / "src", environ={}),
        artefacts=StoreLocator(s.store),
    )
    executor = Wan21BaselineExecutor(
        manifest=s.manifest,
        backend=adapter,
        references=FixedReferences(),
        checkpoint_dir=s.root,
        source_dir=tmp_path / "src",
        artefact_base_uri=ARTEFACT_BASE,
        source_inspector=FakeInspector(),
    )
    assert executor.info.simulated is False
    with pytest.raises(ExecutionRefused) as excinfo:
        executor.execute(s.run, 1)
    assert excinfo.value.code == "not_authorised"
    assert s.files() == []


def test_real_runtime_without_dependencies_or_offline_settings_is_unavailable(
    tmp_path: Path,
) -> None:
    s = Setup(tmp_path)
    adapter = Wan21UpstreamAdapter(
        manifest=s.manifest,
        runtime=TorchWanRuntime(source_dir=tmp_path / "src", environ={"CI": "true"}),
        artefacts=StoreLocator(s.store),
    )
    executor = Wan21BaselineExecutor(
        manifest=s.manifest,
        backend=adapter,
        references=FixedReferences(),
        checkpoint_dir=s.root,
        source_dir=tmp_path / "src",
        artefact_base_uri=ARTEFACT_BASE,
        authorisation=RecordingProvider(),  # test-only grant; the runtime still refuses
        source_inspector=FakeInspector(),
    )
    with pytest.raises(ExecutionRefused) as excinfo:
        executor.execute(s.run, 1)
    assert excinfo.value.code == "backend_unavailable"
    assert s.files() == []
    with pytest.raises(RuntimeUnavailable) as unavailable:
        TorchWanRuntime(source_dir=tmp_path / "src", environ={"CI": "1"}).check_available()
    problems = " ".join(unavailable.value.problems)
    assert "CI and Codespaces" in problems
    assert "HF_HUB_OFFLINE, TRANSFORMERS_OFFLINE" in problems
    assert "wan package" in problems


def test_runtime_environment_rules() -> None:
    offline = {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}
    assert runtime_environment_problems(offline) == []
    assert runtime_environment_problems({**offline, "CODESPACES": "true"})
    assert runtime_environment_problems({**offline, "GITHUB_ACTIONS": "true"})
    assert runtime_environment_problems({**offline, "TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD": "1"})
    assert runtime_environment_problems({"HF_HUB_OFFLINE": "0", "TRANSFORMERS_OFFLINE": "1"})
    secret = {**offline, "CI": "secret-token-value"}
    assert "secret-token-value" not in " ".join(runtime_environment_problems(secret))


@pytest.mark.parametrize(
    ("version", "ok"),
    [
        ("2.6.0", True),
        ("2.6.0+cu124", True),
        ("2.10.1", True),
        ("3.0", True),
        ("2.5.1+cu121", False),
        ("2.4.0", False),
        ("1.13", False),
        (None, False),
        ("dev", False),
    ],
)
def test_torch_version_must_default_to_weights_only_loading(version: str | None, ok: bool) -> None:
    assert (torch_version_problem(version) is None) is ok


def test_environment_digest_reads_metadata_without_importing_ml_packages(tmp_path: Path) -> None:
    code = (
        "import sys; from pathlib import Path;"
        "from frp.baseline.wan21_runtime import TorchWanRuntime;"
        "r = TorchWanRuntime(source_dir=Path('.'), environ={});"
        "d = r.environment_sha256(); assert d == r.environment_sha256() and len(d) == 64;"
        "print([m for m in ('torch','wan','PIL','numpy','torchvision') if m in sys.modules])"
    )
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert done.stdout.strip() == "[]"


def test_importing_the_adapter_modules_loads_no_ml_gpu_or_network_modules() -> None:
    code = (
        "import sys, frp.baseline.wan21_adapter, frp.baseline.wan21_probe,"
        " frp.baseline.wan21_runtime;"
        "bad = [m for m in ('torch','torchvision','wan','dashscope','cv2','PIL','numpy',"
        "'diffusers','transformers','huggingface_hub','requests','imageio') if m in sys.modules];"
        "print(bad)"
    )
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert done.stdout.strip() == "[]"


def test_probe_records_metadata_only(tmp_path: Path) -> None:
    s = Setup(tmp_path)
    outcome = s.executor.execute(s.run, 1)
    text = repr(outcome) + (outcome.conditioning.model_dump_json() if outcome.conditioning else "")
    for secret in (s.manifest.prompts[0].text, "ref-syn", "private-ref", NEGATIVE_PROMPT, GPU):
        assert secret not in text


# -- probe lifecycle -----------------------------------------------------------------------------


def _probe(runtime: FakeRuntime) -> ConditioningProbe:
    return ConditioningProbe(
        inspector=runtime,
        reference=runtime.reference_tensor(runtime.image),
        reference_token="ref-synthetic",  # noqa: S106 - an opaque synthetic token, not a secret
        prompt_text="synthetic prompt",
        negative_prompt=NEGATIVE_PROMPT,
        frame_count=9,
        before_denoiser_call=lambda: None,
    )


def test_probe_install_restores_everything_if_a_component_is_missing() -> None:
    runtime = FakeRuntime()
    pipeline = FakeWanI2V()
    originals = pipeline.components()
    del pipeline.vae
    probe = _probe(runtime)
    with pytest.raises(AttributeError):
        probe.install(pipeline)
    assert (pipeline.text_encoder, pipeline.clip) == originals[:2]
    assert pipeline.model is originals[3]


def test_probe_is_single_use_and_restores_originals() -> None:
    runtime = FakeRuntime()
    pipeline = FakeWanI2V()
    originals = pipeline.components()
    probe = _probe(runtime)
    probe.install(pipeline)
    assert pipeline.components() != originals
    assert pipeline.text_encoder.model is originals[0].model  # attributes are delegated
    probe.release()
    assert pipeline.components() == originals
    with pytest.raises(RuntimeError, match="single use"):
        probe.install(pipeline)


def test_probe_without_any_upstream_call_reports_a_violation() -> None:
    with pytest.raises(ConditioningContractViolation) as excinfo:
        _probe(FakeRuntime()).observation()
    assert len(excinfo.value.problems) == 4
