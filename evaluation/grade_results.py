"""
Grade the product's intent predictions against the Bitext ground-truth labels.

HOW IT WORKS
------------
1. Reads the ground-truth file (bitext_sample.json): trace_id -> true intent.
2. Reads the product's results (results.jsonl): trace_id -> predicted intent.
3. Because the product INVENTS its own intent names, we can't string-match.
   So we ask Claude, per pair, "do these two labels mean the same thing?"
   (a semantic judge). Then we report the agreement percentage.

USAGE
-----
    python evaluation/grade_results.py <path-to-results.jsonl>

The results.jsonl is written by the product after you analyze the sample.
Look in:  data/projects/<project-id>/results.jsonl
"""
from __future__ import annotations
import json, sys, pathlib
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage

from config import settings

GROUND_TRUTH = pathlib.Path(__file__).parent / "bitext_sample.json"


def load_ground_truth() -> dict[str, str]:
    data = json.loads(GROUND_TRUTH.read_text())
    return {t["trace_id"]: t["metadata"]["ground_truth_intent"] for t in data}


def load_predictions(results_path: pathlib.Path) -> dict[str, str]:
    preds = {}
    for line in results_path.read_text().strip().splitlines():
        if line.strip():
            r = json.loads(line)
            preds[r["trace_id"]] = r.get("primary_intent", "")
    return preds


def judge_batch(pairs: list[tuple[str, str, str]]) -> list[bool]:
    """pairs = [(trace_id, true_intent, predicted_intent), ...] -> [is_match, ...]"""
    model = init_chat_model(settings.model_name, api_key=settings.anthropic_api_key)
    numbered = "\n".join(
        f"{i}. TRUE: '{t}'  |  PREDICTED: '{p}'"
        for i, (_, t, p) in enumerate(pairs)
    )
    prompt = (
        "For each numbered pair, decide if the PREDICTED intent means essentially "
        "the same thing as the TRUE intent (synonyms / rephrasing count as a match). "
        "Reply with ONLY a JSON array of true/false, one per pair, in order.\n\n"
        f"{numbered}"
    )
    resp = model.invoke([HumanMessage(content=prompt)])
    text = resp.content if isinstance(resp.content, str) else str(resp.content)
    start, end = text.find("["), text.rfind("]") + 1
    return json.loads(text[start:end])


def main():
    if len(sys.argv) < 2:
        print("Usage: python evaluation/grade_results.py <path-to-results.jsonl>")
        sys.exit(1)

    results_path = pathlib.Path(sys.argv[1])
    truth = load_ground_truth()
    preds = load_predictions(results_path)

    pairs = [(tid, truth[tid], preds[tid]) for tid in truth if tid in preds]
    if not pairs:
        print("No overlapping trace_ids between ground truth and results. "
              "Did you analyze bitext_sample.json?")
        sys.exit(1)

    matches = judge_batch(pairs)

    correct = sum(1 for m in matches if m)
    total = len(pairs)
    print(f"\n{'='*60}")
    print(f"  INTENT ACCURACY: {correct}/{total} = {correct/total*100:.0f}% agreement")
    print(f"{'='*60}\n")
    print("Mismatches (AI predicted something different from the human label):")
    any_miss = False
    for (tid, t, p), m in zip(pairs, matches):
        if not m:
            any_miss = True
            print(f"  {tid}: true='{t}'  ai='{p}'")
    if not any_miss:
        print("  (none — perfect agreement)")


if __name__ == "__main__":
    main()
