"""
End-to-end test of the two-phase engine on labeled data.

Pipeline: extract (new prompt) -> DISCOVER taxonomy by clustering -> CLASSIFY each
trace (borderline-only LLM) -> grade the canonical intent against Bitext labels.

Reports accuracy AND how many traces needed an LLM in the classify step (the
efficiency claim: most take the cheap embedding-only path).

    python evaluation/run_eval_engine.py --limit 30
"""
from __future__ import annotations
import argparse, asyncio, json, pathlib

from sentence_transformers import SentenceTransformer

from extraction.intent_agent import IntentExtractionAgent
from extraction.schemas import TraceData
from analysis.taxonomy_builder import TaxonomyBuilder
from extraction.intent_classifier import IntentClassifier, UNCLASSIFIED
from extraction.intent_llm import make_inducer, make_decider
from evaluation.grade_results import judge_batch

SAMPLE = pathlib.Path(__file__).parent / "bitext_sample.json"


async def extract(traces, concurrency=5):
    agent = IntentExtractionAgent()
    sem = asyncio.Semaphore(concurrency)

    async def one(t):
        async with sem:
            r = await agent.aextract(t)
            return r

    return await asyncio.gather(*[one(t) for t in traces])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=30)
    args = ap.parse_args()

    data = json.loads(SAMPLE.read_text())[: args.limit]
    traces = [TraceData(trace_id=d["trace_id"], messages=d["messages"]) for d in data]
    truth = {d["trace_id"]: d["metadata"]["ground_truth_intent"] for d in data}
    print(f"traces: {len(traces)}   est. cost ~${len(traces)*0.011:.2f} (+ small classify/judge)\n")

    # 1) extract
    results = asyncio.run(extract(traces))

    # 2) discover taxonomy from the free-form intents
    model = SentenceTransformer("all-mpnet-base-v2")
    embed_many = lambda ts: model.encode(ts, normalize_embeddings=True)
    embed_one = lambda t: model.encode(t, normalize_embeddings=True)
    pairs = [(r.raw_intent or r.primary_intent, r.intent_summary) for r in results]
    taxonomy = TaxonomyBuilder(embed_many, make_inducer()).build(pairs)

    # 3) classify each into the taxonomy (borderline-only LLM)
    clf = IntentClassifier(taxonomy, embed_one, make_decider())
    llm_used = 0
    for r in results:
        a = clf.classify(r.raw_intent or r.primary_intent, r.intent_summary)
        r.primary_intent = a.canonical
        llm_used += int(a.used_llm)

    # 4) grade canonical intent vs ground truth (semantic judge)
    graded = [(r.trace_id, truth[r.trace_id], r.primary_intent) for r in results]
    matches = judge_batch(graded)
    correct = sum(1 for m in matches if m)
    unclassified = sum(1 for r in results if r.primary_intent == UNCLASSIFIED)

    print(f"{'='*60}")
    print(f"  discovered taxonomy: {len(taxonomy)} intents")
    print(f"  ACCURACY: {correct}/{len(results)} = {correct/len(results)*100:.0f}%")
    print(f"  LLM calls in classify step: {llm_used}/{len(results)} "
          f"({llm_used/len(results)*100:.0f}% — rest took the cheap path)")
    print(f"  unclassified: {unclassified}")
    print(f"{'='*60}\n")
    print("discovered intents:", [t["canonical"] for t in taxonomy])
    print("\nmismatches:")
    for (tid, t, p), m in zip(graded, matches):
        if not m:
            print(f"  {tid}: true='{t}'  ai='{p}'")


if __name__ == "__main__":
    main()
