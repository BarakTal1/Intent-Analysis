from __future__ import annotations

from functools import cached_property

from sentence_transformers import SentenceTransformer, util

from .schemas import TraceData


_SKILL_PATTERNS = ("_skill", "_tool", "_agent", "_scanner", "_analyzer")

_SBERT_MODEL = "all-mpnet-base-v2"


class SkillsDetector:
    """Detects skill activations from a trace and scores their relevance via Sentence-BERT.

    SBERT scores are semantic similarity between the conversation context and each skill name.
    They are passed to the IntentExtractionAgent as hints — the agent makes the final judgment.

    Score interpretation:
        > 0.60  → high similarity, likely relevant
        0.35–0.60 → ambiguous, agent should decide
        < 0.35  → low similarity, likely not relevant
    """

    def __init__(self, model_name: str = _SBERT_MODEL) -> None:
        self._model_name = model_name

    @cached_property
    def _model(self) -> SentenceTransformer:
        return SentenceTransformer(self._model_name)

    def detect_skills(self, trace: TraceData) -> list[str]:
        """Return skill names found in the trace via tool call names and skills_activated."""
        seen: set[str] = set()
        skills: list[str] = []

        for name in trace.skills_activated:
            if name not in seen:
                seen.add(name)
                skills.append(name)

        for tc in trace.tool_calls:
            name = tc.tool_name
            if name not in seen and self._looks_like_skill(name):
                seen.add(name)
                skills.append(name)

        return skills

    def score_relevance(
        self,
        trace: TraceData,
        skills: list[str] | None = None,
    ) -> dict[str, float]:
        """Compute SBERT cosine similarity between conversation context and each skill name.

        Returns a dict mapping skill_name → similarity score in [0, 1].
        """
        if skills is None:
            skills = self.detect_skills(trace)
        if not skills:
            return {}

        conversation_text = self._conversation_text(trace)
        if not conversation_text.strip():
            return {s: 0.0 for s in skills}

        conv_emb = self._model.encode(conversation_text, normalize_embeddings=True)
        skill_embs = self._model.encode(
            [self._skill_description(s) for s in skills],
            normalize_embeddings=True,
        )

        scores = util.cos_sim(conv_emb, skill_embs)[0].tolist()
        return {skill: round(float(score), 4) for skill, score in zip(skills, scores)}

    @staticmethod
    def _looks_like_skill(name: str) -> bool:
        name_lower = name.lower()
        return any(name_lower.endswith(pat) for pat in _SKILL_PATTERNS)

    @staticmethod
    def _conversation_text(trace: TraceData) -> str:
        return " ".join(
            msg.content for msg in trace.messages if msg.role == "user"
        )

    @staticmethod
    def _skill_description(skill_name: str) -> str:
        readable = skill_name.replace("_", " ").replace("-", " ").strip()
        return f"A tool for {readable}"
