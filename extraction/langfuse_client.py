from __future__ import annotations

import json
import os

import httpx

from .schemas import ToolCall, TraceData, TraceMessage


class LangfuseImporter:
    """Fetches traces from the Langfuse API and converts them to TraceData."""

    def __init__(
        self,
        public_key: str | None = None,
        secret_key: str | None = None,
        host: str | None = None,
    ) -> None:
        self.public_key = public_key or os.environ.get("LANGFUSE_PUBLIC_KEY", "")
        self.secret_key = secret_key or os.environ.get("LANGFUSE_SECRET_KEY", "")
        self.host = (host or os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")).rstrip("/")

    @property
    def is_configured(self) -> bool:
        return bool(self.public_key and self.secret_key)

    async def fetch_traces(
        self,
        limit: int = 50,
        page: int = 1,
        user_id: str | None = None,
        session_id: str | None = None,
        name: str | None = None,
        tags: list[str] | None = None,
        order_by: str = "timestamp",
    ) -> list[TraceData]:
        if not self.is_configured:
            raise ValueError("Langfuse credentials not configured. Set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY.")

        params: dict = {"limit": limit, "page": page}
        if user_id:
            params["userId"] = user_id
        if session_id:
            params["sessionId"] = session_id
        if name:
            params["name"] = name
        if tags:
            for tag in tags:
                params.setdefault("tags", []).append(tag)

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.host}/api/public/traces",
                params=params,
                auth=(self.public_key, self.secret_key),
            )
            resp.raise_for_status()
            data = resp.json()

        traces_raw = data.get("data", [])
        result: list[TraceData] = []
        for raw in traces_raw:
            trace = self._raw_to_trace(raw)
            if trace.messages:
                result.append(trace)

        return result

    async def fetch_trace_detail(self, trace_id: str) -> TraceData:
        if not self.is_configured:
            raise ValueError("Langfuse credentials not configured.")

        async with httpx.AsyncClient(timeout=30) as client:
            trace_resp = await client.get(
                f"{self.host}/api/public/traces/{trace_id}",
                auth=(self.public_key, self.secret_key),
            )
            trace_resp.raise_for_status()
            raw = trace_resp.json()

        return self._raw_to_trace(raw)

    def _raw_to_trace(self, raw: dict) -> TraceData:
        messages: list[TraceMessage] = []
        tool_calls: list[ToolCall] = []
        skills: list[str] = []

        if raw.get("input"):
            inp = raw["input"]
            if isinstance(inp, str) and inp.strip():
                messages.append(TraceMessage(role="user", content=inp))
            elif isinstance(inp, dict):
                if "messages" in inp:
                    self._extract_messages(inp["messages"], messages, tool_calls, skills)
                elif "content" in inp:
                    messages.append(TraceMessage(role="user", content=str(inp["content"])))
                elif "query" in inp:
                    messages.append(TraceMessage(role="user", content=str(inp["query"])))

        if raw.get("output"):
            out = raw["output"]
            if isinstance(out, str) and out.strip():
                messages.append(TraceMessage(role="assistant", content=out))
            elif isinstance(out, dict):
                if "messages" in out:
                    self._extract_messages(out["messages"], messages, tool_calls, skills)
                elif "content" in out:
                    messages.append(TraceMessage(role="assistant", content=str(out["content"])))

        for obs in raw.get("observations", []):
            if isinstance(obs, dict):
                self._extract_observation(obs, messages, tool_calls, skills)

        duration = None
        if raw.get("latency") is not None:
            duration = float(raw["latency"])

        metadata = {}
        if raw.get("tags"):
            metadata["tags"] = raw["tags"]
        if raw.get("metadata") and isinstance(raw["metadata"], dict):
            metadata.update(raw["metadata"])
        if raw.get("timestamp"):
            metadata["timestamp"] = raw["timestamp"]

        return TraceData(
            trace_id=raw.get("id", "unknown"),
            session_id=raw.get("sessionId"),
            user_id=raw.get("userId"),
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
        for msg in msgs:
            if not isinstance(msg, dict):
                continue
            role = msg.get("role", msg.get("type", ""))
            if role in ("human", "user"):
                role = "user"
            elif role in ("ai", "assistant", "bot"):
                role = "assistant"
            else:
                if role == "tool":
                    name = msg.get("name", "")
                    content = msg.get("content", "")
                    if isinstance(content, (dict, list)):
                        content = json.dumps(content, ensure_ascii=False)
                    for tc in tool_calls:
                        if tc.tool_name == name and not tc.output_summary:
                            tc.output_summary = str(content)[:200]
                            break
                continue

            content = msg.get("content", msg.get("text", ""))
            if isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        parts.append(block.get("text", ""))
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

    def _extract_observation(
        self,
        obs: dict,
        messages: list[TraceMessage],
        tool_calls: list[ToolCall],
        skills: list[str],
    ) -> None:
        obs_type = obs.get("type", "").upper()

        if obs_type == "GENERATION":
            inp = obs.get("input")
            if isinstance(inp, dict) and "messages" in inp:
                self._extract_messages(inp["messages"], messages, tool_calls, skills)
            elif isinstance(inp, str) and inp.strip():
                messages.append(TraceMessage(role="user", content=inp))

            out = obs.get("output")
            if isinstance(out, dict):
                if "content" in out:
                    content = out["content"]
                    if isinstance(content, str) and content.strip():
                        messages.append(TraceMessage(role="assistant", content=content))
                for tc in out.get("tool_calls", []):
                    name = tc.get("name", tc.get("function", {}).get("name", ""))
                    args = tc.get("args", tc.get("input", {}))
                    tool_calls.append(ToolCall(
                        tool_name=name,
                        input_summary=json.dumps(args, ensure_ascii=False)[:200] if isinstance(args, dict) else str(args)[:200],
                    ))
                    if "skill" in name.lower():
                        skills.append(name)
            elif isinstance(out, str) and out.strip():
                messages.append(TraceMessage(role="assistant", content=out))

        elif obs_type == "SPAN":
            name = obs.get("name", "")
            if name:
                inp = obs.get("input")
                out = obs.get("output")
                inp_str = json.dumps(inp, ensure_ascii=False)[:200] if isinstance(inp, (dict, list)) else str(inp or "")[:200]
                out_str = json.dumps(out, ensure_ascii=False)[:200] if isinstance(out, (dict, list)) else str(out or "")[:200]
                tool_calls.append(ToolCall(tool_name=name, input_summary=inp_str, output_summary=out_str))
                if "skill" in name.lower():
                    skills.append(name)
