#!/bin/bash
cd "$(dirname "$0")/.." || exit 1
python3 -m openclaw_log_analyzer \
  --csv data/logs2_oc_0323.csv \
  --output-dir /home/tiger/anna/output/output_all \
  --concurrency 80 \
  --limit 5000 \
  --no-checkpoint