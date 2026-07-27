from pathlib import Path

from scripts.run_campaign import build_manifest
from scripts.prepare_ec2_campaign import build_job_plan


def test_campaign_manifest_is_provenance_bound() -> None:
    manifest = build_manifest(Path("artifacts/campaign"), seed=7, timeout_s=10)
    assert manifest["schema"] == "ScienceR-Dsim.ResearchCampaignManifest.v1"
    assert manifest["braket_submission"] is False
    assert manifest["resource_policy"]["max_workers"] == 1
    assert all(len(item["sha256"]) == 64 for item in manifest["inputs"])


def test_campaign_shard_manifest_is_reproducible() -> None:
    manifest = build_manifest(Path("artifacts/campaign"), seed=7, timeout_s=10,
                              lane="discovery", shard_index=1, shard_count=4,
                              execution_mode="ec2_batch", max_workers=2)
    assert manifest["shard_index"] == 1
    assert manifest["shard_count"] == 4
    assert manifest["execution_mode"] == "ec2_batch"
    assert manifest["braket_submission"] is False


def test_ec2_plan_is_plan_only() -> None:
    plan = build_job_plan(shards=2, seed=7, output_dir=Path("artifacts/campaign"),
                          timeout_s=10, max_workers=2)
    assert plan["execution"] == "plan_only"
    assert len(plan["jobs"]) == 2
    assert all(job["braket_submission"] is False for job in plan["jobs"])
