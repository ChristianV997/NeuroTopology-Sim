#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

VERSION = "0.1"
VALIDATOR = "ontology_claim_language"

FORBIDDEN_PHRASES = [
    "proves consciousness",
    "consciousness proven",
    "soul proven",
    "afterlife proven",
    "liberation detected",
    "ontology solved",
    "ultimate reality",
    "q equals self",
    "q equals soul",
    "q_abs equals suffering",
    "f_dress equals karma",
    "sedated implies no_experience",
    "unresponsive implies unconscious",
    "topology proves liberation",
    "eeg proves consciousness",
]

UNSAFE_MAPPINGS = {
    "metric_to_ontology_shortcut": [
        "auc proves", "delta_auc proves", "q_net proves", "q_abs proves",
        "f_dress proves", "topology proves", "eeg proves",
    ],
    "state_label_shortcut": [
        "sedated means no_experience", "unresponsive means unconscious",
        "loc means no experience", "roc means consciousness returned",
    ],
    "forbidden_equivalence": [
        "q = self", "q = soul", "q_abs = suffering", "f_dress = karma",
        "topology = consciousness", "eeg = consciousness",
    ],
}

SKIP_DIRS = {".git", ".venv", "venv", "env", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
SCAN_SUFFIXES = {".md", ".txt", ".json", ".yaml", ".yml"}


def _parse_bool(value: str) -> bool:
    v = str(value).strip().lower()
    if v in {"1", "true", "yes", "y", "on"}:
        return True
    if v in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"Invalid boolean: {value}")


def _iter_files(root: Path, include_tests: bool):
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        parts = set(p.parts)
        if parts & SKIP_DIRS:
            continue
        if not include_tests and "tests" in p.parts:
            continue
        if p.suffix.lower() in SCAN_SUFFIXES:
            yield p


def _in_guardrail_section(lines: list[str], idx: int) -> bool:
    current = ""
    for i in range(0, idx + 1):
        m = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", lines[i])
        if m:
            current = m.group(1).lower()
    return "forbidden" in current or "guardrail" in current


def _sanitize(s: str) -> str:
    return s.replace(" ", "·")


def validate(args: argparse.Namespace) -> tuple[int, dict]:
    root = Path(args.root).resolve()
    skipped_roots: list[str] = []
    files: list[Path] = []

    if args.include_repo_docs:
        docs_root = root / args.docs_root
        if docs_root.exists():
            files.extend(_iter_files(docs_root, args.include_tests))

    if args.include_outputs:
        for out in args.output_roots:
            out_root = root / out
            if out_root.exists():
                files.extend(_iter_files(out_root, args.include_tests))
            else:
                skipped_roots.append(str(Path(out)))

    if args.include_repo_docs:
        for p in _iter_files(root, args.include_tests):
            if str(p).startswith(str(root / ".git")):
                continue
            files.append(p)

    seen = set()
    scan_files = []
    for f in files:
        rel = f.relative_to(root).as_posix()
        if rel in seen:
            continue
        seen.add(rel)
        if rel in {
            "tools/validate_ontology_claim_language.py",
            "outputs/btc_icft/ontology_claim_language_validation.json",
            "outputs/btc_icft/ontology_claim_language_validation.md",
        }:
            continue
        scan_files.append(f)

    violations = []
    forbidden_count = 0
    unsafe_count = 0

    for path in scan_files:
        rel = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        low = text.lower()
        lines = text.splitlines()

        for i, line in enumerate(lines, start=1):
            ll = line.lower()
            if path.suffix.lower() == ".md" and _in_guardrail_section(lines, i - 1):
                continue
            for phrase in FORBIDDEN_PHRASES:
                if phrase in ll:
                    if path.suffix.lower() in {".json", ".yaml", ".yml"} and ("forbidden" in ll or "banned" in ll):
                        continue
                    violations.append({"path": rel, "line": i, "phrase": phrase, "category": "forbidden_phrase", "severity": "error", "context": _sanitize(line.strip()[:160])})
                    forbidden_count += 1
            for category, patterns in UNSAFE_MAPPINGS.items():
                for phrase in patterns:
                    if phrase in ll:
                        violations.append({"path": rel, "line": i, "phrase": phrase, "category": category, "severity": "error", "context": _sanitize(line.strip()[:160])})
                        unsafe_count += 1

    ok = len(violations) == 0
    report = {
        "ok": ok,
        "validator": VALIDATOR,
        "version": VERSION,
        "root": str(root),
        "scanned_files": len(scan_files),
        "violations": violations,
        "warnings": [],
        "skipped_roots": skipped_roots,
        "forbidden_phrase_count": forbidden_count,
        "unsafe_mapping_count": unsafe_count,
    }

    json_out = root / args.json_out
    md_out = root / args.markdown_out
    json_out.parent.mkdir(parents=True, exist_ok=True)
    md_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Ontology Claim-Language Validation", "", "## Summary", "",
        f"- Status: {'PASS' if ok else 'FAIL'}",
        f"- Scanned files: {len(scan_files)}",
        f"- Violations: {len(violations)}",
        "", "## Violations", "",
    ]
    if violations:
        for v in violations:
            lines.append(f"- `{v['path']}:{v['line']}` [{v['category']}] `{_sanitize(v['phrase'])}`")
    else:
        lines.append("- None")
    lines += ["", "## Warnings", "", "- None", "", "## Scanned roots", "", f"- `{args.docs_root}`", *[f"- `{r}`" for r in args.output_roots], "", "## Safe language reminder", "", "- Prefer benchmark and governance language; avoid ontology/metaphysical certainty claims."]
    md_out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if not args.quiet:
        print("PASS ontology claim-language validation" if ok else "FAIL ontology claim-language validation")
    return (0 if ok else 1), report


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate ontology claim language across repo docs and outputs.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--output-roots", action="append", default=["outputs/btc_icft"])
    parser.add_argument("--docs-root", default="docs")
    parser.add_argument("--json-out", default="outputs/btc_icft/ontology_claim_language_validation.json")
    parser.add_argument("--markdown-out", default="outputs/btc_icft/ontology_claim_language_validation.md")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--include-repo-docs", type=_parse_bool, default=True)
    parser.add_argument("--include-outputs", type=_parse_bool, default=True)
    parser.add_argument("--include-tests", action="store_true")
    try:
        code, _ = validate(parser.parse_args())
        return code
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
