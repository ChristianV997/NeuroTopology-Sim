# Awareness Studio — developer convenience targets
# Run from apps/awareness_studio/
# Assumes: python3 is on PATH; venv lives at .venv/

PYTHON   ?= python3
VENV     := .venv
PIP      := $(VENV)/bin/pip
PY       := $(VENV)/bin/python
PYTEST   := $(VENV)/bin/pytest
UVICORN  := $(VENV)/bin/uvicorn
PORT     ?= 8000

.DEFAULT_GOAL := help

# ── bootstrap ─────────────────────────────────────────────────────────────────

.PHONY: setup
setup:  ## Create .venv and install package + dev deps
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --quiet --upgrade pip
	$(PIP) install --quiet -e ".[dev,web]"
	@echo "[setup] done — activate with: source .venv/bin/activate"

# ── tests ─────────────────────────────────────────────────────────────────────

.PHONY: test
test:  ## Run full offline test suite
	$(PYTEST) -q

.PHONY: eval
eval:  ## Run golden eval harness (no LLM required)
	$(VENV)/bin/awareness-eval --no-llm

# ── index ─────────────────────────────────────────────────────────────────────

.PHONY: index
index:  ## (Re)build the BM25 retrieval index
	$(VENV)/bin/awareness-index --force

# ── server ────────────────────────────────────────────────────────────────────

.PHONY: web
web:  ## Start the FastAPI Control Panel (port $(PORT))
	INDEX_BACKEND=bm25 \
	PYTHONPATH=src \
	$(UVICORN) awareness_studio.web.app:app --reload --port $(PORT)

# ── smoke (offline gates) ────────────────────────────────────────────────────

.PHONY: smoke
smoke: test eval index  ## Run all offline smoke gates (test + eval + index)
	@echo "[smoke] all gates passed"

# ── help ──────────────────────────────────────────────────────────────────────

.PHONY: help
help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*##"}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'
