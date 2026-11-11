#!/usr/bin/env bash
# Sprawdza, czy w publicznym repo nie ma prywatnych ścieżek ani sekretów.
#
# Dodałem to po tym, jak trzy pliki z absolutnymi ścieżkami z katalogu
# domowego wylądowały w publicznym repo. Ten skrypt jest po to, żeby nie
# trzeba było o tym pamiętać.
#
# Uruchom przed wypchnięciem:  ./tools/scan_wyciekow.sh
set -u
cd "$(dirname "$0")/.." || exit 1

SKUTKI=0

echo "[1] Prywatne ścieżki"
_TRAF=$(grep -rInE "/home/[a-z0-9]+/|~/[A-Z]?[a-z]*/[A-Za-z/]*|C:\\\\Users\\\\" \
     --exclude-dir=.git --exclude-dir=.venv --exclude-dir=node_modules \
     --exclude-dir=__pycache__ --exclude-dir=.filterlists --exclude=scan_wyciekow.sh . 2>/dev/null | head -10)
if [ -n "$_TRAF" ]; then
  echo "$_TRAF"
  echo "    ↑ coś wskazuje na katalog użytkownika. Wyklucz to w .gitignore"
  SKUTKI=1
else
  echo "    czysto"
fi

echo "[2] Pliki, których nie wolno commitować"
for plik in backend/.session_secret backend/.vault_verifier backend/.cookies backend/.app_settings.json "backend/matrixhunt.db"; do
  if git ls-files --error-unmatch "$plik" >/dev/null 2>&1; then
    echo "    ⚠ $plik jest w gicie"
    SKUTKI=1
  fi
done
[ "$SKUTKI" = "0" ] && echo "    brak plików sesyjnych w gicie"

echo "[3] Rozmiar plików śledzonych w gicie (bez ignorowanych)"
git ls-files -z | xargs -0 du -sch 2>/dev/null | tail -1 | awk '{print "    " $1}'

exit "$SKUTKI"
