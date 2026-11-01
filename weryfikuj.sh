#!/usr/bin/env bash
# Przenośny skrypt weryfikacyjny. Uruchom ./weryfikuj.sh
# Bez twardych ścieżek /home/... — działa z dowolnego klona na dowolnym koncie.
set -u
umask 077
ROOT="$(cd "$(dirname "$0")" && pwd)"
RUN_DIR="${MH_RUN_DIR:-${TMPDIR:-/tmp}/matrixhunt-${USER:-u}}"
mkdir -p "$RUN_DIR"
chmod 700 "$RUN_DIR" || {
  echo "Nie można zabezpieczyć katalogu roboczego: $RUN_DIR" >&2
  exit 1
}
LOG="$RUN_DIR/vp.log"
PORT_FILE="$RUN_DIR/port.txt"
PID_FILE="$RUN_DIR/vp.pid"

# Nie zabijamy cudzych procesów. Sprzątamy tylko poprzednią instancję
# wystartowaną przez ten skrypt (PID zapisany w $RUN_DIR/vp.pid).
if [ -f "$PID_FILE" ]; then
  OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ "${OLD_PID:-}" =~ ^[1-9][0-9]*$ ]] && kill -0 "$OLD_PID" 2>/dev/null; then
    kill "$OLD_PID" 2>/dev/null || true
    sleep 2
  fi
  rm -f "$PID_FILE"
fi

: > "$LOG"
( cd "$ROOT/backend" && setsid "$ROOT/.venv/bin/python" main.py > "$LOG" 2>&1 < /dev/null & echo $! > "$PID_FILE" )

for _ in $(seq 1 40); do
  sleep 1
  if grep -q "Uvicorn running\|MatrixHunt Ultimate ready" "$LOG" 2>/dev/null; then
    break
  fi
done

PORT=$(grep -oE "127\.0\.0\.1:[0-9]+" "$LOG" 2>/dev/null | head -1 | cut -d: -f2)
PORT="${PORT:-8000}"
echo "$PORT" > "$PORT_FILE"
echo "Serwer na porcie: $PORT (log: $LOG)"

MH_PORT="$PORT" MH_RUN_DIR="$RUN_DIR" "$ROOT/.venv/bin/python" "$ROOT/weryfikuj.py"
RC=$?

echo
echo "Serwer zostawiony dzialajacy (PID z $PID_FILE). Zatrzymanie:"
echo "  kill \$(cat \"$PID_FILE\")"

exit $RC
