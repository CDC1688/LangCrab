#!/usr/bin/env python3
"""CLI entry point for the OpenClaw log analyzer."""

from __future__ import annotations

import argparse
import os
import time
import uuid
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="Classify OpenClaw LLM agent logs using LangGraph"
    )
    parser.add_argument(
        "--csv",
        required=True,
        nargs="+",
        help="Path(s) to CSV log file(s)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory (default: <project>/output)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of rows per file (0 = all)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=100,
        help="Max parallel LLM calls (default: 100)",
    )
    parser.add_argument(
        "--no-checkpoint",
        action="store_true",
        help="Disable checkpointing",
    )
    args = parser.parse_args()

    # Set OUTPUT_DIR before importing graph/nodes (they read it at import time via config.py)
    if args.output_dir:
        out_path = Path(args.output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        os.environ["OUTPUT_DIR"] = str(out_path)

    from .graph import create_graph

    graph = create_graph(use_checkpointer=not args.no_checkpoint)

    config = {
        "configurable": {
            "thread_id": str(uuid.uuid4()),
        },
        "max_concurrency": args.concurrency,
    }

    output_dir = os.environ.get("OUTPUT_DIR", "output")
    print(f"Starting classification pipeline...")
    print(f"  CSV files: {len(args.csv)}")
    for f in args.csv:
        print(f"    - {f}")
    print(f"  Output: {output_dir}")
    print(f"  Limit per file: {args.limit or 'all'}")
    print(f"  Max concurrency: {args.concurrency}")
    print()

    t0 = time.time()

    result = graph.invoke(
        {
            "csv_paths": args.csv,
            "limit": args.limit,
            "rows": [],
            "classifications": [],
            "summary": None,
        },
        config,
    )

    elapsed = time.time() - t0
    summary = result.get("summary", {})
    total = summary.get("total", 0)
    print(f"\nDone in {elapsed:.1f}s ({total / max(elapsed, 1):.1f} rows/sec)")
    print(f"  classifications.jsonl: {total} entries")
    print(f"  summary.json: aggregated analytics")
    print(f"  Output: {output_dir}")


if __name__ == "__main__":
    main()
