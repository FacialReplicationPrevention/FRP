"""Command-line interface. Dry-run planning, simulated pipeline and static provenance checks only:
never runs inference or fetches models.

Exit codes: 0 success; 1 invalid manifest, plan, results or provenance inventory; 2 usage error;
3 not ready (only with ``--require-ready``); 4 report files could not be written.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any, TextIO

from frp import __version__
from frp.aggregation import aggregate
from frp.manifest import ExperimentManifest, ManifestError, load_manifest, unset_execution_fields
from frp.planner import PlanInvariantError, PlannedRun, RunPlan, generate_run_plan
from frp.provenance import NOTICE as PROVENANCE_NOTICE
from frp.provenance import (
    Claim,
    ProvenanceError,
    ProvenanceInventory,
    load_provenance,
    pending_claims,
)
from frp.reporting import CSV_FILENAME, MARKDOWN_FILENAME, SIMULATED_BANNER, write_reports
from frp.results import ResultValidationError
from frp.simulation import DEFAULT_SCENARIO, SCENARIOS, simulate_experiment

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_USAGE = 2
EXIT_NOT_READY = 3
EXIT_OUTPUT = 4

NOTICE = (
    "DRY RUN - planning only. No model was loaded, no inference was run, no images or "
    "biometric data were processed, and no scientific outcome has been measured."
)


def _identity_label(run: PlannedRun, show_pseudonyms: bool) -> str:
    return run.identity_pseudonym if show_pseudonyms else f"identity-{run.identity_index:02d}"


def _prompt_label(run: PlannedRun, show_prompt_ids: bool) -> str:
    return run.prompt_id if show_prompt_ids else f"prompt-{run.prompt_index:02d}"


def build_dry_run_report(
    manifest: ExperimentManifest,
    plan: RunPlan,
    *,
    show_pseudonyms: bool = False,
    show_prompt_ids: bool = False,
) -> dict[str, Any]:
    """Privacy-safe dry-run summary. Never includes prompt text, image paths or embeddings.

    User-controlled identifiers (identity pseudonyms, prompt ids) are replaced by ordinal labels
    unless explicitly revealed for private debugging.
    """
    unset = unset_execution_fields(manifest)
    return {
        "notice": NOTICE,
        "dry_run": True,
        "frp_version": __version__,
        "schema_version": plan.schema_version,
        "experiment_id": plan.experiment_id,
        "status": manifest.status,
        "manifest_sha256": plan.manifest_sha256,
        "generation_controls_sha256": plan.generation_controls_sha256,
        "counts": {
            "identities": len(manifest.identities),
            "prompts": len(manifest.prompts),
            "seeds": len(manifest.seeds),
            "variants": 4,
            "trial_groups": len(plan.groups),
            "planned_runs": len(plan.runs),
        },
        "readiness": {"ready_for_execution": not unset, "unset_execution_fields": unset},
        "pseudonyms_redacted": not show_pseudonyms,
        "prompt_ids_redacted": not show_prompt_ids,
        "runs": [
            {
                "run_id": run.run_id,
                "group": run.group_index,
                "identity": _identity_label(run, show_pseudonyms),
                "prompt": _prompt_label(run, show_prompt_ids),
                "seed": run.seed,
                "variant": run.variant.value,
                "clip_conditioning": run.clip_conditioning.value,
                "vae_first_frame_conditioning": run.vae_first_frame_conditioning.value,
            }
            for run in plan.runs
        ],
    }


def _render_text(report: dict[str, Any], out: TextIO) -> None:
    counts = report["counts"]
    readiness = report["readiness"]
    lines = [
        report["notice"],
        "",
        f"Experiment:        {report['experiment_id']} (schema {report['schema_version']}, "
        f"status {report['status']})",
        f"Manifest SHA-256:  {report['manifest_sha256']}",
        f"Controls SHA-256:  {report['generation_controls_sha256']}",
        f"Identities: {counts['identities']}  Prompts: {counts['prompts']}  "
        f"Seeds: {counts['seeds']}  Variants: A,B,C,D",
        f"Trial groups: {counts['trial_groups']}  Planned runs: {counts['planned_runs']}",
        "Pairing check:     passed (each group: A,B,C,D with identical identity, prompt, seed "
        "and generation controls)",
    ]
    if readiness["ready_for_execution"]:
        lines.append(
            "Execution readiness: all execution fields are set (execution is still not implemented)"
        )
        lines.append(
            "  Note: this checks presence and format only, not consent, licence validity or "
            "hash correctness."
        )
    else:
        unset = readiness["unset_execution_fields"]
        lines.append(f"Execution readiness: NOT READY - {len(unset)} field(s) explicitly unset:")
        lines.extend(f"  - {name}" for name in unset)
    if report["pseudonyms_redacted"]:
        lines.append(
            "Identity pseudonyms are redacted to ordinal labels (--show-pseudonyms to reveal)."
        )
    if report["prompt_ids_redacted"]:
        lines.append("Prompt ids are redacted to ordinal labels (--show-prompt-ids to reveal).")
    lines.append("")
    header = ("run_id", "group", "identity", "prompt", "seed", "variant", "clip", "vae_ff")
    rows = [
        (
            r["run_id"],
            str(r["group"]),
            r["identity"],
            r["prompt"],
            str(r["seed"]),
            r["variant"],
            r["clip_conditioning"],
            r["vae_first_frame_conditioning"],
        )
        for r in report["runs"]
    ]
    widths = [max(len(row[i]) for row in (header, *rows)) for i in range(len(header))]
    for row in (header, *rows):
        lines.append(
            "  ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True)).rstrip()
        )
    out.write("\n".join(lines) + "\n")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="frp",
        description=(
            "FRP CPU-only harness. Dry-run planning, simulated pipeline and offline provenance "
            "checks only; never runs inference or downloads models."
        ),
    )
    parser.add_argument("--version", action="version", version=f"frp {__version__}")
    subcommands = parser.add_subparsers(dest="command", required=True)
    plan = subcommands.add_parser(
        "plan", help="validate a manifest and print the paired A/B/C/D run plan"
    )
    plan.add_argument("manifest", help="path to a YAML/JSON experiment manifest")
    plan.add_argument(
        "--dry-run",
        action="store_true",
        help="required: validate and plan without any inference",
    )
    plan.add_argument("--format", choices=("text", "json"), default="text")
    plan.add_argument(
        "--show-pseudonyms",
        action="store_true",
        help="print identity pseudonyms instead of ordinal labels (keep such output private)",
    )
    plan.add_argument(
        "--show-prompt-ids",
        action="store_true",
        help="print manifest prompt ids instead of ordinal labels (keep such output private)",
    )
    plan.add_argument(
        "--require-ready",
        action="store_true",
        help=(
            f"exit {EXIT_NOT_READY} if any execution field is still explicitly unset; checks "
            "presence and format only, not consent, licence validity or hash correctness"
        ),
    )
    simulate = subcommands.add_parser(
        "simulate",
        help="run the simulated pipeline on synthetic fixtures and write aggregate reports",
    )
    simulate.add_argument("manifest", help="path to a YAML/JSON experiment manifest")
    simulate.add_argument(
        "--report-dir",
        required=True,
        help=f"directory for {MARKDOWN_FILENAME} and {CSV_FILENAME} (created if missing)",
    )
    simulate.add_argument(
        "--scenario",
        choices=tuple(SCENARIOS),
        default=DEFAULT_SCENARIO,
        help=f"synthetic fixture scenario (default: {DEFAULT_SCENARIO})",
    )
    simulate.add_argument("--overwrite", action="store_true", help="replace existing report files")
    provenance = subcommands.add_parser(
        "provenance",
        help="validate a model-candidate provenance inventory offline (no network, no weights)",
    )
    provenance.add_argument("inventory", help="path to a YAML/JSON provenance inventory")
    provenance.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def _print_problems(heading: str, problems: Sequence[str]) -> None:
    print(heading, file=sys.stderr)
    for problem in problems:
        print(f"  - {problem}", file=sys.stderr)


def _simulate(args: argparse.Namespace) -> int:
    try:
        manifest = load_manifest(args.manifest)
        results = simulate_experiment(manifest, args.scenario)
    except ManifestError as exc:
        _print_problems("frp: invalid manifest:", exc.problems)
        return EXIT_INVALID
    except PlanInvariantError as exc:
        _print_problems("frp: run plan failed pairing invariants:", exc.problems)
        return EXIT_INVALID
    except ResultValidationError as exc:
        _print_problems("frp: simulated results failed validation:", exc.problems)
        return EXIT_INVALID
    summary = aggregate(results)
    try:
        write_reports(summary, args.report_dir, overwrite=args.overwrite)
    except FileExistsError:
        print(
            "frp: error: report files already exist in the report directory "
            "(pass --overwrite to replace them)",
            file=sys.stderr,
        )
        return EXIT_OUTPUT
    except OSError as exc:
        print(f"frp: error: cannot write reports ({type(exc).__name__})", file=sys.stderr)
        return EXIT_OUTPUT
    executed = sum(v.execution_counts["succeeded"] for v in summary.variants)
    print(
        "\n".join(
            (
                SIMULATED_BANNER,
                "Synthetic fixtures only: no model, image, video, face or embedding was used.",
                "",
                f"Experiment:  {summary.experiment_id} (scenario {summary.simulation_scenario})",
                f"Planned runs: {summary.planned_runs}  Simulated successes: {executed}  "
                f"Trial groups: {summary.trial_groups}",
                f"Wrote {MARKDOWN_FILENAME} and {CSV_FILENAME} to the report directory.",
            )
        )
    )
    return EXIT_OK


def _claim_summary(claim: Claim[Any]) -> dict[str, Any]:
    return {"value": claim.value, "status": claim.status, "evidence_links": len(claim.evidence)}


def build_provenance_report(inventory: ProvenanceInventory) -> dict[str, Any]:
    """Summary of a validated inventory. Statuses are as recorded, not re-verified."""
    return {
        "notice": PROVENANCE_NOTICE,
        "frp_version": __version__,
        "provenance_schema_version": inventory.provenance_schema_version,
        "inventory_id": inventory.inventory_id,
        "reviewed_on": inventory.reviewed_on.isoformat(),
        "execution_ready_candidates": 0,
        "candidates": [
            {
                "candidate_id": c.candidate_id,
                "model_family": c.model_family,
                "task": c.task,
                "provenance": c.provenance,
                "frp_role": c.frp_role,
                "source_repository": c.source_repository,
                "source_commit": _claim_summary(c.source_commit),
                "checkpoint_repository": c.checkpoint_repository,
                "checkpoint_revision": _claim_summary(c.checkpoint_revision),
                "weight_sha256": _claim_summary(c.weight_sha256),
                "licence": _claim_summary(c.licence),
                "conditioning": _claim_summary(c.conditioning),
                "derived_from": None if c.derived_from is None else _claim_summary(c.derived_from),
                "protocols": c.protocols,
                "execution_readiness": c.execution_readiness,
                "unverified_claims": pending_claims(c),
            }
            for c in inventory.candidates
        ],
    }


def _render_provenance_text(report: dict[str, Any]) -> str:
    candidates = report["candidates"]
    lines = [
        report["notice"],
        "",
        f"Inventory:  {report['inventory_id']} (provenance schema "
        f"{report['provenance_schema_version']}, reviewed {report['reviewed_on']})",
        f"Candidates: {len(candidates)}  Execution readiness: NOT READY for every candidate "
        "(schema 1.0 records provenance only)",
        "",
    ]
    header = ("candidate", "provenance", "role", "source commit", "conditioning", "protocols")
    rows = [
        (
            c["candidate_id"],
            c["provenance"],
            c["frp_role"],
            (c["source_commit"]["value"] or "")[:12] or c["source_commit"]["status"],
            c["conditioning"]["status"],
            ",".join(c["protocols"]) or "-",
        )
        for c in candidates
    ]
    widths = [max(len(row[i]) for row in (header, *rows)) for i in range(len(header))]
    for row in (header, *rows):
        lines.append(
            "  ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True)).rstrip()
        )
    lines += ["", "Claims not verified by FRP (status as recorded):"]
    for c in candidates:
        lines.append(f"  {c['candidate_id']}: {', '.join(c['unverified_claims']) or 'none'}")
    return "\n".join(lines) + "\n"


def _provenance(args: argparse.Namespace) -> int:
    try:
        inventory = load_provenance(args.inventory)
    except ProvenanceError as exc:
        _print_problems("frp: invalid provenance inventory:", exc.problems)
        return EXIT_INVALID
    report = build_provenance_report(inventory)
    if args.format == "json":
        json.dump(report, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(_render_provenance_text(report))
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)

    if args.command == "simulate":
        return _simulate(args)
    if args.command == "provenance":
        return _provenance(args)

    if not args.dry_run:
        print(
            "frp: error: only --dry-run is supported; this harness does not execute inference",
            file=sys.stderr,
        )
        return EXIT_USAGE

    try:
        manifest = load_manifest(args.manifest)
        plan = generate_run_plan(manifest)
    except ManifestError as exc:
        print("frp: invalid manifest:", file=sys.stderr)
        for problem in exc.problems:
            print(f"  - {problem}", file=sys.stderr)
        return EXIT_INVALID
    except PlanInvariantError as exc:
        print("frp: run plan failed pairing invariants:", file=sys.stderr)
        for problem in exc.problems:
            print(f"  - {problem}", file=sys.stderr)
        return EXIT_INVALID

    report = build_dry_run_report(
        manifest,
        plan,
        show_pseudonyms=args.show_pseudonyms,
        show_prompt_ids=args.show_prompt_ids,
    )
    if args.format == "json":
        json.dump(report, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        _render_text(report, sys.stdout)

    if args.require_ready and not report["readiness"]["ready_for_execution"]:
        print("frp: manifest is not ready for execution (see unset fields)", file=sys.stderr)
        return EXIT_NOT_READY
    return EXIT_OK
