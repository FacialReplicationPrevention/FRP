"""The fixed 2 x 2 conditioning design from Experiment 002 / Research 004.

Each variant names which *source image* feeds each Wan2.1 I2V image-conditioning route.
The mapping is protocol-defined and intentionally not configurable from a manifest.
"""

from __future__ import annotations

from enum import StrEnum
from types import MappingProxyType
from typing import Final, NamedTuple


class ConditioningSource(StrEnum):
    ORIGINAL = "original"
    ALTERED = "altered"


class Variant(StrEnum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"


class VariantConditioning(NamedTuple):
    clip: ConditioningSource
    vae_first_frame: ConditioningSource


VARIANT_ORDER: Final[tuple[Variant, ...]] = (Variant.A, Variant.B, Variant.C, Variant.D)

VARIANT_CONDITIONING: Final = MappingProxyType(
    {
        Variant.A: VariantConditioning(ConditioningSource.ORIGINAL, ConditioningSource.ORIGINAL),
        Variant.B: VariantConditioning(ConditioningSource.ALTERED, ConditioningSource.ORIGINAL),
        Variant.C: VariantConditioning(ConditioningSource.ORIGINAL, ConditioningSource.ALTERED),
        Variant.D: VariantConditioning(ConditioningSource.ALTERED, ConditioningSource.ALTERED),
    }
)
