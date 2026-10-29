"""Shared synthetic, non-biometric fixtures. No real people, images or model data."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from frp.manifest import parse_manifest
from frp.results import ResultSet, parse_result_set_json
from frp.simulation import simulate_experiment

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_MANIFEST = REPO_ROOT / "examples" / "manifests" / "synthetic-dry-run.yaml"

_BASE: dict[str, Any] = {
    "schema_version": "1.0",
    "experiment_id": "FRP-TEST-001",
    "status": "planned",
    "variants": ["A", "B", "C", "D"],
    "identities": [{"pseudonym": "SYN-001"}, {"pseudonym": "SYN-002"}],
    "prompts": [
        {"id": "P01", "text": "Synthetic test prompt one."},
        {"id": "P02", "text": "Synthetic test prompt two."},
    ],
    "seeds": [7, 11, 13],
    "upstream_repository": "Wan-Video/Wan2.1",
    "upstream_commit_sha": None,
    "checkpoint": "Wan-AI/Wan2.1-I2V-14B-480P",
    "checkpoint_hashes": None,
    "model_license_reviewed": False,
    "consent_record_location": "private_only",
    "number_of_identities": None,
    "image_count_per_identity": 1,
    "prompt_template_version": None,
    "alteration_method_version": None,
    "alteration_parameters": None,
    "sampler": None,
    "sampling_steps": None,
    "guidance_scale": None,
    "frame_count": None,
    "resolution": None,
    "precision": None,
    "face_evaluator_revision": None,
    "face_detection_settings": None,
    "calibration_dataset_version": None,
    "frame_indices": None,
    "quality_rubric_version": None,
    "analysis_plan_version": None,
    "gpu_model": None,
    "software_environment_hash": None,
}

# Syntactically valid but fictitious values used only to exercise "ready" code paths.
_READY_OVERRIDES: dict[str, Any] = {
    "upstream_commit_sha": "0" * 40,
    "checkpoint_hashes": {"fixture-shard.bin": "a" * 64},
    "model_license_reviewed": True,
    "number_of_identities": 2,
    "prompt_template_version": "test-v0",
    "alteration_method_version": "test-v0",
    "alteration_parameters": {"kind": "fixture", "strength": 1.0},
    "sampler": "fixture-sampler",
    "sampling_steps": 4,
    "guidance_scale": 1.5,
    "frame_count": 81,
    "resolution": "832*480",
    "precision": "fixture-precision",
    "face_evaluator_revision": "fixture-evaluator",
    "face_detection_settings": {"threshold": 0.5},
    "calibration_dataset_version": "fixture-calibration",
    "frame_indices": [0, 20, 40, 60, 80],
    "quality_rubric_version": "fixture-rubric",
    "analysis_plan_version": "fixture-analysis",
    "gpu_model": "fixture-gpu",
    "software_environment_hash": "fixture-env",
}


@pytest.fixture
def manifest_data() -> dict[str, Any]:
    """A valid planning manifest with all execution fields explicitly unset."""
    return copy.deepcopy(_BASE)


@pytest.fixture
def ready_manifest_data() -> dict[str, Any]:
    """A valid manifest with every execution field set to fictitious fixture values."""
    return copy.deepcopy(_BASE) | copy.deepcopy(_READY_OVERRIDES)


@pytest.fixture
def write_manifest(tmp_path: Path):
    def _write(data: dict[str, Any] | str, name: str = "manifest.yaml") -> Path:
        path = tmp_path / name
        text = data if isinstance(data, str) else yaml.safe_dump(data, sort_keys=False)
        path.write_text(text, encoding="utf-8")
        return path

    return _write


@pytest.fixture
def small_manifest_data() -> dict[str, Any]:
    """3 identities x 1 prompt x 2 seeds = 6 trial groups (groups 1-2 are identity 1, etc.)."""
    data = copy.deepcopy(_BASE)
    data["identities"] = [{"pseudonym": f"SYN-00{i}"} for i in (1, 2, 3)]
    data["prompts"] = data["prompts"][:1]
    data["seeds"] = [1, 2]
    data["frame_indices"] = [0, 10, 20]
    return data


def results_dict(manifest_data: dict[str, Any], scenario: str = "all-valid") -> dict[str, Any]:
    """JSON-ready dict of a simulated ResultSet, for editing in schema/aggregation tests."""
    return simulate_experiment(parse_manifest(manifest_data), scenario).model_dump(mode="json")


def load_results(data: dict[str, Any]) -> ResultSet:
    return parse_result_set_json(json.dumps(data))


def find_run(data: dict[str, Any], group: int, variant: str) -> dict[str, Any]:
    return next(r for r in data["runs"] if r["group_index"] == group and r["variant"] == variant)


def set_frames(run: dict[str, Any], *values: float | str) -> None:
    """Replace a run's frames: a float is a valid face with that similarity, a str a status."""
    run["frames"] = [
        {
            "frame_index": frame["frame_index"],
            "face_status": "valid" if isinstance(value, float) else value,
            "similarity": value if isinstance(value, float) else None,
        }
        for frame, value in zip(run["frames"], values, strict=True)
    ]


def fail_run(run: dict[str, Any]) -> None:
    run["execution"] = {
        "status": "failed",
        "artefact": None,
        "failure_category": "other",
        "gpu_seconds": None,
    }
    set_frames(run, *["not_evaluated"] * len(run["frames"]))
    run["quality"] = {"status": "not_evaluated", "score": None}
