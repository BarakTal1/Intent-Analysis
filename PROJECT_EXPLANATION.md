# Intent Analysis Framework — Full Project Explanation

## Table of Contents

1. [What Is This Project?](#1-what-is-this-project)
2. [The Problem It Solves](#2-the-problem-it-solves)
3. [High-Level Architecture](#3-high-level-architecture)
4. [The Data Pipeline — Step by Step](#4-the-data-pipeline--step-by-step)
   - [Step 1: Data Ingestion](#step-1-data-ingestion)
   - [Step 2: Trace Parsing & Normalization](#step-2-trace-parsing--normalization)
   - [Step 3: Skills Detection & SBERT Scoring](#step-3-skills-detection--sbert-scoring)
   - [Step 4: LLM-Powered Intent Extraction](#step-4-llm-powered-intent-extraction)
   - [Step 5: Analytics & Visualization](#step-5-analytics--visualization)
5. [Key Technical Terms Explained](#5-key-technical-terms-explained)
6. [Codebase Structure — File by File](#6-codebase-structure--file-by-file)
7. [How the Frontend Works](#7-how-the-frontend-works)
8. [How Everything Connects](#8-how-everything-connects)

---

## 1. What Is This Project?

The Intent Analysis Framework is a web-based analytics tool that takes **conversations between users and AI agents** (called "traces") and automatically analyzes them to answer three questions:

1. **What did the user want?** (Intent extraction)
2. **Was the user satisfied?** (Satisfaction analysis)
3. **Were the right tools used?** (Skills relevance analysis)

It does this by combining two AI techniques: a **large language model (Claude)** that reads and understands conversations, and a **sentence embedding model (Sentence-BERT)** that measures semantic similarity between text. The results are displayed in an interactive dashboard with charts, tables, and drill-down views.

---

## 2. The Problem It Solves

When a company deploys an AI agent (like a chatbot or automated assistant), the agent generates thousands of conversation logs. Product teams need to understand:

- What are users actually asking for? Are there patterns?
- Are users getting what they need, or are they frustrated?
- The agent has many "skills" (tools it can call) — are the right skills firing for the right requests? Are some skills noisy (activating when they shouldn't)?
- Are there user needs that no existing skill covers? (Gaps)

Manually reading thousands of conversations is impractical. This framework automates the entire analysis.

---

## 3. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Browser (Dashboard)                          │
│  index.html + app.js + charts.js (ECharts)                         │
└────────────────────────────────┬────────────────────────────────────┘
                                 │ HTTP (REST API)
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     FastAPI Backend (app.py)                         │
│                                                                     │
│  ┌──────────┐  ┌──────────────┐  ┌────────────┐  ┌──────────────┐  │
│  │ Projects │  │ Upload/Parse │  │ Extraction  │  │  Analytics   │  │
│  │   CRUD   │  │   Pipeline   │  │  Pipeline   │  │   Engines    │  │
│  └──────────┘  └──────┬───────┘  └─────┬──────┘  └──────┬───────┘  │
└─────────────────────────────────────────────────────────────────────┘
                         │               │                │
           ┌─────────────┼───────────────┤                │
           ▼             ▼               ▼                ▼
  ┌──────────────┐ ┌───────────┐ ┌─────────────┐ ┌──────────────────┐
  │ TraceLoader  │ │ Langfuse  │ │ IntentAgent  │ │ IntentAnalyzer   │
  │ (files)      │ │ Importer  │ │ (Claude LLM) │ │ SatisfactionAn.  │
  │              │ │           │ │              │ │ SkillsAnalyzer   │
  │              │ │ LangSmith │ │ SkillsDet.   │ │ SkillsGapAn.    │
  │              │ │ Importer  │ │ (SBERT)      │ │                  │
  └──────────────┘ └───────────┘ └─────────────┘ └──────────────────┘
```

The system has four layers:

- **Frontend**: A single-page HTML/JS dashboard with dark theme, served as static files.
- **Backend**: A FastAPI Python server that exposes REST API endpoints.
- **Extraction Layer**: Handles loading traces from files or APIs, detecting skills, and running the LLM.
- **Analysis Layer**: Pure Python analytics that compute statistics, distributions, and gap analysis from the extraction results.

---

## 4. The Data Pipeline — Step by Step

### Step 1: Data Ingestion

**What happens**: Raw conversation data enters the system.

There are three ways to get data in:

#### A) File Upload
Users can upload files in many formats: Excel (.xlsx), CSV, JSON, JSONL, or plain text. The `TraceLoader` class handles all of these. It auto-detects the format and structure — for example, it can recognize LangChain-style message arrays (where each message has a `type` field like `"human"` or `"ai"`) versus flat CSV rows with `role` and `content` columns.

**Where in the code**: `extraction/trace_loader.py` — the `TraceLoader` class.

#### B) Langfuse API Import
Langfuse is a popular open-source observability platform for LLM applications. It records every interaction as a "trace" with structured observations. Our `LangfuseImporter` connects to the Langfuse REST API using public/secret key authentication, fetches traces, and converts them into our internal format.

**Where in the code**: `extraction/langfuse_client.py` — the `LangfuseImporter` class.

#### C) LangSmith API Import
LangSmith is LangChain's proprietary tracing platform. Our `LangSmithImporter` uses the official `langsmith` Python SDK to connect, list projects, and fetch runs. It converts LangSmith's "run" objects (which have inputs, outputs, and child runs) into our internal format.

**Where in the code**: `extraction/langsmith_client.py` — the `LangSmithImporter` class.

---

### Step 2: Trace Parsing & Normalization

**What happens**: Regardless of the data source, every conversation is converted into a unified `TraceData` object.

```python
class TraceData:
    trace_id: str                           # Unique identifier
    session_id: str | None                  # Groups multiple traces into one session
    user_id: str | None                     # Who the user was
    messages: list[TraceMessage]            # The conversation (role + content pairs)
    tool_calls: list[ToolCall]              # Tools/skills the agent invoked
    skills_activated: list[str]             # Names of skills that fired
    metadata: dict                          # Tags, timestamps, extra info
    duration_seconds: float | None          # How long the interaction took
```

Each `TraceMessage` is simply a `role` (user/assistant) and `content` (what was said). Each `ToolCall` records the tool's name, a summary of its input, and a summary of its output.

This normalization is critical because Langfuse, LangSmith, LangChain exports, and manual CSV files all structure their data differently. The `TraceLoader` handles over a dozen format variations:
- LangChain message arrays with `type: "human"` / `type: "ai"`
- Grouped DataFrames where rows are grouped by `trace_id`
- Flat DataFrames with one row per conversation
- Plain text with `User:` / `Assistant:` prefixes
- Nested JSON with `messages`, `input`/`output`, or `question`/`answer` keys

**Where in the code**: `extraction/schemas.py` (data models), `extraction/trace_loader.py` (parsing logic).

---

### Step 3: Skills Detection & SBERT Scoring

**What happens**: Before sending a trace to the LLM, the system pre-computes a "relevance hint" for each skill/tool using Sentence-BERT embeddings.

#### What is SBERT (Sentence-BERT)?

BERT (Bidirectional Encoder Representations from Transformers) is a neural network architecture published by Google in 2018 that revolutionized NLP. It reads text bidirectionally (left-to-right and right-to-left simultaneously) to build deep contextual understanding of words.

**Sentence-BERT (SBERT)** is a modification of BERT specifically designed to produce meaningful sentence-level embeddings. A regular BERT model produces per-token embeddings that aren't directly comparable between sentences. SBERT fine-tunes the model using a Siamese network structure so that semantically similar sentences produce similar vectors.

The specific model we use is `all-mpnet-base-v2`, which is a 110M-parameter model trained on over 1 billion sentence pairs. It produces 768-dimensional vectors.

#### What is Cosine Similarity?

Once we have two vectors (one for the conversation text, one for a skill name), we measure how similar they are using cosine similarity. This measures the angle between two vectors:

- **1.0** = identical direction (perfectly similar meaning)
- **0.0** = perpendicular (unrelated)
- **-1.0** = opposite direction (opposite meaning)

In practice, scores range from 0.0 to ~0.8 for our use case.

#### How It Works in Our Code

1. The `SkillsDetector` first identifies which skills were activated in a trace. It looks at `skills_activated` and tool call names that match patterns like `_skill`, `_tool`, `_agent`, etc.

2. For each detected skill, it computes SBERT cosine similarity between:
   - **The full conversation text** (all user messages concatenated)
   - **A skill description** (the skill name, cleaned up: `"data_retrieval_tool"` becomes `"A tool for data retrieval tool"`)

3. The resulting scores are interpreted as:
   - **> 0.60**: High similarity — the skill is likely relevant to what the user wanted
   - **0.35–0.60**: Ambiguous — the LLM should decide
   - **< 0.35**: Low similarity — the skill probably isn't relevant

These scores are passed to the LLM as "hints" — supporting evidence, not final judgments.

#### Why Do This Pre-Computation?

The LLM (Claude) makes the final relevance judgment, but SBERT provides a cheap, fast, quantitative signal. This hybrid approach means:
- The LLM has more information to work with
- We get a numeric score we can aggregate in analytics
- The SBERT score acts as a sanity check on the LLM's judgment

**Where in the code**: `extraction/skills_detector.py` — the `SkillsDetector` class.

---

### Step 4: LLM-Powered Intent Extraction

**What happens**: Each trace is sent to Claude (Anthropic's LLM) with a detailed system prompt, and Claude returns a structured analysis.

#### The Intent Extraction Agent

The `IntentExtractionAgent` class wraps a LangChain chat model (Claude Sonnet) configured with **structured output**. This means the LLM doesn't return free text — it returns a JSON object that exactly matches our `IntentRepresentation` schema.

#### What is Structured Output?

LangChain's `with_structured_output()` method constrains the LLM to produce output matching a Pydantic model. Under the hood, this uses Anthropic's tool-use feature: the Pydantic schema is converted to a tool definition, the LLM "calls" that tool with the structured data, and LangChain parses the result back into a Python object. This guarantees we get valid, typed data — no parsing errors.

#### What the LLM Analyzes

The system prompt instructs Claude to analyze three things:

**1. User Intent**
- `intent_summary`: A free-text description of what the user was trying to achieve
- `primary_intent`: A canonical category in snake_case (e.g., `data_retrieval`, `troubleshooting`, `content_generation`)
- `sub_intents`: More specific aspects of the intent

**2. Satisfaction**
- `satisfaction_score`: A 0.0–1.0 score based on observable signals in the conversation
- `satisfaction_signals`: The specific evidence (e.g., "user said thanks", "goal clearly met", "had to rephrase 3 times")
- `goal_achieved`: Boolean — did the user get what they wanted?
- `clarifications_needed`: How many times the user had to re-explain

The scoring rubric is defined in the prompt:
- 0.85–1.0: Short conversation, goal clearly met
- 0.70–0.84: Goal met with minor friction
- 0.40–0.69: Goal partially met, multiple clarifications
- 0.15–0.39: Goal not met, frustration signals
- 0.00–0.14: Abandonment, explicit failure

**3. Skills Relevance**
- For each skill/tool that was activated, the LLM judges whether it was truly relevant to the user's intent
- The SBERT scores are included as supporting hints
- The LLM provides a reason for each judgment

#### Additional Metadata Extracted
- `complexity`: low (single tool call) / medium (multi-step) / high (complex chain)
- `user_expertise`: beginner / intermediate / expert / unknown (inferred from language)

#### The Batch Processor

The `BatchProcessor` orchestrates running the extraction across many traces concurrently. It:
1. Filters out traces with fewer than 2 messages (not enough to analyze)
2. Runs up to 5 traces in parallel using `asyncio.Semaphore`
3. For each trace: runs SBERT scoring, then calls the LLM
4. Tracks progress (completed/failed counts)
5. Saves results to a JSONL file for persistence

**Where in the code**:
- `extraction/intent_agent.py` — the `IntentExtractionAgent` class
- `analysis/batch_processor.py` — the `BatchProcessor` class
- `extraction/schemas.py` — the `IntentRepresentation` output schema

---

### Step 5: Analytics & Visualization

**What happens**: The structured extraction results are aggregated into analytics dashboards.

There are four analytics engines, each operating on the list of `IntentRepresentation` objects:

#### A) Intent Analysis (`IntentAnalyzer`)

Answers: **"What are users asking for?"**

- **Distribution**: Counts how many traces fall into each intent category, computes percentages
- **Top Intents**: The most common intent categories
- **Sub-Intent Hierarchy**: For each primary intent, which sub-intents appear? (e.g., under `data_retrieval`: "fetch customer records", "export report")
- **Unknown Rate**: What percentage of traces couldn't be categorized
- **Satisfaction by Intent**: Which intents have the highest/lowest satisfaction

#### B) Satisfaction Analysis (`SatisfactionAnalyzer`)

Answers: **"Are users happy?"**

- **Mean Satisfaction**: Average score across all traces
- **Goal Achievement Rate**: Percentage of traces where the user's goal was met
- **Distribution Histogram**: Bucketed satisfaction scores (0.0–0.1, 0.1–0.2, etc.)
- **By Intent/Complexity/Expertise**: Satisfaction broken down by different dimensions
- **Sentiment Signals**: Aggregated positive and negative signals from across all traces
- **Low-Satisfaction Traces**: Specific traces with scores below 0.4, for manual review
- **Average Clarifications**: How many times users had to re-explain, on average

#### C) Skills Analysis (`SkillsAnalyzer`)

Answers: **"Are the right tools being used?"**

- **Activation Frequency**: How often each skill fires
- **Relevance Rates**: For each skill, what percentage of activations were judged relevant
- **SBERT Scores**: Average semantic similarity scores per skill
- **Quadrant Analysis**: Places each skill into one of four categories:
  - **CORE**: High frequency + High relevance (keep and invest in these)
  - **NOISY**: High frequency + Low relevance (firing too often when not needed — fix the trigger)
  - **NICHE**: Low frequency + High relevance (specialized but valuable)
  - **REMOVE**: Low frequency + Low relevance (not useful — consider removing)
- **Satisfaction Correlation**: When a skill is relevant, is satisfaction higher? When irrelevant, is it lower?

#### D) Skills Gap Analysis (`SkillsGapAnalyzer`)

Answers: **"What skills are missing?"**

This is the most sophisticated analyzer. It identifies intents that are frequent but lack matching skills — candidates for building new tools.

The **gap score** is computed from multiple signals:
- Frequency: How common is this intent? (More common = higher score)
- Skill coverage: Are any skills activated for this intent? (No skills = +3 points)
- Skill relevance: When skills do fire, are they relevant? (Low relevance = +2 points)
- Satisfaction: Is satisfaction below the global average? (+1.5 points)
- Goal achievement: Is goal achievement below average? (+1.5 points)
- Clarifications: Do users have to re-explain a lot? (+1 point)

Intents with fewer than 2 traces get their score reduced by 70% (not enough data).

For each gap candidate, the analyzer also:
- Lists the sub-intents involved
- Identifies the dominant complexity level
- Provides sample conversation summaries
- Suggests a name for a new skill that could fill the gap

**Where in the code**:
- `analysis/intent_analysis.py` — `IntentAnalyzer`
- `analysis/satisfaction_analysis.py` — `SatisfactionAnalyzer`
- `analysis/skills_analysis.py` — `SkillsAnalyzer`
- `analysis/skills_gap_analysis.py` — `SkillsGapAnalyzer`

---

## 5. Key Technical Terms Explained

### Trace
A single recorded interaction between a user and an AI agent. Contains the conversation messages, any tool calls the agent made, and metadata like timestamps and session IDs. Think of it as one "conversation log."

### Intent
What the user was trying to accomplish. For example, if a user asks "Can you pull last month's sales data?", the intent is `data_retrieval`. A trace can have a primary intent and multiple sub-intents.

### Skill / Tool
A capability that an AI agent can invoke. For example, a database query tool, a web search tool, or a code execution tool. In LangChain and similar frameworks, these are called "tools." We use "skills" and "tools" interchangeably.

### Langfuse
An open-source LLM observability platform. It records traces (conversations), generations (LLM calls), and spans (arbitrary operations) from AI applications. We connect to its REST API to import trace data.

### LangSmith
LangChain's proprietary tracing and evaluation platform. Similar purpose to Langfuse but tightly integrated with the LangChain ecosystem. We use the official Python SDK to import runs.

### LangChain
A popular Python/JavaScript framework for building LLM-powered applications. It provides abstractions for chat models, tools, agents, and chains. We use it to interface with Claude — specifically `langchain-anthropic` for the chat model and `with_structured_output()` for guaranteed schema-compliant responses.

### FastAPI
A modern Python web framework for building REST APIs. It uses Python type hints for automatic request validation and documentation. Our backend is a FastAPI application served by Uvicorn.

### Uvicorn
An ASGI (Asynchronous Server Gateway Interface) server for Python. It runs our FastAPI app and supports hot-reload during development (changes to Python files automatically restart the server).

### Pydantic
A Python data validation library that uses type annotations. All our data models (`TraceData`, `IntentRepresentation`, etc.) are Pydantic models, which means they automatically validate data types, provide serialization to/from JSON, and generate JSON schemas.

### BERT (Bidirectional Encoder Representations from Transformers)
A neural network architecture for understanding natural language. Published by Google in 2018, BERT reads text in both directions simultaneously, which gives it deep contextual understanding. "Transformer" refers to the attention mechanism architecture that powers modern AI — the same architecture behind GPT and Claude.

### Sentence-BERT (SBERT)
A modification of BERT that produces fixed-size vector representations of entire sentences (not just individual words). The model `all-mpnet-base-v2` we use converts any text into a 768-dimensional vector. Texts with similar meaning produce vectors that point in similar directions.

### Embedding
A numerical vector representation of text. When we "embed" a sentence, we convert it from words into a list of numbers (e.g., 768 numbers). These numbers capture the meaning of the text in a way that allows mathematical comparison.

### Cosine Similarity
A measure of how similar two vectors are, based on the angle between them. If two text embeddings have high cosine similarity (close to 1.0), the texts have similar meaning. We use this to check whether a skill name is semantically related to a conversation.

### Structured Output
A technique where the LLM is constrained to return data matching a specific schema (like a Pydantic model). Instead of free-form text, the model returns a valid JSON object with the exact fields we expect. This is implemented via Anthropic's tool-use API — the schema becomes a "tool" the model must call.

### ECharts
A JavaScript charting library (by Apache) used for the dashboard visualizations. We use it for bar charts, donut charts, histograms, and the skills quadrant scatter plot.

### JSONL (JSON Lines)
A file format where each line is a separate JSON object. We use it to persist extraction results — each line is one `IntentRepresentation`. This format is easy to append to and read incrementally.

### Async / Await
Python's concurrency model. When we `await` an LLM call, the server can handle other requests while waiting for the response. The `BatchProcessor` uses `asyncio.Semaphore` to run up to 5 LLM calls concurrently without overwhelming the API.

---

## 6. Codebase Structure — File by File

```
terra-intent-framework/
│
├── run.py                          # Entry point — starts the Uvicorn server on port 8000
├── app.py                          # FastAPI application — all REST API endpoints
├── pyproject.toml                  # Python project config — dependencies and build settings
├── .env                            # Environment variables (API keys) — not committed to git
│
├── config/
│   ├── __init__.py                 # Exports the `settings` singleton
│   └── settings.py                 # Configuration dataclass — reads from environment
│
├── extraction/                     # DATA INGESTION & LLM PROCESSING
│   ├── __init__.py
│   ├── schemas.py                  # Core data models: TraceData, IntentRepresentation, etc.
│   ├── trace_loader.py             # File parser — handles Excel, CSV, JSON, JSONL, text
│   ├── langfuse_client.py          # Langfuse API client — fetches traces via HTTP
│   ├── langsmith_client.py         # LangSmith API client — fetches runs via SDK
│   ├── intent_agent.py             # The LLM agent — sends traces to Claude, gets structured results
│   └── skills_detector.py          # SBERT-based skill relevance scoring
│
├── analysis/                       # ANALYTICS ENGINES
│   ├── __init__.py
│   ├── batch_processor.py          # Orchestrates extraction across multiple traces
│   ├── intent_analysis.py          # Intent distribution, hierarchy, category stats
│   ├── satisfaction_analysis.py    # Satisfaction scores, signals, breakdown by dimension
│   ├── skills_analysis.py          # Skill frequency, relevance rates, quadrant analysis
│   └── skills_gap_analysis.py      # Gap detection — intents that need new skills
│
├── static/                         # FRONTEND (served as static files)
│   ├── index.html                  # Single-page app — all HTML structure
│   ├── css/
│   │   └── theme.css               # Dark/light theme styles
│   └── js/
│       ├── app.js                  # Application logic — API calls, page navigation, state
│       └── charts.js               # ECharts wrapper — chart rendering functions
│
└── data/                           # PERSISTENT STORAGE (created at runtime)
    ├── projects.json               # Project metadata (IDs, names)
    └── projects/
        └── <project-id>/
            ├── uploads/            # Uploaded trace files
            └── results.jsonl       # Extraction results (one IntentRepresentation per line)
```

---

## 7. How the Frontend Works

The frontend is a single-page application (SPA) built with plain HTML, vanilla JavaScript, and Tailwind CSS. No framework (React, Vue, etc.) — just direct DOM manipulation.

### Pages (Tabs)

The dashboard has several tab-based pages:

1. **Upload & Parse** — Upload files or import from Langfuse/LangSmith. Preview parsed traces before extraction.
2. **Intent Overview** — Bar chart and donut chart of intent distribution, sub-intent hierarchy, category breakdown.
3. **Satisfaction Analysis** — Satisfaction histogram, breakdown by intent/complexity/expertise, sentiment signals, low-satisfaction trace list.
4. **Skills Intelligence** — Skill activation frequency, relevance rates, the quadrant chart, satisfaction correlation.
5. **Skills Gap** — Gap candidates with scores and reasons, skill coverage matrix.
6. **Raw Explorer** — Searchable, filterable table of all traces with full conversation view and raw JSON.
7. **Extraction Results** — Paginated table of LLM extraction outputs with filters.
8. **Settings** — API keys, model selection, thresholds, SBERT cutoffs.

### Charts

All charts use ECharts (registered with custom dark/light themes). The `charts.js` file provides wrapper functions:
- `Charts.intentDistribution()` — Horizontal bar chart
- `Charts.intentDonut()` — Donut/pie chart with center count
- `Charts.satisfactionHistogram()` — Gradient-colored histogram
- `Charts.satisfactionByCategory()` — Horizontal bar chart for breakdowns
- `Charts.skillsQuadrant()` — Scatter plot with quadrant labels and marked areas

---

## 8. How Everything Connects

Here is the complete flow from raw data to insight:

```
User uploads file           User clicks "Import      User clicks "Import
or drags & drops      OR    from Langfuse"       OR  from LangSmith"
        │                          │                        │
        ▼                          ▼                        ▼
   TraceLoader              LangfuseImporter         LangSmithImporter
   (parse file)             (HTTP API call)          (SDK API call)
        │                          │                        │
        └──────────────────────────┼────────────────────────┘
                                   │
                                   ▼
                         list[TraceData]  ←── Normalized format
                         (stored in ProjectState.parsed_traces)
                                   │
                                   │  User clicks "Run Extraction"
                                   ▼
                            BatchProcessor
                                   │
                    ┌──────────────┼──────────────┐
                    │              │               │
                    ▼              ▼               ▼
              SkillsDetector  SkillsDetector  SkillsDetector
              (SBERT scores)  (SBERT scores)  (SBERT scores)
                    │              │               │
                    ▼              ▼               ▼
              IntentAgent     IntentAgent     IntentAgent
              (Claude LLM)   (Claude LLM)   (Claude LLM)
                    │              │               │
                    └──────────────┼───────────────┘
                                   │
                                   ▼
                      list[IntentRepresentation]
                      (saved to results.jsonl)
                                   │
                    ┌──────────────┼──────────────────────────┐
                    │              │              │            │
                    ▼              ▼              ▼            ▼
             IntentAnalyzer  SatisfactionAn.  SkillsAn.  SkillsGapAn.
                    │              │              │            │
                    ▼              ▼              ▼            ▼
               Distribution   Mean score    Quadrant     Gap candidates
               Hierarchy      Histogram     Frequency    Coverage matrix
               Categories     By intent     Relevance    Suggested skills
                    │              │              │            │
                    └──────────────┼──────────────┘            │
                                   │                           │
                                   ▼                           ▼
                         Dashboard Charts              Gap Report
                         (ECharts in browser)          (Table + Cards)
```

### The Key Insight: Two-Model Architecture

The system uses two very different AI models for complementary purposes:

| | Sentence-BERT (SBERT) | Claude (LLM) |
|---|---|---|
| **Type** | Embedding model (110M params) | Large language model (billions of params) |
| **Speed** | Very fast (~10ms per trace) | Slower (~2-5s per trace) |
| **Cost** | Free (runs locally) | Paid API call |
| **Capability** | Measures semantic similarity between texts | Reads, understands, and reasons about conversations |
| **Output** | A single number (0.0–1.0) | Structured JSON with multiple fields |
| **Role in pipeline** | Pre-computation: "how similar is this skill to this conversation?" | Final judgment: "what did the user want, were they satisfied, was this skill relevant and why?" |

SBERT provides quantitative hints. Claude provides qualitative understanding. Together, they produce richer analysis than either could alone.

### Data Persistence

- **Projects**: Stored as directories under `data/projects/<id>/`. Metadata (names, IDs) in `data/projects.json`.
- **Uploaded files**: Saved to `data/projects/<id>/uploads/`.
- **Extraction results**: Saved as JSONL to `data/projects/<id>/results.jsonl`. Loaded back on server startup.
- **Runtime settings**: API keys set through the Settings UI live only in `os.environ` (in-memory) and are lost on server restart. To persist them, add them to the `.env` file.

### Concurrency Model

The server is asynchronous (async/await). When extraction runs:
- `BatchProcessor` creates an `asyncio.Semaphore(5)` to limit concurrency
- Up to 5 traces are processed in parallel
- Each trace first gets SBERT scores (fast, local), then calls the Claude API (slower, remote)
- `asyncio.gather()` runs all tasks concurrently, collecting results as they complete
- The frontend can poll `/api/extraction/status` to see progress
