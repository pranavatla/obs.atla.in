#!/usr/bin/env bash
set -euo pipefail

IMAGE_URI="${1:?Usage: ./build-lambda-image.sh <ecr-image-uri> [linux/amd64|linux/arm64]}"
PLATFORM="${2:-linux/amd64}"

docker buildx build \
  --platform "${PLATFORM}" \
  --provenance=false \
  --sbom=false \
  -t "${IMAGE_URI}" \
  --push \
  .
