"""Draft analysis-plan consistency check for the Wan 2.1 I2V single-condition baseline.

Schema ``analysis-plan-0.1-draft``. It checks that a *draft* plan (see
``docs/baseline-analysis-preregistration.md``) is internally consistent **before** any real output
exists. It validates only synthetic or dummy, pseudonymous plan records and does not read images,
run a recogniser or import a model.

It is deliberately small and does not duplicate :class:`~frp.baseline.manifest.BaselineManifest`
(which already enforces role/split agreement, unique pseudonyms and frame bounds for a *planned
run set*). It adds what the manifest cannot express: the identity split across calibration and
evaluation in one plan, the minimum valid later frames, the attempt-selection rule and an explicit
review state for each open decision.

Not an approval. ``status`` can only be ``draft``; a decision can only be ``pending`` (value
``null``) or ``proposed`` (candidate value). There is no ``reviewed``/``frozen``/``approved``
state because nothing here can record a human decision; freezing is a separate, private,
human-signed procedure. Errors never echo input values, pseudonyms or unknown keys.
"""

from __future__ import annotations

import itertools
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Any, Final, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from frp.baseline.manifest import format_validation_error
from frp.baseline.protocol import RunRole
from frp.manifest import (
    _YAML_ERROR_DESCRIPTIONS,
    MAX_MANIFEST_BYTES,
    ExperimentId,
    ManifestError,
    Pseudonym,
    Text,
    _duplicate_positions,
    _StrictSafeLoader,
)

ANALYSIS_PLAN_SCHEMA_VERSION: Final = "analysis-plan-0.1-draft"
DecisionState = Literal["pending", "proposed"]
OPEN_DECISIONS: Final = ("frame_indices", "min_valid_later_frames", "attempt_selection")

_STRICT: Final = ConfigDict(strict=True, extra="forbid", frozen=True)


class AnalysisPlanDraft(BaseModel):
    """A non-binding, non-identifying draft of the analysis choices for one run role."""

    model_config = _STRICT

    schema_version: Literal["analysis-plan-0.1-draft"]
    protocol: Literal["wan2.1-i2v-baseline"]
    plan_id: ExperimentId
    plan_version: Text
    status: Literal["draft"]
    claim_role: RunRole
    # ``calibrated`` needs identity-disjoint calibration identities; ``none`` is uncalibrated.
    calibration_claim: Literal["none", "calibrated"]

    calibration_identities: list[Pseudonym]
    evaluation_identities: list[Pseudonym]

    frame_count: Annotated[int, Field(ge=1)] | None
    frame_indices: Annotated[list[Annotated[int, Field(ge=0)]], Field(min_length=1)] | None
    min_valid_later_frames: Annotated[int, Field(ge=1)] | None
    attempt_selection: Literal["first_attempt", "last_attempt"] | None
    # Fixed controls: missing similarity is never imputed, and failures stay in the denominators.
    missing_similarity_policy: Literal["no_imputation_report_coverage"]
    decision_states: dict[
        Literal["frame_indices", "min_valid_later_frames", "attempt_selection"], DecisionState
    ]

    @field_validator("calibration_identities", "evaluation_identities")
    @classmethod
    def _unique(cls, value: list[str]) -> list[str]:
        if problems := _duplicate_positions(value):
            raise ValueError("duplicate pseudonym at position(s): " + ", ".join(problems))
        return value

    @field_validator("frame_count")
    @classmethod
    def _wan_frame_count(cls, value: int | None) -> int | None:
        if value is not None and value % 4 != 1:
            raise ValueError("frame_count must have the form 4n+1 (e.g. 81) for Wan2.1")
        return value

    @field_validator("frame_indices")
    @classmethod
    def _increasing(cls, value: list[int] | None) -> list[int] | None:
        if value is not None and any(b <= a for a, b in itertools.pairwise(value)):
            raise ValueError("frame_indices must be strictly increasing with no duplicates")
        return value

    @model_validator(mode="after")
    def _consistency(self) -> AnalysisPlanDraft:
        problems: list[str] = []
        cal, ev = self.calibration_identities, self.evaluation_identities

        if overlap := len(set(cal) & set(ev)):
            problems.append(
                f"{overlap} identity(ies) appear in both the calibration and evaluation lists "
                "(they must be disjoint)"
            )
        if self.claim_role == "smoke":
            if cal or ev or self.calibration_claim != "none":
                problems.append(
                    "claim_role smoke supports no calibration or population analysis: "
                    "identity lists must be empty and calibration_claim none"
                )
        elif self.claim_role == "calibration":
            if not cal or ev:
                problems.append(
                    "claim_role calibration needs calibration identities and no evaluation ones"
                )
            if self.calibration_claim != "none":
                problems.append("a calibration plan cannot itself claim to be calibrated")
        else:
            if not ev:
                problems.append("claim_role baseline needs evaluation identities")
            if self.calibration_claim == "none" and cal:
                problems.append("calibration identities require calibration_claim calibrated")
            if self.calibration_claim == "calibrated" and not cal:
                problems.append("calibration_claim calibrated needs calibration identities")
        if self.calibration_claim == "calibrated" and len(cal) < 2:
            problems.append(
                "genuine/impostor calibration needs at least two distinct calibration identities"
            )

        if (
            self.frame_indices is not None
            and self.frame_count is not None
            and self.frame_indices[-1] >= self.frame_count
        ):
            problems.append("frame_indices must be < frame_count")
        if self.min_valid_later_frames is not None and self.frame_indices is not None:
            later = sum(1 for index in self.frame_indices if index != 0)
            if self.min_valid_later_frames > later:
                problems.append(
                    f"min_valid_later_frames exceeds the {later} later (index != 0) sampled frames"
                )

        values = {
            "frame_indices": self.frame_indices,
            "min_valid_later_frames": self.min_valid_later_frames,
            "attempt_selection": self.attempt_selection,
        }
        for name in OPEN_DECISIONS:
            state = self.decision_states.get(name)  # type: ignore[call-overload]
            if state is None:
                problems.append(f"decision_states must declare {name}")
            elif (state == "pending") != (values[name] is None):
                problems.append(
                    f"{name}: a pending decision must be null and a proposed one must carry a "
                    "candidate value (placeholders are not reviewed settings)"
                )
        if problems:
            raise ValueError("; ".join(problems))
        return self


_NAMES: Final = frozenset({*AnalysisPlanDraft.model_fields, *OPEN_DECISIONS})


def parse_analysis_plan(data: Any) -> AnalysisPlanDraft:
    """Validate already-parsed draft-plan data."""
    if not isinstance(data, Mapping):
        raise ManifestError(["<plan>: top level must be a mapping of field names to values"])
    try:
        return AnalysisPlanDraft.model_validate(dict(data))
    except ValidationError as exc:
        raise ManifestError(format_validation_error(exc, _NAMES, "<plan>")) from None
    except RecursionError:
        raise ManifestError(["<plan>: data is nested too deeply"]) from None


def load_analysis_plan(path: str | Path) -> AnalysisPlanDraft:
    """Read, parse and validate a draft analysis-plan file (synthetic content only)."""
    path = Path(path)
    try:
        if path.stat().st_size > MAX_MANIFEST_BYTES:
            raise ManifestError([f"<plan>: file exceeds {MAX_MANIFEST_BYTES} bytes"])
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ManifestError(["<plan>: file not found"]) from None
    except (OSError, UnicodeDecodeError) as exc:
        raise ManifestError([f"<plan>: cannot read file ({type(exc).__name__})"]) from None
    try:
        data = yaml.load(text, Loader=_StrictSafeLoader)  # noqa: S506 - SafeLoader subclass
    except yaml.YAMLError as exc:
        description = next(
            (desc for kind, desc in _YAML_ERROR_DESCRIPTIONS if isinstance(exc, kind)),
            "invalid YAML",
        )
        raise ManifestError([f"<plan>: malformed YAML: {description}"]) from None
    except RecursionError:
        raise ManifestError(["<plan>: malformed YAML: nesting too deep"]) from None
    return parse_analysis_plan(data)


__all__ = [
    "ANALYSIS_PLAN_SCHEMA_VERSION",
    "OPEN_DECISIONS",
    "AnalysisPlanDraft",
    "load_analysis_plan",
    "parse_analysis_plan",
]
