<#
.SYNOPSIS
    One-time AWS bootstrap for the NeuroTopology-Sim autonomous orchestrator.

.DESCRIPTION
    Creates a least-privilege compute substrate for the orchestrator:
      - An S3 bucket for run results
      - An IAM policy scoped to EC2 Spot, that bucket, AWS Batch, and Cost Explorer
      - A CloudWatch billing alarm firing at $5/day estimated charges

    Requires the AWS CLI to be installed and configured (aws configure) with
    credentials that can create IAM policies, S3 buckets, and CloudWatch alarms.

.NOTES
    Does not launch any compute. Run scripts/start_daemon.ps1 separately once
    the bucket name printed at the end has been copied into config/aws_config.py.
#>

$ErrorActionPreference = "Stop"

$BUCKET = "neurotopology-results-$(Get-Random -Maximum 99999)"
$REGION = "us-east-1"
$POLICY_NAME = "NeuroTopologyOrchestrator"

Write-Host "Creating S3 results bucket: $BUCKET (region $REGION)"
if ($REGION -eq "us-east-1") {
    aws s3api create-bucket --bucket $BUCKET --region $REGION
} else {
    aws s3api create-bucket --bucket $BUCKET --region $REGION `
        --create-bucket-configuration LocationConstraint=$REGION
}
aws s3api put-public-access-block --bucket $BUCKET --public-access-block-configuration `
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

Write-Host "Creating least-privilege IAM policy: $POLICY_NAME"
$policyDoc = @"
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "SpotComputeLifecycle",
      "Effect": "Allow",
      "Action": [
        "ec2:RunInstances",
        "ec2:TerminateInstances",
        "ec2:DescribeInstances",
        "ec2:RequestSpotInstances",
        "ec2:DescribeSpotInstanceRequests",
        "ec2:CancelSpotInstanceRequests",
        "ec2:CreateTags"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ResultsBucketOnly",
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject", "s3:ListBucket"],
      "Resource": ["arn:aws:s3:::$BUCKET", "arn:aws:s3:::$BUCKET/*"]
    },
    {
      "Sid": "BatchJobSubmission",
      "Effect": "Allow",
      "Action": [
        "batch:SubmitJob",
        "batch:DescribeJobs",
        "batch:ListJobs",
        "batch:CancelJob",
        "batch:TerminateJob"
      ],
      "Resource": "*"
    },
    {
      "Sid": "CostVisibility",
      "Effect": "Allow",
      "Action": ["ce:GetCostAndUsage"],
      "Resource": "*"
    }
  ]
}
"@

$policyFile = Join-Path $env:TEMP "neurotopology_orchestrator_policy.json"
$policyDoc | Out-File -FilePath $policyFile -Encoding utf8

aws iam create-policy --policy-name $POLICY_NAME --policy-document "file://$policyFile"

Write-Host "Creating CloudWatch billing alarm (fires above `$5.00/day estimated charges)"
aws cloudwatch put-metric-alarm `
    --alarm-name "NeuroTopology-Daily-Spend" `
    --alarm-description "Fires when estimated AWS charges exceed \$5 in a day for the NeuroTopology orchestrator." `
    --metric-name EstimatedCharges `
    --namespace "AWS/Billing" `
    --statistic Maximum `
    --period 86400 `
    --threshold 5.0 `
    --comparison-operator GreaterThanThreshold `
    --evaluation-periods 1 `
    --region us-east-1

Write-Host ""
Write-Host "=========================================================="
Write-Host " AWS bootstrap complete."
Write-Host " Bucket:  $BUCKET"
Write-Host " Region:  $REGION"
Write-Host " Policy:  $POLICY_NAME"
Write-Host ""
Write-Host " Next: copy the bucket name above into config/aws_config.py"
Write-Host " (RESULTS_BUCKET), attach $POLICY_NAME to the IAM role/user the"
Write-Host " orchestrator runs as, and set a real SNS topic ARN as the"
Write-Host " billing alarm action if you want notifications."
Write-Host "=========================================================="
