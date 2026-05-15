"""
Tests for tools/local_agents/obsidian_sync.py (P23).

8 tests covering vault note creation, index, dataset notes,
loop state, matrix, and safety invariants.
"""
import json

import pytest

from tools.local_agents.obsidian_sync import ObsidianSyncConfig, sync_obsidian


# ---------------------------------------------------------------------------
# 1. Sync creates expected note files
# ---------------------------------------------------------------------------
def test_sync_creates_all_expected_notes(tmp_path):
    vault = tmp_path / "vault"
    outputs = tmp_path / "outputs"
    outputs.mkdir()

    result = sync_obsidian(str(outputs), str(vault))

    assert result.error == ""
    assert len(result.notes_written) > 0

    written_names = [p.split("/")[-1] for p in result.notes_written]
    assert "INDEX.md" in written_names


# ---------------------------------------------------------------------------
# 2. Dataset notes are written for all 6 datasets
# ---------------------------------------------------------------------------
def test_sync_writes_per_dataset_notes(tmp_path):
    vault = tmp_path / "vault"
    outputs = tmp_path / "outputs"
    outputs.mkdir()

    result = sync_obsidian(str(outputs), str(vault))

    written = {p.split("/")[-1].replace(".md", "") for p in result.notes_written}
    for ds in ["DS005620", "DS002094", "ds001787", "ds003969", "ds003816", "PhysioNet_GABA"]:
        assert ds in written


# ---------------------------------------------------------------------------
# 3. Loop state note is written
# ---------------------------------------------------------------------------
def test_sync_writes_loop_state(tmp_path):
    vault = tmp_path / "vault"
    outputs = tmp_path / "outputs"
    outputs.mkdir()

    result = sync_obsidian(str(outputs), str(vault))

    written_names = [p.split("/")[-1] for p in result.notes_written]
    assert "loop_state.md" in written_names


# ---------------------------------------------------------------------------
# 4. Matrix note is written
# ---------------------------------------------------------------------------
def test_sync_writes_matrix_note(tmp_path):
    vault = tmp_path / "vault"
    outputs = tmp_path / "outputs"
    outputs.mkdir()

    result = sync_obsidian(str(outputs), str(vault))

    written_names = [p.split("/")[-1] for p in result.notes_written]
    assert "matrix.md" in written_names


# ---------------------------------------------------------------------------
# 5. Index note contains dataset links
# ---------------------------------------------------------------------------
def test_index_note_contains_dataset_links(tmp_path):
    vault = tmp_path / "vault"
    outputs = tmp_path / "outputs"
    outputs.mkdir()

    sync_obsidian(str(outputs), str(vault))

    index_path = vault / "ScienceR-Dsim" / "INDEX.md"
    assert index_path.exists()
    content = index_path.read_text()
    assert "DS005620" in content


# ---------------------------------------------------------------------------
# 6. Dataset note picks up gate output when present
# ---------------------------------------------------------------------------
def test_dataset_note_includes_gate_status(tmp_path):
    vault = tmp_path / "vault"
    outputs = tmp_path / "outputs"
    gate_dir = outputs / "ds005620_real_execution_gate"
    gate_dir.mkdir(parents=True)
    gate_file = gate_dir / "ready_for_real_execution.json"
    gate_file.write_text(json.dumps({
        "ready_for_real_execution": False,
        "next_action": "provide_metadata",
        "peer_review_confirmed_by_human": False,
    }), encoding="utf-8")

    sync_obsidian(str(outputs), str(vault))

    ds_note = vault / "ScienceR-Dsim" / "datasets" / "DS005620.md"
    assert ds_note.exists()
    content = ds_note.read_text()
    assert "provide_metadata" in content


# ---------------------------------------------------------------------------
# 7. Sync never modifies source outputs
# ---------------------------------------------------------------------------
def test_sync_does_not_modify_source_outputs(tmp_path):
    vault = tmp_path / "vault"
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    source_file = outputs / "sentinel.json"
    source_file.write_text('{"original": true}', encoding="utf-8")

    sync_obsidian(str(outputs), str(vault))

    assert source_file.read_text() == '{"original": true}'


# ---------------------------------------------------------------------------
# 8. Custom config works
# ---------------------------------------------------------------------------
def test_sync_with_custom_config(tmp_path):
    vault = tmp_path / "vault"
    outputs = tmp_path / "outputs"
    outputs.mkdir()

    config = ObsidianSyncConfig(
        vault_root=str(vault),
        index_note="MyVault/INDEX.md",
        dataset_folder="MyVault/datasets",
        loop_folder="MyVault/loop",
        matrix_folder="MyVault/matrix",
    )
    result = sync_obsidian(str(outputs), str(vault), config=config)

    assert result.error == ""
    index_path = vault / "MyVault" / "INDEX.md"
    assert index_path.exists()
