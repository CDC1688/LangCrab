#!/bin/bash
# Extract traces + start the trace viewer server
# Usage: bash openclaw_log_analyzer/run_graph.sh

cd "$(dirname "$0")/.." || exit 1

# Step 1: Extract agent traces from CSV (skip if already done)
if [ ! -s output/output_all/agent_traces.jsonl ]; then
    echo "=== Extracting agent traces ==="
    python -m openclaw_log_analyzer.frontend.extract_traces \
        --csv data/logs2_oc_0320.csv data/logs2_oc_0322.csv data/logs2_oc_0323.csv \
        --classifications output/output_all/classifications.jsonl \
        --output output/output_all/agent_traces.jsonl
fi

# Step 2: Kill existing server on port 8080
lsof -ti:8080 2>/dev/null | xargs kill -9 2>/dev/null
sleep 1

# Step 3: Start server
echo "=== Starting trace viewer on http://localhost:8080 ==="
python -m openclaw_log_analyzer.frontend.server \
    --data-dir output/output_all \
    --port 8080
