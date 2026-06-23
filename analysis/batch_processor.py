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
