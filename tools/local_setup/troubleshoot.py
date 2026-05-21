from __future__ import annotations
import argparse, json
from pathlib import Path
from .reporting import write_markdown


def generate(env: dict, smoke: dict) -> str:
    lines = ["# Troubleshoot Report", ""]
    hints = []
    txt = json.dumps(smoke)
    if "make" in txt and "not found" in txt:
        hints.append("`make` not found: install with `sudo apt install make` or use direct Python fallback commands.")
    for mod in ["pytest", "numpy", "pandas", "scipy", "mne", "sklearn"]:
        if f"No module named {mod}" in txt or f"No module named '{mod}'" in txt or f'No module named "{mod}"' in txt:
            hints.append("Missing Python dependency detected: activate `.venv` and run `pip install -r requirements.txt`.")
            break
    if not env.get("python", {}).get("virtualenv_active", False):
        hints.append("Virtual environment inactive: run `source .venv/bin/activate`.")
    if "/mnt/c/" in env.get("repo", {}).get("root", ""):
        hints.append("Repository appears under /mnt/c/: clone inside WSL home (e.g. ~/projects/ScienceR-Dsim).")
    hints.append("OpenAI key missing is expected for mock/dry-run paths; only live RAG needs it.")
    hints.append("Missing real datasets is expected; local setup doctor validates safe local paths only.")
    for h in hints:
        lines.append(f"- {h}")
    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--env", required=True); p.add_argument("--smoke", required=True); p.add_argument("--markdown-out", required=True)
    a = p.parse_args()
    env = json.loads(Path(a.env).read_text(encoding="utf-8")) if Path(a.env).exists() else {}
    smoke = json.loads(Path(a.smoke).read_text(encoding="utf-8")) if Path(a.smoke).exists() else {}
    write_markdown(a.markdown_out, generate(env, smoke))

if __name__ == '__main__':
    main()
