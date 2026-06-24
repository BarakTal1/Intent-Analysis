#!/usr/bin/env python3
"""Interactive calibration tool — compare Claude satisfaction scores to human scores.

Usage:
    python tools/calibrate.py --results data/projects/<id>/results.jsonl --sample 25

Prints: correlation, MAE, and a sorted list of the biggest disagreements.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
from pathlib import Path


def load_results(path: Path) -> list[dict]:
    records = []
    for i, line in enumerate(path.read_text().splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            print(f"Warning: skipping malformed JSON on line {i}")
    return records


def human_score(record: dict) -> float:
    trace_id = record.get("trace_id", "unknown")
    primary_intent = record.get("primary_intent", "unknown")
    goal_achieved = record.get("goal_achieved", "unknown")
    intent_summary = record.get("intent_summary", "(no summary)")
    satisfaction_score = record.get("satisfaction_score")

    if satisfaction_score is None:
        print(f"\nSkipping trace {trace_id}: missing satisfaction_score")
        return -1.0

    print("\n" + "=" * 60)
    print(f"Trace: {trace_id}")
    print(f"Intent: {primary_intent}")
    print(f"Goal achieved: {goal_achieved}")
    print(f"Summary: {intent_summary}")
    signals = record.get("satisfaction_signals") or []
    if signals:
        print("Signals:")
        for s in signals:
            print(f"  - {s}")
    print(f"\nClaude score: {satisfaction_score:.2f}")
    while True:
        raw = input("Your score (0.0 - 1.0, or 's' to skip): ").strip()
        if raw == "s":
            return -1.0
        try:
            score = float(raw)
            if 0.0 <= score <= 1.0:
                return score
        except ValueError:
            pass
        print("Enter a number between 0.0 and 1.0")


def pearson_correlation(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return float("nan")
    mean_x = statistics.mean(xs)
    mean_y = statistics.mean(ys)
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den_x = sum((x - mean_x) ** 2 for x in xs) ** 0.5
    den_y = sum((y - mean_y) ** 2 for y in ys) ** 0.5
    if den_x == 0 or den_y == 0:
        return float("nan")
    return num / (den_x * den_y)


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibrate Claude satisfaction scores")
    parser.add_argument("--results", required=True, help="Path to results.jsonl")
    parser.add_argument("--sample", type=int, default=25, help="Number of traces to sample")
    args = parser.parse_args()

    path = Path(args.results)
    if not path.exists():
        print(f"File not found: {path}")
        return

    all_records = load_results(path)
    if not all_records:
        print("No results found.")
        return

    sample = random.sample(all_records, min(args.sample, len(all_records)))
    print(f"\nCalibrating on {len(sample)} traces. Type 's' to skip a trace.\n")

    pairs: list[tuple[float, float, str]] = []
    for record in sample:
        h = human_score(record)
        if h >= 0:
            pairs.append((record.get("satisfaction_score", 0.0), h, record.get("trace_id", "unknown")))

    if len(pairs) < 3:
        print("\nNot enough scores collected (need at least 3). Exiting.")
        return

    claude_scores = [p[0] for p in pairs]
    human_scores_list = [p[1] for p in pairs]
    corr = pearson_correlation(claude_scores, human_scores_list)
    mae = statistics.mean(abs(c - h) for c, h, _ in pairs)
    disagreements = sorted(pairs, key=lambda p: abs(p[0] - p[1]), reverse=True)

    print("\n" + "=" * 60)
    print("CALIBRATION REPORT")
    print("=" * 60)
    print(f"Traces scored:       {len(pairs)}")
    print(f"Pearson correlation: {corr:.3f}  (>0.7 = solid, <0.4 = noisy)")
    print(f"Mean absolute error: {mae:.3f}  (<0.15 = solid, >0.25 = noisy)")
    print("\nTop disagreements (Claude → Human):")
    for claude, human, tid in disagreements[:5]:
        print(f"  {tid[:16]:<16}  Claude {claude:.2f}  →  Human {human:.2f}  (diff {abs(claude-human):.2f})")

    if math.isnan(corr):
        print("\n⚠️  Correlation undefined — all scores may be identical. Score more traces with varied quality.")
    else:
        if corr >= 0.7 and mae <= 0.15:
            print("\n✅ Signal looks solid. Gap scores are trustworthy.")
        elif corr >= 0.5 or mae <= 0.25:
            print("\n⚠️  Signal is moderate. Gap scores directionally useful but treat with caution.")
        else:
            print("\n❌ Signal is noisy. Consider refining the satisfaction prompt before building on it.")


if __name__ == "__main__":
    main()
