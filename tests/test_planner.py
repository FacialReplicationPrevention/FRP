from __future__ import annotations

import dataclasses

import pytest

from frp.manifest import parse_manifest
from frp.planner import (
    PlanInvariantError,
    RunPlan,
    generate_run_plan,
    make_run_id,
    verify_run_plan,
)
from frp.variants import (
    VARIANT_CONDITIONING,
    VARIANT_ORDER,
    ConditioningSource,
    Variant,
)

ORIGINAL = ConditioningSource.ORIGINAL
ALTERED = ConditioningSource.ALTERED


def test_variant_mapping_matches_experiment_002():
    assert VARIANT_ORDER == (Variant.A, Variant.B, Variant.C, Variant.D)
    assert VARIANT_CONDITIONING[Variant.A] == (ORIGINAL, ORIGINAL)
    assert VARIANT_CONDITIONING[Variant.B] == (ALTERED, ORIGINAL)
    assert VARIANT_CONDITIONING[Variant.C] == (ORIGINAL, ALTERED)
    assert VARIANT_CONDITIONING[Variant.D] == (ALTERED, ALTERED)
    with pytest.raises(TypeError):
        VARIANT_CONDITIONING[Variant.A] = (ALTERED, ALTERED)  # type: ignore[index]


def test_each_tuple_yields_exactly_four_runs_in_order(manifest_data):
    manifest = parse_manifest(manifest_data)
    plan = generate_run_plan(manifest)

    assert len(plan.groups) == 2 * 2 * 3
    assert len(plan.runs) == 2 * 2 * 3 * 4
    for group in plan.groups:
        assert [run.variant for run in group.runs] == list(VARIANT_ORDER)
        assert {run.identity_pseudonym for run in group.runs} == {group.identity_pseudonym}
        assert {run.prompt_id for run in group.runs} == {group.prompt_id}
        assert {run.seed for run in group.runs} == {group.seed}
        assert {run.generation_controls_sha256 for run in group.runs} == {
            plan.generation_controls_sha256
        }


def test_groups_follow_identity_prompt_seed_order(manifest_data):
    plan = generate_run_plan(parse_manifest(manifest_data))
    keys = [(g.identity_pseudonym, g.prompt_id, g.seed) for g in plan.groups]
    assert keys[:4] == [
        ("SYN-001", "P01", 7),
        ("SYN-001", "P01", 11),
        ("SYN-001", "P01", 13),
        ("SYN-001", "P02", 7),
    ]
    assert keys[-1] == ("SYN-002", "P02", 13)
    assert [g.group_index for g in plan.groups] == list(range(1, 13))


def test_paired_runs_differ_only_in_selected_conditioning_route(manifest_data):
    plan = generate_run_plan(parse_manifest(manifest_data))
    a, b, c, d = plan.groups[0].runs
    ignore = {"run_id", "variant", "clip_conditioning", "vae_first_frame_conditioning"}

    def shared(run):
        return {k: v for k, v in dataclasses.asdict(run).items() if k not in ignore}

    assert shared(a) == shared(b) == shared(c) == shared(d)
    assert (b.clip_conditioning, b.vae_first_frame_conditioning) == (ALTERED, ORIGINAL)
    assert (c.clip_conditioning, c.vae_first_frame_conditioning) == (ORIGINAL, ALTERED)
    assert (d.clip_conditioning, d.vae_first_frame_conditioning) == (ALTERED, ALTERED)


def test_plan_is_deterministic_and_independent_of_variant_listing(manifest_data):
    first = generate_run_plan(parse_manifest(manifest_data))
    second = generate_run_plan(parse_manifest(manifest_data))
    assert first == second

    manifest_data["variants"] = ["C", "A", "D", "B"]
    reordered = generate_run_plan(parse_manifest(manifest_data))
    assert reordered.runs == first.runs


def test_run_ids_are_unique_and_non_identifying(manifest_data):
    plan = generate_run_plan(parse_manifest(manifest_data))
    run_ids = [run.run_id for run in plan.runs]
    assert len(set(run_ids)) == len(run_ids)
    assert run_ids[0] == make_run_id("FRP-TEST-001", 1, Variant.A) == "FRP-TEST-001-G0001-A"
    for run in plan.runs:
        assert run.identity_pseudonym not in run.run_id


def _tamper_run(plan: RunPlan, group_pos: int, run_pos: int, **changes) -> RunPlan:
    group = plan.groups[group_pos]
    runs = list(group.runs)
    runs[run_pos] = dataclasses.replace(runs[run_pos], **changes)
    groups = list(plan.groups)
    groups[group_pos] = dataclasses.replace(group, runs=tuple(runs))
    return dataclasses.replace(plan, groups=tuple(groups))


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"seed": 999}, "seed does not match its group"),
        ({"prompt_id": "P02"}, "prompt does not match its group"),
        ({"prompt_index": 2}, "prompt does not match its group"),
        ({"identity_pseudonym": "SYN-002"}, "identity does not match its group"),
        ({"generation_controls_sha256": "f" * 64}, "generation controls differ"),
        ({"clip_conditioning": ORIGINAL}, "conditioning does not match variant B"),
        ({"vae_first_frame_conditioning": ALTERED}, "conditioning does not match variant B"),
        ({"variant": Variant.C}, "expected variants A,B,C,D in order"),
        ({"group_index": 2}, "group_index mismatch"),
        ({"run_id": "FRP-TEST-001-G0001-A"}, "run ids are not unique"),
    ],
)
def test_verify_detects_broken_pairing(manifest_data, changes, expected):
    plan = generate_run_plan(parse_manifest(manifest_data))
    tampered = _tamper_run(plan, 0, 1, **changes)
    with pytest.raises(PlanInvariantError) as info:
        verify_run_plan(tampered)
    assert any(expected in problem for problem in info.value.problems)


def test_verify_detects_missing_variant(manifest_data):
    plan = generate_run_plan(parse_manifest(manifest_data))
    group = dataclasses.replace(plan.groups[0], runs=plan.groups[0].runs[:3])
    tampered = dataclasses.replace(plan, groups=(group, *plan.groups[1:]))
    with pytest.raises(PlanInvariantError, match="expected variants A,B,C,D in order, found A,B,C"):
        verify_run_plan(tampered)


def test_verify_detects_duplicate_and_missing_groups(manifest_data):
    manifest = parse_manifest(manifest_data)
    plan = generate_run_plan(manifest)
    duplicated = dataclasses.replace(plan, groups=(plan.groups[0], plan.groups[0]))
    with pytest.raises(PlanInvariantError) as info:
        verify_run_plan(duplicated)
    problems = "\n".join(info.value.problems)
    assert "group at position 2 has group_index 1" in problems
    assert "same identity/prompt/seed tuple appears in more than one group" in problems

    truncated = dataclasses.replace(plan, groups=plan.groups[:-1])
    verify_run_plan(truncated)
    with pytest.raises(PlanInvariantError, match="do not match the manifest"):
        verify_run_plan(truncated, manifest)


def test_verify_detects_plan_from_different_manifest(manifest_data):
    plan = generate_run_plan(parse_manifest(manifest_data))
    manifest_data["sampler"] = "different-sampler"
    with pytest.raises(PlanInvariantError, match="generation controls hash does not match"):
        verify_run_plan(plan, parse_manifest(manifest_data))


@pytest.mark.parametrize(
    "bad_run_id",
    ["FRP-TEST-001-G0001-X", "FRP-TEST-001-G0099-B", "OTHER-EXP-G0001-B", "run-0002"],
)
def test_verify_detects_unique_but_incorrect_run_id(manifest_data, bad_run_id):
    plan = generate_run_plan(parse_manifest(manifest_data))
    tampered = _tamper_run(plan, 0, 1, run_id=bad_run_id)
    assert len({run.run_id for run in tampered.runs}) == len(tampered.runs)
    with pytest.raises(PlanInvariantError) as info:
        verify_run_plan(tampered)
    assert info.value.problems == (
        f"group 1 run {bad_run_id}: run id does not match the expected FRP-TEST-001-G0001-B",
    )


def test_verify_detects_run_ids_swapped_within_group(manifest_data):
    plan = generate_run_plan(parse_manifest(manifest_data))
    a, b = plan.groups[0].runs[:2]
    tampered = _tamper_run(_tamper_run(plan, 0, 0, run_id=b.run_id), 0, 1, run_id=a.run_id)
    with pytest.raises(PlanInvariantError) as info:
        verify_run_plan(tampered)
    problems = "\n".join(info.value.problems)
    assert "run id does not match the expected FRP-TEST-001-G0001-A" in problems
    assert "run id does not match the expected FRP-TEST-001-G0001-B" in problems
    assert "not unique" not in problems


def test_verify_detects_run_ids_from_another_experiment(manifest_data):
    plan = generate_run_plan(parse_manifest(manifest_data))
    renamed = dataclasses.replace(plan, experiment_id="FRP-TEST-002")
    with pytest.raises(PlanInvariantError) as info:
        verify_run_plan(renamed, parse_manifest(manifest_data))
    problems = "\n".join(info.value.problems)
    assert "plan experiment_id does not match the manifest" in problems
    assert "run id does not match the expected FRP-TEST-002-G0001-A" in problems


def test_prompt_and_identity_indices_follow_manifest_order(manifest_data):
    plan = generate_run_plan(parse_manifest(manifest_data))
    indices = [(g.identity_index, g.prompt_index, g.seed) for g in plan.groups]
    assert indices[:4] == [(1, 1, 7), (1, 1, 11), (1, 1, 13), (1, 2, 7)]
    assert indices[-1] == (2, 2, 13)
