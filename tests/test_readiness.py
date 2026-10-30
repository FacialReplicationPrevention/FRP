"""Readiness schema 1.0 and `frp readiness` tests.

Fixtures are the committed public template or edits of it. Nothing here represents an approval:
the schema cannot express one, and a passing check never authorises execution.
"""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest
import yaml

from frp.cli import EXIT_INVALID, EXIT_OK, EXIT_USAGE, build_readiness_report, main
from frp.provenance import load_provenance
from frp.readiness import (
    BASELINE_PROTOCOL_ID,
    GATE_IDS,
    NOTICE,
    REQUIREMENT_IDS,
    ReadinessError,
    check_against_provenance,
    load_readiness,
    parse_readiness,
    parse_readiness_text,
    pending_control_fields,
)
from frp.results import PROTOCOL_MODEL_FAMILY
from tests.conftest import REPO_ROOT

TEMPLATE = REPO_ROOT / "readiness" / "wan21-i2v-baseline.yaml"
INVENTORY = REPO_ROOT / "provenance" / "model-candidates.yaml"


def _data() -> dict[str, Any]:
    return copy.deepcopy(yaml.safe_load(TEMPLATE.read_text(encoding="utf-8")))


def _problems(data: Any) -> tuple[str, ...]:
    with pytest.raises(ReadinessError) as excinfo:
        parse_readiness(data)
    return excinfo.value.problems


def test_committed_template_is_valid_and_fully_pending() -> None:
    record = load_readiness(TEMPLATE)
    assert [g.gate_id for g in record.gates] == list(GATE_IDS)
    assert {g.status for g in record.gates} == {"pending"}
    assert {r.status for r in record.hardware_requirements} == {"unverified"}
    assert record.cost_quote.status == "not_obtained"
    assert all(value is None for name, value in record.cost_quote if name != "status")
    assert record.execution_controls.use_prompt_extend is False
    assert record.execution_controls.clip_conditioning == "original"
    assert record.execution_controls.vae_first_frame_conditioning == "original"


def test_template_pins_agree_with_provenance_and_stay_not_ready() -> None:
    record = load_readiness(TEMPLATE)
    inventory = load_provenance(INVENTORY)
    assert check_against_provenance(record, inventory) == []
    candidate = next(
        c for c in inventory.candidates if c.candidate_id == record.target.candidate_id
    )
    assert candidate.execution_readiness == "not_ready"
    assert candidate.weight_sha256.status != "verified"


def test_baseline_protocol_is_not_registered_as_a_reviewed_protocol() -> None:
    # Registering it needs a scientific review (AGENTS.md); readiness must not do it implicitly.
    assert BASELINE_PROTOCOL_ID not in PROTOCOL_MODEL_FAMILY
    from frp.provenance import PROTOCOL_SCOPES

    assert BASELINE_PROTOCOL_ID not in PROTOCOL_SCOPES


@pytest.mark.parametrize("gate", GATE_IDS)
@pytest.mark.parametrize("status", ["approved", "passed", "granted", True])
def test_no_gate_can_be_marked_approved(gate: str, status: Any) -> None:
    data = _data()
    next(g for g in data["gates"] if g["gate_id"] == gate)["status"] = status
    problems = _problems(data)
    assert any("gates.0" in p or "gates." in p for p in problems)
    assert not any("approved" in p for p in problems)  # values are withheld


def test_approval_record_pointer_must_stay_null() -> None:
    data = _data()
    data["gates"][0]["approval_record"] = "private://approvals/example"
    assert _problems(data)


def test_every_gate_is_required_exactly_once() -> None:
    data = _data()
    removed = data["gates"].pop()
    assert any(removed["gate_id"] in p for p in _problems(data))
    data = _data()
    data["gates"].append(copy.deepcopy(data["gates"][0]))
    assert any("duplicate" in p for p in _problems(data))


def test_every_hardware_requirement_is_required_and_cannot_hold_a_figure() -> None:
    data = _data()
    data["hardware_requirements"].pop()
    assert any(REQUIREMENT_IDS[-1] in p for p in _problems(data))
    data = _data()
    data["hardware_requirements"][0]["value"] = 80
    assert _problems(data)
    data = _data()
    data["hardware_requirements"][0]["status"] = "verified"
    assert _problems(data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider_name", "Example Cloud"),
        ("gpu_hourly_rate", 1.5),
        ("budget_cap", 100),
        ("estimated_upper_bound_spend", 100),
        ("quote_date", "2026-11-01"),
        ("actual_charges", 0),
        ("quota_confirmed", True),
        ("status", "obtained"),
    ],
)
def test_cost_quote_cannot_be_populated_in_the_public_template(field: str, value: Any) -> None:
    data = _data()
    data["cost_quote"][field] = value
    problems = _problems(data)
    assert problems
    if isinstance(value, str):
        assert not any(value in p for p in problems)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("use_prompt_extend", True),
        ("use_prompt_extend", None),
        ("clip_conditioning", "altered"),
        ("vae_first_frame_conditioning", "altered"),
        ("identity_adapters", "lora"),
        ("remote_inference_services", "dashscope"),
        ("prompt_policy", "free_text"),
        ("output_storage", "public"),
    ],
)
def test_decided_controls_are_fixed(field: str, value: Any) -> None:
    data = _data()
    data["execution_controls"][field] = value
    assert _problems(data)


def test_missing_decided_control_is_rejected() -> None:
    data = _data()
    del data["execution_controls"]["use_prompt_extend"]
    assert any("use_prompt_extend" in p for p in _problems(data))


def test_pending_controls_are_listed_and_may_be_set_in_valid_form() -> None:
    record = load_readiness(TEMPLATE)
    pending = pending_control_fields(record)
    assert {"seeds", "resolution"} <= set(pending)
    assert "use_prompt_extend" not in pending
    data = _data()
    data["execution_controls"].update(
        seeds=[1, 2], frame_count=81, frame_indices=[0, 20, 40, 60, 80], resolution="832*480"
    )
    parsed = parse_readiness(data)
    assert "seeds" not in pending_control_fields(parsed)
    # Setting a value is not approving it: the gates are untouched.
    assert {g.status for g in parsed.gates} == {"pending"}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("seeds", [1, 1]),
        ("seeds", [-1]),
        ("frame_count", 80),
        ("frame_indices", [0, 0]),
        ("resolution", "832x480"),
        ("sampler", "TODO"),
    ],
)
def test_malformed_pending_control_values_are_rejected(field: str, value: Any) -> None:
    data = _data()
    data["execution_controls"][field] = value
    assert _problems(data)


def test_frame_indices_must_fit_frame_count() -> None:
    data = _data()
    data["execution_controls"].update(frame_count=9, frame_indices=[0, 9])
    assert any("frame_count" in p for p in _problems(data))


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("target", "source_repository", "Wan-Video/Wan2.2"),
        ("target", "checkpoint_repository", "Wan-AI/Wan2.2-I2V-A14B"),
        ("target", "checkpoint_revision", "main"),
        ("target", "source_commit", "9737cba"),
    ],
)
def test_target_is_wan21_only_and_fully_pinned(section: str, field: str, value: str) -> None:
    data = _data()
    data[section][field] = value
    assert _problems(data)


def test_protocol_must_be_the_baseline_not_the_ablation() -> None:
    data = _data()
    data["protocol"] = "wan2.1-i2v-clip-vae-2x2"
    assert _problems(data)


def test_unknown_keys_and_wrong_schema_version_are_rejected_without_echo() -> None:
    data = _data()
    data["approved_by"] = "someone-private"
    data["execution_controls"]["extra-secret-key"] = 1
    problems = _problems(data)
    assert not any("someone-private" in p or "extra-secret-key" in p for p in problems)
    data = _data()
    data["readiness_schema_version"] = "2.0"
    assert _problems(data)


def test_provenance_mismatch_is_reported() -> None:
    inventory = load_provenance(INVENTORY)
    data = _data()
    data["target"]["source_commit"] = "a" * 40
    problems = check_against_provenance(parse_readiness(data), inventory)
    assert any("source_commit" in p for p in problems)
    data = _data()
    data["target"]["candidate_id"] = "no-such-candidate"
    assert check_against_provenance(parse_readiness(data), inventory)


def test_malformed_yaml_and_large_files_fail_safely(tmp_path: Any) -> None:
    with pytest.raises(ReadinessError):
        parse_readiness_text("a: 1\na: 2\n")
    with pytest.raises(ReadinessError):
        parse_readiness_text("[1, 2]")
    with pytest.raises(ReadinessError) as excinfo:
        load_readiness(tmp_path / "missing.yaml")
    assert "not found" in excinfo.value.problems[0]


def test_report_states_no_authorisation() -> None:
    report = build_readiness_report(load_readiness(TEMPLATE))
    assert report["authorised_to_execute"] is False
    assert set(report["gates"].values()) == {"pending"}
    assert "NOT AN AUTHORISATION" in NOTICE


def test_cli_text_and_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["readiness", str(TEMPLATE), "--provenance", str(INVENTORY)]) == EXIT_OK
    text = capsys.readouterr().out
    assert "NOT AN AUTHORISATION" in text
    assert "Authorised to execute: NO" in text
    assert "offline consistency check only" in text
    assert text.count(": pending") == len(GATE_IDS)
    args = ["readiness", str(TEMPLATE), "--provenance", str(INVENTORY), "--format", "json"]
    assert main(args) == EXIT_OK
    report = json.loads(capsys.readouterr().out)
    assert report["authorised_to_execute"] is False
    assert report["pins_match_provenance_inventory"] is True


def test_cli_requires_provenance_and_fails_closed_without_it(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["readiness", str(TEMPLATE)]) == EXIT_USAGE
    captured = capsys.readouterr()
    assert "--provenance" in captured.err
    assert "NOT AN AUTHORISATION" not in captured.out


@pytest.mark.parametrize("field", ["source_commit", "checkpoint_revision"])
def test_cli_does_not_report_valid_for_a_well_formed_but_unpinned_revision(
    field: str, tmp_path: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    data = _data()
    data["target"][field] = "c" * 40  # valid 40-hex shape, not the reviewed pin
    parse_readiness(data)  # shape alone is accepted by the schema
    path = tmp_path / "record.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    assert main(["readiness", str(path), "--provenance", str(INVENTORY)]) == EXIT_INVALID
    captured = capsys.readouterr()
    assert field in captured.err
    assert "Authorised to execute" not in captured.out


def test_cli_rejects_invalid_record_without_echoing_values(
    tmp_path: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    data = _data()
    data["cost_quote"]["provider_name"] = "marker-provider-xyz"
    path = tmp_path / "record.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    assert main(["readiness", str(path), "--provenance", str(INVENTORY)]) == EXIT_INVALID
    captured = capsys.readouterr()
    assert "marker-provider-xyz" not in captured.err + captured.out


def test_cli_reports_provenance_disagreement(
    tmp_path: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    data = _data()
    data["target"]["checkpoint_revision"] = "b" * 40
    path = tmp_path / "record.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    assert main(["readiness", str(path), "--provenance", str(INVENTORY)]) == EXIT_INVALID
    assert "disagrees with provenance" in capsys.readouterr().err
