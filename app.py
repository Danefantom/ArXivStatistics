"""Run with: streamlit run app.py"""
from __future__ import annotations

import json
import threading
from datetime import date
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import plotly.express as px
import streamlit as st

from quantum_trends.analysis import analyze
from quantum_trends.arxiv_client import ArxivClient, default_dates, save_json
from quantum_trends.emergence import DEFAULT_CANONICAL_PATH, EmergenceSettings, emerging, evidence, parse_canonical
from quantum_trends.report import COLORS, cloud_figure

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title="Quantum physics in motion", page_icon="◌", layout="wide")
st.markdown("""<style>
.block-container{max-width:1450px;padding-top:2.5rem}h1{letter-spacing:-1.8px}
[data-testid="stMetric"]{border:1px solid #dce5e9;border-radius:12px;padding:16px;background:#f7fafb}
</style>""", unsafe_allow_html=True)


@st.cache_resource
def download_lock():
    return threading.Lock()


@st.cache_data(show_spinner=False)
def read_corpus(path: str, modified: int):
    return json.loads(Path(path).read_text(encoding="utf-8"))


@st.cache_data(show_spinner=False)
def cached_analysis(corpus: dict, min_df: int, compare_months: int, primary: bool, stopwords: str, today: str):
    return analyze(corpus, min_df=min_df, comparison_months=compare_months, primary_only=primary,
                   extra_stopwords=set(stopwords.splitlines()), as_of=date.fromisoformat(today))


@st.cache_data(show_spinner=False)
def cached_discovery(_analysis, signature: tuple, cohort: str, options: tuple, canonical_text: str):
    return emerging(_analysis, cohort, settings=EmergenceSettings(*options),
                    canonical_terms=parse_canonical(canonical_text))


with st.sidebar:
    st.title("◌ Quantum trends")
    st.caption("An arXiv research observatory")
    data_path = Path(st.text_input("Corpus file", str(ROOT / "data" / "corpus.json"))).expanduser()
    with st.expander("Fetch or refresh arXiv metadata"):
        st.caption("Downloads every indexed quant-ph match in the selected dates. Run one downloader at a time; a year can take several minutes. No API key is needed.")
        first, last = default_dates()
        with st.form("fetch"):
            start = st.date_input("First submission date", first, max_value=last)
            end = st.date_input("Last submission date", last, max_value=last)
            refresh = st.checkbox("Bypass the 24-hour cache")
            submit = st.form_submit_button("Download corpus", type="primary")
        if submit:
            lock = download_lock()
            if not lock.acquire(blocking=False):
                st.warning("A download is already running in this dashboard.")
            else:
                try:
                    with st.status("Downloading and verifying arXiv metadata…", expanded=True) as status:
                        client = ArxivClient(ROOT / ".cache" / "arxiv", refresh=refresh, progress=st.write)
                        corpus = client.fetch(start, end)
                        save_json(data_path, corpus)
                        status.update(label=f"Verified {len(corpus['papers']):,} papers", state="complete", expanded=False)
                    st.cache_data.clear()
                except Exception as exc:
                    st.error(str(exc))
                finally:
                    lock.release()
    st.divider()
    primary = st.checkbox("Primary quant-ph category only", help="By default, include papers cross-listed into quant-ph.")
    min_df = st.number_input("Minimum papers per keyword", 1, 1000, 5, help="For emerging terms, this many papers must be in the recent window.")
    compare_months = st.selectbox("Recent window (complete months)", [1, 2, 3, 6], index=2)
    with st.expander("Customize keyword exclusions"):
        stopwords = st.text_area("Additional words or phrases, one per line", height=130)
    with st.expander("Canonical vocabulary & emergence", expanded=False):
        st.caption("Exact matches are excluded. A new, longer phrase can contain canonical words.")
        canonical_text = st.text_area("Canonical terms, one per line", DEFAULT_CANONICAL_PATH.read_text(encoding="utf-8"), height=180)
        learn_canonical = st.checkbox("Also exclude historically common terms", True)
        canonical_pct = st.number_input("Historically common share (%)", 0.1, 100.0, 2.0, 0.5)
        min_growth = st.number_input("Minimum growth ratio", 1.0, 100.0, 1.5, 0.1)
        min_recent_months = st.number_input("Minimum recent months with matches", 1, 6, 2)
        phrases_only = st.checkbox("Multiword phrases only", True)
        min_title_papers = st.number_input("Minimum recent titles mentioning term", 0, 100, 1)
    st.caption("Source: arXiv API · titles & abstracts")

st.caption("ARXIV / RESEARCH OBSERVATORY")
st.title("Quantum physics, in motion.")
st.write("Discover growing terms beyond the standard vocabulary, in quantum physics and Lindblad-based open dynamics.")
if not data_path.is_file():
    st.info("No corpus found. Use the sidebar to download metadata, or run `python -m quantum_trends fetch` first.")
    st.stop()
try:
    corpus = read_corpus(str(data_path), data_path.stat().st_mtime_ns)
    analysis = cached_analysis(corpus, min_df, compare_months, primary, stopwords, last.isoformat())
except Exception as exc:
    st.error(f"Cannot analyze this corpus: {exc}")
    st.stop()

n, nl = len(analysis.papers), int(analysis.papers.lindblad.sum())
columns = st.columns(4)
for col, label, value in zip(columns, ["Quantum-physics papers", "Lindblad / GKSL candidates", "Lindblad share", "Calendar months"],
                             [f"{n:,}", f"{nl:,}", f"{100*nl/n if n else 0:.1f}%", str(len(analysis.months))]):
    col.metric(label, value)
st.caption(f"Original submissions: {corpus['start']} → {corpus['end']} · retrieved {corpus['retrieved_at'][:10]} · latest available abstracts")
st.info("Lindblad subset: explicit Lindblad, Lindbladian, GKSL, GKLS, GKS, or Gorini–Kossakowski–Sudarshan mentions in the title/abstract. This is a candidate screen; inspect the matching text in the paper explorer.")
cohort_label = st.radio("Analyze", ["All quantum physics", "Lindblad-based open dynamics"], horizontal=True)
cohort = "all" if cohort_label == "All quantum physics" else "lindblad"
signature = (str(data_path), data_path.stat().st_mtime_ns, min_df, compare_months, primary, stopwords, last.isoformat())
options = (learn_canonical, canonical_pct, min_growth, min_recent_months, phrases_only, min_title_papers)
with st.spinner("Finding growing terms outside the canonical vocabulary…"):
    discovery = cached_discovery(analysis, signature, cohort, options, canonical_text)
rank = discovery.ranking
emergence_tab, trends, overview, changes, explorer, method = st.tabs([
    "Emerging terms", "Keyword trajectories", "Frequency context", "All share changes", "Paper explorer", "Method & coverage"])

with emergence_tab:
    st.subheader("What is emerging beyond the canonical vocabulary?")
    if discovery.baseline:
        st.caption(f"Recent: {', '.join(discovery.recent)} · Historical baseline: {discovery.baseline[0]} → {discovery.baseline[-1]}")
    st.write("Ranked by excess recent papers × log₂ growth in paper share. Established vocabulary is excluded using the editable list and, optionally, earlier-month prevalence.")
    st.caption("Candidates indicate growing language within this snapshot, not inventions or first appearances in the field. A term absent from the baseline may predate the entire dataset.")
    if rank.empty:
        st.info("No candidates meet these filters, or there are not enough complete months with cohort papers. Try a lower recent support threshold or edit the canonical vocabulary. No common keywords are substituted.")
    else:
        left, right = st.columns([1.3, 1])
        with left:
            shown = rank.head(15).iloc[::-1]
            fig = px.bar(shown, x="score", y="keyword", orientation="h", color_discrete_sequence=[COLORS[0]],
                         hover_data=["baseline_papers", "recent_papers", "baseline_pct", "recent_pct", "growth_ratio"],
                         labels={"score": "Emergence score", "keyword": ""})
            fig.update_layout(height=560)
            st.plotly_chart(fig, width="stretch")
        with right:
            fig = cloud_figure(analysis, cohort, discovery)
            st.pyplot(fig, width="stretch")
            plt.close(fig)
        display_columns = ["keyword", "baseline_papers", "recent_papers", "baseline_pct", "recent_pct", "growth_ratio", "recent_months", "recent_title_papers", "status"]
        st.dataframe(rank[display_columns].head(50), hide_index=True, width="stretch",
                     column_config={name: st.column_config.NumberColumn(name.replace("_", " "), format="%.2f")
                                    for name in ["baseline_pct", "recent_pct", "growth_ratio"]})
        st.download_button("Download emerging terms", rank.to_csv(index=False), f"{cohort}_emerging.csv", "text/csv")
        st.subheader("Inspect the supporting papers")
        candidate = st.selectbox("Emerging keyword", rank.keyword.tolist(), key=f"emerging_keyword_{cohort}")
        selected_evidence = evidence(analysis, candidate, cohort, discovery.recent)
        st.caption(f"{len(selected_evidence)} recent papers containing this extracted term. Select a row to inspect its abstract.")
        event = st.dataframe(selected_evidence[["title", "published", "url"]].reset_index(drop=True),
                             hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
                             column_config={"url": st.column_config.LinkColumn("arXiv", display_text="Read paper")},
                             key=f"emergence_evidence_{cohort}_{candidate}")
        if event.selection.rows and event.selection.rows[0] < len(selected_evidence):
            st.write(selected_evidence.iloc[event.selection.rows[0]].abstract)
        st.download_button("Download supporting papers", selected_evidence.to_csv(index=False), f"{cohort}_emerging_evidence.csv", "text/csv")
    with st.expander(f"Inspect the canonical set ({len(discovery.canonical):,} excluded terms)"):
        st.caption(f"Learned terms must reach {canonical_pct:g}% of baseline papers overall and in at least three baseline months (or all baseline months if fewer than three). Recent months are never used to learn this set. Exclusion is by exact normalized phrase.")
        st.dataframe(discovery.canonical, hide_index=True, width="stretch")
        st.download_button("Download canonical set", discovery.canonical.to_csv(index=False), f"{cohort}_canonical.csv", "text/csv")

with overview:
    left, right = st.columns([1.7, 1])
    with left:
        fig = cloud_figure(analysis, cohort)
        st.pyplot(fig, width="stretch")
        plt.close(fig)
    with right:
        st.subheader("Most common keywords")
        top = analysis.ranked(cohort, 70)
        st.dataframe(top.head(18), hide_index=True, width="stretch",
                     column_config={"share_pct": st.column_config.NumberColumn("Share (%)", format="%.2f")})
        st.download_button("Download keyword frequencies", top.to_csv(index=False), f"{cohort}_keywords.csv", "text/csv")
    volume = analysis.volumes()
    volume["month_label"] = [m + (" *" if m not in analysis.complete_months else "") for m in volume.month]
    count_col = "all_papers" if cohort == "all" else "lindblad_papers"
    fig = px.bar(volume, x="month_label", y=count_col, color_discrete_sequence=[COLORS[0]],
                 labels={"month_label": "Submission month", count_col: "Papers"}, title="Monthly paper volume")
    fig.update_xaxes(type="category")
    st.plotly_chart(fig, width="stretch")
    if cohort == "lindblad":
        volume["share_pct"] = 100*volume.lindblad_papers / volume.all_papers.replace(0, np.nan)
        st.plotly_chart(px.line(volume, x="month_label", y="share_pct", markers=True,
                               title="Lindblad candidates as a share of all quantum physics",
                               labels={"month_label": "Submission month", "share_pct": "Share (%)"},
                               color_discrete_sequence=[COLORS[3]]).update_xaxes(type="category"), width="stretch")
    st.caption("\\* Partial month. Publication counts can lag arXiv processing.")

with trends:
    st.subheader("Follow keywords over time")
    vocabulary = sorted(k for k, v in analysis.frequencies(cohort).items() if v >= min_df)
    defaults = rank.head(6).keyword.tolist()
    selected = st.multiselect("Keywords", vocabulary, default=defaults, key=f"emerging_trajectories_{cohort}")
    measure = st.radio("Vertical axis", ["Share of papers (%)", "Number of papers"], horizontal=True)
    monthly = analysis.monthly(selected, cohort)
    if selected:
        y = "share_pct" if measure.startswith("Share") else "papers"
        monthly["month_label"] = [m + (" *" if m not in analysis.complete_months else "") for m in monthly.month]
        fig = px.line(monthly, x="month_label", y=y, color="keyword", markers=True,
                      hover_data=["papers", "total_papers", "full_month"], color_discrete_sequence=COLORS,
                      labels={"month_label": "Submission month", "share_pct": "Share of papers (%)", "papers": "Papers", "keyword": "Keyword"})
        fig.update_traces(connectgaps=False)
        fig.update_xaxes(type="category")
        fig.update_yaxes(rangemode="tozero")
        st.plotly_chart(fig, width="stretch")
        st.download_button("Download monthly keyword data", monthly.to_csv(index=False), f"{cohort}_monthly.csv", "text/csv")
    else:
        st.info("Select one or more keywords.")
    st.caption("The share uses that month's paper count in the selected cohort. Empty months produce gaps; * marks partial months.")

with changes:
    previous, recent = analysis.windows()
    delta = analysis.changes(cohort)
    if not previous or delta.empty:
        st.info("No comparison is available. Each window needs papers, and the selected window length needs twice as many consecutive complete calendar months.")
    else:
        st.subheader("Which keywords gained or lost share?")
        st.caption(f"Recent: {', '.join(recent)} · Previous: {', '.join(previous)}")
        st.write("A change of +2 percentage points means the term appeared in two more papers per hundred. These are descriptive comparisons, not statistical significance claims.")
        direction = st.radio("Show", ["Increasing", "Decreasing"], horizontal=True)
        shown = delta[delta.change_pp > 0].head(15) if direction == "Increasing" else delta[delta.change_pp < 0].sort_values("change_pp").head(15)
        fig = px.bar(shown.sort_values("change_pp"), x="change_pp", y="keyword", orientation="h",
                     labels={"change_pp": "Change (percentage points)", "keyword": ""}, color_discrete_sequence=[COLORS[0]])
        fig.update_layout(height=520)
        st.plotly_chart(fig, width="stretch")
        st.dataframe(shown, hide_index=True, width="stretch")
        st.download_button("Download all keyword changes", delta.to_csv(index=False), f"{cohort}_changes.csv", "text/csv")
    if cohort == "lindblad":
        st.subheader("Distinctive keywords")
        st.caption("Subset versus its disjoint complement; 0.5-count smoothing stabilizes the frequency ratio. Defining Lindblad terms are omitted.")
        st.dataframe(analysis.enrichment().head(30), hide_index=True, width="stretch")

with explorer:
    st.subheader("Read the papers behind the patterns")
    term = st.selectbox("Require an extracted keyword", ["Any keyword"] + vocabulary, key=f"paper_keyword_{cohort}")
    query = st.text_input("Search title, abstract, or author")
    mask = analysis.mask(cohort)
    if term != "Any keyword":
        mask &= np.array([term in terms for terms in analysis.terms], dtype=bool)
    papers = analysis.papers.loc[mask].copy()
    if query:
        text = papers.title + " " + papers.abstract + " " + papers.authors.map(lambda v: " ".join(v))
        papers = papers[text.str.contains(query, case=False, regex=False)]
    papers = papers.sort_values("published", ascending=False)
    st.caption(f"{len(papers):,} matching papers. Select a row to inspect the abstract and Lindblad evidence.")
    shown = papers[["title", "published", "url", "primary_category", "lindblad"]].reset_index(drop=True)
    event = st.dataframe(shown, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
                         column_config={"url": st.column_config.LinkColumn("arXiv", display_text="Open paper")}, key=f"papers_{cohort}_{term}_{query}")
    if event.selection.rows and event.selection.rows[0] < len(papers):
        paper = papers.iloc[event.selection.rows[0]]
        st.markdown(f"**{paper.title}**")
        st.write(paper.abstract)
        if paper.match_evidence:
            st.caption("Lindblad screen match")
            st.write(paper.match_evidence)
    st.download_button("Download matching papers", papers.to_csv(index=False), f"{cohort}_papers.csv", "text/csv")

with method:
    st.markdown("""
    - **Source:** all indexed `quant-ph` papers in the date range, including cross-lists unless the primary-only filter is enabled.
    - **Dates:** first submission, not update date; latest metadata can change historical counts.
    - **Keywords:** English stopwords and generic prose removed; selected synonyms/plurals merged; adjacent one-, two- and three-word terms plus curated physics phrases. No paid API or model download.
    - **Counts:** document frequency, never repeated mentions within one paper. Shares are normalized within each cohort/month; terms overlap.
    - **Emergence:** the last selected number of complete months versus all earlier complete months. Default candidates need at least five recent papers, matches in two recent months (or one for a one-month window), at least one recent title, and 1.5× growth in smoothed share. Multiword phrases are the default. The canonical list and thresholds are editable; historical exclusions use only baseline months, independently per cohort.
    - **Score:** excess recent papers above the baseline rate × log₂(smoothed share ratio). Smoothing is `(matches + 0.5)/(papers + 1)`. This is a descriptive discovery ranking, not a significance test. Nested phrases are collapsed only when their supporting paper sets are identical.
    - **Comparison:** the last selected number of complete months versus the preceding equal-length window. Shares pool papers across each window. Partial months and zero-denominator windows are excluded.
    - **Lindblad scope:** an explicit mention screen, not a full-text or semantic classifier. It can miss implicit descriptions and include discussions that compare with, or go beyond, Lindblad dynamics. Review the evidence before treating the subset as a systematic review.
    - **Interpretation:** topic language, not citation impact or research quality. Sparse-keyword changes are unstable. Word sizes are comparable within a cloud only.
    - **Retrieval:** sequential requests, at least 3.1 seconds apart; 24-hour page cache; retries; monthly totals checked; failures stop the download instead of silently returning a truncated sample.
    """)
    st.dataframe(corpus["coverage"], hide_index=True, width="stretch")
    st.caption(f"Oldest API response in this corpus: {corpus.get('oldest_response_at', 'unknown')}")
    st.markdown("We thank arXiv for use of its open access interoperability. [API documentation](https://info.arxiv.org/help/api/user-manual.html) · [API terms](https://info.arxiv.org/help/api/tou.html)")
