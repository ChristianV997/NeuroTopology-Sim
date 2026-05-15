#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

VERSION = "0.3"
VALIDATOR = "ontology_claim_language"

FORBIDDEN_PHRASES = [
    "proves consciousness", "consciousness proven", "soul proven", "afterlife proven",
    "liberation detected", "ontology solved", "ultimate reality", "q equals self",
    "q equals soul", "q_abs equals suffering", "f_dress equals karma",
    "sedated implies no_experience", "unresponsive implies unconscious",
    "topology proves liberation", "eeg proves consciousness",
]

UNSAFE_MAPPINGS = {
    "metric_to_ontology_shortcut": ["auc proves", "delta_auc proves", "q_net proves", "q_abs proves", "f_dress proves", "topology proves", "eeg proves"],
    "state_label_shortcut": ["sedated means no_experience", "unresponsive means unconscious", "loc means no experience", "roc means consciousness returned"],
    "forbidden_equivalence": ["q = self", "q = soul", "q_abs = suffering", "f_dress = karma", "topology = consciousness", "eeg = consciousness"],
}

SKIP_DIRS = {".git", ".venv", "venv", "env", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
SCAN_SUFFIXES = {".md", ".txt", ".json", ".yaml", ".yml"}
SECTION_SKIP_TERMS = ("forbidden", "guardrail", "blocked", "cannot be claimed", "unsafe examples")


def _parse_bool(value: str) -> bool:
    v = str(value).strip().lower()
    if v in {"1", "true", "yes", "y", "on"}:
        return True
    if v in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"Invalid boolean: {value}")


def _iter_files(root: Path, include_tests: bool):
    if not root.exists():
        return
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if set(p.parts) & SKIP_DIRS:
            continue
        if not include_tests and "tests" in p.parts:
            continue
        if p.suffix.lower() in SCAN_SUFFIXES:
            yield p


def _sanitize(s: str) -> str:
    return s.replace(" ", "·")


def _markdown_skip_mask(lines: list[str]) -> list[bool]:
    mask = [False] * len(lines)
    stack: list[tuple[int, bool]] = []
    for idx, line in enumerate(lines):
        m = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$", line)
        if m:
            level = len(m.group(1))
            heading = m.group(2).strip().lower()
            while stack and stack[-1][0] >= level:
                stack.pop()
            own_skip = any(term in heading for term in SECTION_SKIP_TERMS)
            parent_skip = stack[-1][1] if stack else False
            stack.append((level, own_skip or parent_skip))
        mask[idx] = stack[-1][1] if stack else False
    return mask


def _load_baseline(path: Path) -> tuple[list[dict], set[tuple[str, str, str]]]:
    if not path.exists():
        return [], set()
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("entries", [])
    keys = {(e.get("path", ""), e.get("phrase", ""), e.get("category", "")) for e in entries}
    return entries, keys


DS005620_GENERATED_ROOTS = [
    "outputs/btc_icft/ds005620_real_benchmark_execution_mock",
    "outputs/btc_icft/ds005620_ontology_evaluation_mock",
    "outputs/btc_icft/science_runtime_inspection",
    "outputs/btc_icft/ds005620_real_local_preflight",
    "outputs/btc_icft/ds005620_real_execution_gate",
    "outputs/btc_icft/ds005620_publication_package",
    "outputs/btc_icft/ds005620_real_controls",
    "outputs/btc_icft/ds005620_claim_promotion",
]

def _collect_files(root: Path, args: argparse.Namespace) -> tuple[list[Path], list[str], list[str]]:
    files: list[Path] = []
    skipped_roots: list[str] = []
    scanned_generated_roots: list[str] = []
    mode = args.scan_mode
    include_docs = mode in {"repo", "docs"}
    include_outputs = mode in {"repo", "outputs", "generated"} or args.strict_outputs
    include_repo = mode == "repo"

    if include_docs:
        files.extend(_iter_files(root / args.docs_root, args.include_tests) or [])
    if include_outputs:
        output_roots = args.output_roots
        if mode == "generated" and args.generated_output_profile == "ds005620":
            output_roots = DS005620_GENERATED_ROOTS
        for out in output_roots:
            out_root = root / out
            if out_root.exists():
                files.extend(_iter_files(out_root, args.include_tests) or [])
                if mode == "generated":
                    scanned_generated_roots.append(str(Path(out)))
            else:
                skipped_roots.append(str(Path(out)))
    if include_repo:
        for p in _iter_files(root, args.include_tests) or []:
            files.append(p)

    seen = set()
    scan_files = []
    excluded = {"tools/validate_ontology_claim_language.py", args.json_out, args.markdown_out}
    if args.write_baseline:
        excluded.add(args.write_baseline)
    for f in files:
        rel = f.relative_to(root).as_posix()
        if rel in seen or rel in excluded:
            continue
        if rel.startswith("outputs/btc_icft/") and any(k in rel for k in ["ontology_claim_language_validation", "claim_language_baseline_candidate", "/tmp."]):
            continue
        seen.add(rel)
        scan_files.append(f)
    return scan_files, skipped_roots, scanned_generated_roots


def validate(args: argparse.Namespace) -> tuple[int, dict]:
    root = Path(args.root).resolve()
    if args.strict_outputs and args.no_baseline:
        baseline_entries, baseline_keys = [], set()
    elif args.no_baseline:
        baseline_entries, baseline_keys = [], set()
    else:
        baseline_entries, baseline_keys = _load_baseline(root / args.baseline)

    scan_files, skipped_roots, scanned_generated_roots = _collect_files(root, args)

    all_violations: list[dict] = []
    forbidden_count = 0
    unsafe_count = 0

    for path in scan_files:
        rel = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        lines = text.splitlines()
        md_skip = _markdown_skip_mask(lines) if path.suffix.lower() == ".md" else [False] * len(lines)

        for i, line in enumerate(lines, start=1):
            ll = line.lower()
            if path.suffix.lower() == ".md" and md_skip[i - 1]:
                continue
            for phrase in FORBIDDEN_PHRASES:
                if phrase in ll:
                    if path.suffix.lower() in {".json", ".yaml", ".yml"} and any(k in ll for k in ["forbidden", "banned", "blocked", "cannot be claimed", "unsafe examples"]):
                        continue
                    all_violations.append({"path": rel, "line": i, "phrase": phrase, "category": "forbidden_phrase", "severity": "error", "context": _sanitize(line.strip()[:160])})
                    forbidden_count += 1
            for category, patterns in UNSAFE_MAPPINGS.items():
                for phrase in patterns:
                    if phrase in ll:
                        all_violations.append({"path": rel, "line": i, "phrase": phrase, "category": category, "severity": "error", "context": _sanitize(line.strip()[:160])})
                        unsafe_count += 1

    baselined, violations = [], []
    for v in all_violations:
        if (v["path"], v["phrase"], v["category"]) in baseline_keys:
            baselined.append(v)
        else:
            violations.append(v)

    if args.write_baseline:
        candidate = {
            "baseline_version": "0.1",
            "purpose": "Known legacy ontology-language findings allowed only until cleaned up.",
            "entries": [
                {
                    "path": v["path"], "line": None, "phrase": v["phrase"], "category": v["category"],
                    "reason": "pending_review", "expires": None, "owner": "repo",
                }
                for v in all_violations
            ],
        }
        p = root / args.write_baseline
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(candidate, indent=2) + "\n", encoding="utf-8")

    ok = len(violations) == 0 and (not args.fail_on_baseline or len(baselined) == 0)
    report = {
        "ok": ok,
        "validator": VALIDATOR,
        "version": VERSION,
        "root": str(root),
        "scanned_files": len(scan_files),
        "violations": violations,
        "baselined_violations": baselined,
        "warnings": [],
        "skipped_roots": skipped_roots,
        "baseline_path": None if args.no_baseline else args.baseline,
        "baseline_entries_loaded": len(baseline_entries),
        "unbaselined_violation_count": len(violations),
        "baselined_violation_count": len(baselined),
        "fail_on_baseline": bool(args.fail_on_baseline),
        "strict_outputs": bool(args.strict_outputs),
        "scan_mode": args.scan_mode,
        "forbidden_phrase_count": forbidden_count,
        "unsafe_mapping_count": unsafe_count,
        "generated_output_profile": args.generated_output_profile,
        "scanned_generated_roots": scanned_generated_roots,
        "missing_generated_roots": skipped_roots if args.scan_mode == "generated" else [],
    }

    json_out = root / args.json_out
    md_out = root / args.markdown_out
    json_out.parent.mkdir(parents=True, exist_ok=True)
    md_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    md = ["# Ontology Claim-Language Validation", "", "## Summary", "", f"- Status: {'PASS' if ok else 'FAIL'}", f"- Scan mode: `{args.scan_mode}`", f"- Unbaselined violations: {len(violations)}", f"- Baselined legacy findings: {len(baselined)}", "", "## Unbaselined violations", ""]
    if violations:
        md += [f"- `{v['path']}:{v['line']}` [{v['category']}] `{_sanitize(v['phrase'])}`" for v in violations]
    else:
        md.append("- None")
    md += ["", "## Baselined legacy findings", ""]
    if baselined:
        md += [f"- `{v['path']}:{v['line']}` [{v['category']}] `{_sanitize(v['phrase'])}`" for v in baselined]
    else:
        md.append("- None")
    md += ["", "## Skipped roots", ""] + ([f"- `{r}`" for r in skipped_roots] or ["- None"])
    if args.scan_mode == "generated":
        md += ["", "## Scanned generated roots", ""] + ([f"- `{r}`" for r in scanned_generated_roots] or ["- None"])
        md += ["", "## Missing generated roots", ""] + ([f"- `{r}`" for r in skipped_roots] or ["- None"])
    md += ["", "## Cleanup recommendation", "", "- Keep baseline entries narrow and temporary; fix generated artifacts instead of waiving them."]
    md_out.write_text("\n".join(md) + "\n", encoding="utf-8")

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
    parser.add_argument("--baseline", default="contracts/btc_icft/ontology_claims/claim_language_baseline.json")
    parser.add_argument("--no-baseline", action="store_true")
    parser.add_argument("--write-baseline")
    parser.add_argument("--fail-on-baseline", action="store_true")
    parser.add_argument("--strict-outputs", action="store_true")
    parser.add_argument("--scan-mode", choices=["repo", "docs", "outputs", "generated"], default="repo")
    parser.add_argument("--generated-output-profile", choices=["generic", "ds005620"], default="generic")
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
