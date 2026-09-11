#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: Docker is not installed. Run: sudo bash 01_prepare_host.sh"
  exit 1
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example."
  echo "Detected GPUs:"
  nvidia-smi -L || true
  echo "Review GPU_ID in .env so it points to your RTX 3090, then run this script again."
  exit 0
fi

mkdir -p hf-cache

echo "==> Selected configuration:"
grep -E '^(GPU_ID|MODEL|VLLM_IMAGE|VLLM_PORT|GPU_MEMORY_UTILIZATION|MAX_MODEL_LEN)=' .env || true

echo "==> Checking host GPU(s)..."
nvidia-smi -L

echo "==> Pulling vLLM image..."
docker compose pull

echo "==> Starting vLLM..."
docker compose up -d

echo "vLLM is starting. Follow logs with: docker compose logs -f vllm"
echo "When ready, run: bash 03_test_vllm.sh"
