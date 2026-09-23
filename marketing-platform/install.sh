#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

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
  echo ".env aus Vorlage erstellt. Passe OLLAMA_MODEL bei Bedarf an."
fi

echo "Baue und starte Marketing Platform ..."
docker compose up -d --build

echo
echo "Fertig."
echo "Frontend: http://localhost:3000"
echo "API:      http://localhost:8000"
echo "Swagger:  http://localhost:8000/docs"
echo
echo "Prüfe bei Problemen, ob Ollama läuft: curl http://localhost:11434/api/tags"
