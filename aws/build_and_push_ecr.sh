#!/usr/bin/env bash
set -euo pipefail
REGION="${AWS_DEFAULT_REGION:-us-east-1}"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text --region "$REGION")"
TAG="${SCIENCERD_IMAGE_TAG:-$(git rev-parse --short HEAD 2>/dev/null || echo local)}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"
for spec in "sciencerd-tddft:docker/td_dft" "neurotopology-tda:docker/tda"; do
  repo="${spec%%:*}"; dir="${spec#*:}"
  docker build --pull -t "$repo:$TAG" -f "$ROOT/$dir/Dockerfile" "$ROOT"
  docker tag "$repo:$TAG" "$ACCOUNT.dkr.ecr.$REGION.amazonaws.com/$repo:$TAG"
  docker push "$ACCOUNT.dkr.ecr.$REGION.amazonaws.com/$repo:$TAG"
done
