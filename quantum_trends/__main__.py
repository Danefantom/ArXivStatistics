from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from .arxiv_client import ArxivClient, RetrievalError, default_dates, save_json


def main():
    parser = argparse.ArgumentParser(description="arXiv quant-ph keyword trends, with a Lindblad/GKSL subset")
    sub = parser.add_subparsers(dest="command", required=True)
    fetch = sub.add_parser("fetch", help="Download complete metadata with resumable page caching")
    run = sub.add_parser("run", help="Fetch metadata and generate the report")
    report = sub.add_parser("report", help="Analyze an existing corpus without network access")
    for command in [fetch, run]:
        command.add_argument("--start", type=date.fromisoformat)
        command.add_argument("--end", type=date.fromisoformat)
        command.add_argument("--months", type=int, default=12, help="Calendar months including the current month (default 12)")
        command.add_argument("--cache-dir", type=Path, default=Path(".cache/arxiv"))
        command.add_argument("--refresh", action="store_true", help="Bypass the 24-hour request cache")
        command.add_argument("--user-agent", default="QuantumKeywordTrends/1.0 (personal research)")
    for command in [fetch, run, report]:
        command.add_argument("--data", type=Path, default=Path("data/corpus.json"))
    for command in [run, report]:
        command.add_argument("--output", type=Path, default=Path("report"))
        command.add_argument("--min-df", type=int, default=5, help="Minimum papers per keyword (default 5)")
        command.add_argument("--compare-months", type=int, default=3)
        command.add_argument("--primary-only", action="store_true", help="Exclude cross-list-only papers")
        command.add_argument("--keywords", help="Comma-separated exact extracted terms to plot")
        command.add_argument("--stopwords", type=Path, help="UTF-8 file with additional excluded words/phrases, one per line")
    args = parser.parse_args()
    try:
        if args.command in {"fetch", "run"}:
            start, end = default_dates(args.months, args.end)
            corpus = ArxivClient(args.cache_dir, refresh=args.refresh, user_agent=args.user_agent).fetch(args.start or start, args.end or end)
            save_json(args.data, corpus)
            print(f"Saved {len(corpus['papers']):,} papers to {args.data.resolve()}")
        else:
            corpus = json.loads(args.data.read_text(encoding="utf-8"))
        if args.command in {"run", "report"}:
            from .analysis import analyze, extract_terms
            from .report import export_report
            stopwords = set(args.stopwords.read_text(encoding="utf-8").splitlines()) if args.stopwords else None
            analysis = analyze(corpus, min_df=args.min_df, comparison_months=args.compare_months,
                               primary_only=args.primary_only, extra_stopwords=stopwords)
            keywords = [v.strip().lower() for v in args.keywords.split(",") if v.strip()] if args.keywords else None
            path = export_report(analysis, args.output, keywords)
            print(f"Report: {path.resolve()}")
            print(f"Lindblad/GKSL candidates: {int(analysis.papers.lindblad.sum()):,}")
        return 0
    except (RetrievalError, ValueError, OSError, KeyError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
