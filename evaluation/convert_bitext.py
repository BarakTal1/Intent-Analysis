"""
Convert the Bitext customer-support dataset into the Intent-Analysis upload format.

Why: Bitext rows come with a HUMAN-LABELLED `intent` (e.g. "cancel_order").
We turn each row into a 2-message trace the product can analyze, and we stash the
true label in metadata as `ground_truth_intent` so we can grade the AI afterwards.

Output: evaluation/bitext_sample.json  (ready to upload in the dashboard)
"""
import urllib.request, json, pathlib

DATASET = "bitext/Bitext-customer-support-llm-chatbot-training-dataset"
API = "https://datasets-server.huggingface.co/rows"

# The dataset is grouped by intent (~1000 rows each). Sample across the file so we
# get a VARIETY of intents, not 60 copies of "cancel_order".
OFFSETS = list(range(0, 27000, 900))   # ~30 spots spread across all 27 intents
PER_OFFSET = 2                          # 2 rows from each spot → ~60 traces total


def fetch(offset, length):
    url = f"{API}?dataset={DATASET}&config=default&split=train&offset={offset}&length={length}"
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)["rows"]


def main():
    traces = []
    for off in OFFSETS:
        try:
            for item in fetch(off, PER_OFFSET):
                row = item["row"]
                traces.append({
                    "trace_id": f"bitext_{item['row_idx']}",
                    "messages": [
                        {"role": "user", "content": row["instruction"]},
                        {"role": "assistant", "content": row["response"]},
                    ],
                    "metadata": {
                        "ground_truth_intent": row["intent"],
                        "ground_truth_category": row["category"],
                    },
                })
        except Exception as e:
            print(f"  (skipped offset {off}: {e})")

    out = pathlib.Path(__file__).parent / "bitext_sample.json"
    out.write_text(json.dumps(traces, indent=2))
    intents = sorted({t["metadata"]["ground_truth_intent"] for t in traces})
    print(f"✓ wrote {len(traces)} traces to {out}")
    print(f"✓ covering {len(intents)} distinct ground-truth intents:")
    print("  " + ", ".join(intents))


if __name__ == "__main__":
    main()
