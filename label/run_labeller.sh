#!/bin/bash
cd "$(dirname "$0")/../.." || exit 1
python -m openclaw_log_analyzer.label \
  --csv ./data/benchmark_positive.csv \
  --concurrency 30