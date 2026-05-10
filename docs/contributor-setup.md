# Contributor Setup Matrix

## Python versions

- Root project targets Python 3.10+ (see syntax and dependencies in `requirements.txt`).
- Awareness Studio is managed from `apps/awareness_studio/pyproject.toml`.

## Root install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Awareness Studio install

```bash
cd apps/awareness_studio
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

## Test commands

- Root: `pytest tests/ -v --tb=short`
- Smoke: `python main.py --mode synthetic`
- Awareness Studio: `cd apps/awareness_studio && python -m pytest -v --tb=short`

## No-secrets rule

- Never commit `.env` files, API keys, tokens, or local credential exports.
- Use environment variables locally and secret managers in CI.

## Codex/Cursor/Claude local workflow

- Keep changes scoped to one task/PR.
- Run targeted tests before commit.
- Do not commit generated artifacts (`results/`, caches, indexes, `.data`).
