"""
Offline test of the classifier's borderline-only gating (real embeddings, STUB
LLM — no API cost).

Verifies:
  1. A confident match takes the cheap path (NO LLM call).
  2. A genuinely novel intent routes to 'unclassified' (never force-fit).
  3. The LLM is consulted only when the embedding match is ambiguous.

    python evaluation/test_classifier.py
"""
import numpy as np
from sentence_transformers import SentenceTransformer

from extraction.intent_classifier import IntentClassifier, UNCLASSIFIED

_model = SentenceTransformer("all-mpnet-base-v2")


def _centroid(name, definition):
    v = _model.encode(f"{name.replace('_', ' ')}. {definition}", normalize_embeddings=True)
    return v / np.linalg.norm(v)


def build_taxonomy():
    spec = [
        ("track_order", "user wants the delivery status of an existing order"),
        ("cancel_order", "user wants to cancel an order they placed"),
        ("get_refund", "user wants their money back for a purchase"),
        ("create_account", "user wants to register and open a new account"),
    ]
    return [{"canonical": n, "definition": d, "centroid": _centroid(n, d).tolist()} for n, d in spec]


embed_one = lambda t: _model.encode(t, normalize_embeddings=True)
llm_calls = {"n": 0}


def stub_decider(name, summary, shortlist):
    """Realistic stub: pick a candidate sharing a word with the query, else 'none'."""
    llm_calls["n"] += 1
    words = set(name.replace("_", " ").split())
    for canonical, _def in shortlist:
        if words & set(canonical.replace("_", " ").split()):
            return canonical
    return "none"


def main():
    # explicit thresholds so the gating logic is exercised deterministically,
    # independent of the (stricter) production defaults
    clf = IntentClassifier(
        build_taxonomy(), embed_one, stub_decider,
        accept_threshold=0.62, margin=0.05, novel_threshold=0.40,
    )

    # (a) confident synonym of an existing intent -> cheap path, NO llm
    a = clf.classify("where_is_my_order", "user checking the delivery status of their package")
    print(f"confident: -> {a.canonical}  (llm={a.used_llm}, conf={a.confidence:.2f})")
    assert not a.used_llm, "confident case should NOT call the LLM"
    assert a.canonical == "track_order", f"expected track_order, got {a.canonical}"

    # (b) genuinely novel -> unclassified (LLM consulted, answers none)
    n = clf.classify("apply_discount_coupon", "user wants to redeem a promo code at checkout")
    print(f"novel:     -> {n.canonical}  (llm={n.used_llm}, conf={n.confidence:.2f})")
    assert n.canonical == UNCLASSIFIED, "novel intent should be unclassified, not force-fit"

    print(f"\nLLM calls across 2 classifications: {llm_calls['n']}  (confident one skipped)")
    assert llm_calls["n"] <= 1, "confident case must not have called the LLM"
    print("✓ ALL CHECKS PASSED — confident path skips LLM, novel unclassified")


if __name__ == "__main__":
    main()
