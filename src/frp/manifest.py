"""Versioned manifest schema for *planned* FRP conditioning-ablation runs.

Field names follow the example manifest in ``experiments/002-conditioning-ablation-protocol.md``.
Schema 1.0 plans the Wan 2.1 I2V CLIP x VAE A/B/C/D protocol only, so ``upstream_repository``
and ``checkpoint`` must name the reviewed Wan 2.1 source and checkpoint; other models fail closed.
Planning inputs (identities, prompts, seeds, variants) are required to build a run plan.
Execution inputs may be ``null`` while planning: ``null`` is the only accepted "explicitly
unset" marker, and placeholder text such as ``TODO`` is rejected. Use
:func:`unset_execution_fields` to check readiness before any future real execution.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import re
from collections import Counter
from collections.abc import Hashable, Sequence
from pathlib import Path
from typing import Annotated, Any, Final, Literal

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

SCHEMA_VERSION: Final = "1.0"

# Upstream Wan2.1 draws a random seed when seed < 0, so negative values are not reproducible.
# The 2**32 - 1 ceiling is a conservative FRP portability choice, not an upstream limit.
SEED_MIN: Final = 0
SEED_MAX: Final = 2**32 - 1

MAX_MANIFEST_BYTES: Final = 1_048_576

# The only source and checkpoint reviewed for the A/B/C/D protocol (Experiment 002, Research 005).
# Widening this scope needs scientific review; Wan 2.2 I2V-A14B has no CLIP-vision path.
WAN21_SOURCE_REPOSITORY: Final = "Wan-Video/Wan2.1"
WAN21_I2V_CHECKPOINTS: Final = ("Wan-AI/Wan2.1-I2V-14B-480P",)

_PLACEHOLDER_RE: Final = re.compile(
    r"^(?:<.*>|\{\{.*\}\}|\?+|x{3,}|tbd|todo|fixme|changeme|placeholder|unknown|unset|none|"
    r"null|n/?a)$",
    re.IGNORECASE,
)


def _reject_placeholder(value: str) -> str:
    if _PLACEHOLDER_RE.match(value):
        raise ValueError(
            "placeholder text is not allowed; use null to mark a value as explicitly unset"
        )
    return value


Text = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=256),
    AfterValidator(_reject_placeholder),
]
PromptText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=2000),
    AfterValidator(_reject_placeholder),
]
ExperimentId = Annotated[str, StringConstraints(pattern=r"^[A-Z0-9][A-Z0-9-]{2,63}$")]
Pseudonym = Annotated[str, StringConstraints(pattern=r"^[A-Z]{2,8}-[0-9]{3,8}$")]
PromptId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")]
GitSha = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]
Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Resolution = Annotated[str, StringConstraints(pattern=r"^[1-9][0-9]{1,4}\*[1-9][0-9]{1,4}$")]
Seed = Annotated[int, Field(ge=SEED_MIN, le=SEED_MAX)]
FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
Scalar = Text | bool | int | FiniteFloat
SettingsMap = Annotated[dict[Text, Scalar], Field(min_length=1)]
VariantCode = Literal["A", "B", "C", "D"]

REQUIRED_VARIANTS: Final = ("A", "B", "C", "D")

_STRICT: Final = ConfigDict(strict=True, extra="forbid", frozen=True)


class ManifestError(Exception):
    """Raised when a manifest cannot be read or fails validation.

    ``problems`` never contains the offending input values, so it is safe to print.
    """

    def __init__(self, problems: Sequence[str]) -> None:
        self.problems = tuple(problems)
        super().__init__("; ".join(self.problems))


class IdentityRef(BaseModel):
    """A pseudonymous identity reference. Never put names, images or embeddings here."""

    model_config = _STRICT

    pseudonym: Pseudonym


class PromptSpec(BaseModel):
    model_config = _STRICT

    id: PromptId
    text: PromptText


def _duplicate_positions(values: Sequence[Hashable]) -> list[str]:
    first_seen: dict[Hashable, int] = {}
    problems = []
    for index, value in enumerate(values):
        if value in first_seen:
            problems.append(f"[{index}] duplicates [{first_seen[value]}]")
        else:
            first_seen[value] = index
    return problems


class ExperimentManifest(BaseModel):
    """Schema version 1.0 of a planned A/B/C/D conditioning-ablation manifest."""

    model_config = _STRICT

    schema_version: Literal["1.0"]
    experiment_id: ExperimentId
    status: Literal["planned"]

    # Planning inputs: required and non-empty.
    variants: list[VariantCode]
    identities: Annotated[list[IdentityRef], Field(min_length=1)]
    prompts: Annotated[list[PromptSpec], Field(min_length=1)]
    seeds: Annotated[list[Seed], Field(min_length=1)]

    # Model provenance.
    upstream_repository: Text
    upstream_commit_sha: GitSha | None
    checkpoint: Text
    checkpoint_hashes: Annotated[dict[Text, Sha256Hex], Field(min_length=1)] | None
    model_license_reviewed: bool

    # Data governance. Consent records must never be stored in this repository.
    consent_record_location: Literal["private_only"]
    number_of_identities: Annotated[int, Field(ge=1)] | None
    image_count_per_identity: Literal[1]

    # Generation controls, shared by every run in an A/B/C/D group.
    prompt_template_version: Text | None
    alteration_method_version: Text | None
    alteration_parameters: SettingsMap | None
    sampler: Text | None
    sampling_steps: Annotated[int, Field(ge=1)] | None
    guidance_scale: Annotated[float, Field(gt=0, allow_inf_nan=False)] | None
    frame_count: Annotated[int, Field(ge=1)] | None
    resolution: Resolution | None
    precision: Text | None

    # Evaluation and environment provenance.
    face_evaluator_revision: Text | None
    face_detection_settings: SettingsMap | None
    calibration_dataset_version: Text | None
    frame_indices: Annotated[list[Annotated[int, Field(ge=0)]], Field(min_length=1)] | None
    quality_rubric_version: Text | None
    analysis_plan_version: Text | None
    gpu_model: Text | None
    software_environment_hash: Text | None

    @field_validator("variants")
    @classmethod
    def _complete_variant_set(cls, value: list[str]) -> list[str]:
        problems = []
        duplicates = sorted(code for code, count in Counter(value).items() if count > 1)
        if duplicates:
            problems.append(f"duplicate variant(s): {', '.join(duplicates)}")
        missing = [code for code in REQUIRED_VARIANTS if code not in value]
        if missing:
            problems.append(f"missing variant(s): {', '.join(missing)}")
        if problems:
            raise ValueError(
                "; ".join(problems) + " (schema 1.0 requires each of A, B, C, D exactly once)"
            )
        return value

    @field_validator("identities")
    @classmethod
    def _unique_identities(cls, value: list[IdentityRef]) -> list[IdentityRef]:
        problems = _duplicate_positions([identity.pseudonym for identity in value])
        if problems:
            raise ValueError("duplicate identity pseudonym: " + ", ".join(problems))
        return value

    @field_validator("prompts")
    @classmethod
    def _unique_prompts(cls, value: list[PromptSpec]) -> list[PromptSpec]:
        problems = []
        if id_problems := _duplicate_positions([prompt.id for prompt in value]):
            problems.append("duplicate prompt id: " + ", ".join(id_problems))
        if text_problems := _duplicate_positions([prompt.text for prompt in value]):
            problems.append("duplicate prompt text: " + ", ".join(text_problems))
        if problems:
            raise ValueError("; ".join(problems))
        return value

    @field_validator("seeds")
    @classmethod
    def _unique_seeds(cls, value: list[int]) -> list[int]:
        duplicates = sorted(seed for seed, count in Counter(value).items() if count > 1)
        if duplicates:
            raise ValueError(
                f"duplicate seed(s): {', '.join(map(str, duplicates))}; "
                "each seed must be listed once (it is reused across A/B/C/D automatically)"
            )
        return value

    @field_validator("upstream_repository")
    @classmethod
    def _wan21_source_only(cls, value: str) -> str:
        if value.casefold() != WAN21_SOURCE_REPOSITORY.casefold():
            raise ValueError(
                "schema 1.0 plans the Wan 2.1 I2V A/B/C/D protocol only; upstream_repository "
                f"must be {WAN21_SOURCE_REPOSITORY} (other models need their own reviewed protocol)"
            )
        return value

    @field_validator("checkpoint")
    @classmethod
    def _wan21_checkpoint_only(cls, value: str) -> str:
        if value.casefold() not in {c.casefold() for c in WAN21_I2V_CHECKPOINTS}:
            raise ValueError(
                "schema 1.0 plans the Wan 2.1 I2V A/B/C/D protocol only; checkpoint must be "
                f"{' or '.join(WAN21_I2V_CHECKPOINTS)} (other models need their own reviewed "
                "protocol)"
            )
        return value

    @field_validator("frame_count")
    @classmethod
    def _wan_frame_count(cls, value: int | None) -> int | None:
        # Wan2.1 generate.py documents --frame_num as "should be 4n+1" (e.g. 81).
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
    def _cross_field_consistency(self) -> ExperimentManifest:
        if self.number_of_identities is not None and self.number_of_identities != len(
            self.identities
        ):
            raise ValueError(
                f"number_of_identities is {self.number_of_identities} but "
                f"{len(self.identities)} identities are listed"
            )
        if (
            self.frame_indices is not None
            and self.frame_count is not None
            and self.frame_indices[-1] >= self.frame_count
        ):
            raise ValueError(
                f"frame_indices must be < frame_count ({self.frame_count}); "
                f"largest index is {self.frame_indices[-1]}"
            )
        return self


GENERATION_CONTROL_FIELDS: Final = (
    "upstream_repository",
    "upstream_commit_sha",
    "checkpoint",
    "checkpoint_hashes",
    "prompt_template_version",
    "alteration_method_version",
    "alteration_parameters",
    "sampler",
    "sampling_steps",
    "guidance_scale",
    "frame_count",
    "resolution",
    "precision",
    "gpu_model",
    "software_environment_hash",
)

EXECUTION_FIELDS: Final = (
    "upstream_commit_sha",
    "checkpoint_hashes",
    "number_of_identities",
    "prompt_template_version",
    "alteration_method_version",
    "alteration_parameters",
    "sampler",
    "sampling_steps",
    "guidance_scale",
    "frame_count",
    "resolution",
    "precision",
    "face_evaluator_revision",
    "face_detection_settings",
    "calibration_dataset_version",
    "frame_indices",
    "quality_rubric_version",
    "analysis_plan_version",
    "gpu_model",
    "software_environment_hash",
)
"""Fields that may be ``null`` while planning but must be set before real execution."""


def unset_execution_fields(manifest: ExperimentManifest) -> list[str]:
    """Return the reasons a manifest is not yet ready for real execution (empty if ready)."""
    unset = [name for name in EXECUTION_FIELDS if getattr(manifest, name) is None]
    if not manifest.model_license_reviewed:
        unset.append("model_license_reviewed (must be true)")
    return unset


def _sha256_of(data: Any) -> str:
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def manifest_sha256(manifest: ExperimentManifest) -> str:
    """Hash of the validated manifest content (independent of YAML formatting/comments)."""
    return _sha256_of(manifest.model_dump(mode="json"))


def generation_controls_sha256(manifest: ExperimentManifest) -> str:
    """Hash of the generation controls that every run in an A/B/C/D group must share."""
    return _sha256_of(manifest.model_dump(mode="json", include=set(GENERATION_CONTROL_FIELDS)))


class _DuplicateKeyError(yaml.constructor.ConstructorError):
    pass


class _NonScalarKeyError(yaml.constructor.ConstructorError):
    pass


class _StrictSafeLoader(yaml.SafeLoader):
    """``yaml.SafeLoader`` that rejects duplicate keys and parses YAML 1.2 / JSON floats.

    PyYAML follows YAML 1.1, where exponent-form numbers without a dot (``1e-05``, as emitted
    by ``json.dumps``) load as strings; the extra resolver below loads them as floats.
    """

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
        seen: set[Any] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            try:
                duplicate = key in seen
                seen.add(key)
            except TypeError as exc:
                raise _NonScalarKeyError(None, None, "", key_node.start_mark) from exc
            if duplicate:
                raise _DuplicateKeyError(None, None, "", key_node.start_mark)
        return super().construct_mapping(node, deep=deep)


_StrictSafeLoader.add_implicit_resolver(
    "tag:yaml.org,2002:float",
    re.compile(r"^[-+]?[0-9][0-9_]*(?:\.[0-9_]*)?[eE][-+]?[0-9]+$"),
    list("-+0123456789"),
)

# YAML error messages can quote fragments of the input, so only fixed descriptions are shown.
_YAML_ERROR_DESCRIPTIONS: Final = (
    (_DuplicateKeyError, "duplicate mapping key"),
    (_NonScalarKeyError, "mapping keys must be scalars"),
    (yaml.constructor.ConstructorError, "unsupported YAML construct (e.g. a custom tag)"),
    (yaml.scanner.ScannerError, "invalid YAML token"),
    (yaml.parser.ParserError, "invalid YAML structure"),
    (yaml.composer.ComposerError, "invalid YAML document (e.g. multiple documents)"),
    (yaml.reader.ReaderError, "unsupported characters in file"),
)

_SCHEMA_NAMES: Final = frozenset(
    {
        *ExperimentManifest.model_fields,
        *IdentityRef.model_fields,
        *PromptSpec.model_fields,
        "[key]",
        "bool",
        "int",
        "float",
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
        location = ".".join(_safe_location_part(part) for part in error["loc"]) or "<manifest>"
        if error["type"] == "extra_forbidden":
            message = "unknown key is not permitted by schema 1.0 (key name withheld)"
        else:
            message = error["msg"].removeprefix("Value error, ")
        problem = f"{location}: {message}"
        if problem not in problems:
            problems.append(problem)
    return problems


def parse_manifest(data: Any) -> ExperimentManifest:
    """Validate already-parsed manifest data."""
    if not isinstance(data, dict):
        raise ManifestError(["<manifest>: top level must be a mapping of field names to values"])
    try:
        return ExperimentManifest.model_validate(data)
    except ValidationError as exc:
        raise ManifestError(_format_validation_error(exc)) from None
    except RecursionError:
        raise ManifestError(["<manifest>: data is nested too deeply"]) from None


def parse_manifest_text(text: str) -> ExperimentManifest:
    """Parse and validate manifest YAML (JSON is also accepted)."""
    try:
        data = yaml.load(text, Loader=_StrictSafeLoader)  # noqa: S506 - SafeLoader subclass
    except yaml.YAMLError as exc:
        description = next(
            (desc for kind, desc in _YAML_ERROR_DESCRIPTIONS if isinstance(exc, kind)),
            "invalid YAML",
        )
        mark = getattr(exc, "problem_mark", None)
        where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
        raise ManifestError([f"<manifest>: malformed YAML{where}: {description}"]) from None
    except RecursionError:
        raise ManifestError(["<manifest>: malformed YAML: nesting too deep"]) from None
    return parse_manifest(data)


def load_manifest(path: str | Path) -> ExperimentManifest:
    """Read, parse and validate a manifest file."""
    path = Path(path)
    try:
        size = path.stat().st_size
        if size > MAX_MANIFEST_BYTES:
            raise ManifestError([f"<manifest>: file exceeds {MAX_MANIFEST_BYTES} bytes"])
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ManifestError(["<manifest>: file not found"]) from None
    except (OSError, UnicodeDecodeError) as exc:
        raise ManifestError([f"<manifest>: cannot read file ({type(exc).__name__})"]) from None
    return parse_manifest_text(text)
