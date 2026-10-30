"""Baseline manifest and plan contracts: strictness, roles, splits, ids, frame bounds."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from frp.baseline.manifest import (
    baseline_controls_sha256,
    identity_overlap,
    load_baseline_manifest,
    parse_baseline_manifest,
    parse_baseline_manifest_text,
    unset_execution_fields,
)
from frp.baseline.planner import (
    BaselinePlanError,
    generate_baseline_plan,
    make_baseline_run_id,
    verify_baseline_plan,
)
from frp.manifest import ManifestError, parse_manifest
from tests.baseline_support import EXAMPLE_BASELINE, example_data, ready_data
from tests.conftest import EXAMPLE_MANIFEST


def _problems(data: Any) -> str:
    with pytest.raises(ManifestError) as excinfo:
        parse_baseline_manifest(data)
    return "; ".join(excinfo.value.problems)


def test_example_is_valid_but_not_execution_ready() -> None:
    manifest = load_baseline_manifest(EXAMPLE_BASELINE)
    unset = unset_execution_fields(manifest)
    assert "checkpoint_hashes" in unset
    assert "software_environment_hash" in unset
    assert "frame_count" in unset  # unset values are preserved in planning mode


def test_a_complete_manifest_has_nothing_unset() -> None:
    assert unset_execution_fields(parse_baseline_manifest(ready_data({"f.bin": "a" * 64}))) == []


def test_baseline_and_ablation_manifests_never_validate_as_each_other() -> None:
    with pytest.raises(ManifestError):
        parse_manifest(example_data())
    ablation = _ablation_data()
    with pytest.raises(ManifestError):
        parse_baseline_manifest(ablation)


def _ablation_data() -> dict[str, Any]:
    import yaml

    return yaml.safe_load(EXAMPLE_MANIFEST.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("use_prompt_extend", True),
        ("clip_conditioning", "altered"),
        ("vae_first_frame_conditioning", "altered"),
        ("adapters", "lora"),
        ("remote_inference_services", "dashscope"),
        ("artefact_storage", "public"),
        ("generator", "random"),
        ("negative_prompt_policy", "custom"),
        ("protocol", "wan2.1-i2v-clip-vae-2x2"),
        ("schema_version", "1.0"),
        ("upstream_repository", "Wan-Video/Wan2.2"),
        ("checkpoint", "Wan-AI/Wan2.2-I2V-A14B"),
        ("upstream_commit_sha", "a" * 40),
        ("checkpoint_revision", "b" * 40),
        ("resolution", "720*1280"),
        ("sampler", "euler"),
        ("frame_count", 80),
        ("seeds", [-1]),
        ("seeds", [1, 1]),
    ],
)
def test_controls_are_frozen_and_invalid_values_rejected(field: str, value: Any) -> None:
    data = example_data()
    data[field] = value
    assert _problems(data)


@pytest.mark.parametrize("field", ["use_prompt_extend", "clip_conditioning", "adapters"])
def test_decided_controls_cannot_be_omitted_or_null(field: str) -> None:
    data = example_data()
    del data[field]
    assert _problems(data)
    data[field] = None
    assert _problems(data)


def test_prompt_extension_has_no_override_and_unknown_keys_are_rejected() -> None:
    data = example_data()
    data["prompt_extend_method"] = "local_qwen"
    assert "unknown key" in _problems(data)
    assert "local_qwen" not in _problems(data)


def test_errors_do_not_echo_values() -> None:
    data = example_data()
    data["prompts"][0]["text"] = "TODO"
    data["checkpoint_hashes"] = {"../escape.bin": "a" * 64}
    problems = _problems(data)
    assert "escape" not in problems


def test_frame_indices_bounds_and_order() -> None:
    assert "frame_indices" in _problems(ready_data({"f": "a" * 64}, frame_indices=[0, 9]))
    assert "frame_indices" in _problems(ready_data({"f": "a" * 64}, frame_indices=[4, 4]))
    assert "frame_indices" in _problems(ready_data({"f": "a" * 64}, frame_indices=[-1]))


def test_placeholders_and_malformed_yaml_are_rejected() -> None:
    data = example_data()
    data["gpu_model"] = "TBD"
    assert "placeholder" in _problems(data)
    with pytest.raises(ManifestError):
        parse_baseline_manifest_text("a: 1\na: 2\n")


def test_roles_constrain_identity_splits() -> None:
    data = example_data()
    data["run_role"] = "calibration"
    assert "identity_split" in _problems(data)  # identities are marked evaluation
    for identity in data["identities"]:
        identity["identity_split"] = "calibration"
    parse_baseline_manifest(data)
    data = example_data()
    data["run_role"] = "smoke"
    assert "smoke" in _problems(data)
    data["identities"] = [{"pseudonym": "SYN-101", "identity_split": None}]
    data["seeds"] = [7]
    parse_baseline_manifest(data)


def test_calibration_and_evaluation_identity_overlap_is_detected_without_names() -> None:
    evaluation = parse_baseline_manifest(example_data())
    data = example_data()
    data["run_role"] = "calibration"
    data["identities"] = [
        {"pseudonym": "SYN-101", "identity_split": "calibration"},
        {"pseudonym": "SYN-900", "identity_split": "calibration"},
    ]
    calibration = parse_baseline_manifest(data)
    problems = identity_overlap(calibration, evaluation)
    assert problems
    assert "SYN-101" not in "".join(problems)
    data["identities"][0]["pseudonym"] = "SYN-901"
    assert identity_overlap(parse_baseline_manifest(data), evaluation) == []


def test_plan_is_identities_times_prompts_times_seeds_with_stable_ids() -> None:
    data = example_data()
    data["prompts"].append({"id": "P02", "text": "A person nods once."})
    manifest = parse_baseline_manifest(data)
    plan = generate_baseline_plan(manifest)
    assert len(plan.runs) == 2 * 2 * 2
    assert [r.run_id for r in plan.runs] == [
        make_baseline_run_id(manifest.experiment_id, n) for n in range(1, 9)
    ]
    assert not any(r.run_id.endswith(("-A", "-B", "-C", "-D")) for r in plan.runs)
    assert generate_baseline_plan(manifest) == plan  # reproducible
    assert {(r.clip_conditioning, r.vae_first_frame_conditioning) for r in plan.runs} == {
        ("original", "original")
    }


def test_run_ids_do_not_depend_on_identity_seed_or_prompt_content() -> None:
    first = generate_baseline_plan(parse_baseline_manifest(example_data()))
    data = example_data()
    data["seeds"] = [5, 6]
    second = generate_baseline_plan(parse_baseline_manifest(data))
    assert [r.run_id for r in first.runs] == [r.run_id for r in second.runs]


def test_controls_hash_ignores_planning_inputs_but_tracks_controls() -> None:
    base = parse_baseline_manifest(example_data())
    data = example_data()
    data["seeds"] = [9]
    assert baseline_controls_sha256(parse_baseline_manifest(data)) == baseline_controls_sha256(base)
    data = example_data()
    data["sampling_steps"] = 10
    assert baseline_controls_sha256(parse_baseline_manifest(data)) != baseline_controls_sha256(base)


def test_plan_verification_catches_tampering() -> None:
    import dataclasses

    manifest = parse_baseline_manifest(example_data())
    plan = generate_baseline_plan(manifest)
    runs = list(plan.runs)
    runs[1] = dataclasses.replace(runs[1], run_id=runs[0].run_id)
    with pytest.raises(BaselinePlanError):
        verify_baseline_plan(dataclasses.replace(plan, runs=tuple(runs)), manifest)
    runs = list(plan.runs)
    runs[0] = dataclasses.replace(runs[0], vae_first_frame_conditioning="altered")  # type: ignore[arg-type]
    with pytest.raises(BaselinePlanError, match="original reference"):
        verify_baseline_plan(dataclasses.replace(plan, runs=tuple(runs)))
    with pytest.raises(BaselinePlanError):
        verify_baseline_plan(dataclasses.replace(plan, runs=plan.runs[:-1]), manifest)


def test_manifest_is_immutable() -> None:
    manifest = parse_baseline_manifest(copy.deepcopy(example_data()))
    with pytest.raises(Exception, match="frozen"):
        manifest.use_prompt_extend = True  # type: ignore[misc]
