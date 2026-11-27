#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
PATTERN="$DIR/.venv/bin/python $DIR/backend/main.py"

PIDS="$(pgrep -f "$DIR/backend/main.py" || true)"
if [ -z "$PIDS" ]; then
  echo "MatrixHunt nie działa."
  exit 0
fi

echo "Zatrzymuję MatrixHunt ($PIDS)..."
kill $PIDS 2>/dev/null || true
sleep 1
STILL="$(pgrep -f "$DIR/backend/main.py" || true)"
if [ -n "$STILL" ]; then
  kill -9 $STILL 2>/dev/null || true
fi
echo "Zatrzymane."
