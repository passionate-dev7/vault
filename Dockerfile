FROM python:3.13-slim

# Install ffmpeg, ffprobe, curl
RUN apt-get update && apt-get install -y \
    ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --no-editable

COPY . .

# Create logs dir
RUN mkdir -p logs

ENV PYTHONPATH=/app
ENV PORT=8080

# Use the PORT env var that Cloud Run sets
CMD ["sh", "-c", "uv run uvicorn web.app:app --host 0.0.0.0 --port ${PORT:-8080}"]
