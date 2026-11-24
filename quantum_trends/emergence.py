"""Descriptive discovery of growing terms outside an auditable canonical set."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from math import log2
from pathlib import Path

import numpy as np
import pandas as pd

from .analysis import Analysis, GENERIC, STOP, extract_terms, normalize

DEFAULT_CANONICAL_PATH = Path(__file__).with_name("canonical_keywords.txt")
PROSE = {"proof", "proofs", "combines", "combined", "sufficiently", "remained", "previously",
         "main", "technical", "respectively", "recently", "considerably"}
INCOMPLETE_ENDINGS = {"lower", "upper", "positive", "negative", "strong", "weak", "collective",
                      "independent", "dependent", "small", "large", "optimal", "arbitrary"}


def parse_canonical(text: str) -> set[str]:
    """One exact normalized term per line; # introduces a comment."""
    result = set()
    for line in text.splitlines():
        term = " ".join(t for t in normalize(line.split("#", 1)[0]) if t.isalnum())
        if term:
            result.add(term)
    return result


@dataclass(frozen=True)
class EmergenceSettings:
    learn_canonical: bool = True
    canonical_pct: float = 2.0
    min_growth: float = 1.5
    min_recent_months: int = 2
    phrases_only: bool = True
    min_title_papers: int = 1

    def __post_init__(self):
        if not 0 < self.canonical_pct <= 100:
            raise ValueError("Canonical share must be between 0 and 100 percent")
        if self.min_growth < 1 or self.min_recent_months < 1 or self.min_title_papers < 0:
            raise ValueError("Growth must be at least 1 and recurring months must be positive")


def emergence_windows(analysis: Analysis) -> tuple[list[str], list[str]]:
    """Recent complete months versus every earlier complete month in the snapshot."""
    n = analysis.comparison_months
    months = analysis.complete_months
    if len(months) < n + 1:
        return [], []
    if months != pd.period_range(months[0], months[-1], freq="M").astype(str).tolist():
        return [], []
    return months[:-n], months[-n:]


@dataclass
class Emergence:
    ranking: pd.DataFrame
    canonical: pd.DataFrame
    baseline: list[str]
    recent: list[str]
    settings: EmergenceSettings
    explicit_canonical: set[str]

    def manifest(self) -> dict:
        return {**asdict(self.settings), "baseline_window": self.baseline,
                "recent_window": self.recent, "explicit_canonical": sorted(self.explicit_canonical),
                "score": "excess_recent_papers * log2(smoothed_share_ratio)",
                "smoothing": "(matching_papers + 0.5) / (total_papers + 1)"}


def emerging(analysis: Analysis, cohort: str = "all", *, settings: EmergenceSettings | None = None,
             canonical_terms: set[str] | None = None) -> Emergence:
    settings = settings or EmergenceSettings()
    explicit = (parse_canonical(DEFAULT_CANONICAL_PATH.read_text(encoding="utf-8"))
                if canonical_terms is None else parse_canonical("\n".join(canonical_terms)))
    baseline, recent = emergence_windows(analysis)
    columns = ["keyword", "score", "baseline_papers", "recent_papers", "baseline_total", "recent_total",
               "baseline_pct", "recent_pct", "change_pp", "growth_ratio", "excess_recent_papers",
               "recent_months", "recent_title_papers", "first_seen", "status"]
    audit_columns = ["keyword", "reason", "baseline_papers", "baseline_pct", "common_baseline_months"]
    mask = analysis.mask(cohort)
    month_masks = {m: mask & analysis.papers.month.eq(m).to_numpy() for m in baseline + recent}
    totals = {m: int(mm.sum()) for m, mm in month_masks.items()}
    counts = {m: analysis.frequencies(cohort, [m]) for m in month_masks}
    p, r = Counter(), Counter()
    for m in baseline:
        p.update(counts[m])
    for m in recent:
        r.update(counts[m])
    npapers, nrpapers = sum(totals[m] for m in baseline), sum(totals[m] for m in recent)
    common_months = Counter()
    for m in baseline:
        if totals[m]:
            common_months.update(t for t, n in counts[m].items() if 100*n/totals[m] >= settings.canonical_pct)
    # No recent data enters the learned canonical vocabulary.
    learned = {t for t, n in p.items() if npapers and 100*n/npapers >= settings.canonical_pct
               and common_months[t] >= min(3, len(baseline))} if settings.learn_canonical else set()
    canonical = explicit | learned
    audit = pd.DataFrame([{"keyword": t,
                           "reason": "explicit + historical" if t in explicit & learned else
                                     "explicit" if t in explicit else "historically common",
                           "baseline_papers": p[t], "baseline_pct": 100*p[t]/npapers if npapers else np.nan,
                           "common_baseline_months": common_months[t]}
                          for t in sorted(canonical)], columns=audit_columns)
    result = Emergence(pd.DataFrame(columns=columns), audit, baseline, recent, settings, explicit)
    if not npapers or not nrpapers:
        return result
    title_counts = Counter()
    recent_mask = mask & analysis.papers.month.isin(recent).to_numpy()
    for title in analysis.papers.loc[recent_mask, "title"]:
        title_counts.update(extract_terms(title))
    rows = []
    for term, count in r.items():
        if term in canonical or count < analysis.min_df or (settings.phrases_only and " " not in term):
            continue
        words = term.split()
        if (set(words) & PROSE or set(words) <= GENERIC | STOP
                or words[-1] in INCOMPLETE_ENDINGS or title_counts[term] < settings.min_title_papers):
            continue
        recurring = sum(counts[m][term] > 0 for m in recent)
        if recurring < min(settings.min_recent_months, len(recent)):
            continue
        old_rate, new_rate = p[term]/npapers, count/nrpapers
        ratio = ((count+.5)/(nrpapers+1))/((p[term]+.5)/(npapers+1))
        if new_rate <= old_rate or ratio < settings.min_growth:
            continue
        excess = count - nrpapers*old_rate
        rows.append({"keyword": term, "score": excess*log2(ratio),
                     "baseline_papers": p[term], "recent_papers": count,
                     "baseline_total": npapers, "recent_total": nrpapers,
                     "baseline_pct": 100*old_rate, "recent_pct": 100*new_rate,
                     "change_pp": 100*(new_rate-old_rate), "growth_ratio": ratio,
                     "excess_recent_papers": excess, "recent_months": recurring,
                     "recent_title_papers": title_counts[term],
                     "first_seen": "", "status": "Not seen in baseline" if not p[term] else "Growing"})
    if not rows:
        return result
    # Collapse nested phrases only when they have exactly the same supporting papers.
    # Equal counts alone do not imply equal document sets.
    candidates = {row["keyword"] for row in rows}
    docsets = {t: set() for t in candidates}
    first_seen = {}
    compared = set(baseline + recent)
    for i, (include, terms, month) in enumerate(zip(mask, analysis.terms, analysis.papers.month)):
        if include:
            for t in candidates.intersection(terms):
                first_seen[t] = min(first_seen.get(t, month), month)
                if month in compared:
                    docsets[t].add(i)
    kept = []
    by_docs = {}
    for row in sorted(rows, key=lambda v: (-len(v["keyword"].split()), v["keyword"])):
        t = row["keyword"]
        key = frozenset(docsets[t])
        if any(f" {t} " in f" {longer} " for longer in by_docs.get(key, [])):
            continue
        by_docs.setdefault(key, []).append(t)
        row["first_seen"] = first_seen[t]
        kept.append(row)
    result.ranking = pd.DataFrame(kept, columns=columns).sort_values(
        ["score", "recent_papers", "keyword"], ascending=[False, False, True]).reset_index(drop=True)
    return result


def evidence(analysis: Analysis, keyword: str, cohort: str = "all", months: list[str] | None = None) -> pd.DataFrame:
    mask = analysis.mask(cohort) & np.array([keyword in terms for terms in analysis.terms], dtype=bool)
    if months is not None:
        mask &= analysis.papers.month.isin(months).to_numpy()
    return analysis.papers.loc[mask].sort_values("published", ascending=False)
