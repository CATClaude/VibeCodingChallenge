#!/usr/bin/env bash
set -Eeuo pipefail

BASE_URL="https://raw.githubusercontent.com/CATClaude/VibeCodingChallenge/main/vllm-docker-setup"
TARGET_DIR="${1:-vllm-docker-setup}"

mkdir -p "$TARGET_DIR"
cd "$TARGET_DIR"

for f in 01_prepare_host.sh 02_start_vllm.sh 03_test_vllm.sh compose.yml .env.example; do
  echo "Downloading $f..."
  curl -fsSLO "$BASE_URL/$f"
done

chmod +x 01_prepare_host.sh 02_start_vllm.sh 03_test_vllm.sh

echo
echo "Downloaded to: $(pwd)"
echo "Next:"
echo "  sudo bash 01_prepare_host.sh"
