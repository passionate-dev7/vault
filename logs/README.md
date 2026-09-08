## MCP tool call log

Proof that the VAULT agent queries ClickHouse through the official `mcp-clickhouse` MCP server.
Every row was written by `agent/mcp_client.py` during a real triage run.

Tool: `run_query` (mcp-clickhouse v0.6.0)
Transport: stdio (JSON-RPC 2.0)
Server: `mcp-clickhouse` subprocess, connecting to localhost:8123

This file is committed to the repo so judges can verify MCP usage without running the agent.
