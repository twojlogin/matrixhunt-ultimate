#!/usr/bin/env bash
# Samo-naprawczy bootstrap MatrixHunt Ultimate.
# Używa arek-bootstrap, jeśli jest dostępny; w przeciwnym razie venv ręcznie.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Szukamy arek-bootstrap w znanych lokalizacjach.
cd "$ROOT"
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r requirements.txt