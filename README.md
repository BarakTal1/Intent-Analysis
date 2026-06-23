# Intent Analysis Framework

A pipeline for understanding how users interact with AI agents. It ingests conversation traces from **Langfuse** or **LangSmith**, runs them through an LLM-powered extraction pipeline, and surfaces intent patterns, satisfaction trends, and skill gaps via an interactive dashboard.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Step 1 — Trace Ingestion](#step-1--trace-ingestion)
4. [Step 2 — Normalization](#step-2--normalization)
5. [Step 3 — Skill Detection (SBERT)](#step-3--skill-detection-sbert)
6. [Step 4 — Intent Extraction (LLM)](#step-4--intent-extraction-llm)
7. [Step 5 — Analytics](#step-5--analytics)
8. [The Gap Score](#the-gap-score)
9. [Quick Start](#quick-start)
10. [Configuration](#configuration)
11. [Project Structure](#project-structure)

---

## Overview

```
Langfuse / LangSmith / File Upload
            │
            ▼
    [ Trace Ingestion ]       ← Pull raw conversation traces
            │
            ▼
    [ Normalization ]         ← Flatten into a unified TraceData schema
            │
            ▼
    [ Skill Detection ]       ← Identify activated skills via tool-call names
            │
            ▼
    [ SBERT Scoring ]         ← Compute semantic similarity: conversation ↔ skill name
            │
            ▼
    [ LLM Extraction ]        ← Claude judges intent, satisfaction, skill relevance
            │
            ▼
    [ Analytics & Dashboard ] ← Intents, satisfaction, skill gaps, raw explorer
```

---

## Architecture

| Layer | Files | Responsibility |
|---|---|---|
| **Ingestion** | `extraction/langfuse_client.py`, `extraction/langsmith_client.py`, `extraction/trace_loader.py` | Fetch or parse traces from any source |
| **Schema** | `extraction/schemas.py` | Unified `TraceData` and `IntentRepresentation` models |
| **Skill Detection** | `extraction/skills_detector.py` | Detect skills + SBERT cosine similarity |
| **LLM Extraction** | `extraction/intent_agent.py` | Structured LLM output via LangChain |
| **Batch Processing** | `analysis/batch_processor.py` | Async concurrency, result persistence |
| **Analytics** | `analysis/intent_analysis.py`, `satisfaction_analysis.py`, `skills_analysis.py`, `skills_gap_analysis.py` | Aggregation and scoring |
| **API** | `app.py` | FastAPI — serves analytics + manages projects |
| **Frontend** | `static/` | Vanilla JS dashboard |

---

## Step 1 — Trace Ingestion

Traces can come from three sources:

### Langfuse
The `LangfuseImporter` calls the Langfuse REST API using your `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY`. You can filter by `user_id`, `session_id`, `name`, or `tags`, and paginate through results.

### LangSmith
The `LangSmithImporter` uses the official `langsmith` Python client. You select a project, optionally filter by run type (chain, llm, tool), and whether to fetch only root runs (the top-level trace) or all child runs.

### File Upload
`TraceLoader` accepts `.json`, `.jsonl`, `.csv`, `.tsv`, `.txt`, and `.xlsx` files. It auto-detects the format and tries multiple parsing strategies:
- **JSONL**: each line is a trace record
- **JSON**: a list of trace objects, or a single trace
- **Tabular (CSV/XLSX)**: each row is a trace; columns are mapped by name

---

## Step 2 — Normalization

Every source is flattened into the same internal schema before anything else happens.

### `TraceData`
```python
TraceData(
    trace_id: str,
    session_id: str | None,
    user_id: str | None,
    messages: list[TraceMessage],   # [{role, content}, ...]
    tool_calls: list[ToolCall],     # [{tool_name, input_summary, output_summary}, ...]
    skills_activated: list[str],    # skill names found in trace metadata
    metadata: dict,
    duration_seconds: float | None,
)
```

**What normalization does:**
- Maps vendor-specific role names (`human` → `user`, `ai` / `AIMessage` / `AIMessageChunk` → `assistant`) to a consistent `user` / `assistant` vocabulary
- Extracts tool call inputs and outputs into short summaries (truncated at 200 chars)
- Reconstructs messages from nested LangChain `generations` arrays if needed
- Deduplicates skills by name, preserving order
- Converts tabular rows into pseudo-conversations using `input` / `output` / `question` / `answer` column conventions

Traces with **fewer than 2 messages** are skipped — single-message traces don't have enough context for meaningful intent analysis.

---

## Step 3 — Skill Detection (SBERT)

Before the LLM sees the trace, the `SkillsDetector` runs two passes:

### 3a. Skill Name Detection
Skills are collected from:
1. `trace.skills_activated` — skill names already present in the trace metadata
2. Tool call names that match patterns like `_skill`, `_tool`, `_agent`, `_analyzer`, `_scanner`

### 3b. SBERT Relevance Scoring
For each detected skill, the detector computes a **cosine similarity** between:
- **Conversation embedding** — the concatenated text of all user messages in the trace
- **Skill description embedding** — `"A tool for {skill_name_readable}"` (underscores replaced with spaces)

Both are encoded with `all-mpnet-base-v2` (Sentence-BERT) and L2-normalized before computing the dot product.

```
score = cosine_similarity(embed(user_messages), embed("A tool for " + skill_name))
```

**Score interpretation:**

| Score | Meaning |
|---|---|
| `> 0.60` | High similarity — skill is likely relevant to the conversation |
| `0.35 – 0.60` | Ambiguous — the LLM decides |
| `< 0.35` | Low similarity — skill likely wasn't needed |

These scores are passed to the LLM as **hints**, not decisions. The LLM's judgment always takes precedence.

---

## Step 4 — Intent Extraction (LLM)

The `IntentExtractionAgent` uses Claude (via LangChain's `init_chat_model`) with **structured output** — the model is forced to return a JSON object matching the `IntentRepresentation` schema.

### What the LLM receives
- The full conversation (all messages)
- All tool calls with their inputs and outputs
- The list of activated skills
- The SBERT similarity scores as labeled hints

### What it returns — `IntentRepresentation`

```python
IntentRepresentation(
    trace_id: str,
    intent_summary: str,         # Free-text description of the user's goal
    primary_intent: str,         # Snake_case category (e.g. "data_retrieval")
    sub_intents: list[str],      # Secondary goals found in the conversation
    goal_achieved: bool,         # Did the user succeed?
    satisfaction_score: float,   # 0.0 – 1.0
    satisfaction_signals: list[str],  # Observable clues that informed the score
    skills_used: list[str],      # Skills the agent judged were activated
    skills_relevance: list[SkillRelevance],  # Per-skill: was_relevant, reason, sbert_score
    complexity: str,             # "low" | "medium" | "high"
    user_expertise: str,         # "beginner" | "intermediate" | "expert" | "unknown"
    clarifications_needed: int,  # How many times user had to re-explain
)
```

### Satisfaction scoring rubric (from the system prompt)

| Score range | Interpretation |
|---|---|
| `0.85 – 1.0` | Short conversation, goal clearly met |
| `0.70 – 0.84` | Goal met with 1–2 minor friction points |
| `0.40 – 0.69` | Goal partially met, 3+ clarifications needed |
| `0.15 – 0.39` | Goal not met, frustration signals, repeated rephrasing |
| `0.0 – 0.14` | Abandonment, explicit failure, no resolution |

### Concurrency
The batch processor runs up to **5 traces in parallel** by default (configurable), using `asyncio.Semaphore`. Results are appended to a `.jsonl` file after each batch so progress is never lost.

---

## Step 5 — Analytics

Four analyzers aggregate the extracted `IntentRepresentation` records:

### Intent Analysis
Groups traces by `primary_intent` and computes:
- Distribution (count + percentage per intent)
- Unknown rate (how many traces couldn't be classified)
- Top categories ranked by frequency

### Satisfaction Analysis
- **Mean satisfaction** across all traces
- **Fully satisfied rate** — percentage with score ≥ `satisfaction_threshold` (default 0.85)
- **Low satisfaction rate** — percentage with score < 0.4
- **Goal achievement rate** — percentage where `goal_achieved = True`
- Breakdowns by intent, complexity, and user expertise
- Histogram across 10 score buckets

### Skills Analysis
- **Activation frequency** — how often each skill fires
- **Relevance rate** — percentage of activations where `was_relevant = True`
- **SBERT score distribution** — average semantic similarity per skill
- **Quadrant classification**: Core (high freq + high relevance), Noisy (high freq + low relevance), Niche (low freq + high relevance), Redundant (low freq + low relevance)

### Skills Gap Analysis
Identifies intents where existing skills aren't sufficient. See the next section.

---

## The Gap Score

The **gap score** is a numeric signal (0–10+) that measures how much an intent *needs* a new or better skill. It is computed per intent from five independent signals:

| Signal | Points added | Condition |
|---|---|---|
| **Frequency** | up to +3.0 | Intent appears in ≥ 5% of traces (`frequency_pct / 10`, capped at 3) |
| **No skills activated** | +3.0 | `avg_skills_per_trace == 0` — nothing is helping the agent here |
| **Low skill activation** | +1.5 | `avg_skills_per_trace < 1.0` — skills fire but rarely |
| **Low skill relevance** | +2.0 | Less than 40% of skill activations were judged relevant |
| **Below-average satisfaction** | +1.5 | Mean satisfaction is more than 0.1 below the global average |
| **Low goal achievement** | +1.5 | Goal achievement rate is 10+ points below global average |
| **High clarification rate** | +1.0 | Users needed more than 1 clarification per trace on average |

**Penalty:** Intents with fewer than 2 traces have their gap score multiplied by 0.3 — not enough data to be confident.

**Threshold:** An intent must reach a gap score of **≥ 1.5** to appear as a candidate. Anything below is considered noise.

The output also includes a **suggested skill name** derived from the intent category and its most common sub-intent.

---

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/BarakTal1/Intent-Analysis.git
cd Intent-Analysis
pip install -e .

# 2. Configure credentials
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY and optionally Langfuse/LangSmith keys

# 3. Run
python run.py
# → Open http://localhost:5001
```

---

## Configuration

All settings are in `config/settings.py` and can be overridden via the dashboard UI or `.env`:

| Setting | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | *(required)* | Claude API key |
| `model_name` | `anthropic:claude-sonnet-4-6` | LLM model for extraction |
| `satisfaction_threshold` | `0.85` | Cutoff for "fully satisfied" classification |
| `skills_relevance_threshold` | `0.5` | SBERT score cutoff for relevance hint display |
| `LANGFUSE_PUBLIC_KEY` | *(optional)* | Langfuse project public key |
| `LANGFUSE_SECRET_KEY` | *(optional)* | Langfuse project secret key |
| `LANGFUSE_HOST` | `https://cloud.langfuse.com` | Langfuse API endpoint |
| `LANGSMITH_API_KEY` | *(optional)* | LangSmith API key |

---

## Project Structure

```
intent-analysis/
├── app.py                  # FastAPI application and all API routes
├── run.py                  # Uvicorn launcher (python run.py)
├── pyproject.toml          # Dependencies and build config
├── .env.example            # Environment variable template
│
├── extraction/             # Ingestion and normalization
│   ├── schemas.py          # TraceData, IntentRepresentation, SkillRelevance models
│   ├── trace_loader.py     # File-based trace parser (JSON, JSONL, CSV, XLSX)
│   ├── langfuse_client.py  # Langfuse API importer
│   ├── langsmith_client.py # LangSmith API importer
│   ├── intent_agent.py     # LLM extraction agent (Claude via LangChain)
│   └── skills_detector.py  # SBERT-based skill detection and scoring
│
├── analysis/               # Analytics and aggregation
│   ├── batch_processor.py  # Async batch runner with concurrency control
│   ├── intent_analysis.py  # Intent distribution and categorization
│   ├── satisfaction_analysis.py  # Satisfaction scoring and breakdowns
│   ├── skills_analysis.py  # Skill activation, relevance, quadrant analysis
│   └── skills_gap_analysis.py   # Gap score computation and skill suggestions
│
├── config/
│   └── settings.py         # Centralized configuration
│
└── static/                 # Frontend (vanilla JS, no build step)
    ├── index.html
    ├── js/
    │   ├── app.js          # All UI logic and API calls
    │   └── charts.js       # ECharts wrappers
    └── css/
        └── theme.css       # Dark-mode design tokens
```
