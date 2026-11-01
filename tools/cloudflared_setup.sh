#!/usr/bin/env bash
# Opcjonalne wystawienie MatrixHunt przez Cloudflare Tunnel (ukrywa IP).
# Użycie: ./tools/cloudflared_setup.sh [hostname]
# Wymaga: konto Cloudflare + zainstalowany cloudflared.
set -Eeuo pipefail

HOSTNAME="${1:-}"
if [ -z "$HOSTNAME" ]; then
  echo "Użycie: $0 <hostname>   np. $0 matrixhunt.twojadomena.pl"
  exit 1
fi
if [[ ! "$HOSTNAME" =~ ^[A-Za-z0-9.-]+$ || "$HOSTNAME" == .* ||
      "$HOSTNAME" == *. || "$HOSTNAME" == *..* || ${#HOSTNAME} -gt 253 ]]; then
  echo "Nieprawidłowa nazwa hosta."
  exit 1
fi

CONFIG="$HOME/.cloudflared/config.yml"
if [ -e "$CONFIG" ]; then
  echo "Nie nadpisuję istniejącego $CONFIG. Scal konfigurację ręcznie."
  exit 1
fi

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "Brak cloudflared. Instalacja:"
  echo "  curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o ~/.local/bin/cloudflared"
  echo "  chmod +x ~/.local/bin/cloudflared"
  exit 1
fi

echo "=== Logowanie do Cloudflare ==="
cloudflared tunnel login

echo "=== Tworzenie tunelu 'matrixhunt' ==="
cloudflared tunnel create matrixhunt

TUNNEL_ID="$(cloudflared tunnel list 2>/dev/null | awk '/matrixhunt/{print $1}' | head -n1)"
if [[ ! "$TUNNEL_ID" =~ ^[a-fA-F0-9-]{36}$ ]]; then
  echo "Nie udało się pobrać TUNNEL_ID - sprawdź 'cloudflared tunnel list'"
  exit 1
fi

echo "=== Routing DNS ==="
cloudflared tunnel route dns matrixhunt "$HOSTNAME"

mkdir -p "$HOME/.cloudflared"
umask 077
set -o noclobber
cat > "$CONFIG" <<EOF
tunnel: $TUNNEL_ID
credentials-file: $HOME/.cloudflared/$TUNNEL_ID.json
ingress:
  - hostname: $HOSTNAME
    service: http://localhost:8000
  - service: http_status:404
EOF

echo
echo "=== Gotowe ==="
echo "Uruchomienie:"
echo "  MH_PUBLIC=1 MH_HOST=0.0.0.0 ./bootstrap.sh   # tryb read-only"
echo "  cloudflared tunnel run matrixhunt"
echo
echo "WAŻNE: włącz Cloudflare Access (Zero Trust -> Access -> Applications)"
echo "dla $HOSTNAME, żeby tylko Ty miał dostęp (email/OTP)."
echo "Bez Access każdy kto zna URL ma dostęp do aplikacji."