#!/usr/bin/env bash
set -euo pipefail

REPO="CATClaude/VibeCodingChallenge"
BRANCH="main"
APP_DIR="moodle-course-builder"
INSTALL_DIR="${MOODLE_COURSE_BUILDER_DIR:-$HOME/moodle-course-builder}"
PORT="${PORT:-8080}"

if [[ ! -f "$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd)/requirements.txt" ]]; then
  echo "Installing Moodle Course Builder to: $INSTALL_DIR"
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  curl -fsSL "https://github.com/${REPO}/archive/refs/heads/${BRANCH}.tar.gz" -o "$tmp/repo.tar.gz"
  tar -xzf "$tmp/repo.tar.gz" -C "$tmp"
  src="$(find "$tmp" -maxdepth 2 -type d -name "$APP_DIR" | head -n1)"
  if [[ -z "$src" ]]; then
    echo "Could not find $APP_DIR in repository archive." >&2
    exit 1
  fi
  mkdir -p "$INSTALL_DIR"
  cp -a "$src"/. "$INSTALL_DIR"/
  chmod +x "$INSTALL_DIR/install.sh"
  echo "Files installed. Starting application..."
  cd "$INSTALL_DIR"
else
  cd "$(dirname "${BASH_SOURCE[0]:-$0}")"
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required." >&2
  exit 1
fi

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

echo
echo "Moodle Course Builder: http://0.0.0.0:${PORT}"
exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
