"""Identity-first aggregation, explicit missingness and paired-comparison completeness.

Fixtures: 3 synthetic identities x 1 prompt x 2 seeds = 6 groups; frame indices 0, 10, 20.
Identity 1 owns groups 1-2, identity 2 groups 3-4, identity 3 groups 5-6.
"""

from __future__ import annotations

import pytest

from frp.aggregation import Interval, aggregate, summarise_clip
from frp.variants import Variant
from tests.conftest import fail_run, find_run, load_results, results_dict, set_frames


@pytest.fixture
def data(small_manifest_data):
    data = results_dict(small_manifest_data)
    for run in data["runs"]:
        set_frames(run, 0.5, 0.5, 0.5)
        run["quality"] = {"status": "scored", "score": 3.0}
    return data


def _variant(summary, code):
    return next(v for v in summary.variants if v.variant.value == code)


def _contrast(summary, code, metric="later_frame_similarity"):
    return next(c for c in summary.contrasts if c.variant.value == code and c.metric == metric)


def test_aggregation_is_identity_first_not_frame_pooled(data):
    # Identity 1 contributes many high-similarity frames; identities 2 and 3 one low frame each.
    for group in (1, 2):
        set_frames(find_run(data, group, "A"), 0.9, 0.9, 0.9)
    for group, value in ((3, 0.1), (4, 0.1), (5, 0.2), (6, 0.2)):
        set_frames(find_run(data, group, "A"), "absent", value, "absent")
    a = _variant(aggregate(load_results(data)), "A")
    # Pooled later-frame median would be 0.9 (8 frames at 0.9 vs 4 low frames).
    assert a.median_later_frame_similarity == pytest.approx(0.2)
    assert a.identities_with_similarity == 3


def test_clip_then_identity_medians(data):
    set_frames(find_run(data, 1, "B"), 0.5, 0.2, 0.4)  # clip median of later frames: 0.3
    set_frames(find_run(data, 2, "B"), 0.5, 0.6, 0.8)  # clip median: 0.7
    for group, value in ((3, 0.1), (4, 0.1), (5, 0.9), (6, 0.9)):
        set_frames(find_run(data, group, "B"), 0.5, value, value)
    summary = aggregate(load_results(data))
    b = _variant(summary, "B")
    # Identity medians: 0.5, 0.1, 0.9 -> 0.5.
    assert b.median_later_frame_similarity == pytest.approx(0.5)


def test_first_frame_is_reported_separately_from_later_frames(data):
    for run in data["runs"]:
        if run["variant"] == "C":
            set_frames(run, 0.95, 0.3, 0.3)
    c = _variant(aggregate(load_results(data)), "C")
    assert c.median_first_frame_similarity == pytest.approx(0.95)
    assert c.median_later_frame_similarity == pytest.approx(0.3)


def test_coverage_denominators_and_status_counts(data):
    set_frames(find_run(data, 1, "D"), "absent", "multiple", "low_quality")
    set_frames(find_run(data, 3, "D"), "error", "absent", 0.4)
    fail_run(find_run(data, 5, "D"))
    find_run(data, 2, "D")["quality"] = {"status": "unscorable", "score": None}
    d = _variant(aggregate(load_results(data)), "D")
    assert d.frames_declared == 18
    assert d.face_status_counts == {
        "valid": 10,
        "absent": 2,
        "multiple": 1,
        "low_quality": 1,
        "error": 1,
        "not_evaluated": 3,
    }
    assert sum(d.face_status_counts.values()) == d.frames_declared
    assert d.execution_counts == {"succeeded": 5, "failed": 1, "not_executed": 0}
    assert d.clips_planned == 6
    assert d.clips_with_similarity == 4
    assert (d.identities_with_similarity, d.identities_total) == (3, 3)
    assert d.quality_status_counts == {
        "scored": 4,
        "unscorable": 1,
        "error": 0,
        "not_evaluated": 1,
    }


def test_missing_scores_are_never_imputed(data):
    for run in data["runs"]:
        if run["variant"] == "D":
            set_frames(run, "absent", "absent", "absent")
            run["quality"] = {"status": "not_evaluated", "score": None}
    summary = aggregate(load_results(data))
    d = _variant(summary, "D")
    assert d.median_later_frame_similarity is None
    assert d.median_first_frame_similarity is None
    assert d.median_quality_score is None
    assert d.identities_with_similarity == 0
    contrast = _contrast(summary, "D")
    assert contrast.median_difference is None
    assert contrast.identities_with_complete_pair == 0
    assert contrast.groups_missing_variant_only == 6
    assert contrast.identity_differences == ()
    assert summary.groups_with_all_variants_similarity == 0


def test_paired_differences_within_groups_then_identities(data):
    for group in range(1, 7):
        set_frames(find_run(data, group, "A"), 0.5, 0.6, 0.6)
    set_frames(find_run(data, 1, "B"), 0.5, 0.4, 0.4)  # -0.2
    set_frames(find_run(data, 2, "B"), 0.5, 0.6, 0.6)  # 0.0 -> identity 1: -0.1
    set_frames(find_run(data, 3, "B"), 0.5, 0.7, 0.7)  # +0.1
    set_frames(find_run(data, 4, "B"), 0.5, 0.7, 0.7)  # +0.1 -> identity 2: +0.1
    set_frames(find_run(data, 5, "B"), 0.5, 0.3, 0.3)  # -0.3
    set_frames(find_run(data, 6, "B"), 0.5, 0.3, 0.3)  # -0.3 -> identity 3: -0.3
    contrast = _contrast(aggregate(load_results(data)), "B")
    assert contrast.label == "B - A"
    assert contrast.identity_differences == pytest.approx((-0.3, -0.1, 0.1))
    assert contrast.median_difference == pytest.approx(-0.1)
    assert contrast.groups_complete == 6
    assert contrast.interval is None


def test_incomplete_pairs_are_flagged_by_cause(data):
    fail_run(find_run(data, 1, "A"))  # baseline missing
    fail_run(find_run(data, 2, "C"))  # variant missing
    fail_run(find_run(data, 3, "A"))
    fail_run(find_run(data, 3, "C"))  # both missing
    fail_run(find_run(data, 4, "C"))  # identity 2 now has no complete C-A pair
    summary = aggregate(load_results(data))
    c = _contrast(summary, "C")
    assert c.groups_total == 6
    assert c.groups_complete == 2
    assert c.groups_missing_baseline_only == 1
    assert c.groups_missing_variant_only == 2
    assert c.groups_missing_both == 1
    assert (
        c.groups_complete
        + c.groups_missing_baseline_only
        + c.groups_missing_variant_only
        + c.groups_missing_both
    ) == c.groups_total
    assert (c.identities_with_complete_pair, c.identities_total) == (1, 3)
    assert summary.groups_with_all_variants_similarity == 2


def test_quality_contrast(data):
    for group in range(1, 7):
        find_run(data, group, "D")["quality"] = {"status": "scored", "score": 1.0}
    find_run(data, 1, "D")["quality"] = {"status": "error", "score": None}
    contrast = _contrast(aggregate(load_results(data)), "D", "quality_score")
    assert contrast.median_difference == pytest.approx(-2.0)
    assert contrast.groups_missing_variant_only == 1


def test_min_valid_later_frames(data):
    run = find_run(data, 1, "A")
    set_frames(run, 0.5, 0.4, "absent")
    results = load_results(data)
    clip = next(r for r in results.runs if r.group_index == 1 and r.variant == "A")
    assert summarise_clip(clip, 1).later_frame_similarity == pytest.approx(0.4)
    assert summarise_clip(clip, 2).later_frame_similarity is None
    assert summarise_clip(clip, 2).valid_later_frames == 1
    assert _variant(aggregate(results, min_valid_later_frames=2), "A").clips_with_similarity == 5
    with pytest.raises(ValueError, match="min_valid_later_frames"):
        aggregate(results, min_valid_later_frames=0)


def test_uncertainty_extension_point_receives_identity_level_values(data):
    seen = []

    class _Fixture:
        name = "fixture-interval"

        def interval(self, identity_values):
            seen.append(tuple(identity_values))
            return Interval(lower=-1.0, upper=1.0, level=0.95)

    summary = aggregate(load_results(data), uncertainty=_Fixture())
    assert summary.uncertainty_method == "fixture-interval"
    assert all(len(values) == 3 for values in seen)  # one value per identity, not per frame
    assert all(c.interval == Interval(-1.0, 1.0, 0.95) for c in summary.contrasts)


def test_summary_counts(data):
    summary = aggregate(load_results(data))
    assert (summary.identities, summary.trial_groups, summary.planned_runs) == (3, 6, 24)
    assert [v.variant for v in summary.variants] == list(Variant)
    assert [(c.label, c.metric) for c in summary.contrasts] == [
        (f"{v} - A", m) for v in "BCD" for m in ("later_frame_similarity", "quality_score")
    ]
    assert summary.later_frame_indices == (10, 20)
