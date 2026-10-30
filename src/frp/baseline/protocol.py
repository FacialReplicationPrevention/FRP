"""Baseline protocol registration, reviewed pins and role-scoped claims (Experiment 003).

The protocol ``wan2.1-i2v-baseline`` is registered **here**, not in
``frp.provenance.PROTOCOL_SCOPES`` or ``frp.results.PROTOCOL_MODEL_FAMILY``: those registries
describe the A/B/C/D ablation and are deliberately left untouched. The baseline is scientifically
distinct because it has one condition (the same original reference on the CLIP-vision and VAE
first-frame routes), no variants, no alteration and no pairing, so it supports descriptive
measurement only and no contrast between conditions. It is constrained to the reviewed Wan 2.1
source and checkpoint below; another model family (for example Wan 2.2, which has no CLIP-vision
path at its pinned commit) needs its own reviewed protocol.

Pins are reviewed *claims* (Research 005, ``provenance/model-candidates.yaml``); this repository has
not downloaded or hashed any weight, and local weight digests remain unverified.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal

from frp.manifest import WAN21_I2V_CHECKPOINTS, WAN21_SOURCE_REPOSITORY

PROTOCOL_WAN21_I2V_BASELINE: Final = "wan2.1-i2v-baseline"
BASELINE_MODEL_FAMILY: Final = "wan2.1-i2v"
BASELINE_SCHEMA_VERSION: Final = "baseline-0.1-draft"

WAN21_SOURCE_COMMIT: Final = "9737cba9c1c3c4d04b33fcad41c111989865d315"
WAN21_CHECKPOINT_REVISION: Final = "6b73f84e66371cdfe870c72acd6826e1d61cf279"
WAN21_PROVENANCE_CANDIDATE_ID: Final = "wan2.1-i2v-14b-480p"

# Sizes upstream lists for task i2v-14B (wan/configs/__init__.py at the pinned commit) that are
# in the 480P class. The 720P sizes are in the same upstream table but were not reviewed for this
# 480P checkpoint, so they are not accepted.
WAN21_BASELINE_RESOLUTIONS: Final = ("480*832", "832*480")
# Upstream MAX_AREA_CONFIGS values (wan/configs/__init__.py at the pinned commit).
WAN21_MAX_AREA: Final = MappingProxyType({"480*832": 480 * 832, "832*480": 832 * 480})
# Upstream --sample_solver choices (generate.py at the pinned commit).
WAN21_SAMPLE_SOLVERS: Final = ("unipc", "dpm++")
# Latent stride 8 times patch size 2 (image2video.py at the pinned commit): output height and
# width are multiples of 16.
WAN21_SPATIAL_MULTIPLE: Final = 16

RunRole = Literal["smoke", "calibration", "baseline"]
RUN_ROLES: Final[tuple[RunRole, ...]] = ("smoke", "calibration", "baseline")
IdentitySplit = Literal["calibration", "evaluation"]
# The identity split each role may contain. ``smoke`` takes one identity and no split.
ROLE_IDENTITY_SPLIT: Final = MappingProxyType(
    {"smoke": None, "calibration": "calibration", "baseline": "evaluation"}
)


@dataclass(frozen=True, slots=True)
class RoleClaims:
    claim_scope: str
    permitted: str
    not_permitted: str


# Experiment 003 section 2. A role fixes which statements its results may support.
ROLE_CLAIMS: Final = MappingProxyType(
    {
        "smoke": RoleClaims(
            claim_scope="technical_smoke_only",
            permitted="technical smoke test passed/failed; runtime and cost",
            not_permitted="any similarity, retention, utility or population conclusion",
        ),
        "calibration": RoleClaims(
            claim_scope="calibration_operating_points",
            permitted="operating points chosen on calibration identities, with error rates",
            not_permitted="reuse of these identities for evaluation; a universal threshold",
        ),
        "baseline": RoleClaims(
            claim_scope="exploratory_uncalibrated_or_calibrated_baseline",
            permitted="identity-clustered descriptive statistics with all failures",
            not_permitted="any efficacy or protection claim; extrapolation to other models",
        ),
    }
)


@dataclass(frozen=True, slots=True)
class BaselineProtocolScope:
    model_family: str
    source_repository: str
    source_commit: str
    checkpoint_repositories: frozenset[str]
    checkpoint_revision: str


# Separate from frp.provenance.PROTOCOL_SCOPES on purpose; extending it needs scientific review.
BASELINE_PROTOCOL_SCOPES: Final = MappingProxyType(
    {
        PROTOCOL_WAN21_I2V_BASELINE: BaselineProtocolScope(
            model_family=BASELINE_MODEL_FAMILY,
            source_repository=WAN21_SOURCE_REPOSITORY.casefold(),
            source_commit=WAN21_SOURCE_COMMIT,
            checkpoint_repositories=frozenset(c.casefold() for c in WAN21_I2V_CHECKPOINTS),
            checkpoint_revision=WAN21_CHECKPOINT_REVISION,
        )
    }
)
