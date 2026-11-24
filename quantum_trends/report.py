"""Static figures, audit tables, and a portable, self-contained HTML report."""
from __future__ import annotations

import base64
import html
import io
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from wordcloud import WordCloud

from .analysis import Analysis

COLORS = ["#0d9488", "#2563eb", "#e87924", "#8b5cf6", "#e34b6c", "#78902a", "#9a6324", "#64748b"]
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.spines.top": False,
                     "axes.spines.right": False, "axes.labelcolor": "#334155",
                     "text.color": "#172b45", "axes.titleweight": "bold", "figure.facecolor": "white"})


def cloud_figure(analysis: Analysis, cohort: str):
    top = analysis.ranked(cohort, 70)
    fig, ax = plt.subplots(figsize=(12, 5.8))
    if top.empty:
        ax.text(.5, .5, "No keywords meet the minimum paper count", ha="center", va="center")
    else:
        cloud = WordCloud(width=1500, height=680, background_color="white", colormap="viridis",
                          prefer_horizontal=.93, random_state=42, collocations=False,
                          max_font_size=130, min_font_size=13, relative_scaling=.5,
                          font_path=matplotlib.font_manager.findfont("DejaVu Sans"))
        cloud.generate_from_frequencies(dict(zip(top.keyword, top.papers)))
        ax.imshow(cloud, interpolation="bilinear")
    ax.axis("off")
    label = "Lindblad / GKSL" if cohort == "lindblad" else "Quantum physics"
    ax.set_title(f"{label} · Keywords in titles & abstracts", loc="left", pad=16, fontsize=17)
    fig.text(.04, .015, "Word size reflects document frequency · a paper counts once per term", fontsize=10, color="#64748b")
    fig.tight_layout(rect=(0, .035, 1, 1))
    return fig


def trends_figure(analysis: Analysis, cohort: str, keywords: list[str] | None = None):
    keywords = keywords or analysis.ranked(cohort, 6).keyword.tolist()
    fig, ax = plt.subplots(figsize=(12, 5.8))
    x = np.arange(len(analysis.months))
    for i, term in enumerate(keywords):
        df = analysis.monthly([term], cohort)
        ax.plot(x, df.share_pct, marker="o", ms=4, linewidth=2, label=term, color=COLORS[i % len(COLORS)])
    for i, month in enumerate(analysis.months):
        if month not in analysis.complete_months:
            ax.axvspan(i-.4, i+.4, color="#e2e8f0", alpha=.65, zorder=0)
    if not keywords:
        ax.text(.5, .5, "No keywords meet the minimum paper count", transform=ax.transAxes, ha="center")
    ax.set_xticks(x, [m + ("*" if m not in analysis.complete_months else "") for m in analysis.months], rotation=40, ha="right")
    ax.set_ylabel("Papers mentioning term (%)")
    ax.set_ylim(bottom=0)
    ax.grid(axis="y", color="#e2e8f0", linewidth=.7)
    label = "Lindblad / GKSL" if cohort == "lindblad" else "Quantum physics"
    ax.set_title(f"{label} · How attention changes over time", loc="left", pad=18, fontsize=17)
    if keywords:
        ax.legend(loc="upper center", bbox_to_anchor=(.5, -.22), ncol=3, frameon=False, fontsize=10)
    fig.text(.04, .01, "* Partial calendar month · gaps mean no papers in that cohort/month", color="#64748b", fontsize=10)
    fig.tight_layout(rect=(0, .04, 1, 1))
    return fig


def volumes_figure(analysis: Analysis):
    df = analysis.volumes()
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))
    x = np.arange(len(df))
    axes[0].bar(x, df.all_papers, color="#0d9488", width=.65)
    axes[1].plot(x, 100*df.lindblad_papers/df.all_papers.replace(0, np.nan), color="#8b5cf6", marker="o", linewidth=2)
    axes[0].set_title("Quantum-physics submissions", loc="left", pad=16)
    axes[0].set_ylabel("Papers")
    axes[1].set_title("Lindblad subset / all quantum physics", loc="left", pad=16)
    axes[1].set_ylabel("Share of papers (%)")
    labels = [m + ("*" if m not in analysis.complete_months else "") for m in df.month]
    for ax in axes:
        ax.set_xticks(x, labels, rotation=50, ha="right", fontsize=9)
        ax.set_ylim(bottom=0)
        ax.grid(axis="y", color="#e2e8f0", linewidth=.6)
        ax.set_axisbelow(True)
    fig.text(.025, .015, "* Partial month; current submission counts can lag arXiv processing.", fontsize=9, color="#64748b")
    fig.tight_layout(rect=(0, .045, 1, 1))
    return fig


def image_tag(fig, path: Path, alt: str) -> str:
    fig.savefig(path, dpi=160, bbox_inches="tight")
    fig.savefig(path.with_suffix(".svg"), bbox_inches="tight")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=125, bbox_inches="tight")
    plt.close(fig)
    encoded = base64.b64encode(buf.getvalue()).decode()
    return f'<img alt="{html.escape(alt)}" src="data:image/png;base64,{encoded}">'


def table(df, count=12) -> str:
    return df.head(count).to_html(index=False, float_format=lambda x: f"{x:.2f}", border=0, classes="data")


def export_report(analysis: Analysis, output: Path, keywords: list[str] | None = None) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    figures = output / "figures"
    figures.mkdir(exist_ok=True)
    tables = output / "tables"
    tables.mkdir(exist_ok=True)
    corpus = analysis.corpus
    papers = analysis.papers.copy()
    # Structured lists become readable cells; the original corpus preserves arrays.
    for column in ["authors", "categories"]:
        papers[column] = papers[column].map(lambda value: "; ".join(value))
    papers.to_csv(tables / "papers.csv", index=False)
    papers[papers.lindblad].to_csv(tables / "lindblad_papers.csv", index=False)
    analysis.volumes().to_csv(tables / "monthly_volume.csv", index=False)
    enrichment = analysis.enrichment()
    enrichment.to_csv(tables / "lindblad_enrichment.csv", index=False)
    prev, recent = analysis.windows()
    windows = f"{', '.join(recent)} versus {', '.join(prev)}" if prev else "Not enough consecutive complete months for the selected comparison."
    n, nl = len(papers), int(papers.lindblad.sum())
    scope = "primary quant-ph only" if analysis.primary_only else "quant-ph including cross-lists"
    body = f"""<header><div class="eyebrow">ARXIV / RESEARCH OBSERVATORY</div>
    <h1>Quantum physics,<br><span>in motion.</span></h1>
    <p>Keyword trends from {html.escape(corpus['start'])} through {html.escape(corpus['end'])}.</p>
    <p class="muted">{scope} · title and abstract analysis · source: arXiv API</p></header>
    <div class="metrics"><div><b>{n:,}</b><span>quantum-physics papers</span></div>
    <div><b>{nl:,}</b><span>Lindblad / GKSL candidates</span></div>
    <div><b>{100*nl/n if n else 0:.1f}%</b><span>of analyzed papers</span></div>
    <div><b>{len(analysis.months)}</b><span>calendar months</span></div></div>
    <div class="note">The Lindblad subset is a transparent title/abstract screening rule. It includes explicit
    Lindblad, Lindbladian, GKSL, GKLS, GKS, or Gorini–Kossakowski–Sudarshan mentions. Mentions can be comparisons or
    negations; review the evidence in <code>tables/lindblad_papers.csv</code>. Full texts are not searched.</div>
    <section><h2>The publication landscape</h2>"""
    body += image_tag(volumes_figure(analysis), figures / "publication_volume.png", "Monthly paper counts and Lindblad share") + "</section>"
    for cohort, label in [("all", "All quantum physics"), ("lindblad", "Lindblad-based open dynamics · candidate subset")]:
        top = analysis.ranked(cohort, 70)
        top.to_csv(tables / f"{cohort}_keywords.csv", index=False)
        selected = keywords or top.head(6).keyword.tolist()
        exported_terms = list(dict.fromkeys(top.head(30).keyword.tolist() + selected))
        analysis.monthly(exported_terms, cohort).to_csv(tables / f"{cohort}_monthly_keywords.csv", index=False)
        changes = analysis.changes(cohort)
        changes.to_csv(tables / f"{cohort}_changes.csv", index=False)
        body += f'<section><div class="eyebrow">{"01 / THE FIELD" if cohort == "all" else "02 / THE FOCUS"}</div><h2>{label}</h2>'
        body += image_tag(cloud_figure(analysis, cohort), figures / f"{cohort}_wordcloud.png", f"{label} word cloud")
        body += image_tag(trends_figure(analysis, cohort, selected), figures / f"{cohort}_trends.png", f"{label} monthly keyword trends")
        body += '<h3>Most common keywords</h3>' + table(top, 12)
        body += '<h3>Recent changes in keyword share</h3><p>' + html.escape(windows) + '</p>'
        body += '<p class="muted">Percentage-point changes in pooled paper shares, excluding partial months. Descriptive rankings, not significance tests.</p>'
        if changes.empty:
            body += '<p>No comparison available for this cohort and window.</p>'
        else:
            cols = ["keyword", "previous_papers", "recent_papers", "previous_pct", "recent_pct", "change_pp"]
            body += '<div class="twocol"><div><h4>Increasing</h4>' + table(changes[changes.change_pp > 0][cols], 10) + '</div>'
            body += '<div><h4>Decreasing</h4>' + table(changes[changes.change_pp < 0].sort_values("change_pp")[cols], 10) + '</div></div>'
        body += '</section>'
    body += '<section><h2>What distinguishes the Lindblad subset?</h2><p>Frequency relative to papers outside the subset. Ratios use 0.5-count smoothing; defining Lindblad terms are excluded.</p>'
    body += table(enrichment, 15) + '</section>'
    body += f"""<section><h2>How to read this analysis</h2><ul>
    <li>Each paper contributes at most once per keyword. A paper may mention many keywords; shares do not sum to 100%.</li>
    <li>Unigrams and adjacent two/three-word phrases are extracted after removing English stopwords, mathematical markup, and generic prose. An editable dictionary merges selected synonyms and plurals.</li>
    <li>Monthly share = matching papers / all papers in that cohort and month. Zero-paper months have an undefined share, not zero.</li>
    <li>The minimum document count is {analysis.min_df}. Word-cloud sizes are relative within each panel; compare exact percentages in tables.</li>
    <li>Growth compares the last {analysis.comparison_months} complete calendar months with the preceding {analysis.comparison_months}, weighted by paper counts. Sparse terms can fluctuate sharply.</li>
    <li>Dates are original submissions (version 1), while titles and abstracts are the latest metadata returned by arXiv. Revisions may change historical keyword counts.</li>
    <li>Coverage is checked against API totals, with one record per arXiv ID. Complete retrieval means all indexed matches at retrieval time; indexing delays can still affect recent dates.</li>
    <li>This measures language and topic attention, not scientific quality, citations, or proven research impact. The Lindblad screen can miss implicit descriptions and include incidental mentions.</li>
    </ul><p>Retrieved: {html.escape(corpus['retrieved_at'])}. Oldest cached API response: {html.escape(str(corpus.get('oldest_response_at', 'unknown')))}.</p>
    <p>We thank arXiv for use of its open access interoperability.
    <a href="https://info.arxiv.org/help/api/user-manual.html">API documentation</a> ·
    <a href="https://info.arxiv.org/help/api/tou.html">API terms</a></p></section>"""
    css = """*{box-sizing:border-box}body{margin:0;background:#f4f7f8;color:#172b45;font:16px/1.65 system-ui,sans-serif}
    main{max-width:1280px;margin:auto;padding:55px 42px}header{padding:20px 0 30px}.eyebrow{font-size:12px;font-weight:750;letter-spacing:2px;color:#0d9488}
    h1{font-size:66px;line-height:1.08;letter-spacing:-3px;margin:24px 0}h1 span{color:#0d9488}h2{font-size:28px;line-height:1.25}h3{margin-top:32px}
    .muted{color:#64748b}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:15px;margin:20px 0 30px}.metrics div{background:white;border:1px solid #dce5e9;border-radius:12px;padding:22px}
    .metrics b{display:block;font-size:36px;font-weight:650}.metrics span{font-size:13px;color:#64748b}.note{border-left:4px solid #0d9488;padding:18px 22px;background:#e9f6f3;border-radius:4px}
    section{background:white;border:1px solid #dce5e9;border-radius:15px;padding:32px;margin-top:28px;overflow-x:auto}img{display:block;width:100%;height:auto;margin:12px 0 28px}
    table{border-collapse:collapse;width:100%;font-size:13px}th{text-align:left;color:#64748b;font-size:11px}td,th{padding:10px 9px;border-bottom:1px solid #e2e8f0}tr:nth-child(even){background:#f8fafc}
    .twocol{display:grid;grid-template-columns:1fr 1fr;gap:28px}.twocol>div{overflow:auto}a{color:#0d9488}li{margin:9px 0}code{font-size:13px}
    @media(max-width:850px){main{padding:24px 15px}h1{font-size:48px}.metrics{grid-template-columns:1fr 1fr}.twocol{grid-template-columns:1fr}section{padding:22px 16px}}
    """
    path = output / "report.html"
    path.write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>arXiv quantum keyword trends</title><style>' + css + '</style><main>' + body + '</main></html>', encoding="utf-8")
    summary = {k: v for k, v in corpus.items() if k != "papers"}
    summary.update({"analyzed_papers": n, "lindblad_candidates": nl, "primary_only": analysis.primary_only,
                    "min_df": analysis.min_df, "comparison_months": analysis.comparison_months,
                    "previous_window": prev, "recent_window": recent})
    (output / "manifest.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return path
