#!/usr/bin/env bash
# Awareness Studio — local bootstrap (macOS / Linux)
# Usage: bash scripts/bootstrap.sh
# Run from apps/awareness_studio/

set -euo pipefail

VENV=".venv"
PYTHON="${PYTHON:-python3}"

echo "==> [bootstrap] Python: $($PYTHON --version)"

# ── 1. Create virtual environment ─────────────────────────────────────────────
if [ ! -d "$VENV" ]; then
    echo "==> [bootstrap] Creating $VENV …"
    $PYTHON -m venv "$VENV"
else
    echo "==> [bootstrap] $VENV already exists, skipping creation"
fi

PIP="$VENV/bin/pip"
PY="$VENV/bin/python"
PYTEST="$VENV/bin/pytest"

# ── 2. Install package in editable mode ───────────────────────────────────────
echo "==> [bootstrap] Installing package + dev/web extras …"
$PIP install --quiet --upgrade pip
$PIP install --quiet -e ".[dev,web]"

# ── 3. Copy .env template if not present ──────────────────────────────────────
if [ ! -f ".env" ]; then
    echo "==> [bootstrap] Copying .env.example → .env"
    cp .env.example .env
    echo "    → Edit .env and set ANTHROPIC_API_KEY (or OPENAI_API_KEY) to enable LLM features."
else
    echo "==> [bootstrap] .env already exists, skipping"
fi

# ── 4. Build index ─────────────────────────────────────────────────────────────
echo "==> [bootstrap] Building BM25 index from sample exports …"
PYTHONPATH=src INDEX_BACKEND=bm25 $VENV/bin/awareness-index --force

# ── 5. Run offline test suite ─────────────────────────────────────────────────
echo "==> [bootstrap] Running offline tests …"
$PYTEST -q

# ── 6. Run golden eval harness ────────────────────────────────────────────────
echo "==> [bootstrap] Running golden eval (no LLM) …"
PYTHONPATH=src $VENV/bin/awareness-eval --no-llm

echo ""
echo "✓ Bootstrap complete!"
echo ""
echo "Next steps:"
echo "  source $VENV/bin/activate"
echo "  make web          # start Control Panel on http://localhost:8000"
echo "  make smoke        # re-run all offline gates"
