"""Static validation of the public GPU-readiness *template* (readiness schema 1.0).

This is a drift guard, not an approval mechanism. Schema 1.0 can only describe a record in which
every human gate is ``pending``, no cost quote or hardware figure has been entered, and the
execution controls that are already decided (prompt extension off, original reference on both
Wan 2.1 image routes, no adapters or remote services) are fixed. A record that passes validation
authorises nothing: approvals, quotes and consent live in private, access-controlled records
that this public repository never holds. Granting any gate would need a separately reviewed
schema version, in the same way provenance schema 1.0 fixes ``execution_readiness: not_ready``.
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Annotated, Any, Final, Literal, get_args

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)

from frp.manifest import (
    _YAML_ERROR_DESCRIPTIONS,
    WAN21_I2V_CHECKPOINTS,
    WAN21_SOURCE_REPOSITORY,
    GitSha,
    Resolution,
    Seed,
    Text,
    _duplicate_positions,
    _StrictSafeLoader,
)
from frp.provenance import ProvenanceInventory

READINESS_SCHEMA_VERSION: Final = "1.0"
MAX_READINESS_BYTES: Final = 1_048_576

# Design-only baseline protocol (experiments/003). Deliberately not registered in
# frp.provenance.PROTOCOL_SCOPES or frp.results: that needs its own scientific review.
BASELINE_PROTOCOL_ID: Final = "wan2.1-i2v-baseline"

NOTICE: Final = (
    "READINESS TEMPLATE CHECK - NOT AN AUTHORISATION. This checks that the public template is "
    "internally consistent. No approval, consent, quote, download, GPU use or data processing "
    "is granted or implied; every gate remains pending."
)

# Each gate is a separate human decision; approving one never implies another.
GateId = Literal[
    "licence_and_intended_use",
    "consent_and_data_processing",
    "restricted_storage_retention_deletion",
    "cloud_provider_terms",
    "quote_and_budget_cap",
    "checkpoint_download_and_hashing",
    "gpu_smoke_test",
]
RequirementId = Literal[
    "gpu_vram_gib",
    "system_ram_gib",
    "weight_storage_gib",
    "working_storage_gib",
    "runtime_per_clip_minutes",
]
GATE_IDS: Final[tuple[str, ...]] = get_args(GateId)
REQUIREMENT_IDS: Final[tuple[str, ...]] = get_args(RequirementId)

_STRICT: Final = ConfigDict(strict=True, extra="forbid", frozen=True)

RecordId = Annotated[str, StringConstraints(pattern=r"^[A-Z0-9][A-Z0-9-]{2,63}$")]
CandidateId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9.-]{2,63}$")]
RepoId = Annotated[
    str,
    StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}/[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$"),
]


class ReadinessError(Exception):
    """Raised when a record cannot be read or fails validation.

    ``problems`` never contains the offending input values, so it is safe to print.
    """

    def __init__(self, problems: Sequence[str]) -> None:
        self.problems = tuple(problems)
        super().__init__("; ".join(self.problems))


class Target(BaseModel):
    """The one reviewed target. Wan 2.1 only: other models need their own reviewed protocol."""

    model_config = _STRICT

    candidate_id: CandidateId
    source_repository: RepoId
    source_commit: GitSha
    checkpoint_repository: RepoId
    checkpoint_revision: GitSha

    @field_validator("source_repository")
    @classmethod
    def _wan21_source_only(cls, value: str) -> str:
        if value.casefold() != WAN21_SOURCE_REPOSITORY.casefold():
            raise ValueError(f"source_repository must be {WAN21_SOURCE_REPOSITORY}")
        return value

    @field_validator("checkpoint_repository")
    @classmethod
    def _wan21_checkpoint_only(cls, value: str) -> str:
        if value.casefold() not in {c.casefold() for c in WAN21_I2V_CHECKPOINTS}:
            raise ValueError(f"checkpoint_repository must be {' or '.join(WAN21_I2V_CHECKPOINTS)}")
        return value


class Gate(BaseModel):
    """A separate human approval. Schema 1.0 cannot record anything but ``pending``."""

    model_config = _STRICT

    gate_id: GateId
    status: Literal["pending"]
    approval_record: Literal[None]  # approvals are kept in private records, never in this file


class HardwareRequirement(BaseModel):
    """A requirement still to be assessed; no figure is entered until a quote grounds it."""

    model_config = _STRICT

    requirement_id: RequirementId
    status: Literal["unverified"]
    value: Literal[None]


class CostQuote(BaseModel):
    """Template for a provider quote. Every field must stay null in schema 1.0."""

    model_config = _STRICT

    status: Literal["not_obtained"]
    provider_name: Literal[None]
    gpu_model: Literal[None]
    gpu_vram_gib: Literal[None]
    region: Literal[None]
    quote_source: Literal[None]
    quote_date: Literal[None]
    currency: Literal[None]
    gpu_hourly_rate: Literal[None]
    storage_billing: Literal[None]
    billing_granularity: Literal[None]
    estimated_upper_bound_spend: Literal[None]
    budget_cap: Literal[None]
    quota_confirmed: Literal[None]
    idle_timeout_minutes: Literal[None]
    emergency_termination_procedure: Literal[None]
    deletion_procedure: Literal[None]
    actual_charges: Literal[None]


class ExecutionControls(BaseModel):
    """Allowlist of generation controls. Undecided values stay ``null`` (pending)."""

    model_config = _STRICT

    # Decided: fixed, and any other value is rejected.
    use_prompt_extend: Literal[False]
    clip_conditioning: Literal["original"]
    vae_first_frame_conditioning: Literal["original"]
    identity_adapters: Literal["none"]
    remote_inference_services: Literal["none"]
    prompt_policy: Literal["neutral_motion_only"]
    output_storage: Literal["private_only"]

    # Pending: not decided, so null. A set value must be well formed, but is still not approved.
    prompt_template_version: Text | None
    seeds: Annotated[list[Seed], Field(min_length=1)] | None
    sampler: Text | None
    sampling_steps: Annotated[int, Field(ge=1)] | None
    guidance_scale: Annotated[float, Field(gt=0, allow_inf_nan=False)] | None
    frame_count: Annotated[int, Field(ge=1)] | None
    resolution: Resolution | None
    precision: Text | None
    frame_indices: Annotated[list[Annotated[int, Field(ge=0)]], Field(min_length=1)] | None
    image_preprocessing_version: Text | None

    @field_validator("seeds")
    @classmethod
    def _unique_seeds(cls, value: list[int] | None) -> list[int] | None:
        if value is not None and (duplicates := _duplicate_positions(value)):
            raise ValueError("duplicate seed: " + ", ".join(duplicates))
        return value

    @field_validator("frame_count")
    @classmethod
    def _wan_frame_count(cls, value: int | None) -> int | None:
        if value is not None and value % 4 != 1:
            raise ValueError("frame_count must have the form 4n+1 (e.g. 81) for Wan2.1")
        return value

    @field_validator("frame_indices")
    @classmethod
    def _increasing_frame_indices(cls, value: list[int] | None) -> list[int] | None:
        if value is not None and any(b <= a for a, b in itertools.pairwise(value)):
            raise ValueError("frame_indices must be strictly increasing with no duplicates")
        return value

    @model_validator(mode="after")
    def _indices_within_frame_count(self) -> ExecutionControls:
        if (
            self.frame_indices is not None
            and self.frame_count is not None
            and self.frame_indices[-1] >= self.frame_count
        ):
            raise ValueError("frame_indices must be < frame_count")
        return self


class ReadinessRecord(BaseModel):
    """Readiness schema 1.0: a public template in which every gate is pending."""

    model_config = _STRICT

    readiness_schema_version: Literal["1.0"]
    record_id: RecordId
    template_updated_on: Annotated[date, Field(strict=False)]  # not evidence of any gate review
    protocol: Literal["wan2.1-i2v-baseline"]
    target: Target
    gates: list[Gate]
    hardware_requirements: list[HardwareRequirement]
    cost_quote: CostQuote
    execution_controls: ExecutionControls

    @model_validator(mode="after")
    def _complete_sets(self) -> ReadinessRecord:
        problems = []
        for name, expected, present in (
            ("gates", GATE_IDS, [g.gate_id for g in self.gates]),
            (
                "hardware_requirements",
                REQUIREMENT_IDS,
                [r.requirement_id for r in self.hardware_requirements],
            ),
        ):
            if duplicates := _duplicate_positions(present):
                problems.append(f"{name}: duplicate entry " + ", ".join(duplicates))
            if missing := [item for item in expected if item not in present]:
                problems.append(f"{name}: missing {', '.join(missing)}")
        if problems:
            raise ValueError("; ".join(problems))
        return self


_SCHEMA_NAMES: Final = frozenset(
    {
        *ReadinessRecord.model_fields,
        *Target.model_fields,
        *Gate.model_fields,
        *HardwareRequirement.model_fields,
        *CostQuote.model_fields,
        *ExecutionControls.model_fields,
        "[key]",
        "int",
        "float",
        "str",
        "date",
    }
)


def _safe_location_part(part: str | int) -> str:
    if isinstance(part, int) or part in _SCHEMA_NAMES:
        return str(part)
    return "<key>"


def _format_validation_error(exc: ValidationError) -> list[str]:
    problems: list[str] = []
    for error in exc.errors(include_url=False, include_input=False, include_context=False):
        location = ".".join(_safe_location_part(part) for part in error["loc"]) or "<record>"
        if error["type"] == "extra_forbidden":
            message = "unknown key is not permitted by readiness schema 1.0 (key name withheld)"
        elif error["type"] == "literal_error":
            message = "value is not permitted by readiness schema 1.0 (value withheld)"
        else:
            message = error["msg"].removeprefix("Value error, ")
        problem = f"{location}: {message}"
        if problem not in problems:
            problems.append(problem)
    return problems


def parse_readiness(data: Any) -> ReadinessRecord:
    """Validate already-parsed record data."""
    if not isinstance(data, dict):
        raise ReadinessError(["<record>: top level must be a mapping of field names to values"])
    try:
        return ReadinessRecord.model_validate(data)
    except ValidationError as exc:
        raise ReadinessError(_format_validation_error(exc)) from None
    except RecursionError:
        raise ReadinessError(["<record>: data is nested too deeply"]) from None


def parse_readiness_text(text: str) -> ReadinessRecord:
    """Parse and validate record YAML (JSON is also accepted)."""
    try:
        data = yaml.load(text, Loader=_StrictSafeLoader)  # noqa: S506 - SafeLoader subclass
    except yaml.YAMLError as exc:
        description = next(
            (desc for kind, desc in _YAML_ERROR_DESCRIPTIONS if isinstance(exc, kind)),
            "invalid YAML",
        )
        mark = getattr(exc, "problem_mark", None)
        where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
        raise ReadinessError([f"<record>: malformed YAML{where}: {description}"]) from None
    except RecursionError:
        raise ReadinessError(["<record>: malformed YAML: nesting too deep"]) from None
    return parse_readiness(data)


def load_readiness(path: str | Path) -> ReadinessRecord:
    """Read, parse and validate a record file. Never touches the network."""
    path = Path(path)
    try:
        if path.stat().st_size > MAX_READINESS_BYTES:
            raise ReadinessError([f"<record>: file exceeds {MAX_READINESS_BYTES} bytes"])
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ReadinessError(["<record>: file not found"]) from None
    except (OSError, UnicodeDecodeError) as exc:
        raise ReadinessError([f"<record>: cannot read file ({type(exc).__name__})"]) from None
    return parse_readiness_text(text)


def pending_control_fields(record: ReadinessRecord) -> list[str]:
    """Execution controls that are still undecided (``null``)."""
    controls = record.execution_controls
    return [name for name, value in controls if value is None]


def check_against_provenance(record: ReadinessRecord, inventory: ProvenanceInventory) -> list[str]:
    """Problems if the record's pins differ from the provenance inventory (empty if they agree).

    Consistency only: it does not re-verify the upstream facts, and agreement grants nothing.
    """
    target = record.target
    candidate = next(
        (c for c in inventory.candidates if c.candidate_id == target.candidate_id), None
    )
    if candidate is None:
        return ["target.candidate_id: not found in the provenance inventory"]
    problems = []
    if (candidate.source_repository or "").casefold() != target.source_repository.casefold():
        problems.append("target.source_repository: differs from the provenance inventory")
    if candidate.checkpoint_repository.casefold() != target.checkpoint_repository.casefold():
        problems.append("target.checkpoint_repository: differs from the provenance inventory")
    for name, claim, pinned in (
        ("source_commit", candidate.source_commit, target.source_commit),
        ("checkpoint_revision", candidate.checkpoint_revision, target.checkpoint_revision),
    ):
        if claim.status != "verified" or claim.value != pinned:
            problems.append(
                f"target.{name}: must equal a verified {name} in the provenance inventory"
            )
    return problems
