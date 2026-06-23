from __future__ import annotations

from collections import Counter

from extraction.schemas import IntentRepresentation


class IntentAnalyzer:
    def __init__(self, results: list[IntentRepresentation]) -> None:
        self.results = results

    def distribution(self) -> list[dict]:
        counts = Counter(r.primary_intent for r in self.results)
        total = len(self.results)
        return sorted(
            [
                {
                    "intent": intent,
                    "count": count,
                    "percentage": round(count / total * 100, 1) if total else 0,
                }
                for intent, count in counts.items()
            ],
            key=lambda x: x["count"],
            reverse=True,
        )

    def top_intents(self, n: int = 8) -> list[dict]:
        return self.distribution()[:n]

    def unknown_rate(self) -> float:
        if not self.results:
            return 0
        unknown = sum(1 for r in self.results if r.primary_intent == "unknown")
        return round(unknown / len(self.results) * 100, 1)

    def sub_intent_hierarchy(self) -> dict[str, list[dict]]:
        hierarchy: dict[str, Counter] = {}
        for r in self.results:
            if r.primary_intent not in hierarchy:
                hierarchy[r.primary_intent] = Counter()
            for sub in r.sub_intents:
                hierarchy[r.primary_intent][sub] += 1

        return {
            intent: [
                {"sub_intent": sub, "count": count}
                for sub, count in counter.most_common()
            ]
            for intent, counter in sorted(
                hierarchy.items(),
                key=lambda x: sum(x[1].values()),
                reverse=True,
            )
        }

    def categories_found(self) -> int:
        return len(set(r.primary_intent for r in self.results))

    def satisfaction_by_intent(self) -> list[dict]:
        intent_scores: dict[str, list[float]] = {}
        for r in self.results:
            intent_scores.setdefault(r.primary_intent, []).append(r.satisfaction_score)

        return sorted(
            [
                {
                    "intent": intent,
                    "mean_satisfaction": round(sum(scores) / len(scores), 2),
                    "count": len(scores),
                    "scores": sorted(scores),
                }
                for intent, scores in intent_scores.items()
            ],
            key=lambda x: x["mean_satisfaction"],
        )

    def overview(self) -> dict:
        if not self.results:
            return {
                "total_traces": 0,
                "top_intent": None,
                "categories_found": 0,
                "unknown_rate": 0,
            }

        dist = self.distribution()
        return {
            "total_traces": len(self.results),
            "top_intent": dist[0]["intent"] if dist else None,
            "top_intent_pct": dist[0]["percentage"] if dist else 0,
            "categories_found": self.categories_found(),
            "unknown_rate": self.unknown_rate(),
            "distribution": dist,
            "top_8": self.top_intents(8),
            "hierarchy": self.sub_intent_hierarchy(),
            "satisfaction_density": self.satisfaction_by_intent(),
        }
