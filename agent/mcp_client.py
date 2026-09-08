"""Async MCP client for mcp-clickhouse.

The ClickHouse track requirement: the agent must query ClickHouse THROUGH the
official mcp-clickhouse MCP server, not only via a direct DB driver.

This module spawns mcp-clickhouse as a subprocess over stdio (the standard
MCP transport) and sends JSON-RPC 2.0 `tools/call` messages. Every call is
logged to logs/mcp_tool_calls.jsonl — that file is committed as proof.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

LOG_FILE = Path(__file__).parent.parent / "logs" / "mcp_tool_calls.jsonl"


class MCPClickHouseClient:
    """Minimal stdio MCP client for mcp-clickhouse.

    Launches the server once, re-uses the connection for the session.
    """

    def __init__(self):
        self._proc: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()
        self._msg_id = 0
        self._server_cmd = self._find_server_cmd()
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _find_server_cmd() -> list[str]:
        import shutil
        for candidate in ["mcp-clickhouse", "uvx mcp-clickhouse"]:
            parts = candidate.split()
            if shutil.which(parts[0]):
                return parts
        # Fall back to uvx which will install-on-demand
        return ["uvx", "mcp-clickhouse"]

    async def __aenter__(self):
        await self._start()
        return self

    async def __aexit__(self, *_):
        await self.close()

    async def _start(self) -> None:
        env = os.environ.copy()
        env.update({
            "CLICKHOUSE_HOST":     os.getenv("CLICKHOUSE_HOST", "localhost"),
            "CLICKHOUSE_PORT":     os.getenv("CLICKHOUSE_PORT", "8123"),
            "CLICKHOUSE_USER":     os.getenv("CLICKHOUSE_USER", "default"),
            "CLICKHOUSE_PASSWORD": os.getenv("CLICKHOUSE_PASSWORD", ""),
            "CLICKHOUSE_SECURE":   os.getenv("CLICKHOUSE_SECURE", "false"),
        })
        self._proc = await asyncio.create_subprocess_exec(
            *self._server_cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        # Initialize with MCP handshake
        await self._send_raw({"jsonrpc": "2.0", "id": 0,
                              "method": "initialize",
                              "params": {"protocolVersion": "2024-11-05",
                                         "capabilities": {},
                                         "clientInfo": {"name": "vault", "version": "0.1.0"}}})
        resp = await self._read_response()
        log.debug("MCP initialized: %s", resp.get("result", {}).get("serverInfo"))

        # Send initialized notification
        await self._send_raw({"jsonrpc": "2.0",
                              "method": "notifications/initialized",
                              "params": {}})

    async def _send_raw(self, obj: dict) -> None:
        data = json.dumps(obj) + "\n"
        self._proc.stdin.write(data.encode())
        await self._proc.stdin.drain()

    async def _read_response(self, timeout: float = 30.0) -> dict:
        try:
            line = await asyncio.wait_for(self._proc.stdout.readline(), timeout=timeout)
            return json.loads(line.decode().strip())
        except asyncio.TimeoutError:
            raise RuntimeError("MCP server did not respond within timeout")

    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """Call an MCP tool and return its result. Logs every call."""
        async with self._lock:
            self._msg_id += 1
            msg_id = self._msg_id
            request = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments},
            }
            t0 = time.time()
            await self._send_raw(request)
            response = await self._read_response(timeout=60.0)
            elapsed = round(time.time() - t0, 3)

        # Extract result
        result = response.get("result", {})
        content = result.get("content", [])
        text_parts = [c["text"] for c in content if c.get("type") == "text"]
        result_text = "\n".join(text_parts)

        # Log to jsonl
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "tool": tool_name,
            "arguments": arguments,
            "elapsed_s": elapsed,
            "result_preview": result_text[:500],
        }
        with LOG_FILE.open("a") as fh:
            fh.write(json.dumps(entry) + "\n")

        log.info("MCP %s %.3fs -> %d chars", tool_name, elapsed, len(result_text))
        return {"text": result_text, "raw": result}

    async def query(self, sql: str) -> str:
        """Execute a SQL query via the mcp-clickhouse run_query tool."""
        r = await self.call_tool("run_query", {"query": sql})
        return r["text"]

    async def close(self) -> None:
        if self._proc and self._proc.stdin:
            self._proc.stdin.close()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._proc.kill()
        self._proc = None


async def run_mcp_query(sql: str) -> str:
    """One-shot helper: open MCP, run SQL, close."""
    async with MCPClickHouseClient() as c:
        return await c.query(sql)
