#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")"

if [[ ! -f .env ]]; then
  echo "ERROR: .env not found."
  exit 1
fi

set -a
source .env
set +a

PORT="${VLLM_PORT:-8000}"
MODEL_NAME="${MODEL:-Qwen/Qwen3-4B}"

echo "==> Container status"
docker compose ps

echo "==> GPU visibility inside vLLM container"
docker exec vllm nvidia-smi || true

echo "==> /v1/models"
curl -fsS "http://127.0.0.1:${PORT}/v1/models"
echo

echo "==> Test chat completion"
curl -fsS "http://127.0.0.1:${PORT}/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d "$(cat <<JSON
{
  \"model\": \"${MODEL_NAME}\",
  \"messages\": [
    {\"role\": \"user\", \"content\": \"Antworte auf Deutsch in zwei kurzen Saetzen: Was ist Incident Response?\"}
  ],
  \"temperature\": 0.2,
  \"max_tokens\": 128
}
JSON
)"
echo

echo "==> Host GPU status"
nvidia-smi
