"""
Intent canonicalization — Option C ("online clustering with a persistent pool").

PROBLEM
-------
Each trace is analyzed independently, so the LLM may name the SAME underlying
intent differently across traces: "track_order", "order_tracking",
"check_order_status". Downstream analytics group intents by EXACT string, so
these fragment into separate categories — inflating the intent count and
diluting the gap score.

SOLUTION
--------
Keep a per-project POOL of canonical intents, each with a running-mean
embedding ("centroid"). For every new intent name:

  1. Embed the name locally with SBERT (no LLM call, ~free).
  2. Find the closest canonical intent in the pool (cosine similarity).
  3. If similarity >= threshold  -> reuse that canonical name (merge).
     Else                        -> add a new canonical intent to the pool.

Because this runs as a single-threaded pass AFTER extraction, there are no
race conditions, and extraction itself stays fully parallel. The pool persists
to disk, so re-running a project keeps intent names STABLE across runs — which
is what makes trends and alerts trustworthy.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

from .schemas import IntentRepresentation

_SBERT_MODEL = "all-mpnet-base-v2"

# Intents we never fold into a cluster (they are meta-labels, not real domains).
_RESERVED = {"unknown", ""}


def _readable(intent_name: str) -> str:
    """'track_order' -> 'track order' for a cleaner embedding."""
    return intent_name.replace("_", " ").replace("-", " ").strip().lower()


def _embed_text(intent_name: str, summary: str = "") -> str:
    """Text we actually embed. The bare intent NAME is too terse — antonyms like
    'create_account'/'delete_account' embed as similar while paraphrases embed as
    distant. Adding the intent SUMMARY (what the user actually wanted) gives the
    embedding real semantic signal, so merges and separations get more reliable."""
    name = _readable(intent_name)
    summary = (summary or "").strip()
    return f"{name}. {summary}" if summary else name


class IntentCanonicalizer:
    """Merges free-text intent names into a stable, per-project canonical set."""

    def __init__(
        self,
        threshold: float = 0.60,
        model: SentenceTransformer | None = None,
        model_name: str = _SBERT_MODEL,
    ) -> None:
        self.threshold = threshold
        self._model = model
        self._model_name = model_name
        # pool entries: list of dicts {canonical, count, aliases: {name: n}, centroid: [floats]}
        self.pool: list[dict] = []

    # ------------------------------------------------------------------ model
    @property
    def model(self) -> SentenceTransformer:
        if self._model is None:
            self._model = SentenceTransformer(self._model_name)
        return self._model

    def _embed(self, text: str) -> np.ndarray:
        return self.model.encode(text, normalize_embeddings=True)

    # ------------------------------------------------------------------ pool io
    def load_pool(self, path: str | Path) -> None:
        path = Path(path)
        if not path.exists():
            self.pool = []
            return
        data = json.loads(path.read_text())
        self.pool = data.get("intents", [])

    def save_pool(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "model": self._model_name,
            "threshold": self.threshold,
            "intents": self.pool,
        }
        path.write_text(json.dumps(payload, indent=2))

    # --------------------------------------------------------------- matching
    def _match(self, embedding: np.ndarray) -> tuple[int, float]:
        """Return (index_of_closest_pool_entry, similarity). (-1, 0.0) if pool empty."""
        if not self.pool:
            return -1, 0.0
        centroids = np.array([e["centroid"] for e in self.pool])
        sims = centroids @ embedding  # both L2-normalized -> dot == cosine
        best = int(np.argmax(sims))
        return best, float(sims[best])

    def _add_entry(self, canonical: str, name: str, embedding: np.ndarray) -> None:
        self.pool.append({
            "canonical": canonical,
            "count": 1,
            "aliases": {name: 1},
            "centroid": embedding.tolist(),
        })

    def _update_entry(self, idx: int, name: str, embedding: np.ndarray) -> None:
        entry = self.pool[idx]
        n = entry["count"]
        old = np.array(entry["centroid"])
        # running mean of normalized vectors, then renormalize
        new = (old * n + embedding) / (n + 1)
        norm = np.linalg.norm(new)
        entry["centroid"] = (new / norm).tolist() if norm else new.tolist()
        entry["count"] = n + 1
        entry["aliases"][name] = entry["aliases"].get(name, 0) + 1

    def canonical_for(self, intent_name: str, summary: str = "") -> str:
        """Map one raw intent name to its canonical form, updating the pool."""
        if intent_name in _RESERVED:
            return intent_name or "unknown"

        emb = self._embed(_embed_text(intent_name, summary))
        idx, sim = self._match(emb)

        if idx >= 0 and sim >= self.threshold:
            self._update_entry(idx, intent_name, emb)
            return self.pool[idx]["canonical"]

        # novel intent → first-seen name becomes the canonical label (stable)
        self._add_entry(intent_name, intent_name, emb)
        return intent_name

    # --------------------------------------------------------------- public
    def canonicalize(self, results: list[IntentRepresentation]) -> list[IntentRepresentation]:
        """Rewrite each result's primary_intent to its canonical form, in place."""
        for r in results:
            r.primary_intent = self.canonical_for(r.primary_intent, r.intent_summary)
        return results
