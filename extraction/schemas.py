from __future__ import annotations

from pydantic import BaseModel, Field


class SkillRelevance(BaseModel):
    skill_name: str
    was_relevant: bool
    reason: str = ""
    sbert_score: float | None = Field(
        default=None,
        description="Sentence-BERT cosine similarity between conversation and skill name (0–1). "
                    "Populated after agent extraction; None if SBERT was not run.",
    )


class IntentRepresentation(BaseModel):
    """Structured output for a single trace analysis."""

    trace_id: str
    intent_summary: str = Field(description="Free-text description of what the user tried to achieve")
    primary_intent: str = Field(description="Canonical intent category")
    sub_intents: list[str] = Field(default_factory=list)
    goal_achieved: bool = Field(description="Whether the user's goal was met")
    satisfaction_score: float = Field(ge=0.0, le=1.0, description="0-1 satisfaction estimate")
    satisfaction_signals: list[str] = Field(
        default_factory=list,
        description="Observable signals that informed the satisfaction score",
    )
    skills_used: list[str] = Field(default_factory=list)
    skills_relevance: list[SkillRelevance] = Field(default_factory=list)
    complexity: str = Field(default="medium", description="low / medium / high")
    user_expertise: str = Field(default="unknown", description="beginner / intermediate / expert / unknown")
    clarifications_needed: int = Field(default=0, description="How many times the user had to clarify")


class TraceMessage(BaseModel):
    role: str
    content: str


class ToolCall(BaseModel):
    tool_name: str
    input_summary: str = ""
    output_summary: str = ""


class TraceData(BaseModel):
    """Normalized representation of a Langfuse trace for agent consumption."""

    trace_id: str
    session_id: str | None = None
    user_id: str | None = None
    messages: list[TraceMessage] = Field(default_factory=list)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    skills_activated: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    duration_seconds: float | None = None
