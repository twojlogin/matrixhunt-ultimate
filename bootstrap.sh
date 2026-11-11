#!/usr/bin/env bash
# Bootstrap MatrixHunt Ultimate — tworzy .venv, instaluje zależności
# i (jeśli terminal) wchodzi do aktywowanego środowiska.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

# Aktywacja działa tylko w bieżącym procesie, więc dla terminala
# uruchamiamy nową powłokę z aktywnym .venv.
if [ -t 0 ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
  exec "${SHELL:-/bin/bash}"
else
  echo "Gotowe. Aktywuj ręcznie: source .venv/bin/activate"
fi
