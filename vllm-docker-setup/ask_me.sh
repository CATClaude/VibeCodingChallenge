#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "$0")"

if [[ $# -eq 0 ]]; then
  echo "Usage: $0 <prompt>" >&2
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "ERROR: jq is required. Install it with: sudo apt install -y jq" >&2
  exit 1
fi

PROMPT="$*"

# Load local configuration when available.
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

PORT="${VLLM_PORT:-8000}"
MODEL_NAME="${MODEL:-quocbao747/Qwen3.8-27B-OBLITERATED-W4A16-24GB}"
MAX_TOKENS="${MAX_TOKENS:-512}"
TEMPERATURE="${TEMPERATURE:-0.2}"

REQUEST_JSON="$(jq -n \
  --arg model "$MODEL_NAME" \
  --arg prompt "$PROMPT" \
  --argjson max_tokens "$MAX_TOKENS" \
  --argjson temperature "$TEMPERATURE" \
  '{
    model: $model,
    messages: [
      {
        role: "user",
        content: $prompt
      }
    ],
    temperature: $temperature,
    max_tokens: $max_tokens,
    stream: true
  }'
)"

# Stream tokens as soon as vLLM emits them.
curl --fail-with-body -N -sS \
  "http://127.0.0.1:${PORT}/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d "$REQUEST_JSON" \
| while IFS= read -r line; do
    [[ "$line" == data:* ]] || continue
    data="${line#data: }"

    [[ "$data" == "[DONE]" ]] && break

    chunk="$(printf '%s' "$data" | jq -r '.choices[0].delta.content // empty' 2>/dev/null || true)"
    if [[ -n "$chunk" ]]; then
      printf '%s' "$chunk"
    fi
  done

printf '\n'
