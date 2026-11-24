from datetime import date

import numpy as np
import pytest

from quantum_trends.analysis import analyze, extract_terms, lindblad_evidence


def paper(identifier, published, text, primary="quant-ph"):
    return {"id": identifier, "published": published + "T12:00:00Z", "updated": published + "T12:00:00Z",
            "title": text, "abstract": text, "categories": [primary, "quant-ph"],
            "primary_category": primary, "authors": ["Example Author"], "url": "https://arxiv.org/abs/" + identifier}


def corpus(records, start="2026-01-01", end="2026-03-15"):
    import pandas as pd
    months = pd.period_range(start, end, freq="M").astype(str)
    return {"start": start, "end": end, "complete": True, "retrieved_at": "2026-03-16T00:00:00Z",
            "papers": records, "coverage": [{"month": m, "complete": True,
            "api_total": sum(p["published"].startswith(m) for p in records),
            "retrieved": sum(p["published"].startswith(m) for p in records)} for m in months]}


def test_document_frequency_normalization_and_partial_month():
    records = [paper("1", "2026-01-10", "Entanglement entanglement"),
               paper("2", "2026-01-20", "Photon"),
               paper("3", "2026-02-10", "Entanglement entanglement entanglement"),
               paper("4", "2026-03-10", "Photon")]
    a = analyze(corpus(records), min_df=1, comparison_months=1, as_of=date(2026,3,16))
    m = a.monthly(["entanglement"])
    assert m.papers.tolist() == [1, 1, 0]
    assert m.share_pct.tolist() == [50, 100, 0]
    assert m.full_month.tolist() == [True, True, False]
    assert a.windows() == (["2026-01"], ["2026-02"])
    delta = a.changes().set_index("keyword").loc["entanglement"]
    assert delta.change_pp == 50
    assert delta.previous_total == 2


def test_empty_cohort_and_zero_paper_month_are_undefined():
    a = analyze(corpus([paper("1", "2026-01-01", "Lindblad entanglement")]), min_df=1)
    assert np.isnan(a.monthly(["entanglement"]).share_pct.iloc[1])
    assert a.changes("lindblad").empty
    assert a.enrichment().empty  # no non-Lindblad comparison corpus
    empty = analyze(corpus([]), min_df=1)
    assert empty.ranked().empty
    assert empty.volumes().all_papers.sum() == 0
    assert empty.enrichment().empty


def test_lindblad_screen_is_explicit_and_auditable():
    for text in ["Lindbladian generators", "GKSL equation", "GKLS semigroups", "Lindblad-based dynamics",
                 "Gorini–Kossakowski–Sudarshan generators"]:
        assert lindblad_evidence(text)
    for text in ["A dissipative quantum system", "An open quantum system", "lindbladish"]:
        assert not lindblad_evidence(text)
    # Deliberate limitation: lexical screening does not understand negations.
    assert lindblad_evidence("We go beyond Lindblad dynamics")


def test_phrases_aliases_boundaries_and_math():
    terms = extract_terms("Open quantum systems with non-Markovian quantum trajectories. Qubits and tensor networks. $x^2 + y^2$ Lindbladians.")
    assert {"open quantum system", "non markovian", "quantum trajectory", "qubit", "tensor network", "lindblad"} <= terms
    assert "trajectory qubit" not in terms
    assert "qubit tensor" not in terms
    assert "non markovian" not in extract_terms("non-Markovian dynamics", extra_stopwords={"non markovian"})
    assert "x" not in terms
    assert "lindblad" in extract_terms("Gorini–Kossakowski–Lindblad–Sudarshan equation")
    assert "lindblad" in extract_terms("GKLS generator")


def test_primary_filter_keeps_correct_denominators_and_complement():
    records = [paper("1", "2026-01-10", "Lindblad entanglement"),
               paper("2", "2026-01-20", "Photon", "cond-mat.stat-mech"),
               paper("3", "2026-01-25", "Entanglement")]
    a = analyze(corpus(records), primary_only=True, min_df=1)
    assert len(a.papers) == 2
    row = a.enrichment().set_index("keyword").loc["entanglement"]
    assert row.ratio == 1
    assert row.lindblad_papers == 1
    assert row.other_papers == 1
    assert a.monthly(["entanglement"]).share_pct.iloc[0] == 100


def test_incomplete_and_duplicated_inputs_fail():
    data = corpus([paper("1v1", "2026-01-10", "Photon"), paper("1v2", "2026-01-10", "Photon")])
    with pytest.raises(ValueError, match="Duplicate"):
        analyze(data)
    data = corpus([])
    data["coverage"][0]["api_total"] = 2
    with pytest.raises(ValueError, match="coverage"):
        analyze(data)
    data["complete"] = False
    with pytest.raises(ValueError, match="incomplete"):
        analyze(data)


def test_boundary_adjusted_manifest():
    data = corpus([paper("1", "2026-01-10", "Photon")])
    data["coverage"][0].update(api_total=2, boundary_excluded=1)
    assert len(analyze(data).papers) == 1


def test_comparison_pools_papers_instead_of_averaging_monthly_rates():
    records = [paper(str(i), "2026-01-10", "Entanglement") for i in range(1)]
    records += [paper(str(i+1), "2026-02-10", "Photon") for i in range(9)]
    records += [paper("11", "2026-03-10", "Photon"), paper("12", "2026-04-10", "Entanglement")]
    a = analyze(corpus(records, end="2026-04-30"), min_df=1, comparison_months=2, as_of=date(2026,5,1))
    row = a.changes().set_index("keyword").loc["entanglement"]
    assert row.previous_pct == 10
    assert row.recent_pct == 50
    assert row.change_pp == 40


def test_cohort_queries_do_not_mutate_membership():
    records = [paper("1", "2026-01-10", "Lindblad entanglement"),
               paper("2", "2026-02-10", "GKSL photon")]
    a = analyze(corpus(records), min_df=1, comparison_months=1)
    original = a.papers.lindblad.copy()
    assert a.frequencies("lindblad", ["2026-01"])["entanglement"] == 1
    assert a.frequencies("lindblad", ["2026-02"])["photon"] == 1
    a.monthly(["photon"], "lindblad")
    assert not a.changes("lindblad").empty
    assert a.papers.lindblad.equals(original)
