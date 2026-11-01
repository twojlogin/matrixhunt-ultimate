#!/usr/bin/env bash
# Samo-naprawczy bootstrap MatrixHunt Ultimate.
# Używa arek-bootstrap, jeśli jest dostępny; w przeciwnym razie venv ręcznie.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Szukamy arek-bootstrap w znanych lokalizacjach.
AREK=""
for cand in \
  "${AREK_BOOTSTRAP:-}" \
  "$HOME/.local/bin/arek-bootstrap" \
  "$HOME/Projekty/Inne/arek-bootstrap/bootstrap.sh"; do
  if [ -n "$cand" ] && [ -x "$cand" ]; then
    AREK="$cand"
    break
  fi
done

if [ -n "$AREK" ]; then
  echo "Używam arek-bootstrap: $AREK"
  exec "$AREK" --root "$ROOT" --install "$@"
else
  echo "arek-bootstrap nie znaleziony - fallback: venv + pip"
  cd "$ROOT"
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/pip install -r requirements.txt
fi