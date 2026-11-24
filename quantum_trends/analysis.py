"""Transparent title/abstract extraction; every count is document frequency."""
from __future__ import annotations

import calendar
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

BOILERPLATE = set("""abstract paper work present presents presented propose proposed proposes
show shows shown study studies studied investigate investigates investigated demonstrate
demonstrates demonstrated consider considers considered obtain obtained results result
approach approaches method methods framework provide provides provided use used using
based new novel also can may thus however furthermore within via particular general
well known respectively example examples allow allows enable enables find found
significant significantly numerical numerically analytical analytically theoretical
theoretically experimental experimentally properties property behavior behaviour
different various certain corresponding associated effective possible case cases
first second order describe described description establish established prove proven
derive derived introduce introduced investigate understanding application applications
analysis demonstrate determine determined develop developed reveal revealed
apply applied applies applying remain remains remaining require requires required requiring
construct constructs constructed construction extend extends extended extending extension
lead leads leading yield yields yielding take takes taken taking give gives given giving
use uses obtain obtaining demonstrate demonstrating show showing propose proposing
allow allowing include includes included including involve involves involved involving
explore explores explored exploring achieve achieves achieved achieving address addresses
addressed addressing discuss discusses discussed discussing introduce introducing
prove proves proving derive derives deriving establish establishes establishing
presenting consider considering provide providing find finding notably therefore
investigating exhibit exhibits exhibited exhibiting capture captures captured capturing
identify identifies identified identifying illustrate illustrates illustrated illustrating
formulate formulates formulated formulating tackle tackling perform performs performed
performing assess assessing clarify clarifying demonstrate demonstrating suggest suggests
suggested suggesting highlight highlights highlighted highlighting enable enabling
""".split())
# Generic single words remain available inside meaningful adjacent phrases.
GENERIC = set("""quantum system state model dynamics time classical physical physics equation
process effect parameter regime limit technique form number non single high low local finite
dimensional exact exactly open master information space structure theory universal arbitrary
closed strong weak large small long short fully simple efficiently efficient independent
constant fixed lower upper standard natural fundamental relevant including consider
size dimension input output optimal level type step role term context degree scheme
setting scenario class family problem task range framework solution equation process""".split())
STOP = set(ENGLISH_STOP_WORDS) | BOILERPLATE
PLURALS = dict(zip(
    "qubits states systems models channels networks circuits gates operators equations trajectories correlations measurements simulations transitions phases modes photons spins atoms algorithms errors reservoirs baths symmetries eigenvalues interactions fluctuations resources bounds ensembles processes effects parameters techniques limits times generators".split(),
    "qubit state system model channel network circuit gate operator equation trajectory correlation measurement simulation transition phase mode photon spin atom algorithm error reservoir bath symmetry eigenvalue interaction fluctuation resource bound ensemble process effect parameter technique limit time generator".split()))
PLURALS.update({"batteries": "battery", "samplers": "sampler", "queries": "query", "codes": "code",
                "observables": "observable", "functions": "function"})

# Explicit, editable aliases; no external embedding model or API key is needed.
ALIASES = [
    (r"\bquantum (?:error correcting|error correction)\b", "quantum error correction"),
    (r"\b(?:open quantum systems?|quantum open systems?)\b", "open quantum system"),
    (r"\b(?:gorini\W+kossakowski\W+(?:sudarshan(?:\W+lindblad)?|lindblad\W+sudarshan)|gksl|gkls|gks)\b", "lindblad"),
    (r"\blindbladians?\b", "lindblad"),
    (r"\bnon[\s-]*markovian\b", "non markovian"),
    (r"\bnon[\s-]*hermitian\b", "non hermitian"),
    (r"\bnon[\s-]*equilibrium\b", "nonequilibrium"),
    (r"\bsteady[\s-]*states?\b", "steady state"),
    (r"\bmany[\s-]*bod(?:y|ies)\b", "many body"),
    (r"\bfew[\s-]*bod(?:y|ies)\b", "few body"),
]

CURATED = [
    "quantum error correction", "open quantum system", "quantum computing",
    "quantum computation", "quantum simulation", "quantum information",
    "quantum control", "quantum thermodynamics", "quantum metrology",
    "quantum sensing", "quantum communication", "quantum entanglement",
    "quantum advantage", "quantum algorithm", "quantum circuit", "quantum channel",
    "quantum trajectory", "quantum speed limit", "error mitigation", "error correction",
    "tensor network", "matrix product state", "neural network", "machine learning",
    "deep learning", "reinforcement learning", "reservoir engineering",
    "dissipative phase transition", "phase transition", "exceptional point",
    "liouvillian gap", "lindblad master equation", "lindblad equation", "master equation",
    "steady state", "non markovian", "non hermitian", "many body", "few body",
    "markovian dynamics", "dissipative dynamics", "decoherence free subspace",
    "density matrix", "entropy production", "detailed balance", "quantum jump",
    "measurement induced", "topological order", "strong coupling", "weak coupling",
    "adiabatic elimination", "dynamical phase transition", "floquet",
]

LINDBLAD = re.compile(
    r"\blindblad(?:ian)?s?\b|\bgksl\b|\bgkls\b|\bgks\b|"
    r"\bgorini[\s-]+kossakowski[\s-]+sudarshan\b", re.I)


def lindblad_evidence(text: str) -> str:
    """Explicit markers imply a candidate, not verified use of Lindblad dynamics."""
    normalized = text.replace("–", "-").replace("—", "-")
    match = LINDBLAD.search(normalized)
    if not match:
        return ""
    return "…" + " ".join(normalized[max(0, match.start()-85):match.end()+120].split()) + "…"


def normalize(text: str) -> list[str]:
    text = text.replace("–", "-").replace("—", "-").replace("−", "-")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    # Keep sentence/math boundaries, so n-grams cannot bridge unrelated passages.
    text = re.sub(r"\$\$.*?\$\$|\$[^$]*\$|\\\(.*?\\\)|\\\[.*?\\\]", " . ", text, flags=re.S)
    text = re.sub(r"\\[a-zA-Z]+", " ", text)
    for pattern, replacement in ALIASES:
        text = re.sub(pattern, replacement, text)
    text = re.sub(r"[-/]", " ", text)
    tokens = re.findall(r"[a-z][a-z0-9]*|[.!?;:\n]", text)
    return [PLURALS.get(t, t) for t in tokens]


def extract_terms(text: str, ngram_max: int = 3, extra_stopwords: set[str] | None = None) -> set[str]:
    tokens = normalize(text)
    extra = {s.strip().lower() for s in (extra_stopwords or set()) if s.strip()}
    stop = STOP | extra
    terms = {t for t in tokens if len(t) > 2 and t not in stop and t not in GENERIC and t.isalpha()}
    # Extract adjacent phrases without joining words across removed stopwords.
    for n in range(2, ngram_max + 1):
        for i in range(len(tokens) - n + 1):
            window = tokens[i:i+n]
            if (all(t.isalpha() and len(t) > 1 and t not in stop for t in window)
                    and window[-1] not in {"quantum", "non", "many", "single", "high", "low", "finite"}):
                terms.add(" ".join(window))
    padded = " " + " ".join(tokens) + " "
    for phrase in CURATED:
        if " " + phrase + " " in padded and not any(t in extra for t in phrase.split()):
            terms.add(phrase)
    return terms - extra


@dataclass
class Analysis:
    corpus: dict
    papers: pd.DataFrame
    terms: list[set[str]]
    months: list[str]
    complete_months: list[str]
    min_df: int
    comparison_months: int
    primary_only: bool

    def mask(self, cohort: str) -> np.ndarray:
        if cohort == "lindblad":
            return self.papers["lindblad"].to_numpy(dtype=bool, copy=True)
        if cohort == "other":
            return ~self.papers["lindblad"].to_numpy(dtype=bool)
        return np.ones(len(self.papers), dtype=bool)

    def frequencies(self, cohort: str = "all", months: list[str] | None = None) -> Counter:
        mask = self.mask(cohort)
        if months is not None:
            mask &= self.papers["month"].isin(months).to_numpy()
        counts: Counter = Counter()
        for include, terms in zip(mask, self.terms):
            if include:
                counts.update(terms)
        return counts

    def ranked(self, cohort: str = "all", limit: int = 60) -> pd.DataFrame:
        counts = self.frequencies(cohort)
        total = int(self.mask(cohort).sum())
        # Suppress a shorter phrase only if a longer phrase has the same document set.
        ordered = sorted(((k, v) for k, v in counts.items() if v >= self.min_df and not (cohort == "lindblad" and k == "lindblad")), key=lambda kv: (-kv[1], -len(kv[0].split()), kv[0]))
        kept = []
        for term, n in ordered:
            if any(n == prev_n and f" {term} " in f" {prev} " for prev, prev_n in kept):
                continue
            kept.append((term, n))
            if len(kept) == limit:
                break
        return pd.DataFrame([{"keyword": k, "papers": n, "share_pct": 100*n/total} for k, n in kept], columns=["keyword", "papers", "share_pct"])

    def monthly(self, keywords: list[str], cohort: str = "all") -> pd.DataFrame:
        rows = []
        for month in self.months:
            mask = self.mask(cohort) & self.papers["month"].eq(month).to_numpy()
            denominator = int(mask.sum())
            counts = self.frequencies(cohort, [month])
            for term in keywords:
                n = counts[term]
                rows.append({"month": month, "keyword": term, "papers": n, "total_papers": denominator,
                             "share_pct": 100*n/denominator if denominator else np.nan,
                             "full_month": month in self.complete_months})
        return pd.DataFrame(rows, columns=["month", "keyword", "papers", "total_papers", "share_pct", "full_month"])

    def volumes(self) -> pd.DataFrame:
        return pd.DataFrame([{"month": m, "all_papers": int(self.papers["month"].eq(m).sum()),
                              "lindblad_papers": int((self.papers["month"].eq(m) & self.papers["lindblad"]).sum()),
                              "full_month": m in self.complete_months} for m in self.months])

    def windows(self) -> tuple[list[str], list[str]]:
        n = self.comparison_months
        # Do not bridge missing/incomplete months in a comparison.
        if len(self.complete_months) < 2*n:
            return [], []
        selected = self.complete_months[-2*n:]
        expected = pd.period_range(selected[0], selected[-1], freq="M").astype(str).tolist()
        if selected != expected:
            return [], []
        return selected[:n], selected[n:]

    def changes(self, cohort: str = "all") -> pd.DataFrame:
        columns = ["keyword", "previous_papers", "recent_papers", "previous_total", "recent_total",
                   "previous_pct", "recent_pct", "change_pp"]
        previous, recent = self.windows()
        if not previous:
            return pd.DataFrame(columns=columns)
        p = self.frequencies(cohort, previous)
        r = self.frequencies(cohort, recent)
        mask = self.mask(cohort)
        npapers = int((mask & self.papers["month"].isin(previous).to_numpy()).sum())
        nrpapers = int((mask & self.papers["month"].isin(recent).to_numpy()).sum())
        if not npapers or not nrpapers:
            return pd.DataFrame(columns=columns)
        rows = [{"keyword": term, "previous_papers": p[term], "recent_papers": r[term],
                 "previous_total": npapers, "recent_total": nrpapers,
                 "previous_pct": 100*p[term]/npapers, "recent_pct": 100*r[term]/nrpapers,
                 "change_pp": 100*(r[term]/nrpapers - p[term]/npapers)}
                for term in p.keys() | r.keys() if p[term] + r[term] >= self.min_df]
        return pd.DataFrame(rows, columns=columns).sort_values(["change_pp", "recent_papers", "keyword"], ascending=[False, False, True]).reset_index(drop=True)

    def enrichment(self) -> pd.DataFrame:
        """Subset versus its disjoint complement, with Jeffreys smoothing."""
        columns = ["keyword", "lindblad_papers", "other_papers", "lindblad_pct", "other_pct", "ratio"]
        nl, no = int(self.mask("lindblad").sum()), int(self.mask("other").sum())
        if nl == 0 or no == 0:
            return pd.DataFrame(columns=columns)
        left, right = self.frequencies("lindblad"), self.frequencies("other")
        rows = [{"keyword": term, "lindblad_papers": n, "other_papers": right[term],
                 "lindblad_pct": 100*n/nl, "other_pct": 100*right[term]/no,
                 "ratio": ((n+.5)/(nl+1))/((right[term]+.5)/(no+1))}
                for term, n in left.items() if n >= self.min_df and not
                ({"lindblad", "gorini", "kossakowski", "sudarshan", "gksl", "gkls", "gks"} & set(term.split()))]
        return pd.DataFrame(rows, columns=columns).sort_values(["ratio", "keyword"], ascending=[False, True]).reset_index(drop=True)


def analyze(corpus: dict, *, min_df: int = 5, comparison_months: int = 3,
            primary_only: bool = False, extra_stopwords: set[str] | None = None,
            as_of: date | None = None) -> Analysis:
    if min_df < 1 or comparison_months < 1:
        raise ValueError("min_df and comparison_months must be positive")
    start, end = date.fromisoformat(corpus["start"]), date.fromisoformat(corpus["end"])
    if start > end:
        raise ValueError("Invalid corpus date range")
    if not corpus.get("complete"):
        raise ValueError("Corpus is incomplete; retrieve a complete date range before analyzing")
    as_of = as_of or datetime.now(timezone.utc).date()
    months = pd.period_range(start, end, freq="M").astype(str).tolist()
    coverage = {row["month"]: row for row in corpus.get("coverage", [])}
    for month in months:
        row = coverage.get(month)
        if not row or not row.get("complete") or row["retrieved"] != row["api_total"] - row.get("boundary_excluded", 0):
            raise ValueError(f"Missing or incomplete coverage for {month}")
    complete = []
    for month in months:
        year, m = map(int, month.split("-"))
        first, last = date(year, m, 1), date(year, m, calendar.monthrange(year, m)[1])
        if start <= first and end >= last and last < as_of:
            complete.append(month)
    rows, terms, seen = [], [], set()
    all_counts: Counter = Counter()
    for p in corpus["papers"]:
        identifier = re.sub(r"v\d+$", "", p["id"])
        if identifier in seen:
            raise ValueError(f"Duplicate paper ID: {identifier}")
        seen.add(identifier)
        submitted = date.fromisoformat(p["published"][:10])
        if not start <= submitted <= end or "quant-ph" not in p["categories"]:
            raise ValueError(f"Paper outside corpus scope: {identifier}")
        all_counts[submitted.strftime("%Y-%m")] += 1
        if primary_only and p["primary_category"] != "quant-ph":
            continue
        text = p["title"] + ". " + p["abstract"]
        evidence = lindblad_evidence(text)
        rows.append({**p, "id": identifier, "month": submitted.strftime("%Y-%m"),
                     "lindblad": bool(evidence), "match_evidence": evidence})
        terms.append(extract_terms(text, extra_stopwords=extra_stopwords))
    for month, row in coverage.items():
        if all_counts[month] != row["retrieved"]:
            raise ValueError(f"Record count does not match manifest for {month}")
    columns = ["id", "title", "abstract", "published", "updated", "categories", "primary_category", "authors", "url", "month", "lindblad", "match_evidence"]
    return Analysis(corpus, pd.DataFrame(rows, columns=columns), terms, months, complete, min_df, comparison_months, primary_only)
