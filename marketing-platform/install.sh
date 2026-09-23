#!/usr/bin/env bash
set -euo pipefail

REPO_ARCHIVE="https://github.com/CATClaude/VibeCodingChallenge/archive/refs/heads/main.tar.gz"
TARGET_DIR="${MARKETING_DIR:-$PWD/marketing-platform}"

SCRIPT_SOURCE="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_SOURCE")" 2>/dev/null && pwd || pwd)"

if [ -f "$SCRIPT_DIR/docker-compose.yml" ] && [ -f "$SCRIPT_DIR/.env.example" ]; then
  APP_DIR="$SCRIPT_DIR"
else
  if ! command -v curl >/dev/null 2>&1; then
    echo "curl wurde nicht gefunden."
    exit 1
  fi
  if ! command -v tar >/dev/null 2>&1; then
    echo "tar wurde nicht gefunden."
    exit 1
  fi

  echo "Lade Marketing Platform aus GitHub ..."
  TMP_DIR="$(mktemp -d)"
  trap 'rm -rf "$TMP_DIR"' EXIT

  curl -fsSL "$REPO_ARCHIVE" -o "$TMP_DIR/repo.tar.gz"
  tar -xzf "$TMP_DIR/repo.tar.gz" -C "$TMP_DIR"

  SRC_DIR="$TMP_DIR/VibeCodingChallenge-main/marketing-platform"
  if [ ! -d "$SRC_DIR" ]; then
    echo "Marketing Platform wurde im GitHub-Archiv nicht gefunden."
    exit 1
  fi

  mkdir -p "$TARGET_DIR"
  cp -a "$SRC_DIR/." "$TARGET_DIR/"
  APP_DIR="$TARGET_DIR"
fi

cd "$APP_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker wurde nicht gefunden. Bitte Docker Engine + Compose Plugin installieren."
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "Das Docker Compose Plugin wurde nicht gefunden."
  exit 1
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo ".env aus Vorlage erstellt."
fi

echo "Baue und starte Marketing Platform ..."
docker compose up -d --build

echo
echo "Fertig."
echo "Installationsordner: $APP_DIR"
echo "Frontend: http://localhost:3000"
echo "API:      http://localhost:8000"
echo "Swagger:  http://localhost:8000/docs"
echo
echo "Ollama prüfen: curl http://localhost:11434/api/tags"
