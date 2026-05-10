# Awareness Studio — local bootstrap (Windows PowerShell)
# Usage: .\scripts\bootstrap.ps1
# Run from apps\awareness_studio\

$ErrorActionPreference = "Stop"

$Venv = ".venv"
$Python = if ($env:PYTHON) { $env:PYTHON } else { "python" }

Write-Host "==> [bootstrap] Python: $(& $Python --version)"

# ── 1. Create virtual environment ─────────────────────────────────────────────
if (-Not (Test-Path $Venv)) {
    Write-Host "==> [bootstrap] Creating $Venv ..."
    & $Python -m venv $Venv
} else {
    Write-Host "==> [bootstrap] $Venv already exists, skipping creation"
}

$Pip    = "$Venv\Scripts\pip.exe"
$Pytest = "$Venv\Scripts\pytest.exe"
$AwarenessIndex = "$Venv\Scripts\awareness-index.exe"
$AwarenessEval  = "$Venv\Scripts\awareness-eval.exe"

# ── 2. Install package ────────────────────────────────────────────────────────
Write-Host "==> [bootstrap] Installing package + dev/web extras ..."
& $Pip install --quiet --upgrade pip
& $Pip install --quiet -e ".[dev,web]"

# ── 3. Copy .env template ─────────────────────────────────────────────────────
if (-Not (Test-Path ".env")) {
    Write-Host "==> [bootstrap] Copying .env.example -> .env"
    Copy-Item ".env.example" ".env"
    Write-Host "    -> Edit .env and set ANTHROPIC_API_KEY to enable LLM features."
} else {
    Write-Host "==> [bootstrap] .env already exists, skipping"
}

# ── 4. Build index ────────────────────────────────────────────────────────────
Write-Host "==> [bootstrap] Building BM25 index ..."
$env:PYTHONPATH = "src"; $env:INDEX_BACKEND = "bm25"
& $AwarenessIndex --force

# ── 5. Run offline tests ──────────────────────────────────────────────────────
Write-Host "==> [bootstrap] Running offline tests ..."
& $Pytest -q

# ── 6. Golden eval ────────────────────────────────────────────────────────────
Write-Host "==> [bootstrap] Running golden eval (no LLM) ..."
& $AwarenessEval --no-llm

Write-Host ""
Write-Host "Bootstrap complete!"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  .venv\Scripts\Activate.ps1"
Write-Host "  make web    # or: uvicorn awareness_studio.web.app:app --port 8000"
