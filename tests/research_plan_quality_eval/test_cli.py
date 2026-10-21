from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tools.research_plan_quality_eval.harness import DEFAULT_MANIFEST

REPO_ROOT = Path(__file__).resolve().parents[2]

_GUARDED_RUN = """
import socket, sys
sys.path.insert(0, sys.argv[1])
def _blocked(*a, **k):
    raise SystemExit("network access attempted")
socket.socket.connect = _blocked
socket.create_connection = _blocked
from tools.research_plan_quality_eval.__main__ import main
raise SystemExit(main(sys.argv[2:]))
"""


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-I", "-c", _GUARDED_RUN, str(REPO_ROOT), *args],
        capture_output=True, text=True, timeout=120, cwd=str(REPO_ROOT),
    )


def _strict(text: str):
    def _reject(token):
        raise ValueError(f"non-finite constant {token}")

    return json.loads(text, parse_constant=_reject)


def test_isolated_cli_run_is_offline_and_writes_strict_json(tmp_path):
    out = tmp_path / "report.json"
    proc = _run(["--json-out", str(out)])
    assert proc.returncode == 0, proc.stderr
    report = _strict(out.read_text(encoding="utf-8"))
    assert report["fixture_set"]["plan_count"] == 10
    assert "plans=10" in proc.stderr


def test_cli_stdout_matches_json_out(tmp_path):
    out = tmp_path / "report.json"
    proc = _run(["--json-out", str(out)])
    assert proc.returncode == 0, proc.stderr
    stdout_proc = _run([])
    assert stdout_proc.returncode == 0, stdout_proc.stderr
    assert stdout_proc.stdout == out.read_text(encoding="utf-8")


def test_cli_can_omit_label_consistency(tmp_path):
    out = tmp_path / "report.json"
    proc = _run(["--json-out", str(out), "--no-label-consistency"])
    assert proc.returncode == 0, proc.stderr
    assert "label_consistency" not in json.loads(out.read_text(encoding="utf-8"))


def test_cli_missing_manifest_exits_2(tmp_path):
    proc = _run(["--manifest", str(tmp_path / "absent.json")])
    assert proc.returncode == 2
    assert "harness error" in proc.stderr


def test_cli_manifest_default_points_at_the_shipped_fixture_set():
    from tools.research_plan_quality_eval.manifest import load_manifest

    manifest = load_manifest(DEFAULT_MANIFEST)
    assert manifest.fixture_set_id
    assert len(manifest.entries) == 10


def test_cli_malformed_nested_plan_exits_2_without_a_traceback(copy_fixture_tree, capsys):
    from tools.research_plan_quality_eval.__main__ import main

    from .conftest import rehash_plan

    manifest_path = copy_fixture_tree()
    plan_file = manifest_path.parent / "plans" / "P03.json"
    data = json.loads(plan_file.read_text(encoding="utf-8"))
    data["reproducibility"] = 7
    plan_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    rehash_plan(manifest_path, "fx-v1-P03")

    code = main(["--manifest", str(manifest_path), "--allow-unpinned-split", "--no-label-consistency"])
    assert code == 2
    assert "harness error" in capsys.readouterr().err


def test_cli_malformed_label_file_exits_2_without_a_traceback(copy_fixture_tree, capsys):
    from tools.research_plan_quality_eval.__main__ import main

    from .conftest import rehash_labels

    manifest_path = copy_fixture_tree()
    labels_path = manifest_path.parent / "labels.json"
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    labels["labels"]["fx-v1-P01"] = "not-an-object"
    labels_path.write_text(json.dumps(labels, indent=2), encoding="utf-8")
    rehash_labels(manifest_path)

    assert main(["--manifest", str(manifest_path)]) == 2
    assert "harness error" in capsys.readouterr().err


def test_cli_unwritable_json_out_exits_2_with_a_message(tmp_path, capsys):
    from tools.research_plan_quality_eval.__main__ import main

    target = tmp_path  # an existing directory cannot be written as a report file
    assert main(["--json-out", str(target), "--no-label-consistency"]) == 2
    assert "harness error" in capsys.readouterr().err
