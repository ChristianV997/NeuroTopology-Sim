from __future__ import annotations
import argparse
from pathlib import Path

def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--root", default="outputs/btc_icft/ds005620_real_runbook"); ap.add_argument("--out", default="outputs/obsidian/ds005620_real_runbook"); a = ap.parse_args()
    src = Path(a.root) / "ds005620_real_runbook_report.md"
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    text = src.read_text(encoding="utf-8") if src.exists() else "# DS005620 Runbook\nMissing source report.\n"
    (out / "index.md").write_text(text, encoding="utf-8")

if __name__ == "__main__":
    main()
