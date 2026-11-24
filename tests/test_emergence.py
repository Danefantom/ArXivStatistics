from datetime import date
from math import log2

import numpy as np
import pytest

from quantum_trends.analysis import analyze, extract_terms
from quantum_trends.emergence import EmergenceSettings, emerging, emergence_windows, evidence, parse_canonical
from test_analysis import corpus, paper


def sample():
    records = []
    for month in range(1, 8):
        for i in range(10):
            text = "Background."
            if i < 2:
                text += " Tensor tomography."  # Constant rate despite unequal window lengths.
            if month in [5, 6] and i < 3:
                text += " Adaptive reservoir."
            if month == 5 and i < 6:
                text += " Flash pulse."  # More papers, but only one recent month.
            if month == 7:
                text += " Partial surge."  # Incomplete month cannot affect ranking.
            records.append(paper(f"{month}-{i}", f"2026-{month:02}-10", text))
    return analyze(corpus(records, end="2026-07-15"), min_df=3, comparison_months=2, as_of=date(2026, 7, 16))


def test_growth_uses_rates_support_recurrence_and_complete_months():
    a = sample()
    cfg = EmergenceSettings(learn_canonical=False)
    result = emerging(a, settings=cfg, canonical_terms=set())
    assert emergence_windows(a) == (["2026-01", "2026-02", "2026-03", "2026-04"], ["2026-05", "2026-06"])
    row = result.ranking.set_index("keyword").loc["adaptive reservoir"]
    assert row.baseline_papers == 0 and row.recent_papers == 6
    assert row.baseline_total == 40 and row.recent_total == 20
    assert row.growth_ratio == pytest.approx((6.5/21)/(.5/41))
    assert row.score == pytest.approx(6*log2(row.growth_ratio))
    assert row.status == "Not seen in baseline" and row.first_seen == "2026-05"
    assert not {"tensor tomography", "flash pulse", "partial surge"} & set(result.ranking.keyword)
    assert np.isfinite(result.ranking.score).all()
    assert len(evidence(a, "adaptive reservoir", months=result.recent)) == 6


def test_learned_canonical_never_uses_recent_data_and_is_auditable():
    a = sample()
    result = emerging(a, canonical_terms={"explicit vocabulary"})
    canonical = result.canonical.set_index("keyword")
    assert canonical.loc["tensor tomography", "reason"] == "historically common"
    assert canonical.loc["tensor tomography", "common_baseline_months"] == 4
    assert canonical.loc["tensor tomography", "baseline_pct"] == 20
    assert "adaptive reservoir" not in canonical.index  # Already 30% recently, but absent earlier.
    assert "adaptive reservoir" in set(result.ranking.keyword)
    assert canonical.loc["explicit vocabulary", "reason"] == "explicit"
    assert result.manifest()["explicit_canonical"] == ["explicit vocabulary"]


def test_exact_canonical_exclusion_preserves_modified_phrases():
    a = sample()
    a.terms = [terms | ({"error correction", "adaptive error correction"} if "adaptive reservoir" in terms else set()) for terms in a.terms]
    cfg = EmergenceSettings(learn_canonical=False, min_title_papers=0)
    result = emerging(a, settings=cfg, canonical_terms={"error correction"})
    assert "error correction" not in set(result.ranking.keyword)
    assert "adaptive error correction" in set(result.ranking.keyword)
    assert parse_canonical("# comment\nQuantum batteries # note\nGKLS\n") == {"quantum battery", "lindblad"}


def test_title_evidence_and_true_document_set_deduplication():
    a = sample()
    for i, terms in enumerate(a.terms):
        if "adaptive reservoir" in terms:
            terms.update({"adaptive reservoir computing", "abstract growth"})
    cfg = EmergenceSettings(learn_canonical=False, min_title_papers=0)
    result = emerging(a, settings=cfg, canonical_terms=set())
    assert "adaptive reservoir computing" in set(result.ranking.keyword)
    assert "adaptive reservoir" not in set(result.ranking.keyword)
    assert "abstract growth" in set(result.ranking.keyword)  # Same document set, unrelated phrase.
    with_titles = emerging(a, settings=EmergenceSettings(learn_canonical=False), canonical_terms=set())
    assert "abstract growth" not in set(with_titles.ranking.keyword)
    # A nested phrase with equal counts but different documents must survive.
    for i, terms in enumerate(a.terms):
        terms.discard("adaptive reservoir computing")
        if a.papers.iloc[i].month in ["2026-05", "2026-06"] and a.papers.iloc[i].id.endswith(("3", "4", "5")):
            terms.add("adaptive reservoir computing")
    result = emerging(a, settings=cfg, canonical_terms=set())
    assert {"adaptive reservoir", "adaptive reservoir computing"} <= set(result.ranking.keyword)


def test_empty_cohort_missing_history_and_no_fallback():
    a = sample()
    assert emerging(a, "lindblad").ranking.empty
    blocked = emerging(a, canonical_terms={"adaptive reservoir", "flash pulse"})
    assert blocked.ranking.empty
    a.comparison_months = 6
    assert emergence_windows(a) == ([], [])
    assert emerging(a).ranking.empty
    a.comparison_months = 1
    a.complete_months = ["2026-01", "2026-03"]
    assert emergence_windows(a) == ([], [])


def test_canonical_learning_is_separate_per_cohort_and_does_not_mutate_masks():
    records = []
    for m in range(1, 7):
        for i in range(100):
            text = "Background."
            if i < 5:
                text += " Lindblad."
            if i == 0 or (m > 4 and i < 3):
                text += " Adaptive sampler."
            records.append(paper(f"{m}-{i}", f"2026-{m:02}-10", text))
    a = analyze(corpus(records, end="2026-06-30"), min_df=3, comparison_months=2, as_of=date(2026, 7, 1))
    before = a.papers.lindblad.copy()
    general = emerging(a, canonical_terms=set())
    focused = emerging(a, "lindblad", canonical_terms=set())
    assert "adaptive sampler" in set(general.ranking.keyword)
    assert "adaptive sampler" not in set(general.canonical.keyword)
    assert "adaptive sampler" in set(focused.canonical.keyword)
    assert "adaptive sampler" not in set(focused.ranking.keyword)
    assert a.papers.lindblad.equals(before)


def test_plural_normalization_and_invalid_settings():
    assert {"quantum battery", "gibbs sampler", "quantum query", "css code"} <= extract_terms(
        "Quantum batteries. Gibbs samplers. Quantum queries. CSS codes.")
    for kwargs in [{"canonical_pct": 0}, {"min_growth": .5}, {"min_recent_months": 0}, {"min_title_papers": -1}]:
        with pytest.raises(ValueError):
            EmergenceSettings(**kwargs)
