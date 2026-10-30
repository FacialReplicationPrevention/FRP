"""Strictly validated manifest for the Wan 2.1 I2V single-condition baseline.

Schema version ``baseline-0.1-draft``.

This is **not** the A/B/C/D :class:`frp.manifest.ExperimentManifest` and never validates as one: the
schema version, protocol id and field set differ, and unknown keys are rejected. It follows the
same conventions: strict types, ``null`` as the only "explicitly unset" marker (placeholder text is
rejected), and error messages that never echo input values.

Decided controls are required keys with a single permitted value, so the baseline cannot be
configured away from them: ``use_prompt_extend: false``, the original reference on both the CLIP
and VAE first-frame routes, no adapters, no remote services, private artefact storage only.
Undecided controls and the hashes/digests may be ``null`` while planning; use
:func:`unset_execution_fields` to see why a syntactically valid manifest is still
``NOT EXECUTION READY``. A manifest, even a complete one, is never an approval.
"""

from __future__ import annotations

import hashlib
import itertools
import json
from collections import Counter
from pathlib import Path
from typing import Annotated, Any, Final, Literal

import yaml
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from frp.baseline.protocol import (
    BASELINE_PROTOCOL_SCOPES,
    PROTOCOL_WAN21_I2V_BASELINE,
    ROLE_IDENTITY_SPLIT,
    WAN21_BASELINE_RESOLUTIONS,
    WAN21_SAMPLE_SOLVERS,
    IdentitySplit,
    RunRole,
)
from frp.manifest import (
    _YAML_ERROR_DESCRIPTIONS,
    MAX_MANIFEST_BYTES,
    ExperimentId,
    GitSha,
    ManifestError,
    PromptSpec,
    Pseudonym,
    Resolution,
    Seed,
    SettingsMap,
    Sha256Hex,
    Text,
    _duplicate_positions,
    _StrictSafeLoader,
)

_STRICT: Final = ConfigDict(strict=True, extra="forbid", frozen=True)


def _safe_relative_path(value: str) -> str:
    parts = value.split("/")
    if (
        not value
        or len(value) > 256
        or value.startswith("/")
        or any(part in ("", ".", "..") for part in parts)
        or any(not all(c.isalnum() or c in "._@+-" for c in part) for part in parts)
    ):
        raise ValueError(
            "checkpoint file names must be plain relative POSIX paths (no '..', no absolute paths)"
        )
    return value


RelativeFilePath = Annotated[str, AfterValidator(_safe_relative_path)]


class BaselineIdentity(BaseModel):
    """A pseudonymous identity reference with its (nullable) calibration/evaluation split."""

    model_config = _STRICT

    pseudonym: Pseudonym
    identity_split: IdentitySplit | None


class BaselineManifest(BaseModel):
    """Schema ``baseline-0.1-draft`` of a planned single-condition Wan 2.1 I2V baseline."""

    model_config = _STRICT

    schema_version: Literal["baseline-0.1-draft"]
    protocol: Literal["wan2.1-i2v-baseline"]
    experiment_id: ExperimentId
    status: Literal["planned"]
    run_role: RunRole

    # Planning inputs: required and non-empty. One run per identity x prompt x seed.
    identities: Annotated[list[BaselineIdentity], Field(min_length=1)]
    prompts: Annotated[list[PromptSpec], Field(min_length=1)]
    seeds: Annotated[list[Seed], Field(min_length=1)]

    # Model provenance. Pins, if set, must equal the reviewed pins; null keeps them unset.
    upstream_repository: Text
    upstream_commit_sha: GitSha | None
    checkpoint: Text
    checkpoint_revision: GitSha | None
    # Expected SHA-256 per checkpoint file; a *claim* until it matches both the private approved
    # file manifest and the locally computed digests (see frp.baseline.executor).
    checkpoint_hashes: Annotated[dict[RelativeFilePath, Sha256Hex], Field(min_length=1)] | None
    software_environment_hash: Sha256Hex | None
    gpu_model: Text | None

    # Decided controls: one permitted value each.
    use_prompt_extend: Literal[False]
    clip_conditioning: Literal["original"]
    vae_first_frame_conditioning: Literal["original"]
    adapters: Literal["none"]
    remote_inference_services: Literal["none"]
    negative_prompt_policy: Literal["upstream_config_default"]
    prompt_policy: Literal["neutral_motion_only"]
    generator: Literal["upstream_seeded_torch_cuda_generator"]
    artefact_storage: Literal["private_only"]
    consent_record_location: Literal["private_only"]
    image_count_per_identity: Literal[1]

    # Undecided generation controls. Names follow the upstream arguments they map to.
    prompt_template_version: Text | None
    sampler: Literal["unipc", "dpm++"] | None
    sampling_steps: Annotated[int, Field(ge=1)] | None
    guidance_scale: Annotated[float, Field(gt=0, allow_inf_nan=False)] | None
    sample_shift: Annotated[float, Field(gt=0, allow_inf_nan=False)] | None
    frame_count: Annotated[int, Field(ge=1)] | None
    resolution: Resolution | None
    precision: Text | None
    offload_model: bool | None
    image_preprocessing_version: Text | None

    # Evaluation provenance and sampling.
    frame_indices: Annotated[list[Annotated[int, Field(ge=0)]], Field(min_length=1)] | None
    face_evaluator_revision: Text | None
    face_detection_settings: SettingsMap | None
    calibration_dataset_version: Text | None
    quality_rubric_version: Text | None
    analysis_plan_version: Text | None

    @field_validator("identities")
    @classmethod
    def _unique_identities(cls, value: list[BaselineIdentity]) -> list[BaselineIdentity]:
        if problems := _duplicate_positions([identity.pseudonym for identity in value]):
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
            raise ValueError("duplicate seed(s): " + ", ".join(map(str, duplicates)))
        return value

    @field_validator("upstream_repository")
    @classmethod
    def _wan21_source_only(cls, value: str) -> str:
        scope = BASELINE_PROTOCOL_SCOPES[PROTOCOL_WAN21_I2V_BASELINE]
        if value.casefold() != scope.source_repository:
            raise ValueError(
                "the baseline protocol is constrained to the reviewed Wan 2.1 source "
                "(other models need their own reviewed protocol)"
            )
        return value

    @field_validator("checkpoint")
    @classmethod
    def _wan21_checkpoint_only(cls, value: str) -> str:
        scope = BASELINE_PROTOCOL_SCOPES[PROTOCOL_WAN21_I2V_BASELINE]
        if value.casefold() not in scope.checkpoint_repositories:
            raise ValueError(
                "the baseline protocol is constrained to the reviewed Wan 2.1 I2V 480P "
                "checkpoint (other models need their own reviewed protocol)"
            )
        return value

    @field_validator("upstream_commit_sha")
    @classmethod
    def _pinned_source_commit(cls, value: str | None) -> str | None:
        pinned = BASELINE_PROTOCOL_SCOPES[PROTOCOL_WAN21_I2V_BASELINE].source_commit
        if value is not None and value != pinned:
            raise ValueError("upstream_commit_sha must equal the reviewed source pin (or be null)")
        return value

    @field_validator("checkpoint_revision")
    @classmethod
    def _pinned_checkpoint_revision(cls, value: str | None) -> str | None:
        pinned = BASELINE_PROTOCOL_SCOPES[PROTOCOL_WAN21_I2V_BASELINE].checkpoint_revision
        if value is not None and value != pinned:
            raise ValueError(
                "checkpoint_revision must equal the reviewed checkpoint pin (or be null)"
            )
        return value

    @field_validator("sampler")
    @classmethod
    def _upstream_solver(cls, value: str | None) -> str | None:
        if value is not None and value not in WAN21_SAMPLE_SOLVERS:
            raise ValueError("sampler must be an upstream sample_solver choice")
        return value

    @field_validator("frame_count")
    @classmethod
    def _wan_frame_count(cls, value: int | None) -> int | None:
        # Wan2.1 generate.py documents --frame_num as "should be 4n+1" (e.g. 81).
        if value is not None and value % 4 != 1:
            raise ValueError("frame_count must have the form 4n+1 (e.g. 81) for Wan2.1")
        return value

    @field_validator("resolution")
    @classmethod
    def _reviewed_resolution(cls, value: str | None) -> str | None:
        if value is not None and value not in WAN21_BASELINE_RESOLUTIONS:
            raise ValueError(
                "resolution must be one of the reviewed 480P-class sizes: "
                + ", ".join(WAN21_BASELINE_RESOLUTIONS)
            )
        return value

    @field_validator("frame_indices")
    @classmethod
    def _increasing_frame_indices(cls, value: list[int] | None) -> list[int] | None:
        if value is not None and any(b <= a for a, b in itertools.pairwise(value)):
            raise ValueError("frame_indices must be strictly increasing with no duplicates")
        return value

    @model_validator(mode="after")
    def _cross_field_consistency(self) -> BaselineManifest:
        problems = []
        if (
            self.frame_indices is not None
            and self.frame_count is not None
            and self.frame_indices[-1] >= self.frame_count
        ):
            problems.append(
                f"frame_indices must be < frame_count ({self.frame_count}); "
                f"largest index is {self.frame_indices[-1]}"
            )
        expected_split = ROLE_IDENTITY_SPLIT[self.run_role]
        if any(identity.identity_split != expected_split for identity in self.identities):
            problems.append(
                f"run_role {self.run_role} requires identity_split "
                f"{expected_split if expected_split else 'null'} for every identity "
                "(calibration and evaluation identities must be disjoint and planned separately)"
            )
        if self.run_role == "smoke" and (
            len(self.identities) != 1 or len(self.prompts) != 1 or len(self.seeds) != 1
        ):
            problems.append("run_role smoke takes exactly one identity, one prompt and one seed")
        if problems:
            raise ValueError("; ".join(problems))
        return self


GENERATION_CONTROL_FIELDS: Final = (
    "protocol",
    "upstream_repository",
    "upstream_commit_sha",
    "checkpoint",
    "checkpoint_revision",
    "checkpoint_hashes",
    "software_environment_hash",
    "gpu_model",
    "use_prompt_extend",
    "clip_conditioning",
    "vae_first_frame_conditioning",
    "adapters",
    "remote_inference_services",
    "negative_prompt_policy",
    "prompt_policy",
    "generator",
    "prompt_template_version",
    "sampler",
    "sampling_steps",
    "guidance_scale",
    "sample_shift",
    "frame_count",
    "resolution",
    "precision",
    "offload_model",
    "image_preprocessing_version",
)
"""Fields hashed into ``generation_controls_sha256`` (``frame_indices`` is an evaluation choice)."""

GENERATION_EXECUTION_FIELDS: Final = (
    "upstream_commit_sha",
    "checkpoint_revision",
    "checkpoint_hashes",
    "software_environment_hash",
    "gpu_model",
    "prompt_template_version",
    "sampler",
    "sampling_steps",
    "guidance_scale",
    "sample_shift",
    "frame_count",
    "resolution",
    "precision",
    "offload_model",
    "image_preprocessing_version",
    "frame_indices",
)
EVALUATION_EXECUTION_FIELDS: Final = (
    "face_evaluator_revision",
    "face_detection_settings",
    "calibration_dataset_version",
    "quality_rubric_version",
    "analysis_plan_version",
)


def unset_execution_fields(manifest: BaselineManifest) -> list[str]:
    """Reasons a syntactically valid manifest is still NOT EXECUTION READY (empty if complete).

    Evaluation provenance is required for the ``calibration`` and ``baseline`` roles only. A
    complete list is necessary, **not** sufficient: it is not an approval and its hashes are
    unverified claims until checked against locally computed digests.
    """
    names = GENERATION_EXECUTION_FIELDS
    if manifest.run_role != "smoke":
        names += EVALUATION_EXECUTION_FIELDS
    return [name for name in names if getattr(manifest, name) is None]


def _sha256_of(data: Any) -> str:
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def baseline_manifest_sha256(manifest: BaselineManifest) -> str:
    """Hash of the validated manifest content (independent of YAML formatting/comments)."""
    return _sha256_of(manifest.model_dump(mode="json"))


def baseline_controls_sha256(manifest: BaselineManifest) -> str:
    """Hash of the generation controls every run in a baseline plan shares."""
    return _sha256_of(manifest.model_dump(mode="json", include=set(GENERATION_CONTROL_FIELDS)))


_SCHEMA_NAMES: Final = frozenset(
    {
        *BaselineManifest.model_fields,
        *BaselineIdentity.model_fields,
        *PromptSpec.model_fields,
        "[key]",
        "bool",
        "int",
        "float",
    }
)


def _safe_location_part(part: str | int, names: frozenset[str]) -> str:
    """Show list indices and schema names; withhold user-supplied mapping keys."""
    if isinstance(part, int) or part in names:
        return str(part)
    if part.startswith("function-after["):
        return "str"
    return "<key>"


def format_validation_error(
    exc: ValidationError, names: frozenset[str], root: str = "<manifest>"
) -> list[str]:
    """Describe validation errors without echoing input values or unknown keys."""
    problems: list[str] = []
    for error in exc.errors(include_url=False, include_input=False, include_context=False):
        location = ".".join(_safe_location_part(part, names) for part in error["loc"]) or root
        if error["type"] == "extra_forbidden":
            message = "unknown key is not permitted by this schema (key name withheld)"
        elif error["type"] == "literal_error":
            message = "value is not permitted by this schema (value withheld)"
        else:
            message = error["msg"].removeprefix("Value error, ")
        problem = f"{location}: {message}"
        if problem not in problems:
            problems.append(problem)
    return problems


def parse_baseline_manifest(data: Any) -> BaselineManifest:
    """Validate already-parsed manifest data."""
    if not isinstance(data, dict):
        raise ManifestError(["<manifest>: top level must be a mapping of field names to values"])
    try:
        return BaselineManifest.model_validate(data)
    except ValidationError as exc:
        raise ManifestError(format_validation_error(exc, _SCHEMA_NAMES)) from None
    except RecursionError:
        raise ManifestError(["<manifest>: data is nested too deeply"]) from None


def parse_baseline_manifest_text(text: str) -> BaselineManifest:
    """Parse and validate baseline manifest YAML (JSON is also accepted)."""
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
    return parse_baseline_manifest(data)


def load_baseline_manifest(path: str | Path) -> BaselineManifest:
    """Read, parse and validate a baseline manifest file."""
    path = Path(path)
    try:
        if path.stat().st_size > MAX_MANIFEST_BYTES:
            raise ManifestError([f"<manifest>: file exceeds {MAX_MANIFEST_BYTES} bytes"])
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ManifestError(["<manifest>: file not found"]) from None
    except (OSError, UnicodeDecodeError) as exc:
        raise ManifestError([f"<manifest>: cannot read file ({type(exc).__name__})"]) from None
    return parse_baseline_manifest_text(text)


def identity_overlap(first: BaselineManifest, second: BaselineManifest) -> list[str]:
    """Problems if two manifests share an identity (calibration must stay disjoint from evaluation).

    Never returns the pseudonyms themselves, only their count and ordinal positions.
    """
    shared = {i.pseudonym for i in first.identities} & {i.pseudonym for i in second.identities}
    if not shared:
        return []
    first_positions = [
        str(position)
        for position, identity in enumerate(first.identities, 1)
        if identity.pseudonym in shared
    ]
    return [
        f"{len(shared)} identity(ies) appear in both manifests "
        f"(first-manifest identity positions: {', '.join(first_positions)})"
    ]
