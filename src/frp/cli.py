"""Command-line interface. Dry-run planning only: no models, images or inference.

Exit codes: 0 success; 1 invalid manifest or plan; 2 usage error; 3 not ready
(only with ``--require-ready``).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any, TextIO

from frp import __version__
from frp.manifest import ExperimentManifest, ManifestError, load_manifest, unset_execution_fields
from frp.planner import PlanInvariantError, PlannedRun, RunPlan, generate_run_plan

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_USAGE = 2
EXIT_NOT_READY = 3

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
        description="FRP CPU-only harness. Planning/dry-run only; never runs inference.",
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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)

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
