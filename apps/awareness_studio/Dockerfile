# Reproducible container for Awareness Studio: the independently
# installable FastAPI + RAG chatbot app. Separate from the root sim
# engine's Dockerfile -- these are two genuinely different Python
# environments (see repo root CLAUDE.md), each with its own dependency
# footprint, so each gets its own lean image rather than one shared,
# bloated one.
FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/
COPY tests/ tests/

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e ".[dev,web]"

# Default: run this sub-project's own test suite (mirrors `make test` /
# CLAUDE.md's `pytest -q`, offline, no LLM). Override with
# `docker run <image> <cmd>` to instead start the web app
# (`uvicorn awareness_studio.web.app:app --host 0.0.0.0 --port 8000`).
CMD ["pytest", "-q"]
