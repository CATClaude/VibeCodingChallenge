#!/usr/bin/env bash
set -Eeuo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8188}"
WAIT_SECONDS="${WAIT_SECONDS:-900}"
OUTPUT_DIR="${OUTPUT_DIR:-output}"
OUTPUT_FILE="${OUTPUT_FILE:-$OUTPUT_DIR/test-de.wav}"

mkdir -p "$OUTPUT_DIR"

echo "Warte auf CosyVoice3 unter $BASE_URL ..."
start_ts="$(date +%s)"

while true; do
  if curl -fsS --max-time 5 "$BASE_URL/health" >/tmp/cosyvoice-health.json 2>/dev/null; then
    echo "CosyVoice3 ist bereit:"
    cat /tmp/cosyvoice-health.json
    printf '\n'
    break
  fi

  now_ts="$(date +%s)"
  elapsed=$((now_ts - start_ts))
  if (( elapsed >= WAIT_SECONDS )); then
    echo "FEHLER: CosyVoice3 wurde nach ${WAIT_SECONDS}s nicht bereit." >&2
    echo "Container-Status:" >&2
    docker compose ps >&2 || true
    echo >&2
    echo "Letzte Logs:" >&2
    docker compose logs --tail=100 cosyvoice >&2 || true
    exit 1
  fi

  printf '\rNoch nicht bereit ... %ss / %ss' "$elapsed" "$WAIT_SECONDS"
  sleep 5
done

printf '\nErzeuge Testaudio ...\n'

http_code="$(curl -sS \
  --connect-timeout 10 \
  --max-time 600 \
  -o "$OUTPUT_FILE" \
  -w '%{http_code}' \
  "$BASE_URL/v1/audio/speech" \
  -H 'Content-Type: application/json' \
  -d '{"model":"cosyvoice3","voice":"de_thorsten","input":"Hallo. Das ist ein deutscher Test von CosyVoice drei auf der RTX 4070 Ti Super.","response_format":"wav","speed":1.0}')"

if [[ "$http_code" != "200" ]]; then
  echo "FEHLER: Audio-API antwortete mit HTTP $http_code" >&2
  if [[ -s "$OUTPUT_FILE" ]]; then
    echo "Antwort:" >&2
    cat "$OUTPUT_FILE" >&2 || true
    printf '\n' >&2
  fi
  echo "Letzte Logs:" >&2
  docker compose logs --tail=100 cosyvoice >&2 || true
  exit 1
fi

if [[ ! -s "$OUTPUT_FILE" ]]; then
  echo "FEHLER: Keine Audiodatei erzeugt." >&2
  exit 1
fi

if command -v ffprobe >/dev/null 2>&1; then
  echo "Audio-Informationen:"
  ffprobe -v error \
    -show_entries format=duration,size \
    -show_entries stream=codec_name,sample_rate,channels \
    -of default=noprint_wrappers=1 \
    "$OUTPUT_FILE"
else
  echo "Hinweis: ffprobe ist auf dem Host nicht installiert; Audio-Prüfung wird übersprungen."
fi

echo
echo "SUCCESS: $(realpath "$OUTPUT_FILE")"
