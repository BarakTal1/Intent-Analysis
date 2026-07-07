from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from extraction.schemas import IntentRepresentation, TraceData
from config import settings


@dataclass
class TraceResult:
    trace_id: str
    success: bool
    result: IntentRepresentation | None = None
    error: str | None = None
    duration_ms: float = 0


@dataclass
class BatchRun:
    total: int = 0
    completed: int = 0
    failed: int = 0
    results: list[TraceResult] = field(default_factory=list)
    is_running: bool = False
    start_time: float = 0


class BatchProcessor:
    def __init__(
        self,
        concurrency: int = 5,
        use_sbert: bool = True,
    ) -> None:
        self.concurrency = concurrency
        self.use_sbert = use_sbert
        self._agent: IntentExtractionAgent | None = None
        self._detector: SkillsDetector | None = None
        self.current_run = BatchRun()
        self._results_store: list[IntentRepresentation] = []

    @property
    def agent(self):
        if self._agent is None:
            from extraction.intent_agent import IntentExtractionAgent
            self._agent = IntentExtractionAgent()
        return self._agent

    @property
    def detector(self):
        if self._detector is None:
            from extraction.skills_detector import SkillsDetector
            self._detector = SkillsDetector()
        return self._detector

    def _embedder(self):
        """Reuse the detector's SBERT model when available, else load one."""
        if self.use_sbert:
            return self.detector.model
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer("all-mpnet-base-v2")

    def assign_intents(self, new_results, all_results, taxonomy_path) -> dict:
        """Two-phase autonomous classification (discover once, classify cheaply).

        - First run (no taxonomy yet): DISCOVER a finite taxonomy (LLM induction over
          the extracted intents), then classify every result into it.
        - Later runs: classify only the NEW results against the stable taxonomy.
        - Drift: if too many results land in 'unclassified', REBUILD the taxonomy
          from the preserved raw intents and re-classify everything.

        Classification is borderline-only: confident matches are decided by cheap
        local embeddings; the LLM is consulted solely for the ambiguous minority.
        """
        from analysis.taxonomy_builder import TaxonomyBuilder
        from extraction.intent_classifier import IntentClassifier, UNCLASSIFIED
        from extraction.intent_llm import make_inducer, make_decider

        model = self._embedder()
        embed_many = lambda ts: model.encode(ts, normalize_embeddings=True)
        embed_one = lambda t: model.encode(t, normalize_embeddings=True)

        def raw_pairs(results):
            return [(r.raw_intent or r.primary_intent, r.intent_summary) for r in results]

        taxonomy = TaxonomyBuilder.load(taxonomy_path)
        if not taxonomy:
            taxonomy = TaxonomyBuilder(embed_many, make_inducer()).build(raw_pairs(all_results))
            TaxonomyBuilder.save(taxonomy, taxonomy_path)
            targets = all_results
        else:
            targets = new_results

        def classify(results, tax):
            clf = IntentClassifier(tax, embed_one, make_decider())
            llm_used = 0
            for r in results:
                a = clf.classify(r.raw_intent or r.primary_intent, r.intent_summary)
                r.primary_intent = a.canonical
                llm_used += int(a.used_llm)
            return llm_used

        llm_used = classify(targets, taxonomy)

        # drift: rebuild from original signal if coverage has degraded
        unclassified = sum(1 for r in all_results if r.primary_intent == UNCLASSIFIED)
        if all_results and unclassified / len(all_results) > 0.15:
            taxonomy = TaxonomyBuilder(embed_many, make_inducer()).build(raw_pairs(all_results))
            TaxonomyBuilder.save(taxonomy, taxonomy_path)
            llm_used += classify(all_results, taxonomy)
            unclassified = sum(1 for r in all_results if r.primary_intent == UNCLASSIFIED)

        return {
            "taxonomy_size": len(taxonomy),
            "classified": len(targets),
            "unclassified": unclassified,
            "llm_calls_used": llm_used,
        }

    @property
    def results(self) -> list[IntentRepresentation]:
        return self._results_store

    def clear_results(self) -> None:
        self._results_store.clear()

    async def process_traces(self, traces: list[TraceData]) -> BatchRun:
        valid = [t for t in traces if len(t.messages) >= 2]

        self.current_run = BatchRun(
            total=len(valid),
            is_running=True,
            start_time=time.time(),
        )

        semaphore = asyncio.Semaphore(self.concurrency)

        async def process_one(trace: TraceData) -> TraceResult:
            async with semaphore:
                start = time.time()
                try:
                    sbert_scores = None
                    if self.use_sbert:
                        skills = self.detector.detect_skills(trace)
                        if skills:
                            sbert_scores = self.detector.score_relevance(trace, skills)

                    result = await self.agent.aextract(trace, sbert_scores)
                    self._results_store.append(result)
                    self.current_run.completed += 1
                    return TraceResult(
                        trace_id=trace.trace_id,
                        success=True,
                        result=result,
                        duration_ms=(time.time() - start) * 1000,
                    )
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    self.current_run.failed += 1
                    return TraceResult(
                        trace_id=trace.trace_id,
                        success=False,
                        error=str(e),
                        duration_ms=(time.time() - start) * 1000,
                    )

        tasks = [process_one(t) for t in valid]
        try:
            trace_results = await asyncio.gather(*tasks)
        finally:
            self.current_run.is_running = False
        self.current_run.results = list(trace_results)
        return self.current_run

    def save_results(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            for r in self._results_store:
                f.write(r.model_dump_json() + "\n")

    def load_results(self, path: str | Path) -> list[IntentRepresentation]:
        path = Path(path)
        if not path.exists():
            return []
        loaded = []
        for line in path.read_text().strip().splitlines():
            if line.strip():
                loaded.append(IntentRepresentation.model_validate_json(line))
        self._results_store.extend(loaded)
        return loaded
