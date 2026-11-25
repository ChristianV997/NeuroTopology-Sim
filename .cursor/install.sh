#!/usr/bin/env bash
# Cloud Agent install script for NeuroTopology-Sim.
#
# Sets up BOTH Python environments this repo ships with (see CLAUDE.md):
#   1. Core sim engine  (repo root)          -> .venv           from requirements.txt
#   2. Awareness Studio (apps/awareness_studio) -> .venv (editable) from pyproject.toml
#
# Idempotent: safe to re-run. Uses per-project virtualenvs so the two
# dependency sets stay isolated, matching the repo's two-environment design.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# --- System dependency: venv support for the default python3 -----------------
# ensurepip/venv is not bundled with the distro python on Debian/Ubuntu images.
PY_MINOR="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if ! python3 -c 'import ensurepip' >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y --no-install-recommends "python${PY_MINOR}-venv"
fi

# --- 1. Core sim engine (repo root) ------------------------------------------
echo "==> [install] Core sim engine venv (.venv)"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

# --- 2. Awareness Studio (apps/awareness_studio) -----------------------------
echo "==> [install] Awareness Studio venv (apps/awareness_studio/.venv)"
pushd apps/awareness_studio >/dev/null
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e ".[dev,web]"
[ -f .env ] || cp .env.example .env
# Build the offline BM25 retrieval index from the bundled sample exports so the
# web app and CLIs are query-ready without any network/LLM calls.
PYTHONPATH=src INDEX_BACKEND=bm25 .venv/bin/awareness-index --force
popd >/dev/null

echo "==> [install] Done."
