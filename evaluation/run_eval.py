"""
End-to-end intent evaluation: extract with the product, grade against Bitext labels.

    # discovery mode (free-form intents, graded by an LLM judge):
    python evaluation/run_eval.py --limit 20

    # taxonomy mode (classify into the dataset's own labels, exact-match graded — free):
    python evaluation/run_eval.py --limit 20 --taxonomy

--limit caps how many traces are extracted (each costs ~1c on Sonnet), so you
control the spend. Reads evaluation/bitext_sample.json (run convert_bitext.py first).
"""
from __future__ import annotations
import argparse, asyncio, json, pathlib

from extraction.intent_agent import IntentExtractionAgent
from extraction.schemas import TraceData

SAMPLE = pathlib.Path(__file__).parent / "bitext_sample.json"


def load_sample(limit: int):
    data = json.loads(SAMPLE.read_text())[:limit]
    traces, truth = [], {}
    for d in data:
        traces.append(TraceData(trace_id=d["trace_id"], messages=d["messages"]))
        truth[d["trace_id"]] = d["metadata"]["ground_truth_intent"]
    all_labels = sorted({v["metadata"]["ground_truth_intent"]
                         for v in json.loads(SAMPLE.read_text())})
    return traces, truth, all_labels


async def extract_all(traces, allowed_intents, concurrency=5):
    agent = IntentExtractionAgent()
    sem = asyncio.Semaphore(concurrency)

    async def one(t):
        async with sem:
            r = await agent.aextract(t, allowed_intents=allowed_intents)
            return t.trace_id, r.primary_intent

    return dict(await asyncio.gather(*[one(t) for t in traces]))


def grade_exact(preds, truth):
    correct = sum(1 for tid, p in preds.items() if p == truth[tid])
    return correct, len(preds)


def grade_semantic(preds, truth):
    """LLM judge for free-form mode (synonyms count as matches)."""
    from evaluation.grade_results import judge_batch
    pairs = [(tid, truth[tid], preds[tid]) for tid in preds]
    matches = judge_batch(pairs)
    return sum(1 for m in matches if m), len(pairs), pairs, matches


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--taxonomy", action="store_true")
    args = ap.parse_args()

    traces, truth, all_labels = load_sample(args.limit)
    allowed = all_labels if args.taxonomy else None
    mode = "TAXONOMY (classify into menu)" if args.taxonomy else "DISCOVERY (free-form)"
    print(f"Mode: {mode}   |   traces: {len(traces)}   |   est. cost ~${len(traces)*0.011:.2f}\n")

    preds = asyncio.run(extract_all(traces, allowed))

    if args.taxonomy:
        correct, total = grade_exact(preds, truth)
        pairs = [(tid, truth[tid], preds[tid]) for tid in preds]
        matches = [p == truth[tid] for tid, _, p in [(t, truth[t], preds[t]) for t in preds]]
    else:
        correct, total, pairs, matches = grade_semantic(preds, truth)

    print(f"{'='*60}")
    print(f"  INTENT ACCURACY: {correct}/{total} = {correct/total*100:.0f}% agreement")
    print(f"{'='*60}\n")
    print("Mismatches:")
    miss = False
    for (tid, t, p), m in zip(pairs, matches):
        if not m:
            miss = True
            print(f"  {tid}: true='{t}'  ai='{p}'")
    if not miss:
        print("  (none — perfect agreement)")


if __name__ == "__main__":
    main()
