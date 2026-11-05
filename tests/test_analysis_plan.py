"""Draft analysis-plan checks: positive and negative rules, redaction. Synthetic data only."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from frp.baseline.analysis_plan import load_analysis_plan, parse_analysis_plan
from frp.manifest import ManifestError

EXAMPLE = Path(__file__).resolve().parents[1] / "examples/analysis-plans"
EXAMPLE_PLAN = EXAMPLE / "synthetic-draft-analysis-plan.yaml"


def _data() -> dict[str, Any]:
    return yaml.safe_load(EXAMPLE_PLAN.read_text(encoding="utf-8"))


def _problems(data: Any) -> str:
    with pytest.raises(ManifestError) as excinfo:
        parse_analysis_plan(data)
    return "; ".join(excinfo.value.problems)


def _with(**changes: Any) -> dict[str, Any]:
    data = copy.deepcopy(_data())
    data.update(changes)
    return data


def test_example_is_valid_and_draft() -> None:
    plan = load_analysis_plan(EXAMPLE_PLAN)
    assert plan.status == "draft"
    assert plan.min_valid_later_frames is None  # left pending, not invented


def test_smoke_plan_valid_only_without_populations() -> None:
    smoke = _with(
        claim_role="smoke",
        calibration_claim="none",
        calibration_identities=[],
        evaluation_identities=[],
    )
    assert parse_analysis_plan(smoke).claim_role == "smoke"
    assert "smoke supports no calibration" in _problems(_with(claim_role="smoke"))


def test_uncalibrated_exploratory_baseline_is_valid() -> None:
    plan = parse_analysis_plan(_with(calibration_claim="none", calibration_identities=[]))
    assert plan.calibration_claim == "none"


def test_calibrated_baseline_needs_calibration_identities() -> None:
    assert "needs calibration identities" in _problems(_with(calibration_identities=[]))
    assert "require calibration_claim calibrated" in _problems(_with(calibration_claim="none"))


def test_single_identity_cannot_support_calibration() -> None:
    assert "at least two distinct" in _problems(_with(calibration_identities=["SYN-201"]))


def test_split_overlap_rejected_without_echoing_pseudonyms() -> None:
    message = _problems(_with(evaluation_identities=["SYN-101", "SYN-201"]))
    assert "disjoint" in message
    assert "SYN-" not in message


def test_duplicate_pseudonym_rejected_without_echo() -> None:
    message = _problems(_with(evaluation_identities=["SYN-101", "SYN-101"]))
    assert "duplicate pseudonym" in message
    assert "SYN-" not in message


def test_calibration_role_shape() -> None:
    ok = _with(
        claim_role="calibration",
        calibration_claim="none",
        evaluation_identities=[],
    )
    assert parse_analysis_plan(ok).claim_role == "calibration"
    assert "calibration needs calibration identities" in _problems(_with(claim_role="calibration"))


def test_baseline_without_evaluation_identities_rejected() -> None:
    assert "needs evaluation identities" in _problems(_with(evaluation_identities=[]))


@pytest.mark.parametrize(
    ("changes", "fragment"),
    [
        ({"frame_indices": [0, 20, 81]}, "frame_indices must be < frame_count"),
        ({"frame_indices": [0, 40, 20]}, "strictly increasing"),
        ({"frame_indices": [0, 0, 20]}, "strictly increasing"),
        ({"frame_indices": [-1, 20]}, "greater than or equal to 0"),
        ({"frame_count": 80}, "4n+1"),
    ],
)
def test_frame_selection_rules(changes: dict[str, Any], fragment: str) -> None:
    assert fragment in _problems(_with(**changes))


def test_minimum_later_frames_must_be_possible() -> None:
    ok = _with(
        min_valid_later_frames=4,
        decision_states={
            "frame_indices": "proposed",
            "min_valid_later_frames": "proposed",
            "attempt_selection": "proposed",
        },
    )
    assert parse_analysis_plan(ok).min_valid_later_frames == 4
    too_many = {**ok, "min_valid_later_frames": 5}
    assert "exceeds the 4 later" in _problems(too_many)
    assert "greater than or equal to 1" in _problems({**ok, "min_valid_later_frames": 0})
    only_zero = {**ok, "frame_indices": [0], "min_valid_later_frames": 1}
    assert "exceeds the 0 later" in _problems(only_zero)


@pytest.mark.parametrize("value", ["best_attempt", "highest_similarity", "mean", ""])
def test_unsupported_attempt_selection_rejected(value: str) -> None:
    assert "value withheld" in _problems(_with(attempt_selection=value))


def test_missing_similarity_must_not_be_imputed() -> None:
    assert "value withheld" in _problems(_with(missing_similarity_policy="zero_imputation"))


@pytest.mark.parametrize("state", ["approved", "frozen", "reviewed", "final"])
def test_bogus_approved_states_rejected(state: str) -> None:
    states = {**_data()["decision_states"], "frame_indices": state}
    assert "value withheld" in _problems(_with(decision_states=states))
    assert "value withheld" in _problems(_with(status=state))


@pytest.mark.parametrize("key", ["approved_by", "approval", "ethics_approved", "frozen"])
def test_approval_keys_are_unknown_and_withheld(key: str) -> None:
    message = _problems({**_data(), key: True})
    assert "unknown key" in message
    assert key not in message


def test_placeholders_are_not_reviewed_settings() -> None:
    states = {**_data()["decision_states"], "min_valid_later_frames": "proposed"}
    assert "placeholders are not reviewed settings" in _problems(_with(decision_states=states))
    states = {**_data()["decision_states"], "attempt_selection": "pending"}
    assert "placeholders are not reviewed settings" in _problems(_with(decision_states=states))
    assert "plan_version" in _problems(_with(plan_version="TBD"))


def test_all_open_decisions_must_be_declared() -> None:
    states = {"frame_indices": "proposed", "min_valid_later_frames": "pending"}
    assert "must declare attempt_selection" in _problems(_with(decision_states=states))


def test_wrong_protocol_or_schema_rejected() -> None:
    assert "value withheld" in _problems(_with(protocol="wan2.2-i2v-baseline"))
    assert "value withheld" in _problems(_with(schema_version="1.0"))


def test_non_mapping_and_missing_file() -> None:
    assert "top level" in _problems(["a"])
    with pytest.raises(ManifestError):
        load_analysis_plan(EXAMPLE / "absent.yaml")


def test_module_imports_no_model_or_network_libraries() -> None:
    source = (Path(__file__).resolve().parents[1] / "src/frp/baseline/analysis_plan.py").read_text()
    for forbidden in ("torch", "cv2", "insightface", "requests", "urllib", "socket", "subprocess"):
        assert f"import {forbidden}" not in source
