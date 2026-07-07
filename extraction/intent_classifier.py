"""
Phase 2 of autonomous intent classification: ASSIGN each trace to the taxonomy.

Efficiency is the whole point — this runs continuously over lots of traces:

  1. Embed the trace's free-form intent (name + summary), compare to the
     taxonomy centroids (cheap, local, no API).
  2. CONFIDENT case (top match is high AND clearly ahead of the runner-up):
     accept it — NO LLM call. This is the ~80% majority.
  3. BORDERLINE case (top match weak, or top-2 too close to call): ONE small LLM
     call decides among a short list of candidates — with their definitions — and
     may answer "none".
  4. NOVEL case (nothing is even close): route to 'unclassified' — never force-fit,
     so wrong assignments don't pollute the analytics.

So we pay for an LLM only on the ~20% of traces that are genuinely ambiguous.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

# A decider gets (intent_name, summary, [(canonical, definition), ...]) and
# returns the chosen canonical or "none". Injected for offline testing; the
# default LLM implementation lives in intent_llm.py.
Decider = Callable[[str, str, list[tuple[str, str]]], str]

UNCLASSIFIED = "unclassified"


@dataclass
class Assignment:
    canonical: str
    confidence: float
    used_llm: bool


def _text(name: str, summary: str = "") -> str:
    name = name.replace("_", " ").replace("-", " ").strip().lower()
    summary = (summary or "").strip()
    return f"{name}. {summary}" if summary else name


class IntentClassifier:
    def __init__(
        self,
        taxonomy: list[dict],
        embed_fn: Callable[[str], np.ndarray],
        decider: Decider,
        accept_threshold: float = 0.82,   # top1 >= this AND margin ok -> accept, no LLM
        margin: float = 0.12,             # top1 must beat top2 by this to be "confident"
        novel_threshold: float = 0.40,    # top1 below this -> likely novel -> unclassified
        shortlist_k: int = 5,
    ) -> None:
        self.taxonomy = taxonomy
        self.embed_fn = embed_fn
        self.decider = decider
        self.accept_threshold = accept_threshold
        self.margin = margin
        self.novel_threshold = novel_threshold
        self.shortlist_k = shortlist_k
        self._centroids = (
            np.asarray([t["centroid"] for t in taxonomy]) if taxonomy else np.zeros((0, 0))
        )

    def classify(self, intent_name: str, summary: str = "") -> Assignment:
        if intent_name == "unknown" or not self.taxonomy:
            return Assignment(intent_name or UNCLASSIFIED, 0.0, used_llm=False)

        emb = np.asarray(self.embed_fn(_text(intent_name, summary)))
        sims = self._centroids @ emb
        order = np.argsort(sims)[::-1]
        top1 = float(sims[order[0]])
        top2 = float(sims[order[1]]) if len(order) > 1 else -1.0

        # 2) confident -> accept, no LLM
        if top1 >= self.accept_threshold and (top1 - top2) >= self.margin:
            return Assignment(self.taxonomy[order[0]]["canonical"], top1, used_llm=False)

        # 4) nothing close -> novel, no LLM
        if top1 < self.novel_threshold:
            return Assignment(UNCLASSIFIED, top1, used_llm=False)

        # 3) borderline -> ONE LLM call among the shortlist
        shortlist = [
            (self.taxonomy[i]["canonical"], self.taxonomy[i].get("definition", ""))
            for i in order[: self.shortlist_k]
        ]
        chosen = self.decider(intent_name, summary, shortlist)
        valid = {c for c, _ in shortlist}
        if chosen in valid:
            return Assignment(chosen, top1, used_llm=True)
        return Assignment(UNCLASSIFIED, top1, used_llm=True)
