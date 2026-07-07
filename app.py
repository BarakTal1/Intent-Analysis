from __future__ import annotations

import asyncio
import json
import os
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

from analysis.batch_processor import BatchProcessor
from analysis.intent_analysis import IntentAnalyzer
from analysis.satisfaction_analysis import SatisfactionAnalyzer
from analysis.skills_analysis import SkillsAnalyzer
from analysis.skills_gap_analysis import SkillsGapAnalyzer
from config import settings
from extraction.schemas import IntentRepresentation, TraceData
from extraction.trace_loader import TraceLoader

app = FastAPI(title="Intent Analyzer", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DIR = Path(__file__).parent / "data"
PROJECTS_DIR = DATA_DIR / "projects"
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
PROJECTS_META_FILE = DATA_DIR / "projects.json"

loader = TraceLoader()


# ---------------------------------------------------------------------------
# Project state container
# ---------------------------------------------------------------------------
class ProjectState:
    def __init__(self, project_id: str, name: str, data_dir: Path) -> None:
        self.project_id = project_id
        self.name = name
        self.data_dir = data_dir
        self.uploads_dir = data_dir / "uploads"
        self.results_file = data_dir / "results.jsonl"
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.processor = BatchProcessor(concurrency=5, use_sbert=True)
        self.staged_files: dict[str, dict] = {}
        self.parsed_traces: list[TraceData] = []

    def load_saved_results(self) -> None:
        if self.results_file.exists():
            self.processor.load_results(self.results_file)


_projects: dict[str, ProjectState] = {}
_active_project_id: str | None = None


def _save_projects_meta() -> None:
    meta = []
    for p in _projects.values():
        meta.append({"id": p.project_id, "name": p.name})
    PROJECTS_META_FILE.write_text(json.dumps(meta, indent=2))


def _load_projects_meta() -> None:
    if not PROJECTS_META_FILE.exists():
        return
    for entry in json.loads(PROJECTS_META_FILE.read_text()):
        pid = entry["id"]
        pdir = PROJECTS_DIR / pid
        pdir.mkdir(parents=True, exist_ok=True)
        state = ProjectState(pid, entry["name"], pdir)
        state.load_saved_results()
        _projects[pid] = state


def _get_project(project_id: str | None = None) -> ProjectState:
    pid = project_id or _active_project_id
    if not pid or pid not in _projects:
        raise HTTPException(400, "No active project. Create or select a project first.")
    return _projects[pid]


# ---------------------------------------------------------------------------
# Migrate legacy data dir into a "default" project if it exists
# ---------------------------------------------------------------------------
def _migrate_legacy_data() -> None:
    legacy_uploads = DATA_DIR / "uploads"
    legacy_results = DATA_DIR / "results.jsonl"
    if not legacy_uploads.exists() and not legacy_results.exists():
        return
    if "default" in _projects:
        return
    pid = "default"
    pdir = PROJECTS_DIR / pid
    pdir.mkdir(parents=True, exist_ok=True)
    dest_uploads = pdir / "uploads"
    if legacy_uploads.exists() and not dest_uploads.exists():
        shutil.copytree(legacy_uploads, dest_uploads)
    if legacy_results.exists():
        shutil.copy2(legacy_results, pdir / "results.jsonl")
    state = ProjectState(pid, "Default Project", pdir)
    state.load_saved_results()
    _projects[pid] = state
    _save_projects_meta()


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def _load_saved_results() -> None:
    global _active_project_id
    _load_projects_meta()
    _migrate_legacy_data()
    if _projects and not _active_project_id:
        _active_project_id = next(iter(_projects))


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
class SettingsUpdate(BaseModel):
    model_name: str | None = None
    api_key: str | None = None
    concurrency: int | None = None
    temperature: float | None = None
    satisfaction_threshold: float | None = None
    skills_relevance: float | None = None
    sbert_high_cutoff: float | None = None
    sbert_low_cutoff: float | None = None
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str | None = None
    langsmith_api_key: str | None = None
    langsmith_host: str | None = None

_runtime_settings: dict = {
    "model_name": settings.model_name,
    "concurrency": 5,
    "temperature": 0.0,
    "satisfaction_threshold": settings.satisfaction_threshold,
    "skills_relevance": settings.skills_relevance_threshold,
    "sbert_high_cutoff": 0.60,
    "sbert_low_cutoff": 0.35,
    "langfuse_host": os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com"),
    "langsmith_host": os.environ.get("LANGSMITH_HOST", "https://api.smith.langchain.com"),
}


@app.get("/api/settings")
async def get_settings():
    return {
        **_runtime_settings,
        "has_api_key": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "has_langfuse_keys": bool(os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")),
        "has_langsmith_key": bool(os.environ.get("LANGSMITH_API_KEY")),
    }


@app.put("/api/settings")
async def update_settings(body: SettingsUpdate):
    if body.model_name is not None:
        _runtime_settings["model_name"] = body.model_name
    if body.api_key is not None:
        os.environ["ANTHROPIC_API_KEY"] = body.api_key
    if body.concurrency is not None:
        _runtime_settings["concurrency"] = body.concurrency
        for p in _projects.values():
            p.processor.concurrency = body.concurrency
    if body.temperature is not None:
        _runtime_settings["temperature"] = body.temperature
    if body.satisfaction_threshold is not None:
        _runtime_settings["satisfaction_threshold"] = body.satisfaction_threshold
    if body.skills_relevance is not None:
        _runtime_settings["skills_relevance"] = body.skills_relevance
    if body.sbert_high_cutoff is not None:
        _runtime_settings["sbert_high_cutoff"] = body.sbert_high_cutoff
    if body.sbert_low_cutoff is not None:
        _runtime_settings["sbert_low_cutoff"] = body.sbert_low_cutoff
    if body.langfuse_public_key is not None:
        os.environ["LANGFUSE_PUBLIC_KEY"] = body.langfuse_public_key
    if body.langfuse_secret_key is not None:
        os.environ["LANGFUSE_SECRET_KEY"] = body.langfuse_secret_key
    if body.langfuse_host is not None:
        os.environ["LANGFUSE_HOST"] = body.langfuse_host
        _runtime_settings["langfuse_host"] = body.langfuse_host
    if body.langsmith_api_key is not None:
        os.environ["LANGSMITH_API_KEY"] = body.langsmith_api_key
    if body.langsmith_host is not None:
        os.environ["LANGSMITH_HOST"] = body.langsmith_host
        _runtime_settings["langsmith_host"] = body.langsmith_host
    return {"status": "ok", "settings": _runtime_settings}


# ---------------------------------------------------------------------------
# Projects CRUD
# ---------------------------------------------------------------------------
class ProjectCreate(BaseModel):
    name: str


class ProjectRename(BaseModel):
    name: str


@app.get("/api/projects")
async def list_projects():
    items = [{"id": p.project_id, "name": p.name, "trace_count": len(p.parsed_traces), "result_count": len(p.processor.results)} for p in _projects.values()]
    return {"projects": items, "active_project_id": _active_project_id}


@app.post("/api/projects")
async def create_project(body: ProjectCreate):
    global _active_project_id
    pid = str(uuid.uuid4())[:8]
    pdir = PROJECTS_DIR / pid
    pdir.mkdir(parents=True, exist_ok=True)
    state = ProjectState(pid, body.name, pdir)
    _projects[pid] = state
    _active_project_id = pid
    _save_projects_meta()
    return {"id": pid, "name": body.name}


@app.put("/api/projects/{project_id}")
async def rename_project(project_id: str, body: ProjectRename):
    if project_id not in _projects:
        raise HTTPException(404, "Project not found")
    _projects[project_id].name = body.name
    _save_projects_meta()
    return {"status": "ok"}


@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: str):
    global _active_project_id
    if project_id not in _projects:
        raise HTTPException(404, "Project not found")
    state = _projects.pop(project_id)
    if state.data_dir.exists():
        shutil.rmtree(state.data_dir)
    if _active_project_id == project_id:
        _active_project_id = next(iter(_projects), None)
    _save_projects_meta()
    return {"status": "ok", "active_project_id": _active_project_id}


@app.post("/api/projects/{project_id}/activate")
async def activate_project(project_id: str):
    global _active_project_id
    if project_id not in _projects:
        raise HTTPException(404, "Project not found")
    _active_project_id = project_id
    return {"status": "ok", "active_project_id": _active_project_id}


# ---------------------------------------------------------------------------
# Upload & Parse
# ---------------------------------------------------------------------------
@app.post("/api/upload")
async def upload_files(files: list[UploadFile] = File(...)):
    proj = _get_project()
    results = []
    for f in files:
        file_id = str(uuid.uuid4())[:8]
        ext = Path(f.filename or "file").suffix.lower()
        dest = proj.uploads_dir / f"{file_id}{ext}"
        content = await f.read()
        dest.write_bytes(content)
        proj.staged_files[file_id] = {
            "id": file_id,
            "filename": f.filename,
            "size": len(content),
            "path": str(dest),
            "status": "staged",
            "rows": None,
        }
        results.append(proj.staged_files[file_id])
    return {"files": results}


@app.get("/api/staged")
async def get_staged_files():
    proj = _get_project()
    return {"files": list(proj.staged_files.values())}


@app.delete("/api/staged/{file_id}")
async def remove_staged_file(file_id: str):
    proj = _get_project()
    info = proj.staged_files.pop(file_id, None)
    if info:
        p = Path(info["path"])
        if p.exists():
            p.unlink()
    return {"status": "ok"}


@app.delete("/api/traces")
async def clear_all_traces():
    proj = _get_project()
    count_traces = len(proj.parsed_traces)
    count_results = len(proj.processor.results)
    proj.parsed_traces.clear()
    proj.staged_files.clear()
    proj.processor.clear_results()
    if proj.results_file.exists():
        proj.results_file.unlink()
    for f in proj.uploads_dir.iterdir():
        f.unlink()
    return {
        "status": "ok",
        "cleared_traces": count_traces,
        "cleared_results": count_results,
    }


class DeleteTracesRequest(BaseModel):
    trace_ids: list[str]


@app.post("/api/traces/delete")
async def delete_traces(body: DeleteTracesRequest):
    proj = _get_project()
    ids = set(body.trace_ids)
    before_traces = len(proj.parsed_traces)
    before_results = len(proj.processor.results)
    proj.parsed_traces = [t for t in proj.parsed_traces if t.trace_id not in ids]
    proj.processor._results_store = [r for r in proj.processor._results_store if r.trace_id not in ids]
    if proj.processor.results or before_results:
        proj.processor.save_results(proj.results_file)
    return {
        "status": "ok",
        "removed_traces": before_traces - len(proj.parsed_traces),
        "removed_results": before_results - len(proj.processor.results),
        "remaining_traces": len(proj.parsed_traces),
        "remaining_results": len(proj.processor.results),
    }


@app.post("/api/parse")
async def parse_all_staged():
    proj = _get_project()
    new_traces: list[TraceData] = []
    errors = []

    for file_id, info in list(proj.staged_files.items()):
        try:
            traces = loader.load(info["path"])
            info["status"] = "parsed"
            info["rows"] = len(traces)
            new_traces.extend(traces)
        except Exception as e:
            info["status"] = "error"
            errors.append({"file": info["filename"], "error": str(e)})

    proj.parsed_traces.extend(new_traces)

    trace_summaries = []
    for t in new_traces:
        user_msgs = [m for m in t.messages if m.role == "user"]
        trace_summaries.append({
            "trace_id": t.trace_id,
            "session_id": t.session_id,
            "num_messages": len(t.messages),
            "num_tool_calls": len(t.tool_calls),
            "skills_activated": t.skills_activated,
            "preview": user_msgs[0].content[:120] if user_msgs else "",
        })

    return {
        "parsed": len(new_traces),
        "total_traces": len(proj.parsed_traces),
        "traces": trace_summaries,
        "errors": errors,
    }


@app.get("/api/traces")
async def get_traces(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    proj = _get_project()
    start = (page - 1) * per_page
    end = start + per_page
    page_traces = proj.parsed_traces[start:end]

    items = []
    for t in page_traces:
        user_msgs = [m for m in t.messages if m.role == "user"]
        items.append({
            "trace_id": t.trace_id,
            "session_id": t.session_id,
            "user_id": t.user_id,
            "num_messages": len(t.messages),
            "num_tool_calls": len(t.tool_calls),
            "skills_activated": t.skills_activated,
            "duration_seconds": t.duration_seconds,
            "preview": user_msgs[0].content[:200] if user_msgs else "",
            "messages": [m.model_dump() for m in t.messages],
            "tool_calls": [tc.model_dump() for tc in t.tool_calls],
            "metadata": t.metadata,
        })

    return {
        "total": len(proj.parsed_traces),
        "page": page,
        "per_page": per_page,
        "items": items,
    }


# ---------------------------------------------------------------------------
# Langfuse API Import
# ---------------------------------------------------------------------------
class LangfuseImportRequest(BaseModel):
    limit: int = 50
    page: int = 1
    user_id: str | None = None
    session_id: str | None = None
    name: str | None = None
    tags: list[str] | None = None


@app.get("/api/import/langfuse/status")
async def langfuse_status():
    from extraction.langfuse_client import LangfuseImporter
    importer = LangfuseImporter()
    return {"configured": importer.is_configured, "host": _runtime_settings.get("langfuse_host", "")}


@app.post("/api/import/langfuse")
async def import_from_langfuse(body: LangfuseImportRequest):
    from extraction.langfuse_client import LangfuseImporter
    proj = _get_project()
    importer = LangfuseImporter()

    if not importer.is_configured:
        raise HTTPException(400, "Langfuse credentials not configured. Set them in Settings or .env file.")

    try:
        traces = await importer.fetch_traces(
            limit=body.limit,
            page=body.page,
            user_id=body.user_id,
            session_id=body.session_id,
            name=body.name,
            tags=body.tags,
        )
    except Exception as e:
        raise HTTPException(502, f"Failed to fetch from Langfuse: {e}")

    existing_ids = {t.trace_id for t in proj.parsed_traces}
    new_traces = [t for t in traces if t.trace_id not in existing_ids]
    proj.parsed_traces.extend(new_traces)

    trace_summaries = []
    for t in new_traces:
        user_msgs = [m for m in t.messages if m.role == "user"]
        trace_summaries.append({
            "trace_id": t.trace_id,
            "session_id": t.session_id,
            "num_messages": len(t.messages),
            "num_tool_calls": len(t.tool_calls),
            "skills_activated": t.skills_activated,
            "preview": user_msgs[0].content[:120] if user_msgs else "",
        })

    return {
        "fetched": len(traces),
        "imported": len(new_traces),
        "skipped_duplicates": len(traces) - len(new_traces),
        "total_traces": len(proj.parsed_traces),
        "traces": trace_summaries,
    }


# ---------------------------------------------------------------------------
# LangSmith API Import
# ---------------------------------------------------------------------------
class LangSmithImportRequest(BaseModel):
    project_name: str | None = None
    project_id: str | None = None
    limit: int = 50
    offset: int = 0
    run_type: str | None = None
    is_root: bool = True


@app.get("/api/import/langsmith/status")
async def langsmith_status():
    from extraction.langsmith_client import LangSmithImporter
    importer = LangSmithImporter()
    return {"configured": importer.is_configured, "host": _runtime_settings.get("langsmith_host", "")}


@app.get("/api/import/langsmith/projects")
async def langsmith_projects():
    from extraction.langsmith_client import LangSmithImporter
    importer = LangSmithImporter()
    if not importer.is_configured:
        raise HTTPException(400, "LangSmith API key not configured.")
    try:
        projects = await importer.list_projects()
    except Exception as e:
        raise HTTPException(502, f"Failed to fetch LangSmith projects: {e}")
    return {"projects": projects}


@app.post("/api/import/langsmith")
async def import_from_langsmith(body: LangSmithImportRequest):
    from extraction.langsmith_client import LangSmithImporter
    proj = _get_project()
    importer = LangSmithImporter()

    if not importer.is_configured:
        raise HTTPException(400, "LangSmith API key not configured. Set it in Settings or .env file.")

    if not body.project_name and not body.project_id:
        raise HTTPException(400, "Please select a LangSmith project before importing.")

    try:
        traces = await importer.fetch_traces(
            project_name=body.project_name,
            project_id=body.project_id,
            limit=body.limit,
            offset=body.offset,
            run_type=body.run_type,
            is_root=body.is_root,
        )
    except Exception as e:
        raise HTTPException(502, f"Failed to fetch from LangSmith: {e}")

    existing_ids = {t.trace_id for t in proj.parsed_traces}
    new_traces = [t for t in traces if t.trace_id not in existing_ids]
    proj.parsed_traces.extend(new_traces)

    trace_summaries = []
    for t in new_traces:
        user_msgs = [m for m in t.messages if m.role == "user"]
        trace_summaries.append({
            "trace_id": t.trace_id,
            "session_id": t.session_id,
            "num_messages": len(t.messages),
            "num_tool_calls": len(t.tool_calls),
            "skills_activated": t.skills_activated,
            "preview": user_msgs[0].content[:120] if user_msgs else "",
        })

    return {
        "fetched": len(traces),
        "imported": len(new_traces),
        "skipped_duplicates": len(traces) - len(new_traces),
        "total_traces": len(proj.parsed_traces),
        "traces": trace_summaries,
    }


# ---------------------------------------------------------------------------
# Extraction (run the LLM pipeline)
# ---------------------------------------------------------------------------
@app.post("/api/extract")
async def run_extraction():
    proj = _get_project()
    if not proj.parsed_traces:
        raise HTTPException(400, "No parsed traces. Upload and parse files first.")
    if proj.processor.current_run.is_running:
        raise HTTPException(409, "Extraction already running.")

    already_extracted = {r.trace_id for r in proj.processor.results}
    new_traces = [t for t in proj.parsed_traces if t.trace_id not in already_extracted]

    if not new_traces:
        return {"status": "nothing_new", "total_results": len(proj.processor.results)}

    run = await proj.processor.process_traces(new_traces)

    # Merge the newly extracted intents into this project's stable canonical set
    # (Option C — online clustering) before persisting, so the same intent always
    # gets the same name across traces and across runs.
    new_results = [tr.result for tr in run.results if tr.success and tr.result]
    proj.processor.canonicalize_results(new_results, proj.data_dir / "intent_pool.json")

    proj.processor.save_results(proj.results_file)

    return {
        "status": "completed",
        "total": run.total,
        "completed": run.completed,
        "failed": run.failed,
        "total_results": len(proj.processor.results),
    }


@app.get("/api/extraction/status")
async def extraction_status():
    proj = _get_project()
    run = proj.processor.current_run
    return {
        "is_running": run.is_running,
        "total": run.total,
        "completed": run.completed,
        "failed": run.failed,
        "total_results": len(proj.processor.results),
    }


# ---------------------------------------------------------------------------
# Extraction Results
# ---------------------------------------------------------------------------
@app.get("/api/results")
async def get_results(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    intent: str | None = None,
    complexity: str | None = None,
    min_satisfaction: float | None = None,
    max_satisfaction: float | None = None,
    goal_achieved: bool | None = None,
    sort_by: str | None = None,
    sort_dir: str = "asc",
):
    proj = _get_project()
    filtered = list(proj.processor.results)

    if intent:
        filtered = [r for r in filtered if r.primary_intent == intent]
    if complexity:
        filtered = [r for r in filtered if r.complexity == complexity]
    if min_satisfaction is not None:
        filtered = [r for r in filtered if r.satisfaction_score >= min_satisfaction]
    if max_satisfaction is not None:
        filtered = [r for r in filtered if r.satisfaction_score <= max_satisfaction]
    if goal_achieved is not None:
        filtered = [r for r in filtered if r.goal_achieved == goal_achieved]

    if sort_by and filtered and hasattr(filtered[0], sort_by):
        filtered.sort(key=lambda r: (getattr(r, sort_by, None) is None, getattr(r, sort_by, None)), reverse=(sort_dir == "desc"))

    total = len(filtered)
    start = (page - 1) * per_page
    page_items = filtered[start : start + per_page]

    trace_map = {t.trace_id: t for t in proj.parsed_traces}
    items = []
    for r in page_items:
        trace = trace_map.get(r.trace_id)
        conversation = []
        if trace:
            conversation = [m.model_dump() for m in trace.messages]

        items.append({
            **r.model_dump(),
            "conversation": conversation,
        })

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "items": items,
    }


@app.get("/api/results/{trace_id}")
async def get_result_detail(trace_id: str):
    proj = _get_project()
    for r in proj.processor.results:
        if r.trace_id == trace_id:
            trace = next((t for t in proj.parsed_traces if t.trace_id == trace_id), None)
            conversation = [m.model_dump() for m in trace.messages] if trace else []
            raw_json = None
            if trace:
                raw_json = trace.model_dump()
            return {
                **r.model_dump(),
                "conversation": conversation,
                "raw_trace": raw_json,
            }
    raise HTTPException(404, "Result not found")


@app.get("/api/results/export/json")
async def export_results_json():
    proj = _get_project()
    return [r.model_dump() for r in proj.processor.results]


# ---------------------------------------------------------------------------
# Intent Overview analytics
# ---------------------------------------------------------------------------
@app.get("/api/analytics/intents")
async def intent_overview():
    proj = _get_project()
    analyzer = IntentAnalyzer(proj.processor.results)
    return analyzer.overview()


# ---------------------------------------------------------------------------
# Satisfaction Analysis analytics
# ---------------------------------------------------------------------------
@app.get("/api/analytics/satisfaction")
async def satisfaction_overview():
    proj = _get_project()
    analyzer = SatisfactionAnalyzer(proj.processor.results)
    return analyzer.overview()


# ---------------------------------------------------------------------------
# Skills Intelligence analytics
# ---------------------------------------------------------------------------
@app.get("/api/analytics/skills")
async def skills_overview():
    proj = _get_project()
    analyzer = SkillsAnalyzer(proj.processor.results)
    return analyzer.overview()


# ---------------------------------------------------------------------------
# Skills Gap Analysis — identify intents needing new skills
# ---------------------------------------------------------------------------
@app.get("/api/analytics/skills-gap")
async def skills_gap_overview():
    proj = _get_project()
    analyzer = SkillsGapAnalyzer(proj.processor.results)
    return analyzer.overview()


# ---------------------------------------------------------------------------
# Raw Explorer — combined traces + results for the explorer page
# ---------------------------------------------------------------------------
@app.get("/api/explorer")
async def raw_explorer(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    search: str | None = None,
    intent: str | None = None,
    complexity: str | None = None,
    goal_achieved: bool | None = None,
    sort_by: str | None = None,
    sort_dir: str = "asc",
):
    proj = _get_project()
    result_map = {r.trace_id: r for r in proj.processor.results}

    items = []
    for t in proj.parsed_traces:
        r = result_map.get(t.trace_id)

        if search:
            text = " ".join(m.content for m in t.messages).lower()
            if search.lower() not in text and search.lower() not in t.trace_id.lower():
                continue
        if intent and r and r.primary_intent != intent:
            continue
        if complexity and r and r.complexity != complexity:
            continue
        if goal_achieved is not None and r and r.goal_achieved != goal_achieved:
            continue

        items.append({
            "trace_id": t.trace_id,
            "session_id": t.session_id,
            "timestamp": t.metadata.get("timestamp"),
            "primary_intent": r.primary_intent if r else None,
            "satisfaction_score": r.satisfaction_score if r else None,
            "complexity": r.complexity if r else None,
            "goal_achieved": r.goal_achieved if r else None,
            "messages": [m.model_dump() for m in t.messages],
            "tool_calls": [tc.model_dump() for tc in t.tool_calls],
            "raw_json": t.model_dump(),
            "extraction": r.model_dump() if r else None,
        })

    if sort_by and items and sort_by in items[0]:
        items.sort(key=lambda x: x.get(sort_by) or "", reverse=(sort_dir == "desc"))

    total = len(items)
    start = (page - 1) * per_page
    page_items = items[start : start + per_page]

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "items": page_items,
    }


# ---------------------------------------------------------------------------
# Dashboard summary — top-level KPIs for the overview cards
# ---------------------------------------------------------------------------
@app.get("/api/analytics/summary")
async def analytics_summary():
    proj = _get_project()
    results = proj.processor.results
    if not results:
        return {
            "total_traces": len(proj.parsed_traces),
            "total_results": 0,
            "mean_satisfaction": None,
            "goal_achievement_rate": None,
            "processing_time": None,
        }

    sat = SatisfactionAnalyzer(results)
    intent = IntentAnalyzer(results)

    run = proj.processor.current_run
    elapsed = None
    if run.start_time and run.total:
        elapsed_total = sum(r.duration_ms for r in run.results) / 1000
        elapsed = round(elapsed_total, 1)

    return {
        "total_traces": len(proj.parsed_traces),
        "total_results": len(results),
        "mean_satisfaction": sat.mean_satisfaction(),
        "goal_achievement_rate": sat.goal_achievement_rate(),
        "fully_satisfied_rate": sat.fully_satisfied_rate(),
        "low_satisfaction_rate": sat.low_satisfaction_rate(),
        "top_intent": intent.distribution()[0] if intent.distribution() else None,
        "categories_found": intent.categories_found(),
        "unknown_rate": intent.unknown_rate(),
        "processing_time": elapsed,
    }


# ---------------------------------------------------------------------------
# Static frontend
# ---------------------------------------------------------------------------
FRONTEND_DIR = Path(__file__).parent / "static"


@app.get("/")
async def index():
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return HTMLResponse("<h1>Intent Analyzer</h1><p>Frontend not built yet.</p>")


if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
