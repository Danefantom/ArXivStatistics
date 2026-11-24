# arXiv Quantum Trends

A Python program for exploring recent keyword trends in arXiv `quant-ph`, with a separate Lindblad/GKSL open-dynamics candidate subset. It prioritizes **emerging terms outside an editable canonical vocabulary**, with an interactive Streamlit dashboard, an offline HTML report, score-weighted word clouds, time-series graphs, and auditable CSV exports. No API key or language-model service is required.

The bundled snapshot contains **20,755 papers**, including **551 Lindblad/GKSL candidates**, originally submitted from **1 December 2025 through 23 November 2026**. It was fetched on 23 November 2026, with coverage verified against arXiv API totals. November is a partial month. The saved corpus remains fixed until you fetch again.

## Start here

Open `report/report.html` in a browser to read the finished analysis immediately. This report embeds its figures and works offline without Python.

For the interactive dashboard, open a terminal in this folder. Python 3.10 or newer is required:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py --server.address 127.0.0.1
```

On Windows, activate the environment with `.venv\Scripts\activate` instead. Streamlit prints the local URL. The dashboard automatically opens the included corpus; use its sidebar to fetch another date range.

The dashboard supports:

- Switching between all quantum-physics papers and the Lindblad subset.
- Emerging-term rankings and word clouds weighted by growth, with supporting papers and an inspectable canonical exclusion list.
- Keyword trajectories defaulting to emerging candidates, plus a separate frequency-context view and monthly publication volume.
- Recent windows of 1, 2, 3, or 6 complete months compared with all earlier complete months for emergence; equal-length windows remain available for general share changes.
- Filtering to primary `quant-ph` papers, including or excluding cross-lists.
- Custom stopwords, searchable papers, clickable arXiv links, matching text, and CSV downloads.

## Emerging terms and the canonical baseline

The default view answers “which terms outside the canonical vocabulary are gaining attention?” rather than ranking the most frequent physics terms. It runs independently for the full corpus and the Lindblad subset.

The **canonical set** combines:

- An editable core list in `quantum_trends/canonical_keywords.txt`, also editable directly in the dashboard. The list is a starting point, not an authoritative taxonomy.
- Optional historical exclusions: terms occurring in at least **2% of baseline papers overall**, and reaching that threshold in at least **three baseline months** (or all baseline months when fewer are available). Only earlier data is used; recently popular terms cannot exclude themselves through this rule. This is learned separately for each cohort.

Exclusions match exact normalized terms. Excluding “error correction” still allows a longer phrase such as “autonomous error correction”. The exported canonical tables show each exclusion's reason and baseline counts. Use `--canonical my-vocabulary.txt` to replace the seed list and `--no-learn-canonical` to use only your own list. Lines beginning with `#` are comments.

By default, the recent period is the last **three complete months** (August–October 2026 in the snapshot), and the baseline is **all earlier complete months** (December 2025–July 2026). A candidate must:

- Be outside the canonical set and have at least **five recent papers**, with matches in **two recent months** (one when using a one-month window).
- Appear in at least **one recent paper title**. This helps suppress incidental abstract phrases.
- Be a multiword phrase, with a positive increase in paper share and at least **1.5× smoothed growth**.

The score balances growth and support:

```text
baseline_rate = baseline_matching_papers / baseline_total_papers
excess_recent_papers = recent_matching_papers - recent_total_papers * baseline_rate
smoothed_growth = ((recent_matching_papers + 0.5) / (recent_total_papers + 1))
                  / ((baseline_matching_papers + 0.5) / (baseline_total_papers + 1))
score = excess_recent_papers * log2(smoothed_growth)
```

This controls for different publication volumes and window lengths. Nested phrases are collapsed only when they have identical supporting paper sets. Generic prose fragments are filtered, but this remains lexical extraction: inspect the linked papers and refine the exclusions when needed.

“Not seen in baseline” means absent from the **earlier portion of this dataset**, not newly invented. Long-established methods can gain attention in a new context. A year of abstracts cannot establish field-wide novelty. Rankings are descriptive, with no claim of statistical significance, and rare-term growth is sensitive to the smoothing choice. If no candidate qualifies, the dashboard says so instead of substituting common terms. Partial months remain visible in trajectories but never affect the score or learned vocabulary.

## Command line

Fetch the most recent 12 calendar months, including the current partial month, and build a report:

```bash
python -m quantum_trends run
```

Choose a date range and output folder:

```bash
python -m quantum_trends run --start 2025-12-01 --end 2026-11-23 --output report
```

The range is inclusive by UTC submission date. With only `--end`, the default start is 12 calendar months back, including the end month. `--months 24` changes that span. These defaults are calculated at runtime.

Regenerate the report offline using the saved corpus:

```bash
python -m quantum_trends report --data data/corpus.json --output report
```

Track specific extracted terms and adjust the comparison:

```bash
python -m quantum_trends report --keywords "quantum error correction,tensor network,entanglement,steady state,non markovian" --compare-months 3 --min-df 5
```

Term names use normalized spelling, as shown in the dashboard or keyword tables. Explicitly requested terms are plotted even if below the minimum display count. An absent term has zero matches in months containing papers.

Download without analysis, or restrict analysis to primary-category papers:

```bash
python -m quantum_trends fetch --months 6 --data data/six-months.json
python -m quantum_trends report --primary-only
```

Customize the discovery criteria:

```bash
python -m quantum_trends report --canonical my-vocabulary.txt --canonical-pct 1.5 --min-df 8 --min-growth 2 --min-recent-months 2
```

Use `--include-unigrams` to admit single-word terms and acronyms. Use `--min-title-papers 0` to allow candidates found only in abstracts. `--min-df` is the minimum **recent** paper count for emergence; it remains an overall support threshold in the frequency-context views. The dashboard exposes all these options. Reports record the full configuration and explicit canonical list in `manifest.json`.

Use `--stopwords exclusions.txt` to exclude one word or phrase per line. Use `--refresh` on `fetch`/`run` to bypass cached pages. `--user-agent "YourResearchTool/1.0 (contact: your-email)"` can identify your research client. All command options are available with `--help`.

## What the analysis measures

1. **Corpus:** `cat:quant-ph` includes primary papers and cross-lists. There is no arbitrary latest-N cap. Requests are split into smaller date intervals and paginated until API totals are satisfied. Each arXiv base ID appears once.
2. **Time:** papers are assigned to their original submission month (`published`), not their revision month (`updated`). The API supplies the latest title and abstract, so later revisions can change historical keyword frequencies.
3. **Keywords:** titles and abstracts are tokenized, mathematical markup is removed, and English stopwords and generic scientific prose are excluded. Adjacent two/three-word phrases are retained, along with a small physics phrase dictionary. Explicit synonym and plural mappings are in `quantum_trends/analysis.py`. This is transparent lexical extraction, not topic modeling or a semantic classifier.
4. **Frequency:** a paper contributes once per keyword, regardless of repetitions. Monthly share is `100 × matching papers / all papers in that cohort/month`. Terms overlap, so shares do not sum to 100%. A month with zero cohort papers has an undefined share and a gap in the plot.
5. **Recent changes:** the default compares the last three complete calendar months with the preceding three. For the bundled corpus, this is **August–October 2026 versus May–July 2026**. Percentages pool papers across each window; the general share-change table ranks their difference in percentage points. This is separate from the emergence ranking described above. It does not average monthly percentages, include unfinished months, or treat ranks as significance tests. Minimum support is the combined document count across the two comparison windows.
6. **Lindblad screen:** explicit title/abstract mentions of Lindblad, Lindbladian, GKSL, GKLS, GKS, or Gorini–Kossakowski–Sudarshan identify candidate articles. Generic “open systems” or “dissipation” alone do not qualify. This rule can include comparisons, incidental mentions, and papers going beyond Lindblad dynamics; it can miss papers whose relevant details appear only in the full text. `lindblad_papers.csv` includes the matching snippet for review. The standalone word “lindblad” is omitted from the subset's default top-keyword list because it defines the cohort; it remains available for explicit tracking.
7. **Enrichment:** keyword frequency in the subset is compared with its **disjoint complement**, rather than the overlapping full corpus. Ratios use `(matches + 0.5)/(papers + 1)` smoothing. Defining Lindblad/GKSL/GKLS terms and eponym names are excluded from this ranking.

Emergence cloud sizes reflect the growth score; frequency-context clouds reflect document counts. Sizes are relative within each panel. Compare exact percentages in the tables across cohorts. Broad keywords can still be nonspecific, and phrases can be redundant. Sparse terms fluctuate sharply. These plots measure topic language, not research quality, citations, or scientific impact.

## Files produced

| Path | Content |
|---|---|
| `data/corpus.json` | Complete metadata snapshot and per-month retrieval manifest |
| `report/report.html` | Portable report with embedded graphics |
| `report/figures/` | PNG and SVG word clouds and graphs |
| `report/tables/papers.csv` | Every analyzed paper and its cohort membership |
| `report/tables/lindblad_papers.csv` | Candidate subset with evidence snippets and links |
| `report/tables/*_emerging.csv` | Candidate scores, baseline/recent counts, denominators, shares, growth ratios, recurrence, title support, and first observed month |
| `report/tables/*_canonical.csv` | Full excluded vocabulary, reasons, and historical counts |
| `report/tables/*_emerging_evidence.csv` | Recent supporting papers and links for the top 30 emerging terms |
| `report/tables/*_keywords.csv` | Top keyword document counts and corpus shares |
| `report/tables/*_monthly_keywords.csv` | Monthly counts, denominators, shares, and full-month flags for the top 30 frequent and emerging terms plus explicitly selected terms |
| `report/tables/*_changes.csv` | All supported keyword comparisons |
| `report/tables/lindblad_enrichment.csv` | Subset-versus-complement frequency ratios |
| `report/manifest.json` | Coverage, retrieval times, filters, and comparison windows |

## Retrieval behavior

The program uses one request at a time, at least 3.1 seconds apart, and caches validated API responses for 24 hours. A year usually takes several minutes to download. Successful pages survive an interrupted download, so rerunning resumes from the cache. Retryable network and service errors use bounded retries. A failed, empty, duplicated, or inconsistent page stops the download; it never silently turns a partial sample into a complete analysis. An existing saved corpus is replaced only after a complete new download.

Date queries include the following midnight, then trim records locally. This avoids losing submissions in the final seconds of a day with the API's minute-resolution date syntax. `boundary_excluded` records any trimmed records in the coverage manifest. API totals can change during indexing; retry with `--refresh` if the coverage check detects this. “Complete” means all indexed matches at retrieval time, not a guarantee that arXiv has finished processing recent submissions.

Run only **one downloader at a time**, including other tools or machines you control, because arXiv's rate limit applies across clients. The dashboard prevents concurrent downloads within its own process. Offline analysis and report generation need no network access.

## Validation and development

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Tests cover API parsing, errors, incomplete and duplicate pagination, date boundaries, recursive date subdivision, first-submission dates, deduplication, document-frequency normalization, cohort isolation, primary-category filtering, empty cohorts, partial months, pooled comparison rates, extraction rules, emergence normalization, historical-only canonical learning, exact phrase exclusions, sparse/one-month bursts, title evidence, partial-month exclusion, true document-set deduplication, and independent cohort baselines.

The main modules are `arxiv_client.py` (retrieval), `analysis.py` (screening and counting), `emergence.py` (canonical vocabulary and growing-term discovery), `report.py` (figures and exports), and `app.py` (dashboard). The included report is reproducible from the included corpus without another API call.

We thank arXiv for use of its open access interoperability. Data are provided by arXiv; this is an independent research tool, not an arXiv product.

- [arXiv API user manual](https://info.arxiv.org/help/api/user-manual.html)
- [arXiv API terms and rate limits](https://info.arxiv.org/help/api/tou.html)
