"""Deterministic run-plan generation for the single-condition Wan 2.1 baseline.

A baseline plan is identities x prompts x seeds (manifest order), **one run per combination**.
There are no variants and no trial groups, so the A/B/C/D pairing invariants of
:mod:`frp.planner` do not apply and this module shares none of its types. Run ids are
``<EXPERIMENT_ID>-R<NNNN>``; the *attempt* is a separate index (see :mod:`frp.baseline.results`),
so a retry never reuses or overwrites a run. No inference is performed here.
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal

from frp.baseline.manifest import (
    BaselineManifest,
    baseline_controls_sha256,
    baseline_manifest_sha256,
)
from frp.baseline.protocol import BASELINE_SCHEMA_VERSION, PROTOCOL_WAN21_I2V_BASELINE, RunRole

PLAN_SCHEMA_VERSION: Final = BASELINE_SCHEMA_VERSION


class BaselinePlanError(Exception):
    """Raised when a baseline run plan violates an invariant. Messages hold no input values."""

    def __init__(self, problems: Sequence[str]) -> None:
        self.problems = tuple(problems)
        super().__init__("; ".join(self.problems))


@dataclass(frozen=True, slots=True)
class BaselinePlannedRun:
    """One planned baseline run. Holds ordinals and the pseudonym, never prompt text or images."""

    run_id: str
    run_index: int
    run_role: RunRole
    identity_index: int
    identity_pseudonym: str
    identity_split: str | None
    prompt_index: int
    prompt_id: str
    seed: int
    generation_controls_sha256: str
    clip_conditioning: Literal["original"] = "original"
    vae_first_frame_conditioning: Literal["original"] = "original"


@dataclass(frozen=True, slots=True)
class BaselinePlan:
    experiment_id: str
    schema_version: str
    protocol: str
    run_role: RunRole
    manifest_sha256: str
    generation_controls_sha256: str
    runs: tuple[BaselinePlannedRun, ...]


def make_baseline_run_id(experiment_id: str, run_index: int) -> str:
    """Deterministic, non-identifying run id (no pseudonym, prompt text, seed or variant)."""
    return f"{experiment_id}-R{run_index:04d}"


def generate_baseline_plan(manifest: BaselineManifest) -> BaselinePlan:
    """Build the plan: identities x prompts x seeds, one run each, verified before returning."""
    controls = baseline_controls_sha256(manifest)
    combinations = itertools.product(
        enumerate(manifest.identities, 1), enumerate(manifest.prompts, 1), manifest.seeds
    )
    runs = tuple(
        BaselinePlannedRun(
            run_id=make_baseline_run_id(manifest.experiment_id, run_index),
            run_index=run_index,
            run_role=manifest.run_role,
            identity_index=identity_index,
            identity_pseudonym=identity.pseudonym,
            identity_split=identity.identity_split,
            prompt_index=prompt_index,
            prompt_id=prompt.id,
            seed=seed,
            generation_controls_sha256=controls,
        )
        for run_index, ((identity_index, identity), (prompt_index, prompt), seed) in enumerate(
            combinations, 1
        )
    )
    plan = BaselinePlan(
        experiment_id=manifest.experiment_id,
        schema_version=manifest.schema_version,
        protocol=manifest.protocol,
        run_role=manifest.run_role,
        manifest_sha256=baseline_manifest_sha256(manifest),
        generation_controls_sha256=controls,
        runs=runs,
    )
    verify_baseline_plan(plan, manifest)
    return plan


def verify_baseline_plan(plan: BaselinePlan, manifest: BaselineManifest | None = None) -> None:
    """Raise :class:`BaselinePlanError` if any plan invariant is violated.

    Checks: protocol and schema; consecutive run numbering; run ids equal
    :func:`make_baseline_run_id`; unique run ids and unique (identity, prompt, seed) tuples;
    original CLIP and VAE conditioning on every run; one controls hash; role-consistent identity
    splits. With ``manifest``, also that the plan covers exactly the manifest's
    identity x prompt x seed product and that hashes and role match.
    """
    problems: list[str] = []
    if plan.protocol != PROTOCOL_WAN21_I2V_BASELINE or plan.schema_version != PLAN_SCHEMA_VERSION:
        problems.append("plan protocol or schema version is not the baseline's")
    for position, run in enumerate(plan.runs, 1):
        label = f"run {run.run_id}"
        if run.run_index != position:
            problems.append(f"run at position {position} has run_index {run.run_index}")
        if run.run_id != make_baseline_run_id(plan.experiment_id, run.run_index):
            problems.append(f"{label}: run id does not match the expected id")
        if run.run_role != plan.run_role:
            problems.append(f"{label}: run_role differs from the plan")
        if run.generation_controls_sha256 != plan.generation_controls_sha256:
            problems.append(f"{label}: generation controls differ from the plan")
        if (run.clip_conditioning, run.vae_first_frame_conditioning) != ("original", "original"):
            problems.append(
                f"{label}: baseline runs must use the original reference on both routes"
            )
    if len({run.run_id for run in plan.runs}) != len(plan.runs):
        problems.append("run ids are not unique")
    keys = [(r.identity_pseudonym, r.prompt_id, r.seed) for r in plan.runs]
    if len(set(keys)) != len(keys):
        problems.append("the same identity/prompt/seed tuple appears in more than one run")
    if not plan.runs:
        problems.append("a plan must contain at least one run")

    if manifest is not None:
        if plan.experiment_id != manifest.experiment_id or plan.run_role != manifest.run_role:
            problems.append("plan experiment_id or run_role does not match the manifest")
        expected = [
            (i_index, i.pseudonym, i.identity_split, p_index, p.id, seed)
            for (i_index, i), (p_index, p), seed in itertools.product(
                enumerate(manifest.identities, 1), enumerate(manifest.prompts, 1), manifest.seeds
            )
        ]
        actual = [
            (
                r.identity_index,
                r.identity_pseudonym,
                r.identity_split,
                r.prompt_index,
                r.prompt_id,
                r.seed,
            )
            for r in plan.runs
        ]
        if actual != expected:
            problems.append("runs do not match the manifest identity x prompt x seed product")
        if plan.generation_controls_sha256 != baseline_controls_sha256(manifest):
            problems.append("plan generation controls hash does not match the manifest")
        if plan.manifest_sha256 != baseline_manifest_sha256(manifest):
            problems.append("plan manifest hash does not match the manifest")
    if problems:
        raise BaselinePlanError(problems)


__all__ = [
    "PLAN_SCHEMA_VERSION",
    "BaselinePlan",
    "BaselinePlanError",
    "BaselinePlannedRun",
    "generate_baseline_plan",
    "make_baseline_run_id",
    "verify_baseline_plan",
]
