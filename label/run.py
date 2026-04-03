#!/usr/bin/env python3
"""CLI entry point for the label-only classification pipeline.

Usage:
    python -m openclaw_log_analyzer.label --csv path/to/logs.csv
    python -m openclaw_log_analyzer.label --csv path/to/logs.csv --limit 50 --concurrency 30
"""

from __future__ import annotations

import argparse
import time
import uuid


def main():
    parser = argparse.ArgumentParser(
        description="Label-only pipeline: classify OpenClaw logs and save Classification back to the CSV"
    )
    parser.add_argument(
        "--csv",
        required=True,
        help="Path to CSV log file",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of rows to process (0 = all)",
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

    from .graph import create_graph

    graph = create_graph(use_checkpointer=not args.no_checkpoint)

    config = {
        "configurable": {
            "thread_id": str(uuid.uuid4()),
        },
        "max_concurrency": args.concurrency,
    }

    print(f"Starting label pipeline...")
    print(f"  CSV: {args.csv}")
    print(f"  Limit: {args.limit or 'all'}")
    print(f"  Max concurrency: {args.concurrency}")
    print()

    t0 = time.time()

    result = graph.invoke(
        {
            "csv_path": args.csv,
            "limit": args.limit,
            "rows": [],
            "classifications": [],
        },
        config,
    )

    elapsed = time.time() - t0
    total = len(result.get("classifications", []))
    print(f"\nDone in {elapsed:.1f}s ({total / max(elapsed, 1):.1f} rows/sec)")
    print(f"  {total} rows labelled and saved to {args.csv}")


if __name__ == "__main__":
    main()
