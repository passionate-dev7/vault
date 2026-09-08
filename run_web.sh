#!/usr/bin/env bash
# Run the VAULT web UI (development mode).
set -e
cd "$(dirname "$0")"
export PYTHONPATH="."
uv run uvicorn web.app:app --host 0.0.0.0 --port 8000 --reload
