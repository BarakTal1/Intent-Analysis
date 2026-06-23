from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .schemas import TraceData, TraceMessage, ToolCall


class TraceLoader:
    """Loads and normalizes traces from exported files (Excel, CSV, JSON, or text)."""

    SUPPORTED_EXTENSIONS = {".xlsx", ".xls", ".csv", ".tsv", ".json", ".jsonl", ".txt"}

    def load(self, path: str | Path) -> list[TraceData]:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Trace file not found: {path}")

        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file type '{ext}'. Supported: {', '.join(sorted(self.SUPPORTED_EXTENSIONS))}"
            )

        if ext in {".xlsx", ".xls"}:
            return self._load_excel(path)
        elif ext in {".csv", ".tsv"}:
            sep = "\t" if ext == ".tsv" else ","
            return self._load_csv(path, sep=sep)
        elif ext == ".json":
            return self._load_json(path)
        elif ext == ".jsonl":
            return self._load_jsonl(path)
        elif ext == ".txt":
            return self._load_text(path)

        return []

    def load_directory(self, directory: str | Path, pattern: str = "*") -> list[TraceData]:
        directory = Path(directory)
        traces: list[TraceData] = []
        for file_path in sorted(directory.iterdir()):
            if file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS:
                if pattern == "*" or file_path.match(pattern):
                    traces.extend(self.load(file_path))
        return traces

    def _load_excel(self, path: Path) -> list[TraceData]:
        df = pd.read_excel(path, engine="openpyxl")
        return self._dataframe_to_traces(df)

    def _load_csv(self, path: Path, sep: str = ",") -> list[TraceData]:
        df = pd.read_csv(path, sep=sep)
        return self._dataframe_to_traces(df)

    def _load_json(self, path: Path) -> list[TraceData]:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [self._dict_to_trace(item) for item in data]
        elif isinstance(data, dict):
            return [self._dict_to_trace(data)]
        return []

    def _load_jsonl(self, path: Path) -> list[TraceData]:
        traces = []
        for line in path.read_text(encoding="utf-8").strip().splitlines():
            line = line.strip()
            if line:
                traces.append(self._dict_to_trace(json.loads(line)))
        return traces

    def _load_text(self, path: Path) -> list[TraceData]:
        text = path.read_text(encoding="utf-8")

        try:
            data = json.loads(text)
            if isinstance(data, list):
                return [self._dict_to_trace(item) for item in data]
            elif isinstance(data, dict):
                return [self._dict_to_trace(data)]
        except json.JSONDecodeError:
            pass

        return self._parse_conversation_text(text, source=path.stem)

    def _dataframe_to_traces(self, df: pd.DataFrame) -> list[TraceData]:
        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

        if self._is_langchain_format(df):
            return self._langchain_dataframe_to_traces(df)

        if "trace_id" in df.columns:
            return self._grouped_dataframe_to_traces(df)

        return self._flat_dataframe_to_traces(df)

    @staticmethod
    def _find_langchain_column(df: pd.DataFrame) -> str | None:
        for col in df.columns:
            if "messages" not in col:
                continue
            sample = str(df[col].iloc[0]).strip()
            if not sample.startswith("["):
                continue
            try:
                msgs = json.loads(sample)
                if isinstance(msgs, list) and len(msgs) > 0 and "type" in msgs[0]:
                    return col
            except (json.JSONDecodeError, KeyError, IndexError):
                continue
        return None

    @staticmethod
    def _is_langchain_format(df: pd.DataFrame) -> bool:
        return TraceLoader._find_langchain_column(df) is not None

    def _langchain_dataframe_to_traces(self, df: pd.DataFrame) -> list[TraceData]:
        traces = []
        msg_col = self._find_langchain_column(df) or "messages"
        id_col = next(
            (c for c in ("thread_id", "trace_id", "id", "session_id") if c in df.columns),
            None,
        )

        for idx, row in df.iterrows():
            raw_msgs = row[msg_col]
            if isinstance(raw_msgs, str):
                try:
                    raw_msgs = json.loads(raw_msgs)
                except json.JSONDecodeError:
                    continue
            if not isinstance(raw_msgs, list):
                continue

            messages: list[TraceMessage] = []
            tool_calls: list[ToolCall] = []
            skills: list[str] = []

            for msg in raw_msgs:
                msg_type = msg.get("type", "")
                content = msg.get("content", "")

                if msg_type == "human":
                    if isinstance(content, str) and content.strip():
                        messages.append(TraceMessage(role="user", content=content))

                elif msg_type == "ai":
                    text_parts = []
                    if isinstance(content, str) and content.strip():
                        text_parts.append(content)
                    elif isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict):
                                if block.get("type") == "text" and block.get("text", "").strip():
                                    text_parts.append(block["text"])
                    if text_parts:
                        messages.append(TraceMessage(role="assistant", content="\n".join(text_parts)))

                    for tc in msg.get("tool_calls", []):
                        name = tc.get("name", "")
                        args = tc.get("args", tc.get("input", {}))
                        tool_calls.append(ToolCall(
                            tool_name=name,
                            input_summary=json.dumps(args, ensure_ascii=False)[:200] if isinstance(args, dict) else str(args)[:200],
                        ))
                        if "skill" in name.lower():
                            skills.append(name)

                elif msg_type == "tool":
                    tool_name = msg.get("name", "")
                    tool_content = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
                    for tc in tool_calls:
                        if tc.tool_name == tool_name and not tc.output_summary:
                            tc.output_summary = tool_content[:200]
                            break

            trace_id = str(row[id_col]) if id_col else f"trace_{idx}"
            traces.append(TraceData(
                trace_id=trace_id,
                session_id=self._get_opt(row, "session_id", "thread_id"),
                user_id=self._get_opt(row, "user_id"),
                messages=messages,
                tool_calls=tool_calls,
                skills_activated=skills or [tc.tool_name for tc in tool_calls],
                metadata=self._extract_metadata(row),
            ))

        return traces

    def _grouped_dataframe_to_traces(self, df: pd.DataFrame) -> list[TraceData]:
        traces = []
        for trace_id, group in df.groupby("trace_id"):
            messages = []
            tool_calls = []
            skills = []

            for _, row in group.iterrows():
                role = str(row.get("role", "")).strip()
                content = str(row.get("content", row.get("message", ""))).strip()
                if role and content and content != "nan":
                    messages.append(TraceMessage(role=role, content=content))

                tool_name = str(row.get("tool_name", row.get("tool", ""))).strip()
                if tool_name and tool_name != "nan":
                    tool_calls.append(ToolCall(
                        tool_name=tool_name,
                        input_summary=str(row.get("tool_input", ""))[:200],
                        output_summary=str(row.get("tool_output", ""))[:200],
                    ))
                    if "skill" in tool_name.lower():
                        skills.append(tool_name)

            traces.append(TraceData(
                trace_id=str(trace_id),
                session_id=self._get_opt(group.iloc[0], "session_id"),
                user_id=self._get_opt(group.iloc[0], "user_id"),
                messages=messages,
                tool_calls=tool_calls,
                skills_activated=skills,
                metadata=self._extract_metadata(group.iloc[0]),
                duration_seconds=self._get_float(group.iloc[0], "duration_seconds", "duration"),
            ))
        return traces

    def _flat_dataframe_to_traces(self, df: pd.DataFrame) -> list[TraceData]:
        traces = []
        for i, row in df.iterrows():
            messages = []
            role = str(row.get("role", "")).strip()
            content = str(row.get("content", row.get("message", row.get("input", "")))).strip()
            if role and content and content != "nan":
                messages.append(TraceMessage(role=role, content=content))

            response = str(row.get("response", row.get("output", row.get("assistant", "")))).strip()
            if response and response != "nan":
                messages.append(TraceMessage(role="assistant", content=response))

            trace_id = str(row.get("id", f"trace_{i}"))
            traces.append(TraceData(
                trace_id=trace_id,
                session_id=self._get_opt(row, "session_id"),
                user_id=self._get_opt(row, "user_id"),
                messages=messages,
                metadata=self._extract_metadata(row),
                duration_seconds=self._get_float(row, "duration_seconds", "duration"),
            ))
        return traces

    def _parse_conversation_text(self, text: str, source: str) -> list[TraceData]:
        messages = []
        current_role = None
        current_content: list[str] = []

        for line in text.splitlines():
            line_lower = line.strip().lower()
            if line_lower.startswith("user:") or line_lower.startswith("human:"):
                if current_role and current_content:
                    messages.append(TraceMessage(role=current_role, content="\n".join(current_content).strip()))
                current_role = "user"
                current_content = [line.split(":", 1)[1].strip()]
            elif line_lower.startswith("assistant:") or line_lower.startswith("bot:") or line_lower.startswith("ai:"):
                if current_role and current_content:
                    messages.append(TraceMessage(role=current_role, content="\n".join(current_content).strip()))
                current_role = "assistant"
                current_content = [line.split(":", 1)[1].strip()]
            elif current_role:
                current_content.append(line)

        if current_role and current_content:
            messages.append(TraceMessage(role=current_role, content="\n".join(current_content).strip()))

        if not messages:
            messages.append(TraceMessage(role="user", content=text.strip()))

        return [TraceData(trace_id=source, messages=messages)]

    def _dict_to_trace(self, d: dict) -> TraceData:
        messages = []
        for msg in d.get("messages", d.get("conversation", [])):
            if isinstance(msg, dict) and "role" in msg:
                content = msg.get("content", msg.get("text", ""))
                if content:
                    messages.append(TraceMessage(role=msg["role"], content=str(content)))

        if not messages:
            user_input = d.get("input", d.get("user_input", d.get("query", "")))
            if user_input:
                messages.append(TraceMessage(role="user", content=str(user_input)))
            output = d.get("output", d.get("response", d.get("answer", "")))
            if output:
                messages.append(TraceMessage(role="assistant", content=str(output)))

        tool_calls = []
        skills = []
        for tc in d.get("tool_calls", d.get("tools", [])):
            if isinstance(tc, dict):
                name = tc.get("tool_name", tc.get("name", ""))
                tool_calls.append(ToolCall(
                    tool_name=name,
                    input_summary=str(tc.get("input", tc.get("input_summary", "")))[:200],
                    output_summary=str(tc.get("output", tc.get("output_summary", "")))[:200],
                ))
                if "skill" in name.lower():
                    skills.append(name)

        for s in d.get("skills_activated", d.get("skills", [])):
            if s not in skills:
                skills.append(str(s))

        return TraceData(
            trace_id=str(d.get("trace_id", d.get("id", "unknown"))),
            session_id=d.get("session_id"),
            user_id=d.get("user_id"),
            messages=messages,
            tool_calls=tool_calls,
            skills_activated=skills,
            metadata=d.get("metadata", {}),
            duration_seconds=d.get("duration_seconds", d.get("duration")),
        )

    @staticmethod
    def _get_opt(row, *keys: str) -> str | None:
        for key in keys:
            val = row.get(key) if hasattr(row, "get") else getattr(row, key, None)
            if val is not None and str(val).strip() and str(val) != "nan":
                return str(val).strip()
        return None

    @staticmethod
    def _get_float(row, *keys: str) -> float | None:
        for key in keys:
            val = row.get(key) if hasattr(row, "get") else getattr(row, key, None)
            if val is not None and str(val) != "nan":
                try:
                    return float(val)
                except (ValueError, TypeError):
                    pass
        return None

    @staticmethod
    def _extract_metadata(row) -> dict:
        meta = {}
        known_fields = {
            "trace_id", "session_id", "user_id", "role", "content", "message",
            "tool_name", "tool", "tool_input", "tool_output", "duration_seconds",
            "duration", "response", "output", "input", "assistant", "id",
        }
        if hasattr(row, "index"):
            for col in row.index:
                if col not in known_fields:
                    val = row[col]
                    if val is not None and str(val) != "nan":
                        meta[col] = val
        return meta
