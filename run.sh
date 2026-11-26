#!/usr/bin/env bash
# Standardowy start MatrixHunt Ultimate.
# Tworzy .venv jeśli brak, instaluje zależności gdy potrzeba, uruchamia serwer.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

VENV="$ROOT/.venv"
PY="$VENV/bin/python"
PIP="$VENV/bin/pip"

if [ ! -x "$PY" ]; then
  echo "[matrixhunt] tworzę .venv..."
  python3 -m venv "$VENV"
fi

# Instaluj zależności tylko gdy requirements się zmieniły lub brak kluczowych pakietów.
REQ_HASH_FILE="$VENV/.requirements.sha256"
REQ_HASH="$(sha256sum requirements.txt | awk '{print $1}')"
OLD_HASH="$(cat "$REQ_HASH_FILE" 2>/dev/null || true)"
if [ "$REQ_HASH" != "$OLD_HASH" ] || ! "$PY" -c "import fastapi, uvicorn" >/dev/null 2>&1; then
  echo "[matrixhunt] instaluję zależności..."
  "$PIP" install --disable-pip-version-check -q --upgrade pip
  "$PIP" install --disable-pip-version-check -q -r requirements.txt
  echo "$REQ_HASH" > "$REQ_HASH_FILE"
fi

exec "$PY" backend/main.py "$@"
