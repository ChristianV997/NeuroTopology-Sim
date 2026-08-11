"""BenchmarkRegistry -- load/validate/query/mark/lock over a benchmark
dataset+artifact registry JSON file, plus the CLI for all of the above.

Usage::

    # dump the (validated) seed registry to a consolidated output file
    python -m benchmarks.export_registry --out outputs/benchmarks/dataset_registry.json

    # validate a registry file
    python -m benchmarks.export_registry --registry benchmarks/registry_seed.json --validate

    # list / query
    python -m benchmarks.export_registry --list-datasets
    python -m benchmarks.export_registry --list-artifacts
    python -m benchmarks.export_registry --check-use ds005620 transition_export
    python -m benchmarks.export_registry --check-use ds005620 final_claim_confirmation

    # mutate (always requires --out; never silently overwrites the input file)
    python -m benchmarks.export_registry --mark-seen ds005620 --seen-by llm --out /tmp/updated.json
    python -m benchmarks.export_registry --lock-for-validation <artifact_id> \\
        --claim-family propofol_awake_sedated_transition --reason "preregistered replication" \\
        --locked-by operator --out /tmp/updated.json

This is the package's only CLI entry point. `benchmarks.dataset_registry`
and `benchmarks.artifact_registry` are library-only (dataclasses +
serialization), matching how `transitions.record.TransitionRecordV1` has no
CLI of its own even though `transitions.export_from_results` does.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional, Union

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from benchmarks.artifact_registry import ArtifactRecordV1  # noqa: E402
from benchmarks.dataset_registry import DatasetRecordV1  # noqa: E402
from benchmarks.holdout_lock import consume_validation_lock, lock_for_validation  # noqa: E402
from benchmarks.split_policy import can_use_artifact, can_use_dataset, mark_seen  # noqa: E402

_SCHEMA = "NeuroTopologySim.BenchmarkRegistry.v1"
_DEFAULT_SEED = _REPO_ROOT / "benchmarks" / "registry_seed.json"

Record = Union[DatasetRecordV1, ArtifactRecordV1]


class RegistryError(ValueError):
    """Raised for registry-file-level problems (missing id, bad JSON shape, ...)."""


class BenchmarkRegistry:
    def __init__(
        self,
        datasets: Optional[dict[str, DatasetRecordV1]] = None,
        artifacts: Optional[dict[str, ArtifactRecordV1]] = None,
    ) -> None:
        self.datasets: dict[str, DatasetRecordV1] = dict(datasets or {})
        self.artifacts: dict[str, ArtifactRecordV1] = dict(artifacts or {})

    # ── load/save ────────────────────────────────────────────────────────

    @classmethod
    def load(cls, path: Union[str, Path]) -> "BenchmarkRegistry":
        path = Path(path)
        if not path.exists():
            raise RegistryError(f"registry file does not exist: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        datasets = {
            d["dataset_id"]: DatasetRecordV1.from_dict(d) for d in data.get("datasets") or []
        }
        artifacts = {
            a["artifact_id"]: ArtifactRecordV1.from_dict(a) for a in data.get("artifacts") or []
        }
        return cls(datasets, artifacts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": _SCHEMA,
            "datasets": [self.datasets[k].to_dict() for k in sorted(self.datasets)],
            "artifacts": [self.artifacts[k].to_dict() for k in sorted(self.artifacts)],
        }

    def save(self, path: Union[str, Path]) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=False) + "\n", encoding="utf-8")
        return path

    # ── validation ───────────────────────────────────────────────────────

    def validate(self, *, repo_root: Optional[Path] = None) -> dict[str, list[str]]:
        """Return {record_key: [errors]} for every record that fails validation."""
        errors: dict[str, list[str]] = {}
        for dataset_id, record in self.datasets.items():
            record_errors = record.validate()
            if record_errors:
                errors[f"dataset:{dataset_id}"] = record_errors
        for artifact_id, record in self.artifacts.items():
            record_errors = record.validate(repo_root=repo_root)
            if record_errors:
                errors[f"artifact:{artifact_id}"] = record_errors
        return errors

    # ── query ────────────────────────────────────────────────────────────

    def list_datasets(
        self, *, role: Optional[str] = None, modality: Optional[str] = None
    ) -> list[DatasetRecordV1]:
        out = list(self.datasets.values())
        if role is not None:
            out = [r for r in out if r.current_role == role]
        if modality is not None:
            out = [r for r in out if modality in r.modalities]
        return sorted(out, key=lambda r: r.dataset_id)

    def list_artifacts(
        self,
        *,
        role: Optional[str] = None,
        modality: Optional[str] = None,
        dataset_id: Optional[str] = None,
    ) -> list[ArtifactRecordV1]:
        out = list(self.artifacts.values())
        if role is not None:
            out = [r for r in out if r.current_role == role]
        if modality is not None:
            out = [r for r in out if r.modality == modality]
        if dataset_id is not None:
            out = [r for r in out if r.dataset_id == dataset_id]
        return sorted(out, key=lambda r: r.artifact_id)

    def get(self, record_id: str) -> Record:
        """Look up a record by dataset_id or artifact_id (datasets checked first)."""
        if record_id in self.datasets:
            return self.datasets[record_id]
        if record_id in self.artifacts:
            return self.artifacts[record_id]
        raise RegistryError(f"no dataset or artifact record with id '{record_id}'")

    # ── use-policy / contamination / locking ────────────────────────────

    def check_use(
        self, record_id: str, requested_use: str, *, claim_family: Optional[str] = None
    ) -> tuple[bool, str]:
        record = self.get(record_id)
        checker = can_use_dataset if record_id in self.datasets else can_use_artifact
        return checker(record, requested_use, claim_family=claim_family)

    def mark_seen(self, record_id: str, *, seen_by: str, note: Optional[str] = None) -> Record:
        return mark_seen(self.get(record_id), seen_by=seen_by, note=note)

    def lock_for_validation(
        self, record_id: str, *, locked_by: str, reason: str, claim_family: str
    ) -> Record:
        return lock_for_validation(
            self.get(record_id), locked_by=locked_by, reason=reason, claim_family=claim_family
        )

    def consume_validation_lock(
        self, record_id: str, *, claim_family: str, consumed_by: str
    ) -> Record:
        return consume_validation_lock(
            self.get(record_id), claim_family=claim_family, consumed_by=consumed_by
        )


# ── CLI ──────────────────────────────────────────────────────────────────


def _print_record_summary(record: Record) -> dict[str, Any]:
    is_dataset = isinstance(record, DatasetRecordV1)
    return {
        "id": record.dataset_id if is_dataset else record.artifact_id,
        "kind": "dataset" if is_dataset else "artifact",
        "current_role": record.current_role,
        "contamination_status": record.contamination_status,
        "claim_scope_ceiling": record.claim_scope_ceiling,
        "evidence_level_ceiling": record.evidence_level_ceiling,
        "allowed_uses": sorted(record.allowed_uses),
        "forbidden_uses": sorted(record.forbidden_uses),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--registry", type=Path, default=_DEFAULT_SEED,
        help=f"registry JSON to load (default: {_DEFAULT_SEED.relative_to(_REPO_ROOT)})",
    )
    parser.add_argument("--out", type=Path, default=None, help="write the (updated) registry here")
    parser.add_argument("--validate", action="store_true", help="validate every record in the registry")
    parser.add_argument("--list-datasets", action="store_true")
    parser.add_argument("--list-artifacts", action="store_true")
    parser.add_argument("--check-use", nargs=2, metavar=("ID", "USE"), default=None)
    parser.add_argument("--claim-family", default=None, help="claim family for --check-use / lock operations")
    parser.add_argument("--mark-seen", metavar="ID", default=None)
    parser.add_argument("--seen-by", default=None, choices=("exploration", "llm", "theory_generation", "model_selection"))
    parser.add_argument("--note", default=None)
    parser.add_argument("--lock-for-validation", metavar="ID", default=None)
    parser.add_argument("--locked-by", default=None)
    parser.add_argument("--reason", default=None)
    parser.add_argument("--consume-validation-lock", metavar="ID", default=None)
    parser.add_argument("--consumed-by", default=None)
    args = parser.parse_args()

    try:
        registry = BenchmarkRegistry.load(args.registry)
    except RegistryError as exc:
        print(f"[benchmarks.export_registry] FAILED: {exc}")
        return 1

    mutated = False

    if args.validate:
        errors = registry.validate()
        if errors:
            print(json.dumps({"valid": False, "errors": errors}, indent=2))
            return 1
        print(json.dumps({"valid": True, "datasets": len(registry.datasets), "artifacts": len(registry.artifacts)}, indent=2))

    if args.list_datasets:
        print(json.dumps([_print_record_summary(r) for r in registry.list_datasets()], indent=2))

    if args.list_artifacts:
        print(json.dumps([_print_record_summary(r) for r in registry.list_artifacts()], indent=2))

    if args.check_use:
        record_id, requested_use = args.check_use
        try:
            allowed, reason = registry.check_use(record_id, requested_use, claim_family=args.claim_family)
        except RegistryError as exc:
            print(f"[benchmarks.export_registry] FAILED: {exc}")
            return 1
        print(json.dumps({"id": record_id, "requested_use": requested_use, "allowed": allowed, "reason": reason}, indent=2))
        if not allowed:
            return 1

    if args.mark_seen:
        if not args.seen_by:
            print("[benchmarks.export_registry] FAILED: --mark-seen requires --seen-by")
            return 1
        try:
            registry.mark_seen(args.mark_seen, seen_by=args.seen_by, note=args.note)
        except (RegistryError, ValueError) as exc:
            print(f"[benchmarks.export_registry] FAILED: {exc}")
            return 1
        mutated = True

    if args.lock_for_validation:
        if not args.claim_family or not args.reason or not args.locked_by:
            print("[benchmarks.export_registry] FAILED: --lock-for-validation requires --claim-family, --reason, and --locked-by")
            return 1
        try:
            registry.lock_for_validation(
                args.lock_for_validation, locked_by=args.locked_by, reason=args.reason, claim_family=args.claim_family
            )
        except (RegistryError, ValueError) as exc:
            print(f"[benchmarks.export_registry] FAILED: {exc}")
            return 1
        mutated = True

    if args.consume_validation_lock:
        if not args.claim_family or not args.consumed_by:
            print("[benchmarks.export_registry] FAILED: --consume-validation-lock requires --claim-family and --consumed-by")
            return 1
        try:
            registry.consume_validation_lock(
                args.consume_validation_lock, claim_family=args.claim_family, consumed_by=args.consumed_by
            )
        except (RegistryError, ValueError) as exc:
            print(f"[benchmarks.export_registry] FAILED: {exc}")
            return 1
        mutated = True

    if mutated and not args.out:
        print("[benchmarks.export_registry] FAILED: mutating operations require --out (never silently overwrites the input registry)")
        return 1

    no_action = not any([
        args.validate, args.list_datasets, args.list_artifacts, args.check_use,
        args.mark_seen, args.lock_for_validation, args.consume_validation_lock,
    ])

    if args.out and (mutated or no_action):
        errors = registry.validate()
        written = registry.save(args.out)
        print(json.dumps({
            "out": str(written),
            "datasets": len(registry.datasets),
            "artifacts": len(registry.artifacts),
            "valid": not errors,
        }, indent=2))
        if errors:
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
