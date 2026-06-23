from __future__ import annotations

from collections import Counter

from extraction.schemas import IntentRepresentation


class SkillsAnalyzer:
    def __init__(self, results: list[IntentRepresentation]) -> None:
        self.results = results

    def total_skills_detected(self) -> int:
        skills: set[str] = set()
        for r in self.results:
            for s in r.skills_used:
                skills.add(s)
        return len(skills)

    def activation_frequency(self) -> list[dict]:
        counts: Counter = Counter()
        for r in self.results:
            for s in r.skills_used:
                counts[s] += 1
        return [
            {"skill": skill, "activations": count}
            for skill, count in counts.most_common()
        ]

    def relevance_rates(self) -> list[dict]:
        relevant_counts: Counter = Counter()
        total_counts: Counter = Counter()
        sbert_sums: dict[str, float] = {}
        sbert_counts: dict[str, int] = {}

        for r in self.results:
            for sr in r.skills_relevance:
                total_counts[sr.skill_name] += 1
                if sr.was_relevant:
                    relevant_counts[sr.skill_name] += 1
                if sr.sbert_score is not None:
                    sbert_sums[sr.skill_name] = sbert_sums.get(sr.skill_name, 0) + sr.sbert_score
                    sbert_counts[sr.skill_name] = sbert_counts.get(sr.skill_name, 0) + 1

        rates = []
        for skill, total in total_counts.most_common():
            rel = relevant_counts.get(skill, 0)
            avg_sbert = None
            if skill in sbert_sums and sbert_counts[skill] > 0:
                avg_sbert = round(sbert_sums[skill] / sbert_counts[skill], 3)
            rates.append({
                "skill": skill,
                "activations": total,
                "relevant": rel,
                "relevance_rate": round(rel / total * 100, 1) if total else 0,
                "avg_sbert_score": avg_sbert,
            })
        return rates

    def quadrant(self) -> list[dict]:
        rates = {r["skill"]: r for r in self.relevance_rates()}
        freq = {f["skill"]: f["activations"] for f in self.activation_frequency()}

        if not freq:
            return []

        max_freq = max(freq.values())
        items = []
        for skill, data in rates.items():
            rel_rate = data["relevance_rate"]
            act = freq.get(skill, data["activations"])

            if act > max_freq * 0.3 and rel_rate >= 50:
                quadrant_label = "CORE"
            elif act > max_freq * 0.3 and rel_rate < 50:
                quadrant_label = "NOISY"
            elif act <= max_freq * 0.3 and rel_rate >= 50:
                quadrant_label = "NICHE"
            else:
                quadrant_label = "REMOVE"

            items.append({
                "skill": skill,
                "activations": act,
                "relevance_rate": rel_rate,
                "quadrant": quadrant_label,
                "avg_sbert_score": data.get("avg_sbert_score"),
            })
        return items

    def most_used_skill(self) -> dict | None:
        freq = self.activation_frequency()
        return freq[0] if freq else None

    def noisiest_skill(self) -> dict | None:
        rates = self.relevance_rates()
        noisy = [r for r in rates if r["activations"] >= 3 and r["relevance_rate"] < 50]
        if not noisy:
            return None
        return min(noisy, key=lambda x: x["relevance_rate"])

    def skills_satisfaction_correlation(self) -> list[dict]:
        skill_sat_relevant: dict[str, list[float]] = {}
        skill_sat_irrelevant: dict[str, list[float]] = {}

        for r in self.results:
            for sr in r.skills_relevance:
                if sr.was_relevant:
                    skill_sat_relevant.setdefault(sr.skill_name, []).append(
                        r.satisfaction_score
                    )
                else:
                    skill_sat_irrelevant.setdefault(sr.skill_name, []).append(
                        r.satisfaction_score
                    )

        all_skills = set(skill_sat_relevant) | set(skill_sat_irrelevant)
        correlations = []
        for skill in sorted(all_skills):
            rel_scores = skill_sat_relevant.get(skill, [])
            irrel_scores = skill_sat_irrelevant.get(skill, [])
            correlations.append({
                "skill": skill,
                "mean_sat_when_relevant": (
                    round(sum(rel_scores) / len(rel_scores), 2) if rel_scores else None
                ),
                "mean_sat_when_irrelevant": (
                    round(sum(irrel_scores) / len(irrel_scores), 2) if irrel_scores else None
                ),
                "relevant_count": len(rel_scores),
                "irrelevant_count": len(irrel_scores),
            })
        return correlations

    def top_skills(self, n: int = 10) -> list[dict]:
        rates = self.relevance_rates()
        return sorted(rates, key=lambda x: x["activations"], reverse=True)[:n]

    def overview(self) -> dict:
        most_used = self.most_used_skill()
        noisiest = self.noisiest_skill()
        return {
            "total_skills_detected": self.total_skills_detected(),
            "most_used_skill": most_used,
            "noisiest_skill": noisiest,
            "quadrant": self.quadrant(),
            "top_skills": self.top_skills(),
            "activation_frequency": self.activation_frequency(),
            "relevance_rates": self.relevance_rates(),
            "satisfaction_correlation": self.skills_satisfaction_correlation(),
        }
