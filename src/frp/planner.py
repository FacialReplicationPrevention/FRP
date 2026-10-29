"""Deterministic A/B/C/D run-plan generation for paired conditioning-ablation trials.

A *trial group* is one (identity pseudonym, prompt id, seed) tuple. Each group contains exactly
four planned runs in the fixed order A, B, C, D that differ **only** in which source image feeds
the CLIP and VAE first-frame conditioning routes. No inference is performed here.
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from dataclasses import dataclass

from frp.manifest import ExperimentManifest, generation_controls_sha256, manifest_sha256
from frp.variants import VARIANT_CONDITIONING, VARIANT_ORDER, ConditioningSource, Variant


class PlanInvariantError(Exception):
    """Raised when a run plan violates an A/B/C/D pairing invariant."""

    def __init__(self, problems: Sequence[str]) -> None:
        self.problems = tuple(problems)
        super().__init__("; ".join(self.problems))


@dataclass(frozen=True, slots=True)
class PlannedRun:
    run_id: str
    group_index: int
    identity_index: int
    identity_pseudonym: str
    prompt_index: int
    prompt_id: str
    seed: int
    variant: Variant
    clip_conditioning: ConditioningSource
    vae_first_frame_conditioning: ConditioningSource
    generation_controls_sha256: str


@dataclass(frozen=True, slots=True)
class TrialGroup:
    group_index: int
    identity_index: int
    identity_pseudonym: str
    prompt_index: int
    prompt_id: str
    seed: int
    runs: tuple[PlannedRun, ...]


@dataclass(frozen=True, slots=True)
class RunPlan:
    experiment_id: str
    schema_version: str
    manifest_sha256: str
    generation_controls_sha256: str
    groups: tuple[TrialGroup, ...]

    @property
    def runs(self) -> tuple[PlannedRun, ...]:
        return tuple(run for group in self.groups for run in group.runs)


def make_run_id(experiment_id: str, group_index: int, variant: Variant) -> str:
    """Deterministic, non-identifying run id (contains no pseudonym, prompt text or seed)."""
    return f"{experiment_id}-G{group_index:04d}-{variant.value}"


def generate_run_plan(manifest: ExperimentManifest) -> RunPlan:
    """Build the paired run plan: identities x prompts x seeds (manifest order) x A/B/C/D.

    The variant order is always A, B, C, D regardless of the order listed in the manifest.
    The returned plan is verified with :func:`verify_run_plan` before being returned.
    """
    controls = generation_controls_sha256(manifest)
    groups = []
    tuples = itertools.product(
        enumerate(manifest.identities, 1), enumerate(manifest.prompts, 1), manifest.seeds
    )
    for group_index, ((identity_index, identity), (prompt_index, prompt), seed) in enumerate(
        tuples, 1
    ):
        runs = tuple(
            PlannedRun(
                run_id=make_run_id(manifest.experiment_id, group_index, variant),
                group_index=group_index,
                identity_index=identity_index,
                identity_pseudonym=identity.pseudonym,
                prompt_index=prompt_index,
                prompt_id=prompt.id,
                seed=seed,
                variant=variant,
                clip_conditioning=VARIANT_CONDITIONING[variant].clip,
                vae_first_frame_conditioning=VARIANT_CONDITIONING[variant].vae_first_frame,
                generation_controls_sha256=controls,
            )
            for variant in VARIANT_ORDER
        )
        groups.append(
            TrialGroup(
                group_index=group_index,
                identity_index=identity_index,
                identity_pseudonym=identity.pseudonym,
                prompt_index=prompt_index,
                prompt_id=prompt.id,
                seed=seed,
                runs=runs,
            )
        )
    plan = RunPlan(
        experiment_id=manifest.experiment_id,
        schema_version=manifest.schema_version,
        manifest_sha256=manifest_sha256(manifest),
        generation_controls_sha256=controls,
        groups=tuple(groups),
    )
    verify_run_plan(plan, manifest)
    return plan


def _check_group(group: TrialGroup, experiment_id: str, expected_controls: str) -> list[str]:
    where = f"group {group.group_index}"
    problems = []
    variants = tuple(run.variant for run in group.runs)
    if variants != VARIANT_ORDER:
        found = ",".join(v.value for v in variants) or "none"
        problems.append(f"{where}: expected variants A,B,C,D in order, found {found}")
    for run in group.runs:
        label = f"{where} run {run.run_id}"
        if run.group_index != group.group_index:
            problems.append(f"{label}: group_index mismatch")
        if run.run_id != make_run_id(experiment_id, group.group_index, run.variant):
            problems.append(
                f"{label}: run id does not match the expected "
                f"{make_run_id(experiment_id, group.group_index, run.variant)}"
            )
        if (run.identity_index, run.identity_pseudonym) != (
            group.identity_index,
            group.identity_pseudonym,
        ):
            problems.append(f"{label}: identity does not match its group")
        if (run.prompt_index, run.prompt_id) != (group.prompt_index, group.prompt_id):
            problems.append(f"{label}: prompt does not match its group")
        if run.seed != group.seed:
            problems.append(f"{label}: seed does not match its group")
        if run.generation_controls_sha256 != expected_controls:
            problems.append(f"{label}: generation controls differ from the plan")
        expected = VARIANT_CONDITIONING.get(run.variant)
        actual = (run.clip_conditioning, run.vae_first_frame_conditioning)
        if expected is None or actual != tuple(expected):
            problems.append(f"{label}: conditioning does not match variant {run.variant}")
    return problems


def verify_run_plan(plan: RunPlan, manifest: ExperimentManifest | None = None) -> None:
    """Raise :class:`PlanInvariantError` if any A/B/C/D pairing invariant is violated.

    Checks: four runs per group in order A-D; identical identity, prompt, seed and generation
    controls within each group; protocol-defined conditioning per variant; every run id equals
    :func:`make_run_id` for its experiment, group and variant; unique run ids and unique
    (identity, prompt, seed) tuples; consecutive group numbering. If ``manifest`` is given,
    also checks the experiment id, that the plan covers exactly the manifest's
    identity x prompt x seed product (including ordinal indices), and matching hashes.
    """
    problems: list[str] = []
    for position, group in enumerate(plan.groups, 1):
        if group.group_index != position:
            problems.append(f"group at position {position} has group_index {group.group_index}")
        problems.extend(_check_group(group, plan.experiment_id, plan.generation_controls_sha256))

    run_ids = [run.run_id for run in plan.runs]
    if len(set(run_ids)) != len(run_ids):
        problems.append("run ids are not unique")
    keys = [(g.identity_pseudonym, g.prompt_id, g.seed) for g in plan.groups]
    indexed_keys = [
        (g.identity_index, g.identity_pseudonym, g.prompt_index, g.prompt_id, g.seed)
        for g in plan.groups
    ]
    if len(set(keys)) != len(keys):
        problems.append("the same identity/prompt/seed tuple appears in more than one group")

    if manifest is not None:
        if plan.experiment_id != manifest.experiment_id:
            problems.append("plan experiment_id does not match the manifest")
        expected_keys = [
            (identity_index, identity.pseudonym, prompt_index, prompt.id, seed)
            for (identity_index, identity), (prompt_index, prompt), seed in itertools.product(
                enumerate(manifest.identities, 1), enumerate(manifest.prompts, 1), manifest.seeds
            )
        ]
        if indexed_keys != expected_keys:
            problems.append("groups do not match the manifest identity x prompt x seed product")
        if plan.generation_controls_sha256 != generation_controls_sha256(manifest):
            problems.append("plan generation controls hash does not match the manifest")
        if plan.manifest_sha256 != manifest_sha256(manifest):
            problems.append("plan manifest hash does not match the manifest")

    if problems:
        raise PlanInvariantError(problems)
