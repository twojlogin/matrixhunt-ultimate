# MatrixHunt Ultimate

[![CI](https://github.com/twojlogin/matrixhunt-ultimate/actions/workflows/ci.yml/badge.svg)](https://github.com/twojlogin/matrixhunt-ultimate/actions/workflows/ci.yml)
[![License: CC BY-NC-SA 4.0](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey.svg)](LICENSE.md)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)](requirements.txt)
[![GitHub stars](https://img.shields.io/github/stars/twojlogin/matrixhunt-ultimate?style=flat)](https://github.com/twojlogin/matrixhunt-ultimate/stargazers)
[![Last commit](https://img.shields.io/github/last-commit/twojlogin/matrixhunt-ultimate)](https://github.com/twojlogin/matrixhunt-ultimate/commits/main)

> Lokalny agregator darmowych gier: zbiera oferty ze sklepów, pokazuje je w przeglądarce, czyści strony z reklam i trackerów. Zero chmury, zero CDN — React i Babel są zvendorowane, baza to lokalny SQLite.

`Python 3.12 · FastAPI · SQLite (WAL) · local-first`

---

## 🇵🇱 Polski

### Szybki start

```bash
./run.sh
```

Skrypt tworzy `.venv` (jeśli brak), doinstalowuje zależności i uruchamia serwer.  
Domyślny port startowy: **8765**. Jeśli zajęty, aplikacja wybierze kolejny wolny.  
Własny port:

```bash
MH_PORT=9010 ./run.sh
```

Ręcznie:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
.venv/bin/python backend/main.py
```

### Co robi aplikacja

| Adres | Opis |
|---|---|
| `/` | Dashboard ofert |
| `/offers` | Lista ofert |
| `/view` | Proxy stron: wklej URL sklepu, dostajesz oczyszczoną wersję |
| `/db` | Podgląd bazy (tylko odczyt) |
| `/retro` | Hub retro + skan sprzętu |
| `/pad` | Test pada (Gamepad API) |
| `/wiki`, `/bookmarks` | Wiki i zakładki |
| `/flash` | Gry arcade przez embed (Internet Archive) |
| `/muzeum` | Lokalne próbki treści odrzuconych przez sanityzer |
| `/uwagi` | Uwagi |

### Źródła danych

Aktywne scrapery: GamerPower, Epic Games, Steam, GOG, IndieGala, Reddit, Łowcy Gier.  
Zaparkowane źródła i powody: `GET /api/scrapers` (`reason`).

**Ceny:** wiążące są `price_claim` + `price_source`.  
`api:<sklep>` = pomiar z API sklepu, `listing:<url>` = deklaracja strony zbierającej.  
Brak `price_source` = cena niesprawdzona.

### Bezpieczeństwo i prywatność

- Mutacje API wymagają tokena `X-MH-Token` z `/api/client-config`.
- Proxy ma bramkę SSRF (`is_url_allowed`) na każdym hopie/redirectcie.
- HTML z zewnątrz jest czyszczony (`clean_html`), obrazy przechodzą przez `/api/img` z walidacją magic bytes + `nosniff`.
- Sesje sklepowe: osobny słoik per host lub tryb ulotny (RAM, 30 min).
- Hasła formularzy nie są zapisywane; zapisywane są tylko cookies sesyjne.
- Treści 18+ domyślnie ukryte (UI/API/RSS).

To jest projekt local-first. Nie wystawiaj go publicznie bez zrozumienia ryzyka. Opcjonalny self-hosting: `SECURITY.md`.

### Testy

```bash
.venv/bin/python -m pytest tests/ -q
node tools/scripts/smoke_render.js
./weryfikuj.sh
./tools/shell/scan_wyciekow.sh
```

### Struktura

```
backend/    FastAPI, scrapery, cleaner, vault, sessions, DB
frontend/   widoki / i /offers (React zvendorowany)
tools/      strony HTML, skrypty, assety
data/       dane katalogowe/seed
tests/      testy
```

Runtime (gitignorowane): `.venv/`, `*.db*`, `.cookies/`, `.session_secret`, `.app_settings.json`, `.filterlists/`, `.specimens/`.

### Licencja

CC BY-NC-SA 4.0, autor: **Arkadiusz Slowik**.  
Oprogramowanie jest darmowe — jeśli ktoś je sprzedaje, oszukuje.  
Używaj tylko z grami i treściami, do których masz prawa.

---

## 🇬🇧 English

### Quick start

```bash
./run.sh
```

The script creates `.venv` if missing, installs dependencies when needed, and starts the server.  
Default starting port: **8765**. If busy, the app picks the next free one.  
Custom port:

```bash
MH_PORT=9010 ./run.sh
```

Manual run:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
.venv/bin/python backend/main.py
```

### What it does

MatrixHunt Ultimate is a local-first free-game aggregator. It collects offers from stores/sources, shows them in a browser UI, and can proxy external pages through an HTML cleaner.

| Route | Description |
|---|---|
| `/` | Offers dashboard |
| `/offers` | Offers list |
| `/view` | Page proxy/viewer with sanitization |
| `/db` | Read-only DB viewer |
| `/retro` | Retro hub + hardware scan |
| `/pad` | Gamepad test |
| `/wiki`, `/bookmarks` | Wiki and bookmarks |
| `/flash` | Arcade embeds (Internet Archive) |
| `/muzeum` | Local specimens rejected by sanitizer |

### Data sources & pricing

Active scrapers: GamerPower, Epic Games, Steam, GOG, IndieGala, Reddit, LowcyGier.  
Parked sources and reasons: `GET /api/scrapers`.

Pricing is explicit: `price_claim` + `price_source`.  
`api:<store>` means measured from store API; `listing:<url>` means listing claim.  
Missing `price_source` means unverified.

### Security & privacy

- API mutations require `X-MH-Token` from `/api/client-config`.
- Proxy has SSRF guards on every hop/redirect.
- External HTML is sanitized; images go through `/api/img` with magic-byte validation and `nosniff`.
- Store sessions are isolated per host, or ephemeral in RAM (30 min).
- Passwords are not stored; only session cookies are persisted when using persistent mode.
- Adult content is hidden by default (UI/API/RSS).

This is a local-first app. Do not expose it publicly without understanding the risks. Optional self-hosting notes: `SECURITY.md`.

### Tests

```bash
.venv/bin/python -m pytest tests/ -q
node tools/scripts/smoke_render.js
./weryfikuj.sh
./tools/shell/scan_wyciekow.sh
```

### License

CC BY-NC-SA 4.0, author: **Arkadiusz Slowik**.  
The software is free — if someone sells it, they are scamming you.  
Use only with games/content you have rights to.
