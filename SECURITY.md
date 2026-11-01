# Security Policy

## Zgłaszanie problemów

Jeśli znajdziesz podatność, otwórz **prywatny** security advisory w repozytorium
GitHub (Security → Advisories) albo napisz do autora. Nie publikuj exploita,
zanim poprawka nie trafi do `main`.

## Model bezpieczeństwa

MatrixHunt Ultimate to **aplikacja lokalna** — działa na `127.0.0.1`,
zero chmury, zero CDN. React, Babel i Ruffle są zvendorowane w `frontend/vendor/`.

### Co aplikacja robi w sieci (tylko na żądanie)

- Odpytuje sklepy/agregatory po oferty (GamerPower, Epic, Steam, GOG, itch.io, …)
- Pobiera listy filtrów (EasyList i spółka) co 24 h
- Audyt zależności (OSV + CISA KEV) — tylko po kliknięciu „Sprawdź” w `/api/vulncheck`
- Sprawdza Tor (`check.torproject.org`) — tylko jeśli włączysz tryb Tor

**Nie ma** telemetrii, analityki, webhooków, LLM API. Audyt statyczny w `AUDYT_SIEC.md`.

### Zabezpieczenia

- **SSRF**: `/api/clean` i `/api/img` blokują prywatne adresy na każdym hopie; przy połączeniu bezpośrednim DNS jest przypinany do sprawdzonego publicznego IP. Ruch przez jawnie skonfigurowany proxy ufa jego stronie wyjściowej.
- **Untrusted HTML**: skrypty, style, SVG/MathML i bezpośrednie zewnętrzne zasoby są usuwane; obrazy przechodzą przez walidujący `/api/img`, a odpowiedź ma restrykcyjne CSP.
- **Path traversal**: `/data/...` blokuje `..` i dostęp do plików poza `data/`.
- **API/CSRF**: w trybie lokalnym `/api/*` wymaga rzeczywistego loopback peer oraz loopback `Host`; cross-origin i cross-site są blokowane, a zapisy wymagają `X-MH-Token`. Proxy GET wymaga same-origin sygnału przeglądarki; formularze proxy mają token w akcji i middleware usuwa go przed przekazaniem żądania do sklepu.
- **Token sesji**: zapisy wymagają nagłówka `X-MH-Token` z `/api/client-config` (losowany na start).
- **CORS**: `allow_origins=[]` — obcy origin nie dostaje nagłówków.
- **Ciasteczka**: per-host w `backend/.cookies/`, uprawnienia `0600`.
- **Session secret**: `backend/.session_secret`, uprawnienia `0600`.

### Znane ograniczenia

- `.app_settings.json` jest zapisywany jawnie (plaintext), gdy sejf jest zablokowany.
  Strażnik pilnuje tego tylko dla ciasteczek, nie dla ustawień.
- Vendored pliki (React, Babel, Ruffle) nie są weryfikowane sumą kontrolną
  (sprawdzone ręcznie przy dodaniu, nie automatycznie).
- Proxy `/api/clean` przekazuje formularze POST w całości do sklepu
  (w tym hasła) — to konieczne, żeby logowanie przez viewer działało.

### Zależności

- `pip-audit` / `osv-scanner` do audytu: uruchom `./.venv/bin/python -m pip install pip-audit`
  albo użyj `arek-bootstrap --install`.
- `certifi>=2026.10.23` — aktualne CA (incydent eMudhra/emSign, X 2026).
- Zaktualizuj pip przed instalacją: `.venv/bin/python -m pip install --upgrade pip`

### Pobieranie gier

MatrixHunt Ultimate **nie pobiera i nie uruchamia gier**. Linkuje do stron sklepów.
Pobieranie i uruchamianie gier to Twoja odpowiedzialność — pobieraj tylko z oficjalnych
źródeł (Steam, Epic, GOG, itch.io). Aplikacja ostrzega, że żadna oferta nie ma
potwierdzonej ceny z API sklepu.

### Wystawianie publiczne (opcjonalne, zaawansowane)

MatrixHunt to aplikacja **local-first** (127.0.0.1). Wystawianie jej publicznie
zmienia model bezpieczeństwa. Jeśli chcesz to zrobić (np. demo, self-hosting):

1. **Cloudflare Tunnel** — ukrywa IP, brak port forwarding:
   ```bash
   ./tools/cloudflared_setup.sh matrixhunt.twojadomena.pl
   ```
2. **Tryb read-only** — zablokuj zapisy i scrapowanie:
   ```bash
   MH_PUBLIC=1 MH_HOST=0.0.0.0 ./bootstrap.sh
   ```
   Bez `MH_PUBLIC=1` uruchomienie z nie-loopback `MH_HOST` kończy się błędem. W trybie publicznym endpointy mutujące na `/api/*` zwracają 403, a żądania API nadal wymagają same-origin albo tokenu.
3. **Cloudflare Access (Zero Trust)** — OBOWIĄZKOWE. Bez tego każdy kto zna URL
   ma dostęp. Ustaw politykę Allow → Emails → Twoje konto.
4. **IP podczas scrapowania** — sklepy widzą Twoje IP. Włącz tryb Tor w ustawieniach
   (Settings → Tor) lub użyj upstream proxy (`socks5h://127.0.0.1:9050`).
5. **Alternatywa — Tailscale** (mesh VPN, darmowy, 100 urządzeń): brak publicznego
   URL, brak ataków z internetu. Zalecane zamiast Cloudflare Tunnel dla
   użytku prywatnego.

**Nie wystawiaj MatrixHunt publicznie bez Cloudflare Access lub Tailscale.**

### Weryfikacja

```bash
./weryfikuj.sh   # 42/42 sprawdzeń (SSRF, XSS, traversal, filtry, F2P, wyciek)
```
