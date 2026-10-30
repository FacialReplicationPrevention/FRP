"""Static, CPU-only validation of the FRP model-candidate provenance inventory.

The inventory records what FRP has checked about candidate generative models: pinned source
commits, checkpoint revisions, licences, observed image-conditioning paths and which reviewed
protocol (if any) may be applied. Validation is offline and structural. It never fetches source
code or weights, so a valid inventory is internally consistent, **not** proof that the recorded
facts are true; the evidence links must be reviewed by a person.

Each checkable fact is a :class:`Claim` with an explicit status:

- ``verified``: checked by FRP against the cited primary source at a pinned revision. Requires a
  value and evidence; GitHub/Hugging Face links must be pinned to a 40-hex revision.
- ``pending``: value from a credible source, but FRP's check or human review is incomplete.
- ``not_verified``: not yet checkable (e.g. weight digests before an approved download); null.
- ``unknown``: could not be determined from credible sources; null.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from types import MappingProxyType
from typing import Annotated, Any, Final, Generic, Literal, NamedTuple, TypeVar

import yaml
from pydantic import (
    AfterValidator,
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
    GitSha,
    Sha256Hex,
    _duplicate_positions,
    _reject_placeholder,
    _StrictSafeLoader,
)
from frp.results import PROTOCOL_MODEL_FAMILY, PROTOCOL_WAN21_I2V_CLIP_VAE_2X2

PROVENANCE_SCHEMA_VERSION: Final = "1.0"
MAX_PROVENANCE_BYTES: Final = 1_048_576

NOTICE: Final = (
    "STATIC PROVENANCE CHECK - no source code or model weights were fetched. Recorded statuses "
    "were checked for internal consistency only, not re-verified against upstream sources."
)

ClaimStatus = Literal["verified", "pending", "not_verified", "unknown"]
CLAIM_STATUSES: Final[tuple[ClaimStatus, ...]] = ("verified", "pending", "not_verified", "unknown")

ConditioningPath = Literal[
    "text_t5",
    "clip_vision",
    "vae_first_frame_concat",
    "first_frame_latent_replacement",
    "optional_vlm_prompt_extension",
]
Task = Literal[
    "image-to-video",
    "text-image-to-video",
    "character-animation",
    "speech-to-video",
]
Provenance = Literal["official", "official-conversion", "derivative"]
FrpRole = Literal["initial-baseline", "later-candidate", "inventory-only"]

_STRICT: Final = ConfigDict(strict=True, extra="forbid", frozen=True)

CandidateId = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z0-9][a-z0-9.-]{2,63}$"),
    AfterValidator(_reject_placeholder),
]
ModelFamily = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z0-9][a-z0-9.+-]{1,63}$"),
    AfterValidator(_reject_placeholder),
]
RepoId = Annotated[
    str,
    StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}/[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$"),
]
InventoryId = Annotated[str, StringConstraints(pattern=r"^[A-Z0-9][A-Z0-9-]{2,63}$")]
LicenceId = Annotated[
    str,
    StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9.+-]{0,63}$"),
    AfterValidator(_reject_placeholder),
]
ProtocolId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9.+-]{2,63}$")]
WeightFile = Annotated[
    str,
    StringConstraints(
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}(?:/[A-Za-z0-9][A-Za-z0-9_.-]{0,127}){0,4}$"
    ),
]
WeightDigests = Annotated[dict[WeightFile, Sha256Hex], Field(min_length=1)]
ConditioningPaths = Annotated[list[ConditioningPath], Field(min_length=1)]
# Public primary-source hosts only; local paths and private storage locations are rejected.
EvidenceUrl = Annotated[
    str,
    StringConstraints(pattern=r"^https://(?:github\.com|huggingface\.co|arxiv\.org)/\S{1,400}$"),
]

_PINNED_RE: Final = re.compile(r"/(?:blob|tree|commit|resolve)/([0-9a-f]{40})(?:[/#?]|$)")
_ARXIV_VERSIONED_RE: Final = re.compile(r"^https://arxiv\.org/abs/[0-9]{4}\.[0-9]{4,5}v[0-9]+$")


def _is_pinned(url: str) -> bool:
    return _ARXIV_VERSIONED_RE.match(url) is not None or _PINNED_RE.search(url) is not None


class ProtocolScope(NamedTuple):
    """Where a reviewed experiment protocol may be applied."""

    model_family: str
    source_repository: str
    checkpoint_repositories: frozenset[str]
    required_conditioning: frozenset[str]


# Experiment 002 / Research 004 define the A/B/C/D CLIP x VAE design for the official,
# unmodified Wan 2.1 I2V-14B-480P checkpoint only. Extending this table needs scientific review.
PROTOCOL_SCOPES: Final = MappingProxyType(
    {
        PROTOCOL_WAN21_I2V_CLIP_VAE_2X2: ProtocolScope(
            model_family=PROTOCOL_MODEL_FAMILY[PROTOCOL_WAN21_I2V_CLIP_VAE_2X2],
            source_repository="wan-video/wan2.1",
            checkpoint_repositories=frozenset({"wan-ai/wan2.1-i2v-14b-480p"}),
            required_conditioning=frozenset({"clip_vision", "vae_first_frame_concat"}),
        )
    }
)


class ProvenanceError(Exception):
    """Raised when an inventory cannot be read or fails validation.

    ``problems`` never contains the offending input values, so it is safe to print.
    """

    def __init__(self, problems: Sequence[str]) -> None:
        self.problems = tuple(problems)
        super().__init__("; ".join(self.problems))


T = TypeVar("T")


class Claim(BaseModel, Generic[T]):
    """A checkable fact with its verification status and evidence links."""

    model_config = _STRICT

    value: T | None
    status: ClaimStatus
    evidence: list[EvidenceUrl]

    @model_validator(mode="after")
    def _status_rules(self) -> Claim[T]:
        if self.status in ("not_verified", "unknown"):
            if self.value is not None:
                raise ValueError(f"status '{self.status}' requires value null")
        elif self.value is None:
            raise ValueError(
                f"status '{self.status}' requires a value; use not_verified or unknown "
                "when no value is known"
            )
        if duplicates := _duplicate_positions(self.evidence):
            raise ValueError("duplicate evidence link: " + ", ".join(duplicates))
        if self.status == "verified":
            if not self.evidence:
                raise ValueError("a verified claim requires at least one evidence link")
            unpinned = [str(i) for i, url in enumerate(self.evidence) if not _is_pinned(url)]
            if unpinned:
                raise ValueError(
                    "verified evidence must be pinned to a 40-hex revision, not a moving branch "
                    f"(evidence [{', '.join(unpinned)}])"
                )
        return self


def _evidence_cites(claim: Claim[Any], prefix: str, revision: str) -> bool:
    prefix = prefix.casefold()
    return any(
        url.casefold().startswith(prefix) and revision in url.split("#", 1)[0]
        for url in claim.evidence
    )


class ModelCandidate(BaseModel):
    """Provenance record of one model checkpoint considered by FRP."""

    model_config = _STRICT

    candidate_id: CandidateId
    model_family: ModelFamily
    task: Task
    provenance: Provenance
    frp_role: FrpRole
    source_repository: RepoId | None
    source_commit: Claim[GitSha]
    checkpoint_repository: RepoId
    checkpoint_revision: Claim[GitSha]
    weight_sha256: Claim[WeightDigests]
    licence: Claim[LicenceId]
    conditioning: Claim[ConditioningPaths]
    derived_from: Claim[RepoId] | None
    protocols: list[ProtocolId]
    # Schema 1.0 cannot mark a candidate ready: execution needs verified weights, licence and
    # consent review and an approved cost quote, which are separate reviewed gates.
    execution_readiness: Literal["not_ready"]

    @field_validator("protocols")
    @classmethod
    def _unique_protocols(cls, value: list[str]) -> list[str]:
        if duplicates := _duplicate_positions(value):
            raise ValueError("duplicate protocol: " + ", ".join(duplicates))
        return value

    @model_validator(mode="after")
    def _consistency(self) -> ModelCandidate:
        problems: list[str] = []
        problems += self._source_problems()
        if self.weight_sha256.status == "verified":
            problems.append(
                "weight_sha256: cannot be verified in provenance schema 1.0; digests must be "
                "checked against approved local downloads, a later gated step (use pending for "
                "platform-reported digests)"
            )
        if self.checkpoint_revision.status == "verified" and not _evidence_cites(
            self.checkpoint_revision,
            f"https://huggingface.co/{self.checkpoint_repository}/",
            self.checkpoint_revision.value or "",
        ):
            problems.append(
                "checkpoint_revision: verified revision must cite a Hugging Face link to "
                "checkpoint_repository pinned to that revision"
            )
        if self.conditioning.value is not None and (
            duplicates := _duplicate_positions(self.conditioning.value)
        ):
            problems.append("conditioning: duplicate path: " + ", ".join(duplicates))
        problems += self._conditioning_evidence_problems()
        if (self.provenance == "official") != (self.derived_from is None):
            problems.append(
                "derived_from: required for, and only for, official-conversion and derivative "
                "provenance"
            )
        for index, protocol in enumerate(self.protocols):
            problems += [f"protocols.{index}: {p}" for p in self._protocol_problems(protocol)]
        if problems:
            raise ValueError("; ".join(problems))
        return self

    def _source_problems(self) -> list[str]:
        commit = self.source_commit
        if self.source_repository is None:
            if commit.value is not None:
                return ["source_commit: a commit requires source_repository"]
            return []
        if commit.status == "verified" and not _evidence_cites(
            commit, f"https://github.com/{self.source_repository}/", commit.value or ""
        ):
            return [
                "source_commit: verified commit must cite a GitHub link to source_repository "
                "pinned to that commit"
            ]
        return []

    def _conditioning_evidence_problems(self) -> list[str]:
        if self.conditioning.status != "verified":
            return []
        if self.source_repository is None or self.source_commit.status != "verified":
            return ["conditioning: verified conditioning requires a verified source_commit"]
        allowed = [
            f"https://github.com/{self.source_repository}/blob/{self.source_commit.value}/",
        ]
        if self.checkpoint_revision.status == "verified":
            allowed.append(
                f"https://huggingface.co/{self.checkpoint_repository}/"
                f"resolve/{self.checkpoint_revision.value}/"
            )
            allowed.append(
                f"https://huggingface.co/{self.checkpoint_repository}/"
                f"blob/{self.checkpoint_revision.value}/"
            )
        allowed = [prefix.casefold() for prefix in allowed]
        stray = [
            str(i)
            for i, url in enumerate(self.conditioning.evidence)
            if not url.casefold().startswith(tuple(allowed))
        ]
        if stray:
            return [
                "conditioning: verified evidence must be source files at the pinned "
                "source_commit or checkpoint files at the pinned checkpoint_revision "
                f"(evidence [{', '.join(stray)}])"
            ]
        return []

    def _protocol_problems(self, protocol: str) -> list[str]:
        scope = PROTOCOL_SCOPES.get(protocol)
        if scope is None:
            return ["unsupported protocol (no reviewed protocol with this id; value withheld)"]
        problems = []
        if self.model_family != scope.model_family:
            problems.append(f"protocol {protocol} requires model_family {scope.model_family}")
        if (self.source_repository or "").casefold() != scope.source_repository:
            problems.append(f"protocol {protocol} does not apply to this source_repository")
        if self.checkpoint_repository.casefold() not in scope.checkpoint_repositories:
            problems.append(f"protocol {protocol} does not apply to this checkpoint_repository")
        if self.provenance != "official":
            problems.append(f"protocol {protocol} requires the unmodified official checkpoint")
        if self.source_commit.status != "verified":
            problems.append(f"protocol {protocol} requires a verified source_commit")
        if self.conditioning.status != "verified":
            problems.append(f"protocol {protocol} requires verified conditioning")
        elif missing := sorted(scope.required_conditioning - set(self.conditioning.value or ())):
            problems.append(
                f"protocol {protocol} requires conditioning path(s) absent from this "
                f"candidate: {', '.join(missing)}"
            )
        return problems


class ProvenanceInventory(BaseModel):
    """Provenance schema 1.0: the list of model candidates and their verification status."""

    model_config = _STRICT

    provenance_schema_version: Literal["1.0"]
    inventory_id: InventoryId
    reviewed_on: Annotated[date, Field(strict=False)]
    candidates: Annotated[list[ModelCandidate], Field(min_length=1)]

    @model_validator(mode="after")
    def _unique_and_consistent(self) -> ProvenanceInventory:
        problems = []
        ids = [c.candidate_id.casefold() for c in self.candidates]
        if duplicates := _duplicate_positions(ids):
            problems.append("duplicate candidate_id: " + ", ".join(duplicates))
        checkpoints = [c.checkpoint_repository.casefold() for c in self.candidates]
        if duplicates := _duplicate_positions(checkpoints):
            problems.append("duplicate checkpoint_repository: " + ", ".join(duplicates))
        baselines = [
            str(i) for i, c in enumerate(self.candidates) if c.frp_role == "initial-baseline"
        ]
        if len(baselines) > 1:
            problems.append(
                "at most one candidate may be the initial-baseline "
                f"(candidates {', '.join(baselines)})"
            )
        if problems:
            raise ValueError("; ".join(problems))
        return self


_SCHEMA_NAMES: Final = frozenset(
    {
        *ProvenanceInventory.model_fields,
        *ModelCandidate.model_fields,
        *Claim.model_fields,
        "[key]",
        "bool",
        "int",
        "float",
        "str",
        "date",
    }
)


def _safe_location_part(part: str | int) -> str:
    """Show list indices and schema names; withhold user-supplied mapping keys."""
    if isinstance(part, int) or part in _SCHEMA_NAMES:
        return str(part)
    if part.startswith("function-after["):
        return "str"
    return "<key>"


def _format_validation_error(exc: ValidationError) -> list[str]:
    problems: list[str] = []
    for error in exc.errors(include_url=False, include_input=False, include_context=False):
        location = ".".join(_safe_location_part(part) for part in error["loc"]) or "<inventory>"
        if error["type"] == "extra_forbidden":
            message = "unknown key is not permitted by provenance schema 1.0 (key name withheld)"
        else:
            message = error["msg"].removeprefix("Value error, ")
        problem = f"{location}: {message}"
        if problem not in problems:
            problems.append(problem)
    return problems


def parse_provenance(data: Any) -> ProvenanceInventory:
    """Validate already-parsed inventory data."""
    if not isinstance(data, dict):
        raise ProvenanceError(["<inventory>: top level must be a mapping of field names to values"])
    try:
        return ProvenanceInventory.model_validate(data)
    except ValidationError as exc:
        raise ProvenanceError(_format_validation_error(exc)) from None
    except RecursionError:
        raise ProvenanceError(["<inventory>: data is nested too deeply"]) from None


def parse_provenance_text(text: str) -> ProvenanceInventory:
    """Parse and validate inventory YAML (JSON is also accepted)."""
    try:
        data = yaml.load(text, Loader=_StrictSafeLoader)  # noqa: S506 - SafeLoader subclass
    except yaml.YAMLError as exc:
        description = next(
            (desc for kind, desc in _YAML_ERROR_DESCRIPTIONS if isinstance(exc, kind)),
            "invalid YAML",
        )
        mark = getattr(exc, "problem_mark", None)
        where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
        raise ProvenanceError([f"<inventory>: malformed YAML{where}: {description}"]) from None
    except RecursionError:
        raise ProvenanceError(["<inventory>: malformed YAML: nesting too deep"]) from None
    return parse_provenance(data)


def load_provenance(path: str | Path) -> ProvenanceInventory:
    """Read, parse and validate an inventory file. Never touches the network."""
    path = Path(path)
    try:
        if path.stat().st_size > MAX_PROVENANCE_BYTES:
            raise ProvenanceError([f"<inventory>: file exceeds {MAX_PROVENANCE_BYTES} bytes"])
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ProvenanceError(["<inventory>: file not found"]) from None
    except (OSError, UnicodeDecodeError) as exc:
        raise ProvenanceError([f"<inventory>: cannot read file ({type(exc).__name__})"]) from None
    return parse_provenance_text(text)


def pending_claims(candidate: ModelCandidate) -> list[str]:
    """Names of claims that are not ``verified`` (empty if every claim is verified)."""
    claims = {
        "source_commit": candidate.source_commit,
        "checkpoint_revision": candidate.checkpoint_revision,
        "weight_sha256": candidate.weight_sha256,
        "licence": candidate.licence,
        "conditioning": candidate.conditioning,
    }
    if candidate.derived_from is not None:
        claims["derived_from"] = candidate.derived_from
    return [
        f"{name} ({claim.status})" for name, claim in claims.items() if claim.status != "verified"
    ]
