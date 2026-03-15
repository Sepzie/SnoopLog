"""Tool executor for repository and log inspection."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from inspect import signature
from pathlib import Path
from typing import Any

from shared.log_buffer import search_logs

EXCLUDED_DIRS = {".git", ".next", "node_modules", "__pycache__"}


class ToolExecutor:
    """Executes investigation tools against the mounted repository."""

    def __init__(self, repo_path: str | None = None, timeout_seconds: int = 10) -> None:
        self._repo_path = Path(repo_path or os.getenv("REPO_PATH", "/repo")).resolve()
        self._timeout_seconds = timeout_seconds

    def list_files(self, path: str = ".", limit: int = 200) -> str:
        target = self._resolve_path(path)
        if not target.exists():
            return self._format_output("list_files", {"path": path}, error=f"Path not found: {path}")
        if target.is_file():
            return self._format_output(
                "list_files",
                {"path": path},
                data={"entries": [str(target.relative_to(self._repo_path))], "count": 1},
                summary=f"1 file found for {path}",
            )

        results: list[str] = []
        for root, dirs, files in os.walk(target):
            dirs[:] = [name for name in dirs if name not in EXCLUDED_DIRS]
            for name in sorted(files):
                rel = (Path(root) / name).relative_to(self._repo_path)
                results.append(str(rel))
                if len(results) >= limit:
                    break
            if len(results) >= limit:
                break
        return self._format_output(
            "list_files",
            {"path": path, "limit": limit},
            data={"entries": results, "count": len(results)},
            summary=f"Listed {len(results)} file(s) under {path}",
        )

    def read_file(
        self,
        path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> str:
        target = self._resolve_path(path)
        if not target.exists():
            return self._format_output("read_file", {"path": path}, error=f"Path not found: {path}")
        if not target.is_file():
            return self._format_output("read_file", {"path": path}, error=f"Not a file: {path}")

        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        start = max((start_line or 1) - 1, 0)
        end = min(end_line or len(lines), len(lines))
        selected = lines[start:end]
        formatted = [f"{idx}: {line}" for idx, line in enumerate(selected, start=start + 1)]
        return self._format_output(
            "read_file",
            {"path": path, "start_line": start + 1, "end_line": end},
            data={"path": path, "content": formatted, "line_count": len(formatted)},
            summary=f"Read {len(formatted)} line(s) from {path}",
        )

    def grep_code(self, pattern: str, file_glob: str | None = None, limit: int = 100) -> str:
        rg_path = shutil.which("rg")
        if rg_path is None:
            return self._format_output("grep_code", {"pattern": pattern}, error="ripgrep is not installed")

        command = [rg_path, "-n", "--hidden", "--glob", "!node_modules", "--glob", "!.git"]
        if file_glob:
            command.extend(["--glob", file_glob])
        command.extend([pattern, str(self._repo_path)])
        raw = self._run(command, limit=limit)
        return self._format_output(
            "grep_code",
            {"pattern": pattern, "file_glob": file_glob, "limit": limit},
            data={"matches": raw.splitlines() if raw and raw != "(no output)" else [], "match_count": 0 if raw == "(no output)" else len(raw.splitlines())},
            summary=f"grep_code found {0 if raw == '(no output)' else len(raw.splitlines())} match line(s)",
        )

    def git_blame(
        self,
        path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> str:
        target = self._resolve_path(path)
        rel = str(target.relative_to(self._repo_path))
        command = ["git", "-C", str(self._repo_path), "blame"]
        if start_line is not None and end_line is not None:
            command.extend(["-L", f"{start_line},{end_line}"])
        command.extend(["--", rel])
        raw = self._run(command)
        return self._format_output(
            "git_blame",
            {"path": path, "start_line": start_line, "end_line": end_line},
            data={"path": rel, "lines": raw.splitlines() if raw != "(no output)" else []},
            summary=f"git_blame returned {0 if raw == '(no output)' else len(raw.splitlines())} line(s)",
        )

    def git_log(self, path: str | None = None, n: int = 10) -> str:
        command = [
            "git",
            "-C",
            str(self._repo_path),
            "log",
            f"-n{n}",
            "--oneline",
            "--decorate",
        ]
        if path:
            rel = str(self._resolve_path(path).relative_to(self._repo_path))
            command.extend(["--", rel])
        raw = self._run(command)
        return self._format_output(
            "git_log",
            {"path": path, "n": n},
            data={"commits": raw.splitlines() if raw != "(no output)" else []},
            summary=f"git_log returned {0 if raw == '(no output)' else len(raw.splitlines())} commit(s)",
        )

    def search_logs(self, pattern: str, minutes: int | None = None, limit: int = 20) -> str:
        results = search_logs(pattern, minutes=minutes)[:limit]
        return self._format_output(
            "search_logs",
            {"pattern": pattern, "minutes": minutes, "limit": limit},
            data={"count": len(results), "entries": results},
            summary=f"search_logs returned {len(results)} matching event(s)",
        )

    def run_tool(self, tool_name: str, **kwargs: Any) -> str:
        handler = getattr(self, tool_name, None)
        if handler is None or tool_name.startswith("_"):
            raise ValueError(f"Unknown tool: {tool_name}")
        try:
            sanitized = self._sanitize_kwargs(handler, kwargs)
            return handler(**sanitized)
        except Exception as exc:
            return f"Tool failed: {exc}"

    def has_tool(self, tool_name: str) -> bool:
        handler = getattr(self, tool_name, None)
        return callable(handler) and not tool_name.startswith("_")

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "list_files",
                    "description": "List files in the repository relative to the repo root.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Relative directory path to inspect.",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of file paths to return.",
                                "minimum": 1,
                                "maximum": 500,
                            },
                        },
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read a file from the repository with line numbers.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Relative file path."},
                            "start_line": {"type": "integer", "minimum": 1},
                            "end_line": {"type": "integer", "minimum": 1},
                        },
                        "required": ["path"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "grep_code",
                    "description": "Search the repository code for a regex pattern.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "pattern": {"type": "string", "description": "Regex search pattern."},
                            "file_glob": {
                                "type": "string",
                                "description": "Optional file glob to narrow the search.",
                            },
                            "limit": {"type": "integer", "minimum": 1, "maximum": 500},
                        },
                        "required": ["pattern"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "git_blame",
                    "description": "Show git blame information for a file or line range.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Relative file path."},
                            "start_line": {"type": "integer", "minimum": 1},
                            "end_line": {"type": "integer", "minimum": 1},
                        },
                        "required": ["path"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "git_log",
                    "description": "Show recent git commits for the repository or a file.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Optional relative file path."},
                            "n": {"type": "integer", "minimum": 1, "maximum": 50},
                        },
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_logs",
                    "description": "Search recently ingested logs in the shared in-memory buffer.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "pattern": {"type": "string", "description": "Regex search pattern."},
                            "minutes": {
                                "type": "integer",
                                "description": "Optional lookback window in minutes.",
                                "minimum": 1,
                            },
                            "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                        },
                        "required": ["pattern"],
                        "additionalProperties": False,
                    },
                },
            },
        ]

    def _resolve_path(self, path: str) -> Path:
        candidate = (self._repo_path / path).resolve()
        if candidate != self._repo_path and self._repo_path not in candidate.parents:
            raise ValueError(f"Path escapes repo root: {path}")
        return candidate

    def _sanitize_kwargs(self, handler, kwargs: dict[str, Any]) -> dict[str, Any]:
        allowed = set(signature(handler).parameters.keys())
        return {key: value for key, value in kwargs.items() if key in allowed}

    def _run(self, command: list[str], limit: int | None = None) -> str:
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
                check=False,
            )
        except Exception as exc:
            return f"Command failed: {exc}"

        output = result.stdout.strip() or result.stderr.strip() or "(no output)"
        if limit is None:
            return output

        lines = output.splitlines()
        return "\n".join(lines[:limit])

    def _format_output(
        self,
        tool_name: str,
        args: dict[str, Any],
        *,
        data: dict[str, Any] | None = None,
        summary: str | None = None,
        error: str | None = None,
    ) -> str:
        payload = {
            "tool": tool_name,
            "ok": error is None,
            "summary": summary or "",
            "args": {key: value for key, value in args.items() if value is not None},
            "data": data or {},
        }
        if error is not None:
            payload["error"] = error
        return json.dumps(payload, indent=2)
