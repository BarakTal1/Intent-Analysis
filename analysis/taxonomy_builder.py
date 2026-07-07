"""
Phase 1 of autonomous intent classification: DISCOVER a finite taxonomy.

Approach: LLM-driven taxonomy induction (not flat clustering). We collect a
representative, deduplicated sample of the free-form intents the extractor
produced (name + summary), and ask the LLM to design ONE coherent taxonomy of
mutually-exclusive intents, each with a definition. This is far more stable and
better-separated than average-linkage clustering of short intent names — which
tends to fuse distinct intents into vague blobs and shifts run to run.

Each taxonomy intent gets a centroid embedding (of its name+definition) so the
classifier can shortlist candidates cheaply before spending an LLM call.

Output: a finite list of intents, persisted per project for stability.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Callable

import numpy as np

# An inducer takes representative "(intent) summary" samples and returns a
# taxonomy: [{canonical, definition, examples}]. Injected for offline testing;
# the default LLM implementation lives in intent_llm.py.
Inducer = Callable[[list[str]], list[dict]]


class TaxonomyBuilder:
    def __init__(
        self,
        embed_fn: Callable[[list[str]], np.ndarray],
        inducer: Inducer,
        max_samples: int = 80,
    ) -> None:
        self.embed_fn = embed_fn
        self.inducer = inducer
        self.max_samples = max_samples

    def _representative_samples(self, items: list[tuple[str, str]]) -> list[str]:
        """Deduplicate by intent name, keep the most frequent, cap the count —
        so the induction prompt stays small even with millions of traces."""
        by_name: dict[str, str] = {}
        freq: Counter = Counter()
        for name, summary in items:
            if not name or name == "unknown":
                continue
            freq[name] += 1
            by_name.setdefault(name, summary or "")
        top = [name for name, _ in freq.most_common(self.max_samples)]
        return [f"({name}) {by_name[name]}".strip() for name in top]

    def build(self, items: list[tuple[str, str]]) -> list[dict]:
        """items = [(intent_name, summary), ...] -> taxonomy list of dicts."""
        samples = self._representative_samples(items)
        if not samples:
            return []

        induced = self.inducer(samples)
        if not induced:
            return []

        # centroid = embedding of "canonical. definition" (used for cheap shortlisting)
        texts = [
            f"{d['canonical'].replace('_', ' ')}. {d.get('definition', '')}".strip()
            for d in induced
        ]
        embeddings = np.asarray(self.embed_fn(texts))

        taxonomy = []
        for d, emb in zip(induced, embeddings):
            norm = np.linalg.norm(emb)
            taxonomy.append({
                "canonical": d["canonical"],
                "definition": d.get("definition", ""),
                "examples": d.get("examples", []),
                "centroid": (emb / norm).tolist() if norm else emb.tolist(),
            })
        return taxonomy

    # ---------------------------------------------------------------- persistence
    @staticmethod
    def save(taxonomy: list[dict], path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"intents": taxonomy}, indent=2))

    @staticmethod
    def load(path: str | Path) -> list[dict]:
        path = Path(path)
        if not path.exists():
            return []
        return json.loads(path.read_text()).get("intents", [])
