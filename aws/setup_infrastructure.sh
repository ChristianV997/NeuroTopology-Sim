#!/usr/bin/env bash
set -euo pipefail
REGION="${AWS_DEFAULT_REGION:-us-east-1}"
BUCKET="${SCIENCERD_ARTIFACT_BUCKET:-sciencerd-sim-artifacts-2026}"
APPLY=0
for arg in "$@"; do [[ "$arg" == "--apply" ]] && APPLY=1; done
command -v aws >/dev/null || { echo "missing executable: aws" >&2; exit 2; }
IDENTITY="$(aws sts get-caller-identity --region "$REGION" --output json)"
ACCOUNT="$(printf '%s' "$IDENTITY" | python -c 'import json,sys; print(json.load(sys.stdin)["Account"])')"
mkdir -p artifacts
printf '%s\n' "$IDENTITY" > artifacts/aws_identity.json
echo "AWS account: $ACCOUNT | region: $REGION | bucket: $BUCKET"
echo "Mode: $([[ $APPLY == 1 ]] && echo APPLY || echo DRY-RUN)"
if aws s3api head-bucket --bucket "$BUCKET" --region "$REGION" >/dev/null 2>&1; then
  echo "S3 bucket exists: $BUCKET"
elif [[ $APPLY == 1 ]]; then
  aws s3api create-bucket --bucket "$BUCKET" --region "$REGION"
  aws s3api put-public-access-block --bucket "$BUCKET" --region "$REGION" --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
else
  echo "DRY-RUN: would create s3://$BUCKET"
fi
for repo in sciencerd-tddft neurotopology-tda; do
  if aws ecr describe-repositories --repository-names "$repo" --region "$REGION" >/dev/null 2>&1; then
    echo "ECR repository exists: $repo"
  elif [[ $APPLY == 1 ]]; then
    aws ecr create-repository --repository-name "$repo" --region "$REGION" --image-scanning-configuration scanOnPush=true >/dev/null
  else
    echo "DRY-RUN: would create ECR repository: $repo"
  fi
done
cat > artifacts/aws/infrastructure_plan.json <<EOF
{"schema":"ScienceR-Dsim.AwsInfrastructurePlan.v1","account":"$ACCOUNT","region":"$REGION","bucket":"$BUCKET","apply":$APPLY,"datasets":["ds003969","ds005620","ds005237"],"destructive_operations":false}
EOF
echo "Wrote artifacts/aws/infrastructure_plan.json"
