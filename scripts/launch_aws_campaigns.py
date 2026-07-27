"""Fail-closed AWS campaign controller for pre-provisioned resources."""
from __future__ import annotations
import argparse, hashlib, json, os
from pathlib import Path
from urllib.request import Request, urlopen
from typing import Any

DATASETS = ("ds003969", "ds005620", "ds005237")
REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

def session() -> Any:
    try:
        import boto3
        return boto3.Session(region_name=REGION)
    except ImportError as exc:
        raise RuntimeError("boto3 is required") from exc

def preflight(bucket: str) -> dict[str, Any]:
    s = session(); result: dict[str, Any] = {"schema":"ScienceR-Dsim.AwsPreflight.v1", "region":REGION, "bucket":bucket, "capabilities":{}}
    result["identity"] = s.client("sts").get_caller_identity()
    try: s.client("s3").head_bucket(Bucket=bucket); result["capabilities"]["s3"] = True
    except Exception as exc: result["capabilities"]["s3"] = False; result.setdefault("errors", []).append(f"s3: {exc}")
    # boto3 exposes Amazon Elastic File System as ``efs``.  The longer
    # console product name (Elastic File System) is not a valid boto3 service
    # identifier and caused false-negative preflight failures.
    for service, op in (("ecr", "describe_repositories"), ("batch", "describe_compute_environments"), ("efs", "describe_file_systems")):
        try:
            c = s.client(service)
            if service == "ecr": c.describe_repositories(maxResults=1)
            elif service == "batch": c.describe_compute_environments(maxResults=1)
            else: c.describe_file_systems(MaxItems=1)
            result["capabilities"][service] = True
        except Exception as exc: result["capabilities"][service] = False; result.setdefault("errors", []).append(f"{service}: {exc}")
    return result

def dataset_inventory(dataset: str, snapshot: str) -> dict[str, Any]:
    query = "query SnapshotFiles($dataset: ID!, $tag: String!) { snapshot(datasetId: $dataset, tag: $tag) { files(recursive: true) { filename size directory annexed } } }"
    body = json.dumps({"query":query, "variables":{"dataset":dataset, "tag":snapshot}}).encode()
    with urlopen(Request("https://openneuro.org/crn/graphql", data=body, headers={"Content-Type":"application/json"}, method="POST"), timeout=60) as response:
        payload = json.load(response)
    if payload.get("errors"): raise RuntimeError(str(payload["errors"]))
    files = [x for x in payload.get("data",{}).get("snapshot",{}).get("files",[]) if not x.get("directory")]
    digest = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",",":")).encode()).hexdigest()
    return {"dataset":dataset, "snapshot":snapshot, "file_count":len(files), "manifest_sha256":digest, "files":files}

def submit_batch(campaign: str, queue: str, definition: str) -> dict[str, Any]:
    response = session().client("batch").submit_job(jobName=f"sciencerd-{campaign}", jobQueue=queue, jobDefinition=definition, parameters={"campaign":campaign})
    return {"schema":"ScienceR-Dsim.BatchSubmission.v1", "campaign":campaign, "job_id":response["jobId"], "job_name":response["jobName"]}

def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument("mode", choices=("preflight","inventory","submit")); p.add_argument("--bucket", default=os.getenv("SCIENCERD_ARTIFACT_BUCKET","amazon-braket-us-east-1-721955910125")); p.add_argument("--snapshot", default="1.0.0"); p.add_argument("--datasets", nargs="*", default=list(DATASETS)); p.add_argument("--campaign", choices=("td-dft","spectral-density","cohort-topology")); p.add_argument("--job-queue"); p.add_argument("--job-definition"); p.add_argument("--submit", action="store_true"); p.add_argument("--output-dir", type=Path, default=Path("artifacts/aws")); a=p.parse_args(); a.output_dir.mkdir(parents=True, exist_ok=True)
    if a.mode == "preflight": result=preflight(a.bucket)
    elif a.mode == "inventory": result={"schema":"ScienceR-Dsim.DatasetInventory.v1", "datasets":[dataset_inventory(d,a.snapshot) for d in a.datasets]}
    else:
        if not a.submit: raise SystemExit("submit is dry-run; add --submit explicitly")
        if not a.campaign or not a.job_queue or not a.job_definition: raise SystemExit("campaign, job queue, and definition are required")
        result=submit_batch(a.campaign,a.job_queue,a.job_definition)
    out=a.output_dir/f"{a.mode}.json"; out.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False)+"\n", encoding="utf-8"); print(json.dumps({"output":str(out),"schema":result["schema"]})); return 0

if __name__ == "__main__": raise SystemExit(main())
