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

REQUEST_JSON="$(jq -n \
  --arg model "$MODEL_NAME" \
  --arg prompt "$PROMPT" \
  '{
    model: $model,
    messages: [
      {
        role: "user",
        content: $prompt
      }
    ],
    temperature: 0.2,
    max_tokens: 512
  }'
)"

RESPONSE="$(curl --fail-with-body -sS \
  "http://127.0.0.1:${PORT}/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d "$REQUEST_JSON"
)"

CONTENT="$(jq -r '.choices[0].message.content // empty' <<<"$RESPONSE")"

if [[ -z "$CONTENT" ]]; then
  echo "ERROR: No assistant content returned." >&2
  echo "$RESPONSE" | jq . >&2 || echo "$RESPONSE" >&2
  exit 1
fi

printf '%s\n' "$CONTENT"
