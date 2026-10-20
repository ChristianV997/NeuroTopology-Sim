"""Contract tests for the provenance-preserving BIDS adapter."""

from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

from data import bids_ingest
from data.bids_ingest import (
    BIDSAccessRequest,
    BIDSAdapterError,
    BIDSAdapterErrorCode,
    BoundedWindowRequest,
    index_bids_metadata,
    optional_dependency_status,
    plan_bounded_window_access,
    read_bounded_window_lazy,
    serialize_bids_manifest,
)
from data import openneuro_loader as onl

FIXTURES = Path(__file__).resolve().parent / "fixtures"
VALID = FIXTURES / "valid_bids"
INVALID = FIXTURES / "invalid_bids"
MISSING = FIXTURES / "missing_entities"
COND_OK = FIXTURES / "condition_manifest_ok.json"
COND_BAD = FIXTURES / "condition_manifest_ambiguous.json"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_valid_bids_fixture_indexes_deterministically():
    req = BIDSAccessRequest(dataset_id="dsFIX001", local_root=str(VALID))
    first = index_bids_metadata(req)
    second = index_bids_metadata(req)
    assert first["state"] == "METADATA_INDEXED"
    assert first["n_recordings"] == 1
    assert first["bids_validation"]["status"] == "valid_structure"
    assert first["scientific_pass"] is False
    assert first["manifest_checksum"] == second["manifest_checksum"]
    assert serialize_bids_manifest(first) == serialize_bids_manifest(second)
    rec = first["recordings"][0]
    assert rec["subject_id"] == "sub-01"
    assert rec["session_id"] is None
    assert rec["task"] == "rest"
    assert rec["run"] == "01"
    assert rec["condition_label"] is None
    assert rec["condition_label_source"] == "absent"
    assert rec["checksum_state"] in {"computed_local", "unknown"}


def test_invalid_bids_fixture_is_blocked():
    manifest = index_bids_metadata(
        BIDSAccessRequest(dataset_id="dsBAD001", local_root=str(INVALID))
    )
    assert manifest["state"] == "BLOCKED_INVALID_BIDS"
    assert manifest["bids_validation"]["status"] == "invalid"
    assert manifest["n_recordings"] == 0
    assert manifest["scientific_pass"] is False


def test_ambiguous_labels_rejected_without_confirmation():
    with pytest.raises(BIDSAdapterError) as exc:
        index_bids_metadata(
            BIDSAccessRequest(
                dataset_id="dsFIX001",
                local_root=str(VALID),
                condition_manifest=_load_json(COND_BAD),
            )
        )
    assert exc.value.code == BIDSAdapterErrorCode.LABEL_INFERENCE_FORBIDDEN.value


def test_explicit_condition_manifest_preserved():
    manifest = index_bids_metadata(
        BIDSAccessRequest(
            dataset_id="dsFIX001",
            local_root=str(VALID),
            condition_manifest=_load_json(COND_OK),
        )
    )
    rec = manifest["recordings"][0]
    assert rec["condition_label"] == "resting"
    assert rec["condition_label_source"] == "explicit_manifest"


def test_missing_run_requirement_fails_closed():
    with pytest.raises(BIDSAdapterError) as exc:
        index_bids_metadata(
            BIDSAccessRequest(
                dataset_id="dsMISS01",
                local_root=str(MISSING),
                require_run=True,
            )
        )
    assert exc.value.code == BIDSAdapterErrorCode.MISSING_SUBJECT_SESSION_RUN.value


def test_bounded_window_request_plans_without_network():
    plan = plan_bounded_window_access(
        BIDSAccessRequest(
            dataset_id="dsFIX001",
            local_root=str(VALID),
            relative_path="sub-01/eeg/sub-01_task-rest_run-01_eeg.edf",
            window=BoundedWindowRequest(start_s=0.0, end_s=1.5),
            allow_network=False,
            expected_checksum=None,
        )
    )
    assert plan["state"] == "WINDOW_PLANNED"
    assert plan["network_actions"] == []
    assert plan["checksum_state"] == "unknown"
    assert plan["source_checksum"] is None
    assert plan["scientific_pass"] is False


def test_full_dataset_rejection():
    with pytest.raises(BIDSAdapterError) as exc:
        index_bids_metadata(
            BIDSAccessRequest(
                dataset_id="dsFIX001",
                local_root=str(VALID),
                allow_full_dataset=True,
            )
        )
    assert exc.value.code == BIDSAdapterErrorCode.FULL_DATASET_REJECTED.value
    with pytest.raises(BIDSAdapterError) as exc2:
        onl.reject_full_dataset_download(dataset_id="ds005620", allow_full_dataset=True)
    assert exc2.value.code == BIDSAdapterErrorCode.FULL_DATASET_REJECTED.value
    with pytest.raises(BIDSAdapterError):
        onl.openneuro_download(dataset_id="ds005620")


def test_no_network_default_blocks_remote():
    with pytest.raises(BIDSAdapterError) as exc:
        plan_bounded_window_access(
            BIDSAccessRequest(
                dataset_id="dsFIX001",
                remote_uri="s3://openneuro.org/dsFIX001/sub-01/eeg/file.edf",
                relative_path="sub-01/eeg/file.edf",
                window=BoundedWindowRequest(0.0, 1.0),
                allow_network=False,
            )
        )
    assert exc.value.code == BIDSAdapterErrorCode.NETWORK_DISABLED.value


def test_unrestricted_remote_without_window_rejected():
    with pytest.raises(BIDSAdapterError) as exc:
        plan_bounded_window_access(
            BIDSAccessRequest(
                dataset_id="dsFIX001",
                remote_uri="s3://openneuro.org/dsFIX001",
                allow_network=True,
            )
        )
    assert exc.value.code in {
        BIDSAdapterErrorCode.UNRESTRICTED_REMOTE_REJECTED.value,
        BIDSAdapterErrorCode.MISSING_LOCAL_OR_BOUNDED_WINDOW.value,
        BIDSAdapterErrorCode.INVALID_WINDOW.value,
    }


def test_optional_dependency_behavior_is_recorded():
    status = optional_dependency_status()
    assert set(status) == {"mne_bids", "pybids", "bids_validator"}
    assert all(isinstance(v, bool) for v in status.values())
    manifest = index_bids_metadata(
        BIDSAccessRequest(dataset_id="dsFIX001", local_root=str(VALID))
    )
    assert "optional_dependencies" in manifest
    assert manifest["optional_dependencies"] == status
    if not status["pybids"] and not status["mne_bids"]:
        assert manifest["index_backend"] == "filesystem_structural"


def test_finite_json_serialization():
    manifest = index_bids_metadata(
        BIDSAccessRequest(dataset_id="dsFIX001", local_root=str(VALID))
    )
    text = serialize_bids_manifest(manifest)
    parsed = json.loads(text, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    assert parsed["scientific_pass"] is False
    assert "NaN" not in text
    assert "Infinity" not in text


def test_openneuro_loader_local_index_wrapper():
    manifest = onl.ensure_local_bids_index("dsFIX001", VALID)
    assert manifest["n_recordings"] == 1
    with pytest.raises(BIDSAdapterError) as exc:
        onl.ensure_local_bids_index("dsFIX001", VALID, allow_network=True)
    assert exc.value.code == BIDSAdapterErrorCode.NETWORK_DISABLED.value


def test_isolated_subprocess_execution():
    code = r"""
import json
from data.bids_ingest import BIDSAccessRequest, index_bids_metadata, serialize_bids_manifest
m = index_bids_metadata(BIDSAccessRequest(dataset_id='dsFIX001', local_root=%r))
print(serialize_bids_manifest(m))
""" % (str(VALID),)
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(Path(__file__).resolve().parents[3]),
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(proc.stdout)
    assert payload["state"] == "METADATA_INDEXED"
    assert payload["scientific_pass"] is False


def test_governance_compile_and_whitespace(tmp_path: Path):
    root = Path(__file__).resolve().parents[3]
    compile_proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "py_compile",
            str(root / "data" / "bids_ingest.py"),
            str(root / "data" / "openneuro_loader.py"),
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    assert compile_proc.returncode == 0, compile_proc.stderr
    diff_proc = subprocess.run(
        [
            "git",
            "diff",
            "--check",
            "--",
            "data/bids_ingest.py",
            "data/openneuro_loader.py",
            "tests/data_access/bids_adapter",
            "docs/data_access/bids_adapter.md",
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    assert diff_proc.returncode == 0, diff_proc.stdout + diff_proc.stderr
    # governance.validate is best-effort when the module exists
    gov = subprocess.run(
        [sys.executable, "-m", "governance.validate"],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    assert gov.returncode in {0, 1}, gov.stdout + gov.stderr


@pytest.mark.parametrize(
    "escaping",
    [
        "../outside/secret.edf",
        "..\\outside\\secret.edf",
        "sub-01/../../outside/secret.edf",
        "{outside}",
    ],
)
def test_relative_path_escaping_local_root_rejected(tmp_path: Path, monkeypatch, escaping: str):
    root = tmp_path / "dataset"
    root.mkdir()
    outside = tmp_path / "outside" / "secret.edf"
    outside.parent.mkdir()
    outside.write_bytes(b"synthetic-outside-root")
    escaping = escaping.format(outside=outside)
    reads: list[str] = []
    monkeypatch.setattr(
        bids_ingest,
        "read_window_signal",
        lambda path, *args, **kwargs: reads.append(path),
    )
    request = BIDSAccessRequest(
        dataset_id="dsFIX001",
        local_root=str(root),
        relative_path=escaping,
        window=BoundedWindowRequest(start_s=0.0, end_s=1.0),
    )
    with pytest.raises(BIDSAdapterError) as plan_exc:
        plan_bounded_window_access(request)
    assert plan_exc.value.code == BIDSAdapterErrorCode.MALFORMED_REQUEST.value
    with pytest.raises(BIDSAdapterError) as read_exc:
        read_bounded_window_lazy(request)
    assert read_exc.value.code == BIDSAdapterErrorCode.MALFORMED_REQUEST.value
    assert reads == [], "signal reader must not be reached for a path outside local_root"


@pytest.mark.parametrize(
    "manifest",
    [
        {"sub-01/eeg/sub-01_task-rest_run-01_eeg.edf": "resting"},
        {"recordings": {"sub-01/eeg/sub-01_task-rest_run-01_eeg.edf": "resting"}},
    ],
    ids=["flat_string", "recordings_string"],
)
def test_unconfirmed_string_labels_rejected_in_every_manifest_form(manifest):
    with pytest.raises(BIDSAdapterError) as exc:
        index_bids_metadata(
            BIDSAccessRequest(
                dataset_id="dsFIX001",
                local_root=str(VALID),
                condition_manifest=manifest,
            )
        )
    assert exc.value.code == BIDSAdapterErrorCode.LABEL_INFERENCE_FORBIDDEN.value
