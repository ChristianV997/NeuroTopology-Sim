"""Submit experiments to EC2 Spot and poll S3 for results.

Requires config/aws_config.py to be filled in (RESULTS_BUCKET, AMI_ID,
KEY_NAME) after running scripts/setup_aws.ps1 and creating an EC2 key pair.
"""
import base64
import time

import boto3

from config.aws_config import (
    AMI_ID,
    INSTANCE_TYPE_CPU,
    KEY_NAME,
    REGION,
    RESULTS_BUCKET,
)

ec2 = boto3.client("ec2", region_name=REGION)
s3 = boto3.client("s3", region_name=REGION)


def submit_spot_job(experiment: dict) -> str:
    """Launch a Spot instance, run the pipeline, upload results, self-terminate."""
    user_data = f"""#!/bin/bash
set -e
yum install -y git python3-pip
git clone https://github.com/ChristianV993/NeuroTopology-Sim /opt/sim
cd /opt/sim
pip3 install -r requirements.txt
python3 {experiment['script']} {experiment.get('args', '')} > /tmp/run.log 2>&1
aws s3 cp /tmp/run.log s3://{RESULTS_BUCKET}/{experiment['name']}/run.log
aws s3 cp {experiment.get('output_path', '.')} s3://{RESULTS_BUCKET}/{experiment['name']}/ --recursive
shutdown -h now
"""
    encoded = base64.b64encode(user_data.encode()).decode()

    response = ec2.request_spot_instances(
        SpotPrice="0.50",
        InstanceCount=1,
        Type="one-time",
        LaunchSpecification={
            "ImageId": AMI_ID,
            "InstanceType": experiment.get("instance_type", INSTANCE_TYPE_CPU),
            "KeyName": KEY_NAME,
            "UserData": encoded,
            "IamInstanceProfile": {"Name": "NeuroTopologyOrchestrator"},
        },
    )
    request_id = response["SpotInstanceRequests"][0]["SpotInstanceRequestId"]
    print(f"[AWS] Spot request submitted: {request_id}")
    return request_id


def wait_for_results(experiment_name: str, timeout_hours: int = 4) -> dict:
    """Poll S3 until results appear or timeout."""
    prefix = f"{experiment_name}/"
    deadline = time.time() + timeout_hours * 3600
    while time.time() < deadline:
        resp = s3.list_objects_v2(Bucket=RESULTS_BUCKET, Prefix=prefix)
        if resp.get("Contents"):
            log_obj = s3.get_object(Bucket=RESULTS_BUCKET, Key=f"{prefix}run.log")
            log_text = log_obj["Body"].read().decode()
            return {"log": log_text, "s3_prefix": f"s3://{RESULTS_BUCKET}/{prefix}"}
        time.sleep(60)
    raise TimeoutError(f"Job {experiment_name} did not complete within {timeout_hours}h")
