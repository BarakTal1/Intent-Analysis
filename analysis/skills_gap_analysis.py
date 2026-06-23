from __future__ import annotations

from collections import Counter

from extraction.schemas import IntentRepresentation


class SkillsGapAnalyzer:
    """Identifies intents that are frequent but lack matching skills — candidates for new skill creation."""

    def __init__(self, results: list[IntentRepresentation]) -> None:
        self.results = results

    def _existing_skills(self) -> set[str]:
        skills: set[str] = set()
        for r in self.results:
            for s in r.skills_used:
                skills.add(s)
            for sr in r.skills_relevance:
                skills.add(sr.skill_name)
        return skills

    def _intent_stats(self) -> dict[str, dict]:
        stats: dict[str, dict] = {}
        for r in self.results:
            intent = r.primary_intent
            if intent not in stats:
                stats[intent] = {
                    "count": 0,
                    "sat_scores": [],
                    "goal_achieved_count": 0,
                    "skills_used_counts": Counter(),
                    "total_skills_used": 0,
                    "relevant_skill_hits": 0,
                    "total_skill_evals": 0,
                    "sub_intents": Counter(),
                    "clarifications": [],
                    "complexity_counts": Counter(),
                    "sample_summaries": [],
                }
            s = stats[intent]
            s["count"] += 1
            s["sat_scores"].append(r.satisfaction_score)
            if r.goal_achieved:
                s["goal_achieved_count"] += 1
            for sk in r.skills_used:
                s["skills_used_counts"][sk] += 1
            s["total_skills_used"] += len(r.skills_used)
            for sr in r.skills_relevance:
                s["total_skill_evals"] += 1
                if sr.was_relevant:
                    s["relevant_skill_hits"] += 1
            for sub in r.sub_intents:
                s["sub_intents"][sub] += 1
            s["clarifications"].append(r.clarifications_needed)
            s["complexity_counts"][r.complexity] += 1
            if len(s["sample_summaries"]) < 3:
                s["sample_summaries"].append(r.intent_summary)
        return stats

    def skill_coverage_by_intent(self) -> list[dict]:
        stats = self._intent_stats()
        items = []
        for intent, s in stats.items():
            count = s["count"]
            mean_sat = round(sum(s["sat_scores"]) / count, 2)
            goal_rate = round(s["goal_achieved_count"] / count * 100, 1)
            avg_skills = round(s["total_skills_used"] / count, 1)
            relevance_rate = (
                round(s["relevant_skill_hits"] / s["total_skill_evals"] * 100, 1)
                if s["total_skill_evals"] > 0
                else None
            )
            top_skills = [
                {"skill": sk, "count": c}
                for sk, c in s["skills_used_counts"].most_common(5)
            ]
            items.append({
                "intent": intent,
                "count": count,
                "mean_satisfaction": mean_sat,
                "goal_achievement_rate": goal_rate,
                "avg_skills_per_trace": avg_skills,
                "skill_relevance_rate": relevance_rate,
                "top_skills_used": top_skills,
                "has_skill_coverage": avg_skills > 0,
            })
        return sorted(items, key=lambda x: x["count"], reverse=True)

    def gap_candidates(self) -> list[dict]:
        """Intents that are frequent AND have signals suggesting a new skill would help:
        - no/few skills activated, OR
        - low skill relevance (existing skills aren't matching well), OR
        - low satisfaction / low goal achievement despite volume
        """
        coverage = self.skill_coverage_by_intent()
        stats = self._intent_stats()
        total = len(self.results)
        if total == 0:
            return []

        global_mean_sat = sum(r.satisfaction_score for r in self.results) / total
        global_goal_rate = sum(1 for r in self.results if r.goal_achieved) / total * 100

        candidates = []
        for item in coverage:
            intent = item["intent"]
            if intent == "unknown":
                continue

            s = stats[intent]
            gap_score = 0.0
            reasons = []

            frequency_pct = item["count"] / total * 100
            if frequency_pct >= 5:
                gap_score += min(frequency_pct / 10, 3.0)

            if item["avg_skills_per_trace"] == 0:
                gap_score += 3.0
                reasons.append("No skills activated for this intent")
            elif item["avg_skills_per_trace"] < 1.0:
                gap_score += 1.5
                reasons.append(f"Low skill activation ({item['avg_skills_per_trace']} avg per trace)")

            if item["skill_relevance_rate"] is not None and item["skill_relevance_rate"] < 40:
                gap_score += 2.0
                reasons.append(f"Low skill relevance ({item['skill_relevance_rate']}% — existing skills aren't matching)")

            if item["mean_satisfaction"] < global_mean_sat - 0.1:
                gap_score += 1.5
                reasons.append(f"Below-average satisfaction ({item['mean_satisfaction']} vs {round(global_mean_sat, 2)} global)")

            if item["goal_achievement_rate"] < global_goal_rate - 10:
                gap_score += 1.5
                reasons.append(f"Low goal achievement ({item['goal_achievement_rate']}% vs {round(global_goal_rate, 1)}% global)")

            avg_clarif = sum(s["clarifications"]) / len(s["clarifications"])
            if avg_clarif > 1.0:
                gap_score += 1.0
                reasons.append(f"High clarification rate ({round(avg_clarif, 1)} avg)")

            if item["count"] < 2:
                gap_score *= 0.3

            if gap_score < 1.5:
                continue

            top_sub_intents = [
                {"sub_intent": sub, "count": c}
                for sub, c in s["sub_intents"].most_common(5)
            ]
            dominant_complexity = s["complexity_counts"].most_common(1)[0][0] if s["complexity_counts"] else "unknown"

            candidates.append({
                "intent": intent,
                "gap_score": round(gap_score, 1),
                "count": item["count"],
                "frequency_pct": round(frequency_pct, 1),
                "mean_satisfaction": item["mean_satisfaction"],
                "goal_achievement_rate": item["goal_achievement_rate"],
                "avg_skills_per_trace": item["avg_skills_per_trace"],
                "skill_relevance_rate": item["skill_relevance_rate"],
                "reasons": reasons,
                "sub_intents": top_sub_intents,
                "dominant_complexity": dominant_complexity,
                "sample_summaries": s["sample_summaries"],
                "suggested_skill_name": self._suggest_skill_name(intent, top_sub_intents),
            })

        return sorted(candidates, key=lambda x: x["gap_score"], reverse=True)

    @staticmethod
    def _suggest_skill_name(intent: str, sub_intents: list[dict]) -> str:
        base = intent.replace("_", " ").title()
        if sub_intents:
            top_sub = sub_intents[0]["sub_intent"].replace("_", " ")
            return f"{base} ({top_sub})"
        return f"{base} Helper"

    def intent_skill_matrix(self) -> list[dict]:
        """Shows which skills are used for each intent — helps spot where existing skills
        could be extended vs where a new skill is needed."""
        stats = self._intent_stats()
        all_skills = self._existing_skills()

        matrix = []
        for intent, s in sorted(stats.items(), key=lambda x: x[1]["count"], reverse=True):
            skill_row = {}
            for sk in all_skills:
                skill_row[sk] = s["skills_used_counts"].get(sk, 0)
            matrix.append({
                "intent": intent,
                "count": s["count"],
                "skills": skill_row,
            })
        return matrix

    def overview(self) -> dict:
        candidates = self.gap_candidates()
        coverage = self.skill_coverage_by_intent()
        existing_skills = self._existing_skills()

        uncovered = [c for c in coverage if not c["has_skill_coverage"]]
        low_relevance = [c for c in coverage if c["skill_relevance_rate"] is not None and c["skill_relevance_rate"] < 40]

        return {
            "total_intents": len(coverage),
            "total_existing_skills": len(existing_skills),
            "uncovered_intent_count": len(uncovered),
            "low_relevance_intent_count": len(low_relevance),
            "gap_candidates": candidates,
            "skill_coverage": coverage,
            "intent_skill_matrix": self.intent_skill_matrix(),
        }
