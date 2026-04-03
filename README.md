# LangCrab

**LLM-powered log classification and analysis for AI agent sessions.**

LangCrab automatically categorizes AI agent session logs into meaningful categories, detects tool execution errors and recovery patterns, and provides an interactive dashboard for exploring results.

## What It Does

- **Classifies** agent sessions across 12 primary categories and 500+ subcategories using LLM-based analysis with self-correction
- **Detects** tool execution errors, recovery patterns, and error loops
- **Visualizes** agent execution flows through an interactive React dashboard
- **Supports** human review with an annotation system (approve / reject / flag / correct)

## Architecture

```
                    +-----------------------+
                    |   CSV Log Files       |
                    +-----------+-----------+
                                |
                    +-----------v-----------+
                    |   Signal Extraction   |
                    |  (parser.py)          |
                    +-----------+-----------+
                                |
              +-----------------v-----------------+
              |        LangGraph Pipeline         |
              |                                   |
              |  Outer Graph: fan-out per row      |
              |  Inner Graph: classify + validate  |
              |               + self-correct       |
              +-----------------+-----------------+
                                |
              +-----------------v-----------------+
              |           Output Files            |
              |  classifications.jsonl            |
              |  summary.json                     |
              |  error_report.jsonl               |
              +-----------------+-----------------+
                                |
              +-----------------v-----------------+
              |       Frontend Dashboard          |
              |  FastAPI + React + WebSocket      |
              +-----------------+-----------------+
```

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js (for frontend UI)
- An OpenAI-compatible LLM API endpoint

### Environment Variables

```bash
export ARK_API_KEY="your-api-key"

# Optional overrides (defaults in config.py)
export LLM_BASE_URL="https://your-llm-endpoint/api/v3"
export LLM_MODEL="your-model-name"
```

### Install Dependencies

```bash
pip install langchain-core langgraph pydantic openai tqdm fastapi uvicorn sqlalchemy
```

### Run the Analyzer

```bash
python -m openclaw_log_analyzer \
  --csv data/your_logs.csv \
  --output-dir ./output \
  --concurrency 30
```

**Options:**

| Flag | Description |
|---|---|
| `--csv` | One or more CSV files to process |
| `--output-dir` | Directory for output files |
| `--limit N` | Process only N rows (0 = all) |
| `--concurrency N` | Parallel LLM calls (default: 100) |
| `--no-checkpoint` | Disable LangGraph checkpointing |
| `--continue` | Resume from a prior run |

### Launch the Dashboard

```bash
# Extract agent traces
python -m openclaw_log_analyzer.frontend.extract_traces \
  --csv data/your_logs.csv \
  --classifications output/classifications.jsonl \
  --output output/agent_traces.jsonl

# Start the server
python -m openclaw_log_analyzer.frontend.server \
  --data-dir output \
  --port 8080
```

Then open `http://localhost:8080`.

### Quick Label (Classification Only)

For lightweight labeling that writes results back to the CSV:

```bash
python -m openclaw_log_analyzer.label \
  --csv data/your_logs.csv \
  --concurrency 30
```

## How Classification Works

1. **Signal Extraction** -- Parse CSV rows, extract conversation content, tool names, and error signals
2. **Heuristic Short-Circuit** -- Known patterns (e.g., heartbeat checks) skip the LLM entirely
3. **LLM Classification** -- Structured prompt sent to LLM, response parsed into a `Classification` schema
4. **Validation** -- Programmatic checks for tool-category consistency, language detection, intent quality
5. **Self-Correction** -- If validation fails, error feedback is sent back to the LLM (up to 3 retries)

### Categories

| Category | Examples |
|---|---|
| `coding` | Bug fixes, refactoring, code generation |
| `communication` | Feishu, Telegram, email bots |
| `web_research` | Web scraping, search |
| `data_analysis` | Reports, data extraction |
| `file_management` | File operations |
| `scheduling` | Cron jobs, reminders |
| `system_maintenance` | Health checks, monitoring |
| `content_creation` | Articles, posts |
| `finance_crypto` | Trading, crypto analysis |
| `memory_management` | Knowledge base storage |
| `agent_orchestration` | Multi-agent coordination |
| `other` | Catch-all |

See [subcategories.json](subcategories.json) for the full taxonomy of 500+ subcategories.

## Error Analysis

The parser detects and categorizes tool execution errors:

- Permission errors, timeouts, rate limits, connection failures
- Python exceptions, syntax errors, command failures
- Tracks whether the agent **recovered** after errors
- Detects **error loops** (consecutive failures)

## Output Files

```
output/
  classifications.jsonl       # One JSON record per classified session
  summary.json                # Aggregated statistics
  error_report.jsonl          # Detailed error analysis per session
  inner_graph_details.jsonl   # Full LangGraph trace per row
  validation_errors.jsonl     # Sessions that failed validation
```

## Frontend Features

- **Session browser** with filtering by category, language, confidence, errors
- **Agent flow visualization** using React Flow -- tool calls, errors, retries, sub-agents
- **WebSocket replay** of agent execution with speed control
- **Annotation system** -- approve, reject, flag, or correct classifications (stored in SQLite)
- **Statistics dashboard** -- category distribution, error rates, subcategory counts

## Project Structure

```
openclaw_log_analyzer/
  config.py           # LLM and pipeline configuration
  parser.py           # CSV parsing, signal extraction, error detection
  nodes.py            # LangGraph node implementations
  graph.py            # LangGraph outer/inner graph definitions
  schemas.py          # Pydantic models (Classification, PipelineState, RowState)
  prompts.py          # LLM prompt templates
  run.py              # CLI entry point
  subcategories.json  # Full category taxonomy
  frontend/
    server.py         # FastAPI + WebSocket server
    models.py         # API data models
    trace_builder.py  # Build execution graphs from traces
    extract_traces.py # Extract agent traces from CSV
    ui/               # React frontend
  label/
    run.py            # Label-only CLI entry point
    graph.py          # Simplified LangGraph for labeling
    nodes.py          # Label pipeline nodes
    schemas.py        # Label pipeline state models
```

## License

MIT
