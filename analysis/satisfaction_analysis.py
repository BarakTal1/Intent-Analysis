from __future__ import annotations

from collections import Counter

from extraction.schemas import IntentRepresentation


class SatisfactionAnalyzer:
    def __init__(self, results: list[IntentRepresentation]) -> None:
        self.results = results

    def mean_satisfaction(self) -> float:
        if not self.results:
            return 0
        return round(sum(r.satisfaction_score for r in self.results) / len(self.results), 2)

    def goal_achievement_rate(self) -> float:
        if not self.results:
            return 0
        return round(
            sum(1 for r in self.results if r.goal_achieved) / len(self.results) * 100, 1
        )

    def fully_satisfied_rate(self) -> float:
        if not self.results:
            return 0
        return round(
            sum(1 for r in self.results if r.satisfaction_score >= 0.85)
            / len(self.results)
            * 100,
            1,
        )

    def low_satisfaction_rate(self) -> float:
        if not self.results:
            return 0
        return round(
            sum(1 for r in self.results if r.satisfaction_score < 0.4)
            / len(self.results)
            * 100,
            1,
        )

    def distribution_histogram(self, bins: int = 10) -> list[dict]:
        if not self.results:
            return []
        step = 1.0 / bins
        buckets: list[dict] = []
        for i in range(bins):
            lo = round(i * step, 2)
            hi = round((i + 1) * step, 2)
            count = sum(1 for r in self.results if lo <= r.satisfaction_score < hi)
            if i == bins - 1:
                count += sum(1 for r in self.results if r.satisfaction_score == 1.0)
            buckets.append({"range": f"{lo:.1f}-{hi:.1f}", "count": count})
        return buckets

    def by_intent(self) -> list[dict]:
        groups: dict[str, list[float]] = {}
        for r in self.results:
            groups.setdefault(r.primary_intent, []).append(r.satisfaction_score)
        return sorted(
            [
                {
                    "intent": intent,
                    "mean": round(sum(s) / len(s), 2),
                    "min": round(min(s), 2),
                    "max": round(max(s), 2),
                    "median": round(sorted(s)[len(s) // 2], 2),
                    "count": len(s),
                    "scores": sorted(s),
                }
                for intent, s in groups.items()
            ],
            key=lambda x: x["mean"],
        )

    def by_complexity(self) -> list[dict]:
        groups: dict[str, list[float]] = {}
        for r in self.results:
            groups.setdefault(r.complexity, []).append(r.satisfaction_score)
        order = {"low": 0, "medium": 1, "high": 2}
        return sorted(
            [
                {
                    "complexity": c,
                    "mean": round(sum(s) / len(s), 2),
                    "count": len(s),
                    "scores": sorted(s),
                }
                for c, s in groups.items()
            ],
            key=lambda x: order.get(x["complexity"], 99),
        )

    def by_expertise(self) -> list[dict]:
        groups: dict[str, list[float]] = {}
        for r in self.results:
            groups.setdefault(r.user_expertise, []).append(r.satisfaction_score)
        return [
            {
                "expertise": e,
                "mean": round(sum(s) / len(s), 2),
                "count": len(s),
                "scores": sorted(s),
            }
            for e, s in groups.items()
        ]

    def sentiment_signals(self) -> dict:
        positive_keywords = [
            "goal clearly met", "confirmed", "thanks", "useful", "concise",
            "positive", "success", "exactly", "perfect",
        ]
        negative_keywords = [
            "not what I meant", "try again", "repeated", "frustration",
            "abandoned", "failure", "confusion", "nevermind", "unclear",
        ]

        positive: list[dict] = []
        negative: list[dict] = []

        all_signals = []
        for r in self.results:
            for sig in r.satisfaction_signals:
                all_signals.append(sig)

        pos_counts: Counter = Counter()
        neg_counts: Counter = Counter()
        for sig in all_signals:
            sig_lower = sig.lower()
            for kw in positive_keywords:
                if kw in sig_lower:
                    pos_counts[kw] += 1
                    break
            for kw in negative_keywords:
                if kw in sig_lower:
                    neg_counts[kw] += 1
                    break

        positive = [{"signal": k, "count": v} for k, v in pos_counts.most_common()]
        negative = [{"signal": k, "count": v} for k, v in neg_counts.most_common()]

        return {"positive": positive, "negative": negative}

    def low_satisfaction_traces(self, threshold: float = 0.4) -> list[dict]:
        low = [r for r in self.results if r.satisfaction_score < threshold]
        return sorted(
            [
                {
                    "trace_id": r.trace_id,
                    "intent": r.primary_intent,
                    "score": r.satisfaction_score,
                    "signals": r.satisfaction_signals,
                    "goal_achieved": r.goal_achieved,
                }
                for r in low
            ],
            key=lambda x: x["score"],
        )

    def avg_clarifications(self) -> float:
        if not self.results:
            return 0
        return round(
            sum(r.clarifications_needed for r in self.results) / len(self.results), 1
        )

    def overview(self) -> dict:
        return {
            "total_traces": len(self.results),
            "mean_satisfaction": self.mean_satisfaction(),
            "fully_satisfied_rate": self.fully_satisfied_rate(),
            "low_satisfaction_rate": self.low_satisfaction_rate(),
            "goal_achievement_rate": self.goal_achievement_rate(),
            "avg_clarifications": self.avg_clarifications(),
            "distribution": self.distribution_histogram(),
            "by_intent": self.by_intent(),
            "by_complexity": self.by_complexity(),
            "by_expertise": self.by_expertise(),
            "sentiment_signals": self.sentiment_signals(),
            "low_satisfaction_traces": self.low_satisfaction_traces(),
        }
