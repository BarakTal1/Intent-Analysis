from __future__ import annotations

import asyncio
import json
import os

from langsmith import Client as LangSmithClient

from .schemas import ToolCall, TraceData, TraceMessage


class LangSmithImporter:
    """Fetches runs/traces from the LangSmith API and converts them to TraceData."""

    def __init__(
        self,
        api_key: str | None = None,
        host: str | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("LANGSMITH_API_KEY", "")
        self.host = (host or os.environ.get("LANGSMITH_HOST", "https://api.smith.langchain.com")).rstrip("/")

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _get_client(self) -> LangSmithClient:
        return LangSmithClient(api_key=self.api_key, api_url=self.host)

    async def fetch_traces(
        self,
        project_name: str | None = None,
        project_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
        run_type: str | None = None,
        is_root: bool = True,
    ) -> list[TraceData]:
        if not self.is_configured:
            raise ValueError("LangSmith API key not configured. Set LANGSMITH_API_KEY.")

        client = self._get_client()

        kwargs: dict = {
            "limit": limit,
            "is_root": is_root,
        }
        if project_name:
            kwargs["project_name"] = project_name
        if project_id:
            kwargs["project_id"] = project_id
        if run_type:
            kwargs["run_type"] = run_type

        def _list_runs():
            return list(client.list_runs(**kwargs))

        loop = asyncio.get_event_loop()
        runs = await loop.run_in_executor(None, _list_runs)

        result: list[TraceData] = []
        for run in runs:
            run_dict = run.dict() if hasattr(run, "dict") else run.model_dump()
            trace = self._run_to_trace(run_dict)
            if trace.messages:
                result.append(trace)

        return result

    async def list_projects(self) -> list[dict]:
        if not self.is_configured:
            raise ValueError("LangSmith API key not configured.")

        client = self._get_client()

        def _list_projects():
            return [
                {"id": str(p.id), "name": p.name}
                for p in client.list_projects(limit=100)
            ]

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _list_projects)

    def _run_to_trace(self, run: dict) -> TraceData:
        messages: list[TraceMessage] = []
        tool_calls: list[ToolCall] = []
        skills: list[str] = []

        inp = run.get("inputs", {})
        if isinstance(inp, dict):
            if "messages" in inp:
                self._extract_messages(inp["messages"], messages, tool_calls, skills)
            elif "input" in inp:
                val = inp["input"]
                if isinstance(val, str) and val.strip():
                    messages.append(TraceMessage(role="user", content=val))
                elif isinstance(val, list):
                    self._extract_messages(val, messages, tool_calls, skills)
            elif "question" in inp or "query" in inp:
                q = inp.get("question") or inp.get("query", "")
                if isinstance(q, str) and q.strip():
                    messages.append(TraceMessage(role="user", content=q))

        out = run.get("outputs", {})
        if isinstance(out, dict):
            if "messages" in out:
                self._extract_messages(out["messages"], messages, tool_calls, skills)
            elif "output" in out:
                val = out["output"]
                if isinstance(val, str) and val.strip():
                    messages.append(TraceMessage(role="assistant", content=val))
                elif isinstance(val, dict) and "content" in val:
                    messages.append(TraceMessage(role="assistant", content=str(val["content"])))
            elif "answer" in out or "result" in out:
                a = out.get("answer") or out.get("result", "")
                if isinstance(a, str) and a.strip():
                    messages.append(TraceMessage(role="assistant", content=a))

        for child in (run.get("child_runs") or []):
            self._extract_child_run(child, messages, tool_calls, skills)

        duration = None
        if run.get("total_time"):
            duration = run["total_time"]
        elif run.get("latency"):
            duration = run["latency"]

        metadata = {}
        if run.get("tags"):
            metadata["tags"] = run["tags"]
        if run.get("extra") and isinstance(run["extra"], dict):
            extra_meta = run["extra"].get("metadata")
            if extra_meta and isinstance(extra_meta, dict):
                metadata.update(extra_meta)
        if run.get("start_time"):
            metadata["timestamp"] = str(run["start_time"])

        return TraceData(
            trace_id=str(run.get("id", "unknown")),
            session_id=str(run["session_id"]) if run.get("session_id") else None,
            user_id=None,
            messages=messages,
            tool_calls=tool_calls,
            skills_activated=skills or [tc.tool_name for tc in tool_calls],
            metadata=metadata,
            duration_seconds=duration,
        )

    def _extract_messages(
        self,
        msgs: list,
        messages: list[TraceMessage],
        tool_calls: list[ToolCall],
        skills: list[str],
    ) -> None:
        if not isinstance(msgs, list):
            return
        for msg in msgs:
            if not isinstance(msg, dict):
                continue

            role = msg.get("role", msg.get("type", ""))
            if role in ("human", "HumanMessage"):
                role = "user"
            elif role in ("ai", "AIMessage", "AIMessageChunk"):
                role = "assistant"
            elif role in ("tool", "ToolMessage"):
                name = msg.get("name", "")
                content = msg.get("content", "")
                if isinstance(content, (dict, list)):
                    content = json.dumps(content, ensure_ascii=False)
                for tc in tool_calls:
                    if tc.tool_name == name and not tc.output_summary:
                        tc.output_summary = str(content)[:200]
                        break
                continue
            elif role in ("system", "SystemMessage"):
                continue
            else:
                continue

            content = msg.get("content", msg.get("text", ""))
            if isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        parts.append(block.get("text", ""))
                    elif isinstance(block, str):
                        parts.append(block)
                content = "\n".join(parts)
            if isinstance(content, str) and content.strip():
                messages.append(TraceMessage(role=role, content=content))

            for tc in msg.get("tool_calls", []):
                name = tc.get("name", tc.get("function", {}).get("name", ""))
                args = tc.get("args", tc.get("input", tc.get("function", {}).get("arguments", {})))
                tool_calls.append(ToolCall(
                    tool_name=name,
                    input_summary=json.dumps(args, ensure_ascii=False)[:200] if isinstance(args, dict) else str(args)[:200],
                ))
                if "skill" in name.lower():
                    skills.append(name)

    def _extract_child_run(
        self,
        child: dict,
        messages: list[TraceMessage],
        tool_calls: list[ToolCall],
        skills: list[str],
    ) -> None:
        run_type = child.get("run_type", "")

        if run_type == "tool":
            name = child.get("name", "")
            inp = child.get("inputs", {})
            out = child.get("outputs", {})
            inp_str = json.dumps(inp, ensure_ascii=False)[:200] if isinstance(inp, (dict, list)) else str(inp or "")[:200]
            out_str = json.dumps(out, ensure_ascii=False)[:200] if isinstance(out, (dict, list)) else str(out or "")[:200]
            tool_calls.append(ToolCall(tool_name=name, input_summary=inp_str, output_summary=out_str))
            if "skill" in name.lower():
                skills.append(name)

        elif run_type == "llm":
            inp = child.get("inputs", {})
            if isinstance(inp, dict) and "messages" in inp:
                self._extract_messages(inp["messages"], messages, tool_calls, skills)

            out = child.get("outputs", {})
            if isinstance(out, dict):
                if "generations" in out:
                    for gen_list in out["generations"]:
                        if isinstance(gen_list, list):
                            for gen in gen_list:
                                if isinstance(gen, dict):
                                    text = gen.get("text", "")
                                    msg = gen.get("message", {})
                                    content = msg.get("content", text) if isinstance(msg, dict) else text
                                    if isinstance(content, str) and content.strip():
                                        messages.append(TraceMessage(role="assistant", content=content))
