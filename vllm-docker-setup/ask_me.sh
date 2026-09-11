#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "$0")"

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <stream|nostream> <prompt>" >&2
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "ERROR: jq is required. Install it with: sudo apt install -y jq" >&2
  exit 1
fi

if ! command -v glow >/dev/null 2>&1; then
  echo "ERROR: glow is required for Markdown rendering." >&2
  echo "Install it with: sudo snap install glow" >&2
  exit 1
fi

MODE="${1,,}"
shift
PROMPT="$*"

case "$MODE" in
  stream|1|true|yes|on) STREAM=true ;;
  nostream|0|false|no|off) STREAM=false ;;
  *)
    echo "ERROR: First parameter must be stream or nostream." >&2
    exit 1
    ;;
esac

if [[ -f .env ]]; then
  set -a
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
  --argjson stream "$STREAM" \
  '{model:$model,messages:[{role:"user",content:$prompt}],temperature:$temperature,max_tokens:$max_tokens,stream:$stream}')"

if [[ "$STREAM" == "true" ]]; then
  curl --fail-with-body -N -sS \
    "http://127.0.0.1:${PORT}/v1/chat/completions" \
    -H "Content-Type: application/json" \
    -d "$REQUEST_JSON" \
  | while IFS= read -r line; do
      [[ "$line" == data:* ]] || continue
      data="${line#data: }"
      [[ "$data" == "[DONE]" ]] && break
      printf '%s' "$data" | jq -jr '.choices[0].delta.content // empty'
    done \
  | glow -
else
  RESPONSE="$(curl --fail-with-body -sS \
    "http://127.0.0.1:${PORT}/v1/chat/completions" \
    -H "Content-Type: application/json" \
    -d "$REQUEST_JSON")"

  CONTENT="$(jq -r '.choices[0].message.content // empty' <<<"$RESPONSE")"
  if [[ -z "$CONTENT" ]]; then
    echo "ERROR: No assistant content returned." >&2
    echo "$RESPONSE" | jq . >&2 || echo "$RESPONSE" >&2
    exit 1
  fi

  printf '%s\n' "$CONTENT" | glow -
fi
