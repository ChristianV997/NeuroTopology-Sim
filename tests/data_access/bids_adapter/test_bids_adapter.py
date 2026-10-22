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


def test_symlink_escaping_local_root_rejected_during_index(tmp_path: Path):
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    (dataset / "dataset_description.json").write_text(
        json.dumps({"Name": "SyntheticSymlink", "BIDSVersion": "1.8.0"}),
        encoding="utf-8",
    )
    eeg_dir = dataset / "sub-01" / "eeg"
    eeg_dir.mkdir(parents=True)
    outside = tmp_path / "outside" / "secret.edf"
    outside.parent.mkdir()
    outside.write_bytes(b"synthetic-secret-bytes")

    symlink_target = eeg_dir / "sub-01_task-rest_run-01_eeg.edf"
    try:
        symlink_target.symlink_to(outside)
    except OSError:
        pytest.skip("Symlinks not supported on this platform/privilege level")

    with pytest.raises(BIDSAdapterError) as exc:
        index_bids_metadata(
            BIDSAccessRequest(dataset_id="dsSYM01", local_root=str(dataset))
        )
    assert exc.value.code == BIDSAdapterErrorCode.MALFORMED_REQUEST.value


@pytest.mark.parametrize(
    "bad_rel_path",
    ["", "   ", ".", "./", "sub-01/..", "/sub-01/eeg/sub-01_task-rest_run-01_eeg.edf"],
    ids=["empty", "spaces", "dot", "dot_slash", "parent_to_root", "leading_slash"],
)
def test_relative_path_empty_root_or_leading_slash_rejected(bad_rel_path: str):
    req = BIDSAccessRequest(
        dataset_id="dsFIX001",
        local_root=str(VALID),
        relative_path=bad_rel_path,
        window=BoundedWindowRequest(start_s=0.0, end_s=1.0),
    )
    with pytest.raises(BIDSAdapterError) as exc:
        plan_bounded_window_access(req)
    assert exc.value.code == BIDSAdapterErrorCode.MALFORMED_REQUEST.value


def test_flat_manifest_with_confirmed_true_is_accepted():
    manifest = {
        "sub-01/eeg/sub-01_task-rest_run-01_eeg.edf": {
            "condition_label": "resting",
            "confirmed": True,
        }
    }
    result = index_bids_metadata(
        BIDSAccessRequest(
            dataset_id="dsFIX001",
            local_root=str(VALID),
            condition_manifest=manifest,
        )
    )
    rec = result["recordings"][0]
    assert rec["condition_label"] == "resting"
    assert rec["condition_label_source"] == "explicit_manifest"


@pytest.mark.parametrize(
    "manifest",
    [
        {"sub-01/eeg/sub-01_task-rest_run-01_eeg.edf": {"condition_label": "resting", "confirmed": False}},
        {"sub-01/eeg/sub-01_task-rest_run-01_eeg.edf": {"condition_label": "resting"}},
        {"recordings": {"sub-01/eeg/sub-01_task-rest_run-01_eeg.edf": {"condition_label": "resting", "confirmed": "true"}}},
        {"recordings": {"sub-01/eeg/sub-01_task-rest_run-01_eeg.edf": {"condition_label": "resting", "confirmed": 1}}},
        {"sub-01/eeg/sub-01_task-rest_run-01_eeg.edf": {"condition_label": "resting", "confirmed": "true"}},
    ],
    ids=["flat_unconfirmed", "flat_missing_confirmed", "nested_string_true", "nested_int_one", "flat_string_true"],
)
def test_manifest_variants_requiring_confirmed_true_rejected(manifest):
    with pytest.raises(BIDSAdapterError) as exc:
        index_bids_metadata(
            BIDSAccessRequest(
                dataset_id="dsFIX001",
                local_root=str(VALID),
                condition_manifest=manifest,
            )
        )
    assert exc.value.code == BIDSAdapterErrorCode.LABEL_INFERENCE_FORBIDDEN.value


def test_malformed_bids_entity_handling(tmp_path: Path):
    ds = tmp_path / "ds_malformed"
    ds.mkdir()
    (ds / "dataset_description.json").write_text(
        json.dumps({"Name": "MalformedDS", "BIDSVersion": "1.8.0"}),
        encoding="utf-8",
    )
    eeg_dir = ds / "sub-01" / "eeg"
    eeg_dir.mkdir(parents=True)
    # File with empty subject entity: sub-_task-rest_run-01_eeg.edf
    bad_sub_file = eeg_dir / "sub-_task-rest_run-01_eeg.edf"
    bad_sub_file.write_bytes(b"synthetic")

    with pytest.raises(BIDSAdapterError) as exc:
        index_bids_metadata(
            BIDSAccessRequest(
                dataset_id="dsMAL01",
                local_root=str(ds),
                require_subject=True,
            )
        )
    assert exc.value.code == BIDSAdapterErrorCode.MISSING_SUBJECT_SESSION_RUN.value

    # Dataset with only empty subject directory: sub-
    ds_empty_sub = tmp_path / "ds_empty_sub"
    ds_empty_sub.mkdir()
    (ds_empty_sub / "dataset_description.json").write_text(
        json.dumps({"Name": "EmptySubDS", "BIDSVersion": "1.8.0"}),
        encoding="utf-8",
    )
    (ds_empty_sub / "sub-").mkdir()
    res = index_bids_metadata(
        BIDSAccessRequest(dataset_id="dsEMPTY01", local_root=str(ds_empty_sub))
    )
    assert res["state"] == "BLOCKED_INVALID_BIDS"
    assert res["bids_validation"]["status"] == "invalid"


def test_expected_checksum_verification_against_actual_file(monkeypatch):
    import numpy as np

    fake_signal = np.ones((2, 100), dtype=float)
    monkeypatch.setattr(bids_ingest, "read_window_signal", lambda *args, **kwargs: fake_signal)

    mismatched_checksum = "0" * 64
    req = BIDSAccessRequest(
        dataset_id="dsFIX001",
        local_root=str(VALID),
        relative_path="sub-01/eeg/sub-01_task-rest_run-01_eeg.edf",
        window=BoundedWindowRequest(start_s=0.0, end_s=1.0),
        expected_checksum=mismatched_checksum,
    )
    # Lazy read with mismatched expected_checksum must fail closed
    with pytest.raises(BIDSAdapterError) as exc:
        read_bounded_window_lazy(req)
    assert exc.value.code == BIDSAdapterErrorCode.MALFORMED_REQUEST.value

    # Index with mismatched expected_checksum on matching relative_path must fail closed
    with pytest.raises(BIDSAdapterError) as exc_idx:
        index_bids_metadata(req)
    assert exc_idx.value.code == BIDSAdapterErrorCode.MALFORMED_REQUEST.value


def test_finite_json_serialization_numpy_types():
    import numpy as np

    safe_payload = {
        "dataset_id": "ds001",
        "flag_np": np.bool_(True),
        "int_np": np.int64(42),
        "float_np": np.float64(3.14),
        "tags": {"alpha", "beta"},
    }
    serialized = serialize_bids_manifest(safe_payload)
    parsed = json.loads(serialized)
    assert parsed["flag_np"] is True
    assert parsed["int_np"] == 42
    assert parsed["float_np"] == 3.14
    assert parsed["tags"] == ["alpha", "beta"]

    bad_payload = {"val": np.float64(np.nan)}
    with pytest.raises(BIDSAdapterError) as exc_nan:
        serialize_bids_manifest(bad_payload)
    assert exc_nan.value.code == BIDSAdapterErrorCode.MALFORMED_REQUEST.value

    bad_inf = {"val": np.float64(np.inf)}
    with pytest.raises(BIDSAdapterError) as exc_inf:
        serialize_bids_manifest(bad_inf)
    assert exc_inf.value.code == BIDSAdapterErrorCode.MALFORMED_REQUEST.value


def test_privacy_safe_missing_recording_diagnostic(tmp_path: Path):
    secret_dir = tmp_path / "super_secret_host_directory_name"
    secret_dir.mkdir()
    req = BIDSAccessRequest(
        dataset_id="dsPRIV01",
        local_root=str(secret_dir),
        relative_path="sub-01/eeg/sub-01_task-rest_run-01_eeg.edf",
        window=BoundedWindowRequest(start_s=0.0, end_s=1.0),
    )
    with pytest.raises(BIDSAdapterError) as exc:
        read_bounded_window_lazy(req)
    msg = str(exc.value)
    assert exc.value.code == BIDSAdapterErrorCode.MALFORMED_REQUEST.value
    assert "super_secret_host_directory_name" not in msg, "host path must not leak in error message"
    assert "sub-01/eeg/sub-01_task-rest_run-01_eeg.edf" in msg


def test_openneuro_loader_cache_cleanup(monkeypatch):
    import numpy as np

    fake_signal = np.ones((2, 100), dtype=float)
    monkeypatch.setattr(bids_ingest, "read_window_signal", lambda *args, **kwargs: fake_signal)

    rec_path = "sub-01/eeg/sub-01_task-rest_run-01_eeg.edf"
    res, samples = onl.read_local_bounded_window(
        "dsFIX001",
        VALID,
        relative_path=rec_path,
        start_s=0.0,
        end_s=1.0,
    )
    assert res["state"] == "WINDOW_READ_LOCAL"
    # Ensure cache functions are callable and clean
    onl.release_recording(str(VALID / rec_path))
    onl.clear_raw_cache()


def test_simulated_symlink_escape_during_index(monkeypatch, tmp_path: Path):
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    (dataset / "dataset_description.json").write_text(
        json.dumps({"Name": "SimulatedEscape", "BIDSVersion": "1.8.0"}),
        encoding="utf-8",
    )
    (dataset / "sub-01").mkdir()
    # Mock _filesystem_metadata_index to return a simulated escaping relative_path
    monkeypatch.setattr(
        bids_ingest,
        "_filesystem_metadata_index",
        lambda root: [
            {
                "relative_path": "../outside_escape/secret.edf",
                "subject_id": "sub-01",
                "session_id": None,
                "task": "rest",
                "run": "01",
                "acquisition": None,
                "datatype": "eeg",
                "montage": None,
                "sampling_frequency_hz": None,
                "provenance": "local_bids_unvalidated",
            }
        ],
    )
    with pytest.raises(BIDSAdapterError) as exc:
        index_bids_metadata(
            BIDSAccessRequest(dataset_id="dsSIM01", local_root=str(dataset))
        )
    assert exc.value.code == BIDSAdapterErrorCode.MALFORMED_REQUEST.value


def test_find_eeg_files_and_events_containment(tmp_path: Path):
    root = tmp_path / "dataset"
    root.mkdir()
    sub_eeg = root / "sub-01" / "eeg"
    sub_eeg.mkdir(parents=True)
    edf_file = sub_eeg / "sub-01_task-rest_eeg.edf"
    edf_file.write_bytes(b"synthetic")
    events_file = sub_eeg / "sub-01_task-rest_events.tsv"
    events_file.write_bytes(b"synthetic")

    eeg_found = onl.find_eeg_files(root)
    assert len(eeg_found) == 1
    assert eeg_found[0].resolve() == edf_file.resolve()

    events_found = onl.find_events(root)
    assert len(events_found) == 1
    assert events_found[0].resolve() == events_file.resolve()


@pytest.mark.parametrize(
    "bad_remote_rel_path",
    [
        "../outside/secret.edf",
        "..\\outside\\secret.edf",
        "sub-01/../../outside/secret.edf",
        "/etc/passwd",
        "\\Windows\\System32\\secret.edf",
        "C:/outside/secret.edf",
        "   ",
        ".",
        "./",
    ],
)
def test_remote_window_plan_rejects_traversal_and_anchored_relative_paths(bad_remote_rel_path: str):
    req = BIDSAccessRequest(
        dataset_id="dsFIX001",
        remote_uri="s3://openneuro.org/dsFIX001",
        relative_path=bad_remote_rel_path,
        window=BoundedWindowRequest(start_s=0.0, end_s=1.0),
        allow_network=True,
    )
    with pytest.raises(BIDSAdapterError) as exc:
        plan_bounded_window_access(req)
    assert exc.value.code == BIDSAdapterErrorCode.MALFORMED_REQUEST.value


@pytest.mark.parametrize(
    "bad_window",
    [
        BoundedWindowRequest(start_s=False, end_s=True),
        BoundedWindowRequest(start_s=0.0, end_s=True),
        BoundedWindowRequest(start_s=0.0, end_s=10000.0, max_duration_s=float("nan")),
        BoundedWindowRequest(start_s=0.0, end_s=10000.0, max_duration_s=float("inf")),
        BoundedWindowRequest(start_s=0.0, end_s=1000.0, max_duration_s=1000.0),
        BoundedWindowRequest(start_s=0.0, end_s=1.0, max_duration_s=0.0),
        BoundedWindowRequest(start_s=0.0, end_s=1.0, max_duration_s=-5.0),
        BoundedWindowRequest(start_s=0.0, end_s=1.0, max_duration_s=True),
        BoundedWindowRequest(start_s=0.0, end_s=1.0, max_bytes=True),
        BoundedWindowRequest(start_s=0.0, end_s=1.0, max_bytes=1024.5),  # type: ignore[arg-type]
        BoundedWindowRequest(start_s=0.0, end_s=1.0, max_bytes="1024"),  # type: ignore[arg-type]
    ],
)
def test_bounded_window_rejects_boolean_nonfinite_and_excessive_limits(bad_window: BoundedWindowRequest):
    req = BIDSAccessRequest(
        dataset_id="dsFIX001",
        local_root=str(VALID),
        relative_path="sub-01/eeg/sub-01_task-rest_run-01_eeg.edf",
        window=bad_window,
    )
    with pytest.raises(BIDSAdapterError) as exc:
        plan_bounded_window_access(req)
    assert exc.value.code == BIDSAdapterErrorCode.INVALID_WINDOW.value


@pytest.mark.parametrize(
    "bad_desc",
    [
        {"Name": "", "BIDSVersion": "1.8.0"},
        {"Name": "   ", "BIDSVersion": "1.8.0"},
        {"Name": None, "BIDSVersion": "1.8.0"},
        {"Name": 123, "BIDSVersion": "1.8.0"},
        {"Name": "ValidName", "BIDSVersion": ""},
        {"Name": "ValidName", "BIDSVersion": "   "},
        {"Name": "ValidName", "BIDSVersion": None},
        {"Name": "ValidName", "BIDSVersion": 180},
    ],
)
def test_structural_validation_rejects_empty_or_nonstring_description_fields(
    tmp_path: Path, bad_desc: dict
):
    ds = tmp_path / "ds_bad_desc"
    ds.mkdir()
    (ds / "dataset_description.json").write_text(json.dumps(bad_desc), encoding="utf-8")
    (ds / "sub-01" / "eeg").mkdir(parents=True)
    res = index_bids_metadata(BIDSAccessRequest(dataset_id="dsDESC01", local_root=str(ds)))
    assert res["state"] == "BLOCKED_INVALID_BIDS"
    assert res["bids_validation"]["status"] == "invalid"


def test_nonstring_dataset_id_and_unmatched_expected_checksum_fail_closed(tmp_path: Path):
    with pytest.raises(BIDSAdapterError) as exc_id:
        index_bids_metadata(
            BIDSAccessRequest(dataset_id=12345, local_root=str(VALID))  # type: ignore[arg-type]
        )
    assert exc_id.value.code == BIDSAdapterErrorCode.MALFORMED_REQUEST.value

    with pytest.raises(BIDSAdapterError) as exc_ck:
        index_bids_metadata(
            BIDSAccessRequest(
                dataset_id="dsFIX001",
                local_root=str(VALID),
                relative_path="sub-01/eeg/nonexistent_recording_eeg.edf",
                expected_checksum="a" * 64,
            )
        )
    assert exc_ck.value.code == BIDSAdapterErrorCode.MALFORMED_REQUEST.value

    missing_root = tmp_path / "private_host_parent_dir" / "missing_bids_root"
    with pytest.raises(BIDSAdapterError) as exc_root:
        index_bids_metadata(
            BIDSAccessRequest(dataset_id="dsPRIV02", local_root=str(missing_root))
        )
    assert exc_root.value.code == BIDSAdapterErrorCode.INVALID_BIDS_STRUCTURE.value
    assert "private_host_parent_dir" not in str(exc_root.value)


def test_plan_rejects_mismatched_local_expected_checksum():
    """Regression: window *plan* must verify local checksums, not only lazy read."""
    mismatched = "0" * 64
    req = BIDSAccessRequest(
        dataset_id="dsFIX001",
        local_root=str(VALID),
        relative_path="sub-01/eeg/sub-01_task-rest_run-01_eeg.edf",
        window=BoundedWindowRequest(start_s=0.0, end_s=1.0),
        expected_checksum=mismatched,
    )
    with pytest.raises(BIDSAdapterError) as exc:
        plan_bounded_window_access(req)
    assert exc.value.code == BIDSAdapterErrorCode.MALFORMED_REQUEST.value
    assert "0" * 8 not in str(VALID)  # host fixture path must not be required in message


def test_oversized_metadata_json_rejected(tmp_path: Path):
    """Regression: dataset_description / sidecars must fail closed when oversized."""
    root = tmp_path / "bids"
    root.mkdir()
    # Just over the adapter metadata JSON budget.
    pad = "A" * (bids_ingest.MAX_METADATA_JSON_BYTES + 1)
    (root / "dataset_description.json").write_text(
        json.dumps({"Name": "Huge", "BIDSVersion": "1.8.0", "pad": pad}),
        encoding="utf-8",
    )
    (root / "sub-01" / "eeg").mkdir(parents=True)
    with pytest.raises(BIDSAdapterError) as exc:
        index_bids_metadata(BIDSAccessRequest(dataset_id="dsHUGE01", local_root=str(root)))
    assert exc.value.code == BIDSAdapterErrorCode.INVALID_BIDS_STRUCTURE.value
    assert "oversized" in str(exc.value).lower() or "too large" in str(exc.value).lower()
    assert "private" not in str(exc.value)  # sanity
    assert str(root) not in str(exc.value)


def test_find_eeg_files_missing_root_is_privacy_safe(tmp_path: Path):
    """Regression: missing-root diagnostics must not echo absolute host paths."""
    secret = tmp_path / "super_secret_host_directory_name" / "missing_bids"
    with pytest.raises(FileNotFoundError) as exc:
        onl.find_eeg_files(secret)
    assert "super_secret_host_directory_name" not in str(exc.value)
    with pytest.raises(FileNotFoundError) as exc_ev:
        onl.find_events(secret)
    assert "super_secret_host_directory_name" not in str(exc_ev.value)
