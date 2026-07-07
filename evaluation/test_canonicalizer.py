"""
Verify intent canonicalization merges synonyms but keeps distinct intents apart.
Runs with LOCAL embeddings only — no API key needed.

    python evaluation/test_canonicalizer.py
"""
from extraction.intent_canonicalizer import IntentCanonicalizer
from extraction.schemas import IntentRepresentation


def _r(intent: str, summary: str) -> IntentRepresentation:
    return IntentRepresentation(
        trace_id=f"t_{intent}",
        intent_summary=summary,
        primary_intent=intent,
        goal_achieved=True,
        satisfaction_score=0.8,
    )


def main():
    # (intent_name, summary) — same underlying goal phrased differently, plus a
    # couple of genuinely different intents. Summaries mirror what the LLM produces.
    raw_pairs = [
        ("track_order", "user wants to know the delivery status of their order"),
        ("order_tracking", "user is asking where their package is"),
        ("check_order_status", "user wants an update on their order status"),
        ("cancel_order", "user wants to cancel their order"),
        ("cancel_my_order", "user requests to cancel the order they placed"),
        ("get_refund", "user wants their money back for a purchase"),
        ("create_account", "user wants to register and open a new account"),
        ("delete_account", "user wants to permanently close and remove their account"),
        ("unknown", ""),
    ]
    raw = [p[0] for p in raw_pairs]
    results = [_r(name, summary) for name, summary in raw_pairs]

    canon = IntentCanonicalizer(threshold=0.60)
    canon.canonicalize(results)

    final = [r.primary_intent for r in results]
    distinct = sorted(set(final))

    print("raw intents:   ", raw)
    print("canonicalized: ", final)
    print("distinct pool: ", distinct)
    print(f"\n{len(raw)} raw names → {len(distinct)} canonical intents\n")

    # Assertions
    order_group = {final[0], final[1], final[2]}
    assert len(order_group) == 1, f"order-tracking synonyms did not merge: {order_group}"
    cancel_group = {final[3], final[4]}
    assert len(cancel_group) == 1, f"cancel synonyms did not merge: {cancel_group}"
    assert final[0] != final[3], "distinct intents (track vs cancel) were wrongly merged"
    assert final[6] != final[7], "opposite intents (create vs delete account) were wrongly merged"
    assert "unknown" in final, "'unknown' should be preserved"
    # clusters: order, cancel, get_refund, create_account, delete_account, unknown
    assert len(distinct) == 6, f"expected 6 canonical intents, got {len(distinct)}: {distinct}"

    print("✓ ALL CHECKS PASSED — synonyms merged, distinct intents preserved")


if __name__ == "__main__":
    main()
