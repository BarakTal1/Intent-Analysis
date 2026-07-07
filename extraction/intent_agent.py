from __future__ import annotations

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage

from config import settings
from .schemas import IntentRepresentation, TraceData


INTENT_EXTRACTION_PROMPT = """\
You are an Intent Analysis Agent that processes traces from AI agent systems.

You receive a single trace — a conversation between a user and an AI assistant/agent, \
including any tool calls and their results. Your job is to analyze the trace and produce \
a structured intent representation.

## What to analyze

1. **User Intent** — What was the user trying to achieve? Identify the primary intent \
and any sub-intents. Derive the intent category from the actual conversation domain.

2. **Satisfaction** — Did the user achieve their goal? Look for signals:
   - Short conversation with goal clearly met → high satisfaction (0.85–1.0)
   - Goal met with 1–2 minor friction points → mostly satisfied (0.7–0.84)
   - Goal partially met, 3+ clarifications needed → partial (0.4–0.69)
   - Goal not met, repeated rephrasing, frustration signals → low (0.15–0.39)
   - Abandonment, explicit failure, no resolution → very low (0.0–0.14)

3. **Skills** — For each skill/tool in the "Skills Activated" list, judge whether it was \
relevant to what the user was trying to do. A tool that fires without contributing to \
the user's goal is NOT relevant, even if it ran successfully.

## Important guidelines

- `trace_id`: copy exactly from the trace header
- `primary_intent`: a SPECIFIC, snake_case label for the user's concrete goal — \
name the actual action + object, not a broad functional bucket. \
Prefer `cancel_order`, `check_invoice`, `recover_password`, `change_shipping_address`, \
`track_refund` over vague categories. \
DO NOT use generic catch-alls like `general_assistance`, `information_retrieval`, \
`data_retrieval`, `account_management`, `task_automation`, or `troubleshooting` when a \
more specific intent is identifiable — those hide the real intent and are almost never \
the right answer. Use `unknown` ONLY when the goal genuinely cannot be determined. \
Two conversations with the same underlying goal must get the same label.
- `complexity`: low = single tool call; medium = multi-step; high = complex multi-tool chain
- `user_expertise`: infer from language sophistication and domain knowledge shown
- `clarifications_needed`: count how many times the user had to re-explain or restate their request

If pre-computed SBERT relevance hints are provided for skills, treat them as supporting evidence \
for your judgment — they measure semantic similarity between the conversation and the skill name. \
High scores (> 0.6) suggest relevance; low scores (< 0.35) suggest the skill may not fit the \
user's intent. Your judgment takes precedence.
"""


class IntentExtractionAgent:
    """Extracts structured intent from a single agent trace."""

    def __init__(self, model_name: str | None = None) -> None:
        model = init_chat_model(
            model_name or settings.model_name,
            api_key=settings.anthropic_api_key,
        )
        self.chain = model.with_structured_output(IntentRepresentation)

    def extract(
        self,
        trace: TraceData,
        sbert_scores: dict[str, float] | None = None,
        allowed_intents: list[str] | None = None,
    ) -> IntentRepresentation:
        trace_text = self._format_trace(trace, sbert_scores)
        result: IntentRepresentation = self.chain.invoke([
            SystemMessage(content=self._system_content(allowed_intents)),
            HumanMessage(content=trace_text),
        ])
        result.trace_id = trace.trace_id
        self._fill_sbert_scores(result, sbert_scores)
        return result

    async def aextract(
        self,
        trace: TraceData,
        sbert_scores: dict[str, float] | None = None,
        allowed_intents: list[str] | None = None,
    ) -> IntentRepresentation:
        trace_text = self._format_trace(trace, sbert_scores)
        result: IntentRepresentation = await self.chain.ainvoke([
            SystemMessage(content=self._system_content(allowed_intents)),
            HumanMessage(content=trace_text),
        ])
        result.trace_id = trace.trace_id
        self._fill_sbert_scores(result, sbert_scores)
        return result

    @staticmethod
    def _system_content(allowed_intents: list[str] | None) -> str:
        """Base prompt, plus a taxonomy constraint when the caller supplies a
        fixed menu of intents (classify-into-taxonomy mode). Without a menu the
        model discovers intents freely (discovery mode)."""
        if not allowed_intents:
            return INTENT_EXTRACTION_PROMPT
        menu = ", ".join(allowed_intents)
        return INTENT_EXTRACTION_PROMPT + (
            "\n\n## Fixed intent taxonomy\n"
            "You MUST set `primary_intent` to exactly one of these labels, copied "
            "verbatim (do not invent new labels or rephrase):\n"
            f"{menu}\n"
            "Pick the single best-fitting label. Use `unknown` only if none apply."
        )

    def _format_trace(self, trace: TraceData, sbert_scores: dict[str, float] | None) -> str:
        parts = [f"# Trace: {trace.trace_id}"]

        if trace.session_id:
            parts.append(f"Session: {trace.session_id}")
        if trace.user_id:
            parts.append(f"User: {trace.user_id}")
        if trace.duration_seconds is not None:
            parts.append(f"Duration: {trace.duration_seconds:.1f}s")

        parts.append("\n## Conversation")
        for msg in trace.messages:
            parts.append(f"**{msg.role}:** {msg.content}")

        if trace.tool_calls:
            parts.append("\n## Tool Calls")
            for tc in trace.tool_calls:
                parts.append(f"- **{tc.tool_name}**")
                if tc.input_summary:
                    parts.append(f"  Input: {tc.input_summary}")
                if tc.output_summary:
                    parts.append(f"  Output: {tc.output_summary}")

        if trace.skills_activated:
            parts.append(f"\n## Skills Activated: {', '.join(trace.skills_activated)}")

        if sbert_scores:
            parts.append("\n## Pre-computed Relevance Hints (Sentence-BERT cosine similarity)")
            parts.append("Use as supporting evidence — your judgment takes precedence.")
            for skill, score in sbert_scores.items():
                hint = "high → likely relevant" if score > 0.6 else ("low → likely not relevant" if score < 0.35 else "medium → unclear")
                parts.append(f"- {skill}: {score:.2f} ({hint})")

        return "\n".join(parts)

    @staticmethod
    def _fill_sbert_scores(
        result: IntentRepresentation,
        sbert_scores: dict[str, float] | None,
    ) -> None:
        if not sbert_scores:
            return
        for sr in result.skills_relevance:
            if sr.sbert_score is None and sr.skill_name in sbert_scores:
                sr.sbert_score = sbert_scores[sr.skill_name]
