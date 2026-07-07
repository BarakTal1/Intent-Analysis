"""
Default LLM-backed callables for the two-phase intent engine:

- make_inducer: designs a clean finite taxonomy from a sample  (1 call per build)
- make_decider: picks among a shortlist for a borderline trace, or 'none'
                (1 call, only on the ~20% of traces the classifier can't place cheaply)

Both are thin adapters over the project's configured chat model, injected into
TaxonomyBuilder / IntentClassifier so those modules stay testable offline.
"""
from __future__ import annotations

import json

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage

from config import settings


def _model():
    return init_chat_model(settings.model_name, api_key=settings.anthropic_api_key)


def _extract_json(text: str, open_ch: str, close_ch: str):
    start, end = text.find(open_ch), text.rfind(close_ch) + 1
    return json.loads(text[start:end])


def make_inducer(target_min: int = 12, target_max: int = 30):
    """Induce a clean, finite intent taxonomy from a sample of observed intents.

    LLM-driven (not flat clustering): the model sees the range of intents+summaries
    and designs well-separated categories with definitions. Far more coherent and
    stable than average-linkage clustering of short intent names.
    """
    model = _model()

    def inducer(samples: list[str]) -> list[dict]:
        joined = "\n".join(f"- {s}" for s in samples)
        prompt = (
            "Below are observed user intents (each: an intent label and what the user "
            "wanted) from an AI agent's conversations. Design a SINGLE consistent "
            f"taxonomy of roughly {target_min}-{target_max} intents that covers them.\n\n"
            "Rules:\n"
            "- Each intent: specific and snake_case (cancel_order, check_invoice, "
            "recover_password) — never vague buckets (general_assistance, account_management).\n"
            "- Categories must be MUTUALLY EXCLUSIVE: do not create overlapping intents "
            "like 'check_invoice' and 'check_invoice_or_delivery_info'. Keep genuinely "
            "different goals separate (e.g. cancel_order vs close_account are different).\n"
            "- Merge only true paraphrases; split when the underlying goal differs.\n"
            "- definition: one sentence stating the goal, phrased to be told apart from "
            "neighbouring intents.\n\n"
            f"Observed intents:\n{joined}\n\n"
            "Reply with ONLY a JSON array, each: "
            '{"canonical": "...", "definition": "...", "examples": ["...", "..."]}'
        )
        resp = model.invoke([HumanMessage(content=prompt)])
        text = resp.content if isinstance(resp.content, str) else str(resp.content)
        return _extract_json(text, "[", "]")

    return inducer


def make_decider():
    model = _model()

    def decider(intent_name: str, summary: str, shortlist: list[tuple[str, str]]) -> str:
        options = "\n".join(f"- {c}: {d}" for c, d in shortlist)
        prompt = (
            "Classify this user intent into exactly ONE of the candidate intents, "
            "using the definitions. If none genuinely fit, answer 'none' — do not "
            "force a poor match.\n\n"
            f"Intent to classify: {intent_name}\n"
            f"What the user wanted: {summary}\n\n"
            f"Candidates:\n{options}\n\n"
            "Reply with ONLY the chosen snake_case label (or 'none'). No other text."
        )
        resp = model.invoke([HumanMessage(content=prompt)])
        text = resp.content if isinstance(resp.content, str) else str(resp.content)
        return text.strip().strip(".`'\" ").split()[0] if text.strip() else "none"

    return decider
