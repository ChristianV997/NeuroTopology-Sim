from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "fmri_tda_ds000245.yml"


def test_ds000245_workflow_requires_local_data_and_has_no_full_download_commands():
    text = WORKFLOW.read_text(encoding="utf-8")
    lowered = text.lower()
    assert "bids_root" in lowered
    assert "pre-provisioned" in lowered
    assert "aws s3 sync" not in lowered
    assert "aws s3 cp" not in lowered
    assert "curl -f" not in lowered
    assert "s3://openneuro.org" not in lowered
    assert "atlas_url" not in lowered
