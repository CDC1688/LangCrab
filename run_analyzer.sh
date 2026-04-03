#!/bin/bash
cd "$(dirname "$0")/.." || exit 1
python3 -m openclaw_log_analyzer \
  --csv data/logs2_oc_0323.csv data/logs2_oc_0320.csv data/logs2_oc_0322.csv \
  --output-dir ./output/output_all_3logs \
  --concurrency 30 \
  --no-checkpoint \
  --continue