#!/usr/bin/env python3
"""Generate synthetic Langfuse-style traces for testing the Intent Analyzer.

Produces a JSON file with realistic AI agent conversations that cover the full
range of intents, satisfaction levels, skill combinations, and edge cases.

Usage:
    python generate_test_data.py                  # 100 traces → data/synthetic_traces.json
    python generate_test_data.py -n 250           # 250 traces
    python generate_test_data.py -n 50 -o my.json # custom output
"""
from __future__ import annotations

import argparse
import json
import random
import uuid
from pathlib import Path

# ---------------------------------------------------------------------------
# Agent skills (matching typical deep-agent naming conventions)
# ---------------------------------------------------------------------------
SKILLS = [
    "web_search_skill",
    "code_executor_skill",
    "file_reader_skill",
    "file_writer_skill",
    "database_query_skill",
    "api_caller_skill",
    "calculator_skill",
    "image_generator_skill",
    "chart_builder_skill",
    "email_sender_skill",
    "calendar_skill",
    "summarizer_skill",
    "translator_skill",
    "pdf_parser_skill",
    "spreadsheet_skill",
    "browser_tool",
    "shell_executor_skill",
    "memory_skill",
    "planner_skill",
    "knowledge_base_skill",
]

# ---------------------------------------------------------------------------
# Intent definitions — each has conversation templates and typical skills
# ---------------------------------------------------------------------------
INTENT_PROFILES: list[dict] = [
    {
        "intent": "data_analysis",
        "weight": 16,
        "skills": ["database_query_skill", "spreadsheet_skill", "chart_builder_skill", "calculator_skill"],
        "conversations": [
            {
                "messages": [
                    ("user", "Analyze the sales data in {filename}. Break down revenue by {dimension} and show trends over the last {time_range}."),
                    ("assistant", "I'll load the data and run the analysis. Let me start by reading the file and examining the structure."),
                    ("assistant", "[spreadsheet_skill] Loaded {filename}: {row_count} rows, {col_count} columns. Key columns: {columns}"),
                    ("assistant", "[chart_builder_skill] Analysis complete:\n\n**Revenue by {dimension}:**\n{breakdown}\n\n**Trend:** {trend_description}\n\nTop performer: {top_item} at {top_value}"),
                    ("user", "Can you also show the month-over-month growth rate?"),
                    ("assistant", "[calculator_skill] Month-over-month growth rates:\n{growth_rates}\n\nAverage monthly growth: {avg_growth}%"),
                ],
                "tool_calls": [
                    ("spreadsheet_skill", "read {filename}", "Loaded {row_count} rows"),
                    ("chart_builder_skill", "plot revenue by {dimension}", "Chart generated"),
                    ("calculator_skill", "compute growth rates", "Growth analysis complete"),
                ],
            },
            {
                "messages": [
                    ("user", "Run a quick summary of the {dataset_name} dataset — averages, medians, and outliers"),
                    ("assistant", "[spreadsheet_skill] Summary statistics for {dataset_name}:\n\n{summary_stats}\n\nOutliers detected: {outlier_count} rows above {outlier_threshold}"),
                    ("user", "That's exactly what I needed, thanks"),
                ],
                "tool_calls": [
                    ("spreadsheet_skill", "describe {dataset_name}", "Summary statistics computed"),
                ],
            },
        ],
    },
    {
        "intent": "code_generation",
        "weight": 15,
        "skills": ["code_executor_skill", "file_writer_skill", "web_search_skill"],
        "conversations": [
            {
                "messages": [
                    ("user", "Write a {language} function that {task_description}. It should handle edge cases like {edge_case}."),
                    ("assistant", "Here's the implementation:\n\n```{language}\n{code_snippet}\n```\n\nThis handles {edge_case} by {edge_case_handling}."),
                    ("user", "Can you add unit tests for it?"),
                    ("assistant", "[code_executor_skill] Tests written and executed:\n\n```{language}\n{test_code}\n```\n\n**Results:** {test_count} tests passed, 0 failed."),
                ],
                "tool_calls": [
                    ("file_writer_skill", "write {output_file}", "File created"),
                    ("code_executor_skill", "run tests", "{test_count} tests passed"),
                ],
            },
            {
                "messages": [
                    ("user", "Debug this {language} code — it's throwing {error_type}:\n```\n{buggy_code}\n```"),
                    ("assistant", "I found the issue. The problem is {bug_explanation}.\n\nHere's the fix:\n```{language}\n{fixed_code}\n```\n\n{fix_explanation}"),
                    ("user", "Works now, thanks!"),
                ],
                "tool_calls": [
                    ("code_executor_skill", "execute and debug", "Error reproduced and fixed"),
                ],
            },
        ],
    },
    {
        "intent": "research",
        "weight": 14,
        "skills": ["web_search_skill", "summarizer_skill", "knowledge_base_skill", "pdf_parser_skill"],
        "conversations": [
            {
                "messages": [
                    ("user", "Research {topic} — I need a comprehensive overview with recent developments and key players."),
                    ("assistant", "I'll search for the latest information on {topic} and compile a summary."),
                    ("assistant", "[web_search_skill] Found {source_count} relevant sources. Analyzing..."),
                    ("assistant", "[summarizer_skill] **Research Summary: {topic}**\n\n**Overview:**\n{overview}\n\n**Key Players:**\n{key_players}\n\n**Recent Developments:**\n{recent_devs}\n\n**Sources:** {source_count} sources consulted"),
                    ("user", "Can you go deeper on the {subtopic} aspect?"),
                    ("assistant", "[web_search_skill] Deep-dive on {subtopic}:\n\n{deep_dive}\n\nKey takeaway: {takeaway}"),
                ],
                "tool_calls": [
                    ("web_search_skill", "search {topic}", "Found {source_count} results"),
                    ("summarizer_skill", "summarize findings", "Summary generated"),
                    ("web_search_skill", "search {subtopic}", "Found additional details"),
                ],
            },
            {
                "messages": [
                    ("user", "Summarize this PDF for me: {filename}"),
                    ("assistant", "[pdf_parser_skill] Parsed {filename} ({page_count} pages).\n\n**Summary:**\n{pdf_summary}\n\n**Key Points:**\n{key_points}"),
                    ("user", "Great summary, thanks"),
                ],
                "tool_calls": [
                    ("pdf_parser_skill", "parse {filename}", "Parsed {page_count} pages"),
                    ("summarizer_skill", "summarize document", "Summary ready"),
                ],
            },
        ],
    },
    {
        "intent": "content_generation",
        "weight": 10,
        "skills": ["file_writer_skill", "web_search_skill", "image_generator_skill"],
        "conversations": [
            {
                "messages": [
                    ("user", "Write a {content_type} about {topic}. Target audience is {audience}. Tone should be {tone}."),
                    ("assistant", "Here's your {content_type}:\n\n{generated_content}\n\nWord count: {word_count}. Optimized for {audience} with a {tone} tone."),
                    ("user", "Can you make it shorter and punchier?"),
                    ("assistant", "Revised version:\n\n{revised_content}\n\nCut to {revised_word_count} words while keeping the key points."),
                ],
                "tool_calls": [
                    ("file_writer_skill", "write {content_type}.md", "Content saved"),
                ],
            },
            {
                "messages": [
                    ("user", "Generate an image for the {content_type} — something that represents {visual_concept}"),
                    ("assistant", "[image_generator_skill] Image generated: {image_description}\n\nSaved as {image_filename}. Resolution: {resolution}."),
                ],
                "tool_calls": [
                    ("image_generator_skill", "generate --prompt {visual_concept}", "Image created"),
                ],
            },
        ],
    },
    {
        "intent": "task_automation",
        "weight": 12,
        "skills": ["shell_executor_skill", "file_reader_skill", "file_writer_skill", "api_caller_skill"],
        "conversations": [
            {
                "messages": [
                    ("user", "I need to {automation_task}. The files are in {directory} and should be processed {processing_rule}."),
                    ("assistant", "I'll set this up. Let me first check the directory structure."),
                    ("assistant", "[file_reader_skill] Found {file_count} files in {directory}:\n{file_list}"),
                    ("assistant", "[shell_executor_skill] Processing complete:\n- Processed: {processed_count} files\n- Skipped: {skipped_count} files\n- Output saved to: {output_dir}"),
                    ("user", "Perfect, exactly what I needed"),
                ],
                "tool_calls": [
                    ("file_reader_skill", "list {directory}", "Found {file_count} files"),
                    ("shell_executor_skill", "batch process", "Processed {processed_count} files"),
                    ("file_writer_skill", "write results", "Output saved"),
                ],
            },
            {
                "messages": [
                    ("user", "Set up a workflow to {workflow_description} every time {trigger_condition}"),
                    ("assistant", "[planner_skill] Workflow plan:\n\n1. {step_1}\n2. {step_2}\n3. {step_3}\n\nShall I implement this?"),
                    ("user", "Yes, go ahead"),
                    ("assistant", "[shell_executor_skill] Workflow configured:\n- Trigger: {trigger_condition}\n- Actions: {action_count} steps\n- Status: Active\n\n{workflow_note}"),
                ],
                "tool_calls": [
                    ("planner_skill", "plan workflow", "Plan created"),
                    ("shell_executor_skill", "setup automation", "Workflow active"),
                ],
            },
        ],
    },
    {
        "intent": "report_generation",
        "weight": 10,
        "skills": ["spreadsheet_skill", "chart_builder_skill", "file_writer_skill", "pdf_parser_skill"],
        "conversations": [
            {
                "messages": [
                    ("user", "Generate a {report_type} report from the {dataset_name} data. Include charts and a summary."),
                    ("assistant", "I'll compile a comprehensive {report_type} report based on the data.\n\nAnalyzing {dataset_name}..."),
                    ("assistant", "[chart_builder_skill] Report generated:\n- **Summary**: {metric_count} metrics analyzed\n- **Key Finding**: {key_finding}\n- **Charts**: {chart_count} visualizations\n- **Format**: {report_format}\n\nThe report includes trend analysis and actionable recommendations."),
                    ("user", "Add a comparison with last {time_period}'s numbers"),
                    ("assistant", "[spreadsheet_skill] Comparison added:\n\n{comparison_table}\n\nFinal report saved as `{report_filename}` ({page_count} pages)."),
                ],
                "tool_calls": [
                    ("spreadsheet_skill", "analyze {dataset_name}", "Analysis complete"),
                    ("chart_builder_skill", "generate charts", "Created {chart_count} charts"),
                    ("file_writer_skill", "write report", "Report saved"),
                ],
            },
            {
                "messages": [
                    ("user", "I need a quick summary dashboard of the {metric_name} metrics"),
                    ("assistant", "[chart_builder_skill] Dashboard generated:\n\n**{metric_name} Overview:**\n- Current: {current_value}\n- Previous: {previous_value}\n- Change: {change_pct}%\n\nSaved as `dashboard_{date}.html`."),
                ],
                "tool_calls": [
                    ("chart_builder_skill", "generate dashboard", "Dashboard created"),
                ],
            },
        ],
    },
    {
        "intent": "data_retrieval",
        "weight": 8,
        "skills": ["database_query_skill", "api_caller_skill", "web_search_skill"],
        "conversations": [
            {
                "messages": [
                    ("user", "Pull the {data_type} records from {data_source} where {filter_condition}. I need it in {output_format} format."),
                    ("assistant", "[database_query_skill] Query executed. Retrieved {record_count} records matching {filter_condition}.\n\nExported to {output_format}: `{output_file}`"),
                    ("user", "Can you filter further to only include {extra_filter}?"),
                    ("assistant", "[database_query_skill] Filtered results: {filtered_count} records remaining.\n\nUpdated file: `{output_file}`"),
                ],
                "tool_calls": [
                    ("database_query_skill", "SELECT * FROM {data_source} WHERE {filter_condition}", "Retrieved {record_count} records"),
                    ("database_query_skill", "apply filter {extra_filter}", "Filtered to {filtered_count} records"),
                ],
            },
        ],
    },
    {
        "intent": "scheduling",
        "weight": 5,
        "skills": ["calendar_skill", "email_sender_skill", "planner_skill"],
        "conversations": [
            {
                "messages": [
                    ("user", "Schedule a {meeting_type} with {participants} for {time_preference}. Topic: {meeting_topic}."),
                    ("assistant", "[calendar_skill] Checking availability for {participants}...\n\nBest available slot: {suggested_time}\n\nShall I send the invite?"),
                    ("user", "Yes, send it"),
                    ("assistant", "[email_sender_skill] Calendar invite sent to {participant_count} participants:\n- Time: {suggested_time}\n- Duration: {duration}\n- Topic: {meeting_topic}\n\nAll confirmations pending."),
                ],
                "tool_calls": [
                    ("calendar_skill", "check availability", "Found {slot_count} available slots"),
                    ("email_sender_skill", "send invite", "Invite sent to {participant_count} people"),
                ],
            },
        ],
    },
    {
        "intent": "translation",
        "weight": 4,
        "skills": ["translator_skill", "file_reader_skill", "file_writer_skill"],
        "conversations": [
            {
                "messages": [
                    ("user", "Translate this document from {source_lang} to {target_lang}: {filename}"),
                    ("assistant", "[file_reader_skill] Loaded {filename} ({word_count} words).\n\n[translator_skill] Translation complete ({source_lang} → {target_lang}).\n\nSaved as `{translated_filename}`."),
                    ("user", "Looks good, but can you adjust the {section_name} section to be more {tone}?"),
                    ("assistant", "[translator_skill] Revised the {section_name} section with a more {tone} tone.\n\nUpdated file saved."),
                ],
                "tool_calls": [
                    ("file_reader_skill", "read {filename}", "Loaded {word_count} words"),
                    ("translator_skill", "translate {source_lang} to {target_lang}", "Translation complete"),
                ],
            },
        ],
    },
    {
        "intent": "troubleshooting",
        "weight": 8,
        "skills": ["shell_executor_skill", "web_search_skill", "code_executor_skill", "file_reader_skill"],
        "conversations": [
            {
                "messages": [
                    ("user", "My {system_component} is throwing this error: `{error_message}`. How do I fix it?"),
                    ("assistant", "Let me investigate this. I'll check the logs and search for known solutions."),
                    ("assistant", "[file_reader_skill] Log analysis:\n{log_summary}"),
                    ("assistant", "[web_search_skill] Found {solution_count} potential solutions. The most relevant fix:\n\n**Root cause:** {root_cause}\n\n**Fix:**\n```\n{fix_command}\n```\n\n{fix_explanation}"),
                    ("user", "That fixed it, thanks!"),
                ],
                "tool_calls": [
                    ("file_reader_skill", "read logs", "Log entries analyzed"),
                    ("web_search_skill", "search error {error_message}", "Found {solution_count} solutions"),
                    ("shell_executor_skill", "apply fix", "Fix applied"),
                ],
            },
            {
                "messages": [
                    ("user", "Why is my {system_component} running so slowly? It used to be fast."),
                    ("assistant", "[shell_executor_skill] Diagnostics:\n- CPU: {cpu_usage}%\n- Memory: {memory_usage}%\n- Disk I/O: {disk_io}\n\nBottleneck identified: **{bottleneck}**\n\nRecommendation: {recommendation}"),
                    ("user", "Makes sense. Apply the fix."),
                    ("assistant", "[shell_executor_skill] Fix applied. Performance improved:\n- Before: {before_metric}\n- After: {after_metric}"),
                ],
                "tool_calls": [
                    ("shell_executor_skill", "run diagnostics", "Diagnostics complete"),
                    ("shell_executor_skill", "apply optimization", "Performance improved"),
                ],
            },
        ],
    },
    {
        "intent": "general_assistance",
        "weight": 8,
        "skills": [],
        "conversations": [
            {
                "messages": [
                    ("user", "What's the best approach for {general_topic}?"),
                    ("assistant", "{general_answer}\n\nThe key tradeoff is {tradeoff}. For your use case, I'd recommend {recommendation}."),
                    ("user", "Makes sense, thanks"),
                ],
                "tool_calls": [],
            },
            {
                "messages": [
                    ("user", "Explain {concept} in simple terms"),
                    ("assistant", "{concept_explanation}\n\nIn practice, this means {practical_implication}. A common analogy is {analogy}."),
                ],
                "tool_calls": [],
            },
            {
                "messages": [
                    ("user", "What are the pros and cons of {option_a} vs {option_b}?"),
                    ("assistant", "Here's a comparison:\n\n**{option_a}:**\n- Pros: {option_a_pros}\n- Cons: {option_a_cons}\n\n**{option_b}:**\n- Pros: {option_b_pros}\n- Cons: {option_b_cons}\n\nBottom line: {comparison_verdict}"),
                    ("user", "Thanks, that's helpful"),
                ],
                "tool_calls": [],
            },
        ],
    },
    {
        "intent": "api_integration",
        "weight": 5,
        "skills": ["api_caller_skill", "code_executor_skill", "file_writer_skill"],
        "conversations": [
            {
                "messages": [
                    ("user", "Connect to the {api_name} API and fetch {data_type}. Use the key in my env vars."),
                    ("assistant", "[api_caller_skill] Connected to {api_name}. Fetching {data_type}..."),
                    ("assistant", "[api_caller_skill] Retrieved {record_count} records:\n\n{api_response_preview}\n\nFull response saved to `{output_file}`."),
                    ("user", "Transform this into a {output_format} and save it"),
                    ("assistant", "[file_writer_skill] Transformed and saved as {output_format}: `{transformed_file}`\n\n{record_count} records processed."),
                ],
                "tool_calls": [
                    ("api_caller_skill", "GET {api_endpoint}", "Retrieved {record_count} records"),
                    ("file_writer_skill", "write {transformed_file}", "File saved"),
                ],
            },
        ],
    },
]

# ---------------------------------------------------------------------------
# Satisfaction profiles — applied as an overlay to control score distribution
# ---------------------------------------------------------------------------
SATISFACTION_PROFILES = [
    {"range": (0.85, 1.0), "weight": 35, "goal_achieved": True,
     "signals": ["Goal clearly met", "Short conversation", "No clarifications needed",
                 "User expressed satisfaction", "Efficient workflow"]},
    {"range": (0.70, 0.84), "weight": 25, "goal_achieved": True,
     "signals": ["Goal met with minor friction", "One clarification needed",
                 "Slightly longer than necessary", "Minor tool error recovered"]},
    {"range": (0.40, 0.69), "weight": 20, "goal_achieved": None,
     "signals": ["Partial results obtained", "Multiple clarifications needed",
                 "User had to rephrase request", "Some tool failures"]},
    {"range": (0.15, 0.39), "weight": 12, "goal_achieved": False,
     "signals": ["Goal not fully met", "Repeated rephrasing", "Tool errors",
                 "User showed frustration", "Workaround required"]},
    {"range": (0.0, 0.14), "weight": 8, "goal_achieved": False,
     "signals": ["User abandoned session", "Complete tool failure",
                 "No useful output", "Explicit frustration expressed"]},
]

# ---------------------------------------------------------------------------
# Fill-in values for template variables
# ---------------------------------------------------------------------------
FILENAMES = [
    "sales_q1_2026.csv", "customer_data.xlsx", "product_metrics.json",
    "revenue_report.csv", "user_analytics.parquet", "inventory.xlsx",
    "transactions_may.csv", "marketing_kpis.csv",
]
DATASETS = [
    "quarterly_revenue", "user_engagement", "product_performance",
    "customer_churn", "marketing_attribution", "support_tickets",
    "conversion_funnel", "retention_cohorts",
]
TOPICS = [
    "large language model fine-tuning strategies",
    "real-time data streaming architectures",
    "customer retention optimization",
    "microservices vs monolith tradeoffs",
    "CI/CD pipeline best practices",
    "product-led growth strategies",
    "edge computing for IoT applications",
    "vector database performance comparison",
]
SUBTOPICS = [
    "cost optimization", "scaling challenges", "open-source alternatives",
    "enterprise adoption", "performance benchmarks", "migration strategies",
]
LANGUAGES = ["Python", "TypeScript", "Go", "Rust", "Java"]
TASK_DESCRIPTIONS = [
    "parses CSV files and validates data types",
    "implements a rate limiter with sliding window",
    "builds a REST API endpoint with pagination",
    "processes a queue of async tasks with retries",
    "generates a PDF report from a template",
]
ERROR_TYPES = [
    "TypeError", "ConnectionRefusedError", "TimeoutError",
    "MemoryError", "ImportError", "KeyError",
]
ERROR_MESSAGES = [
    "Cannot connect to database at localhost:5432",
    "Module 'numpy' has no attribute 'float'",
    "Request timeout after 30s — upstream service unavailable",
    "Out of memory: cannot allocate 2GB tensor",
    "Permission denied: cannot write to /var/log/app.log",
    "Key 'user_id' not found in response payload",
]
SYSTEM_COMPONENTS = [
    "Docker container", "API gateway", "database connection pool",
    "Kubernetes pod", "CI pipeline", "message queue",
    "caching layer", "load balancer",
]
CONTENT_TYPES = [
    "blog post", "product description", "email newsletter",
    "technical documentation", "landing page copy", "release notes",
]
API_NAMES = [
    "Stripe", "OpenAI", "Slack", "GitHub", "Twilio",
    "SendGrid", "AWS S3", "Google Sheets",
]
MEETING_TYPES = [
    "sprint planning", "design review", "1-on-1",
    "project kickoff", "retrospective", "stakeholder demo",
]
USERS = [f"user_{i:03d}" for i in range(1, 21)]
SESSIONS = [f"session_{uuid.uuid4().hex[:8]}" for _ in range(50)]


def _pick_weighted(items: list[dict], key: str = "weight") -> dict:
    weights = [item[key] for item in items]
    return random.choices(items, weights=weights, k=1)[0]


def _fill_template(text: str, ctx: dict) -> str:
    try:
        return text.format_map(ctx)
    except (KeyError, IndexError):
        return text


def _build_context() -> dict:
    filename = random.choice(FILENAMES)
    dataset_name = random.choice(DATASETS)
    topic = random.choice(TOPICS)
    language = random.choice(LANGUAGES)
    api_name = random.choice(API_NAMES)

    return {
        "filename": filename,
        "dataset_name": dataset_name,
        "topic": topic,
        "subtopic": random.choice(SUBTOPICS),
        "language": language,
        "dimension": random.choice(["region", "product category", "channel", "customer segment"]),
        "time_range": random.choice(["6 months", "quarter", "12 months", "3 months"]),
        "row_count": random.randint(500, 50000),
        "col_count": random.randint(8, 35),
        "columns": ", ".join(random.sample(["revenue", "date", "customer_id", "product", "region", "quantity", "cost", "channel", "status"], k=4)),
        "breakdown": "\n".join(f"  - {item}: ${random.randint(100, 999)}K" for item in random.sample(["North America", "Europe", "APAC", "LATAM", "Enterprise", "SMB", "Direct", "Partner"], k=4)),
        "trend_description": random.choice(["Steady growth of 12% QoQ", "Flat with seasonal dips in Q3", "Strong upward trend since March", "Declining 5% MoM since February"]),
        "top_item": random.choice(["Enterprise segment", "North America", "Direct channel", "SaaS product line"]),
        "top_value": f"${random.randint(200, 900)}K",
        "growth_rates": "\n".join(f"  - {m}: {random.uniform(-5, 15):.1f}%" for m in ["Jan", "Feb", "Mar", "Apr", "May"]),
        "avg_growth": round(random.uniform(2, 12), 1),
        "summary_stats": f"Mean: {random.randint(50, 500)}, Median: {random.randint(40, 450)}, Std: {random.randint(10, 100)}",
        "outlier_count": random.randint(3, 20),
        "outlier_threshold": f"{random.randint(2, 4)}σ",
        "task_description": random.choice(TASK_DESCRIPTIONS),
        "edge_case": random.choice(["empty input", "null values", "concurrent access", "very large files", "unicode characters"]),
        "edge_case_handling": random.choice(["returning an empty result", "raising a descriptive error", "using a default fallback", "validating input first"]),
        "code_snippet": f"def process_{random.choice(['data', 'request', 'batch', 'stream'])}(input):\n    # Implementation here\n    pass",
        "test_code": "def test_basic(): assert process(valid_input) == expected\ndef test_edge(): assert process(None) raises ValueError",
        "test_count": random.randint(4, 12),
        "output_file": f"output_{random.choice(['data', 'report', 'results'])}.{random.choice(['json', 'csv', 'xlsx'])}",
        "buggy_code": f"for item in data:\n    result += item['{random.choice(['id', 'name', 'value'])}']",
        "fixed_code": "for item in data:\n    if key in item:\n        result += item[key]",
        "bug_explanation": random.choice(["a missing key check", "an off-by-one error", "a type mismatch", "a race condition"]),
        "fix_explanation": random.choice(["Added null check before access", "Fixed loop boundary condition", "Added type coercion", "Used a lock for thread safety"]),
        "error_type": random.choice(ERROR_TYPES),
        "error_message": random.choice(ERROR_MESSAGES),
        "source_count": random.randint(5, 25),
        "overview": "The field has seen rapid growth driven by advances in foundational models and enterprise adoption.",
        "key_players": "\n".join(f"  - {p}" for p in random.sample(["OpenAI", "Google DeepMind", "Anthropic", "Meta AI", "Mistral", "Cohere", "Databricks"], k=4)),
        "recent_devs": "\n".join(f"  - {d}" for d in ["New benchmark results released", "Major partnership announced", "Open-source model launch"]),
        "deep_dive": "Detailed analysis of emerging trends and competitive dynamics in this space.",
        "takeaway": random.choice(["The market is consolidating around a few key players", "Open-source is closing the gap", "Enterprise demand is outpacing supply"]),
        "pdf_summary": "The document covers strategic recommendations for the next fiscal year.",
        "key_points": "\n".join(f"  {i+1}. {p}" for i, p in enumerate(random.sample(["Revenue targets updated", "New market expansion planned", "Headcount adjustments proposed", "Product roadmap revised"], k=3))),
        "page_count": random.randint(5, 60),
        "content_type": random.choice(CONTENT_TYPES),
        "audience": random.choice(["developers", "executives", "general public", "data scientists", "product managers"]),
        "tone": random.choice(["professional", "casual", "technical", "persuasive", "educational"]),
        "generated_content": "Lorem ipsum content placeholder — real generation would produce the full text.",
        "revised_content": "Shorter, punchier version of the content.",
        "word_count": random.randint(300, 2000),
        "revised_word_count": random.randint(150, 800),
        "visual_concept": random.choice(["data flowing through a pipeline", "team collaboration", "growth chart", "abstract technology"]),
        "image_description": "Generated illustration matching the concept",
        "image_filename": f"image_{uuid.uuid4().hex[:6]}.png",
        "resolution": random.choice(["1024x1024", "1920x1080", "1280x720"]),
        "automation_task": random.choice(["rename and organize all CSV files by date", "batch convert images to WebP format", "extract data from PDFs and merge into one spreadsheet", "clean up duplicate records across files"]),
        "directory": random.choice(["./data/raw", "./exports", "./uploads/pending", "./reports/2026"]),
        "processing_rule": random.choice(["alphabetically by date prefix", "grouped by category", "filtered by size > 1MB", "sorted by last modified"]),
        "file_count": random.randint(10, 200),
        "file_list": "\n".join(f"  - file_{i}.csv ({random.randint(10, 500)}KB)" for i in range(1, 4)),
        "processed_count": random.randint(8, 180),
        "skipped_count": random.randint(0, 10),
        "output_dir": "./data/processed",
        "workflow_description": random.choice(["sync data from the API to our database", "send a weekly digest email", "generate and upload reports", "clean and archive old files"]),
        "trigger_condition": random.choice(["a new file is added", "every Monday at 9am", "the API returns new data", "storage exceeds 80%"]),
        "step_1": random.choice(["Check for new data", "Pull latest records", "Validate input files"]),
        "step_2": random.choice(["Transform and clean data", "Generate visualizations", "Apply business rules"]),
        "step_3": random.choice(["Save results and notify", "Upload to destination", "Send summary email"]),
        "action_count": random.randint(3, 7),
        "workflow_note": random.choice(["First run scheduled for tomorrow.", "Monitoring dashboard available.", "Error notifications enabled."]),
        "report_type": random.choice(["quarterly performance", "weekly metrics", "annual review", "monthly KPI"]),
        "metric_count": random.randint(5, 20),
        "key_finding": random.choice(["Revenue grew 15% QoQ", "Churn rate dropped to 3.2%", "NPS improved by 12 points", "Conversion rate hit all-time high"]),
        "chart_count": random.randint(3, 10),
        "report_format": random.choice(["PDF", "HTML", "Google Slides", "Markdown"]),
        "comparison_table": "| Metric | This Period | Last Period | Change |\n|---|---|---|---|\n| Revenue | $1.2M | $1.05M | +14% |",
        "report_filename": f"report_{random.choice(['q1', 'q2', 'weekly', 'monthly'])}_{random.randint(2025, 2026)}.pdf",
        "time_period": random.choice(["quarter", "month", "year"]),
        "metric_name": random.choice(["revenue", "user engagement", "conversion", "retention"]),
        "current_value": f"{random.randint(50, 300)}K",
        "previous_value": f"{random.randint(40, 250)}K",
        "change_pct": round(random.uniform(-10, 30), 1),
        "date": "2026-05-18",
        "data_type": random.choice(["customer", "transaction", "product", "order"]),
        "data_source": random.choice(["users_db", "analytics_warehouse", "crm_system", "events_table"]),
        "filter_condition": random.choice(["status = 'active'", "created_at > '2026-01-01'", "region = 'US'", "amount > 1000"]),
        "output_format": random.choice(["CSV", "JSON", "Parquet", "Excel"]),
        "record_count": random.randint(50, 10000),
        "extra_filter": random.choice(["last 30 days only", "premium tier customers", "completed transactions", "non-null email"]),
        "filtered_count": random.randint(20, 5000),
        "meeting_type": random.choice(MEETING_TYPES),
        "participants": random.choice(["the engineering team", "Alice and Bob", "the product squad", "all stakeholders"]),
        "time_preference": random.choice(["sometime this week", "tomorrow afternoon", "next Monday morning", "ASAP"]),
        "meeting_topic": random.choice(["Q2 roadmap review", "Architecture decision", "Sprint retro", "Feature demo"]),
        "suggested_time": random.choice(["Tuesday 2:00 PM", "Wednesday 10:00 AM", "Thursday 3:30 PM", "Friday 11:00 AM"]),
        "participant_count": random.randint(2, 8),
        "duration": random.choice(["30 min", "45 min", "1 hour"]),
        "slot_count": random.randint(2, 5),
        "source_lang": random.choice(["English", "Spanish", "French", "German", "Japanese"]),
        "target_lang": random.choice(["English", "Spanish", "French", "German", "Portuguese"]),
        "translated_filename": f"translated_{uuid.uuid4().hex[:6]}.docx",
        "section_name": random.choice(["introduction", "conclusion", "summary", "methodology"]),
        "system_component": random.choice(SYSTEM_COMPONENTS),
        "log_summary": "Last 50 log entries show repeated connection timeouts starting at 14:32 UTC.",
        "root_cause": random.choice(["Connection pool exhaustion", "Misconfigured timeout", "Memory leak in worker process", "DNS resolution failure"]),
        "fix_command": random.choice(["docker restart api-gateway", "kubectl rollout restart deployment/app", "systemctl restart postgresql", "npm run migrate:fix"]),
        "solution_count": random.randint(3, 15),
        "cpu_usage": random.randint(20, 95),
        "memory_usage": random.randint(30, 98),
        "disk_io": random.choice(["high (85% utilized)", "normal", "bottlenecked on writes"]),
        "bottleneck": random.choice(["Memory pressure from cache overflow", "Disk I/O saturation", "CPU-bound query processing", "Network latency to upstream"]),
        "recommendation": random.choice(["Increase memory limit to 4GB", "Add an index on the queried column", "Enable connection pooling", "Scale horizontally to 3 replicas"]),
        "before_metric": random.choice(["450ms p99 latency", "85% memory usage", "12 req/s throughput"]),
        "after_metric": random.choice(["120ms p99 latency", "52% memory usage", "48 req/s throughput"]),
        "general_topic": random.choice(["building a data pipeline", "choosing a database", "structuring a monorepo", "implementing caching"]),
        "general_answer": "There are several valid approaches, each with different tradeoffs around complexity, cost, and maintainability.",
        "tradeoff": random.choice(["simplicity vs flexibility", "cost vs performance", "speed vs correctness", "consistency vs availability"]),
        "concept": random.choice(["vector embeddings", "event sourcing", "eventual consistency", "rate limiting", "blue-green deployments"]),
        "concept_explanation": "A technique used to improve system reliability and performance by distributing workload across components.",
        "practical_implication": "you can handle failures gracefully without losing data",
        "analogy": random.choice(["like having a backup route for your commute", "similar to how a library index card system works", "like a factory assembly line with quality checks"]),
        "option_a": random.choice(["PostgreSQL", "REST API", "Monolith", "AWS Lambda"]),
        "option_b": random.choice(["MongoDB", "GraphQL", "Microservices", "ECS Fargate"]),
        "option_a_pros": random.choice(["Strong consistency, mature tooling", "Simple, well-understood", "Easy to deploy initially"]),
        "option_a_cons": random.choice(["Schema rigidity", "Over-fetching issues", "Harder to scale individual components"]),
        "option_b_pros": random.choice(["Flexible schema", "Client-driven queries", "Independent scaling"]),
        "option_b_cons": random.choice(["Weaker consistency guarantees", "Steeper learning curve", "Operational complexity"]),
        "comparison_verdict": random.choice(["Go with the simpler option unless you have a specific scaling need", "Either works — pick based on team familiarity", "The second option pays off at scale but has higher upfront cost"]),
        "api_name": api_name,
        "api_endpoint": f"/v1/{random.choice(['users', 'orders', 'products', 'events'])}",
        "api_response_preview": '{"data": [...], "total": ' + str(random.randint(50, 500)) + '}',
        "transformed_file": f"output.{random.choice(['csv', 'json', 'xlsx'])}",
    }


def _add_frustration_messages(messages: list[tuple[str, str]], sat_profile: dict) -> list[tuple[str, str]]:
    """For low-satisfaction traces, inject clarification / frustration messages."""
    lo, hi = sat_profile["range"]
    mid = (lo + hi) / 2

    if mid >= 0.7:
        return messages

    frustration_inserts = [
        ("user", "That's not what I asked for. Let me rephrase..."),
        ("user", "No, I mean specifically the {dataset_name} data, not the other one."),
        ("user", "This is taking too long. Can you try a different approach?"),
        ("assistant", "I apologize for the confusion. Let me re-run with the correct parameters."),
        ("user", "The tool seems to have failed. What happened?"),
        ("assistant", "There was an error processing the request. Retrying with adjusted settings..."),
    ]

    result = list(messages)
    n_inserts = 1 if mid >= 0.4 else random.randint(2, 3)

    for _ in range(n_inserts):
        insert = random.choice(frustration_inserts)
        pos = random.randint(1, max(1, len(result) - 1))
        result.insert(pos, insert)

    return result


def _pick_irrelevant_skills(intent_skills: list[str], n: int) -> list[str]:
    """Pick skills that are NOT relevant to the current intent — for noisy activations."""
    candidates = [s for s in SKILLS if s not in intent_skills]
    return random.sample(candidates, k=min(n, len(candidates)))


def generate_trace(trace_num: int) -> dict:
    intent_profile = _pick_weighted(INTENT_PROFILES)
    sat_profile = _pick_weighted(SATISFACTION_PROFILES)
    conv_template = random.choice(intent_profile["conversations"])
    ctx = _build_context()

    # Build messages
    raw_messages = conv_template["messages"]
    raw_messages = _add_frustration_messages(raw_messages, sat_profile)
    messages = [
        {"role": role, "content": _fill_template(content, ctx)}
        for role, content in raw_messages
    ]

    # Build tool calls
    tool_calls = [
        {
            "tool_name": tc[0],
            "input_summary": _fill_template(tc[1], ctx),
            "output_summary": _fill_template(tc[2], ctx),
        }
        for tc in conv_template.get("tool_calls", [])
    ]

    # Skills: relevant + occasional irrelevant noise
    relevant_skills = [tc["tool_name"] for tc in tool_calls if tc["tool_name"] in SKILLS]
    for s in intent_profile["skills"]:
        if s not in relevant_skills and random.random() < 0.3:
            relevant_skills.append(s)

    # 30% chance of adding 1-2 irrelevant skills (noisy activations)
    if random.random() < 0.3:
        irrelevant = _pick_irrelevant_skills(intent_profile["skills"], random.randint(1, 2))
        relevant_skills.extend(irrelevant)

    # Duration correlates loosely with conversation length and satisfaction
    base_duration = len(messages) * random.uniform(15, 45)
    lo, hi = sat_profile["range"]
    if (lo + hi) / 2 < 0.4:
        base_duration *= random.uniform(1.5, 3.0)  # frustrated sessions run longer

    trace_id = f"trace_{uuid.uuid4().hex[:12]}"

    return {
        "trace_id": trace_id,
        "session_id": random.choice(SESSIONS),
        "user_id": random.choice(USERS),
        "messages": messages,
        "tool_calls": tool_calls,
        "skills_activated": list(dict.fromkeys(relevant_skills)),  # dedupe, preserve order
        "metadata": {
            "timestamp": f"2026-05-{random.randint(1, 18):02d}T{random.randint(8, 22):02d}:{random.randint(0, 59):02d}:00Z",
            "source": "synthetic_generator",
            "intent_hint": intent_profile["intent"],
            "satisfaction_hint": round(random.uniform(*sat_profile["range"]), 2),
            "goal_achieved_hint": sat_profile["goal_achieved"]
            if sat_profile["goal_achieved"] is not None
            else random.choice([True, False]),
        },
        "duration_seconds": round(base_duration, 1),
    }


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic traces for the Intent Analyzer")
    parser.add_argument("-n", "--count", type=int, default=100, help="Number of traces to generate")
    parser.add_argument("-o", "--output", type=str, default=None, help="Output file path")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    args = parser.parse_args()

    random.seed(args.seed)

    output_path = Path(args.output) if args.output else Path(__file__).parent / "data" / "synthetic_traces.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    traces = [generate_trace(i) for i in range(args.count)]

    output_path.write_text(json.dumps(traces, indent=2, ensure_ascii=False), encoding="utf-8")

    # Print distribution summary
    intent_counts: dict[str, int] = {}
    sat_sum = 0.0
    for t in traces:
        intent = t["metadata"]["intent_hint"]
        intent_counts[intent] = intent_counts.get(intent, 0) + 1
        sat_sum += t["metadata"]["satisfaction_hint"]

    print(f"Generated {len(traces)} traces → {output_path}")
    print(f"\nIntent distribution:")
    for intent, count in sorted(intent_counts.items(), key=lambda x: -x[1]):
        print(f"  {intent:<30} {count:>3} ({count/len(traces)*100:.0f}%)")
    print(f"\nMean satisfaction hint: {sat_sum / len(traces):.2f}")
    print(f"Unique sessions: {len(set(t['session_id'] for t in traces))}")
    print(f"Unique users: {len(set(t['user_id'] for t in traces))}")


if __name__ == "__main__":
    main()
