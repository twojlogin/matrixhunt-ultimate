# MatrixHunt Ultimate

> Lokalny agregator darmowych gier: zbiera oferty ze sklepów, pokazuje je w przeglądarce,
> czyści strony z reklam i trackerów. Zero chmury, zero CDN — React i Babel
> są zvendorowane, baza to lokalny SQLite.

`Python 3.12 · FastAPI · SQLite (WAL) · 46 tras API · pytest · offline-first`

## Spis treści

1. [Szybki start](#1-szybki-start)
2. [Interfejs](#2-interfejs)
3. [API](#3-api)
4. [Źródła danych](#4-źródła-danych)
5. [Bezpieczeństwo](#5-bezpieczeństwo)
6. [Prywatność i treści 18+](#6-prywatność-i-treści-18)
7. [Retro i Flash](#7-retro-i-flash)
8. [Testy](#8-testy)
9. [Struktura projektu](#9-struktura-projektu)
10. [Ograniczenia](#10-ograniczenia)
11. [Licencja](#11-licencja)

## 1. Szybki start

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
cd backend && ../.venv/bin/python main.py
```

Lub uruchom bootstrap.sh (tworzy .venv i instaluje zależności):

```bash
bash bootstrap.sh
cd backend && ../.venv/bin/python main.py
```https://github.com/twojlogin/matrixhunt-ultimate/blob/main/README.md

Aplikacja zajmuje pierwszy wolny port od 8000 i wypisuje go w konsoli.
Przy pustej bazie robi jednorazowy scrape startowy. Internetu używa tylko do:
sklepów/agregatorów, list filtrów (EasyList i spółka) oraz audytu zależności (na klik).

## 2. Interfejs

Wszystkie podstrony mają górne menu z 10 linkami — nic nie jest schowane w stopce.

| Adres | Co to jest |
|---|---|
| `/` | dashboard ofert |
| `/offers` | lista ofert (osobny widok) |
| `/view` | proxy stron: wklej URL sklepu, dostajesz oczyszczoną wersję (goły `/view` to ekran startowy) |
| `/db` | podgląd bazy (tylko odczyt) |
| `/retro` | hub emulatorowy + skan sprzętu (rozdz. 7) |
| `/pad` | test pada (Gamepad API) |
| `/wiki`, `/bookmarks` | wiki, zakładki |
| `/flash` | gry arcade uruchamiane w przeglądarce, bez pobierania plików |
| `/muzeum` | lokalne próbki treści odrzuconych przez sanityzer |
| `/uwagi` | uwagi |

## 3. API

Pełna lista tras: `grep -oE '@app\.(get|post|put|delete)\(' backend/main.py | wc -l` (46 tras).

| Grupa | Trasy |
|---|---|
| Oferty | `GET /api/offers`, `GET /api/stats`, `GET /api/scrapers`, `POST /api/scrape`, `GET /api/price-changes` |
| Proxy | `/api/clean`, `/api/img`, `/api/netcheck`, `/api/filterlists`, `/api/filterlog` |
| Sesje | `/api/sessions`, `/api/sessions-ephemeral`, `/api/auth/steam/*` |
| Narzędzia | `/api/db/*`, `/api/settings`, `/api/vulncheck`, `/api/cvefeed`, `/api/vault/*`, `/api/rss` |

Zasady:

- Zapisy wymagają nagłówka `X-MH-Token` z `/api/client-config` (token losowany na start).
- CORS: `allow_origins=[]` — obcy origin nie dostaje nagłówków, odczyt blokuje przeglądarka.
- `GET /api/offers` defaultowo pomija `is_adult`; dorosłe tylko z `?nsfw=1` (po bramce 18+ w UI). RSS nigdy nie niesie 18+.
- Bez bliźniaków: URLe kanoniczne na wejściu (bez `utm_*`, kotwic i slasha);
  na odczycie ta sama gra z kilku źródeł skleja się w jeden wiersz
  (pomiar `api:*` wygrywa z opisem `listing:*`).

## 4. Źródła danych

| Aktywne (7) | Skąd biorą tytuły |
|---|---|
| GamerPower | agregator: `gamerpower.com/api/giveaways` |
| Epic | oficjalne API: darmowe gry tygodnia |
| Steam | wyszukiwarka + oficjalne `api/appdetails` na grę |
| GOG | wewnętrzny endpoint sklepu (zwykle 0 — uczciwie, patrz ograniczenia) |
| IndieGala | `freebies.indiegala.com` (HTML) |
| Reddit | `r/FreeGameFindings` przez mirror Arctic Shift |
| Łowcy Gier | polskie `lowcygier.pl/darmowe/` przez RSS (strona za Cloudflare) |

Zaparkowane (8, powód każdego w `/api/scrapers` → `reason`): FreeSteamKeys, Nebula,
SharewareOnSale, Humble, GameJolt, GiveawayRadar, FreeToGame, Itch.io.

**Polityka cen:** `price` bywa puste; wiążące są `price_claim` + `price_source`.
`api:<sklep>` = pomiar z API sklepu, `listing:<url>` = deklaracja strony zbierającej.
Wiersz bez `price_source` to cena niesprawdzona. Powtórny scrape aktualizuje cenę
(listing nigdy nie nadpisuje pomiaru `api:*`), zmiany lądują w `price_history`.

Migawka lokalnej bazy z 2026-10-15 (baza jest lokalna, nie w repo): 112 ofert,
zero pomiarów `api:*` poza scraperami API.

## 5. Bezpieczeństwo

| Ryzyko | Zabezpieczenie |
|---|---|
| CSRF / obce originy | token `X-MH-Token` + strażnik `_api_guard` (tylko loopback) |
| SSRF przez proxy | bramka `is_url_allowed` na każdym hopy (bloki: intranet, metadata, `file:`, porty) |
| hasło formularza przez proxy | POST formularza jest dozwolony wyłącznie do HTTPS; przekierowanie POST do HTTP jest blokowane |
| XSS z obcych stron | sanacja HTML (`clean_html`), resourcy tylko z allowlist; schematy (`javascript:`/`data:`) zdejmowane **po normalizacji** znaków sterujących (obfuskacja tab/newline) |
| Polygloty w obrazkach | `validate_image` po magic bytes + `nosniff` |
| Wrogie URL-e w bazie | tylko `http(s)` z hostem, zero plików `.exe/.zip/.rar` (zapora na wejściu) |
| Prompt injection w cudzej treści | deterministyczny sanityzer `sanitize_text` (bidi, znaki sterujące/zerowej szerokości, tag-block) + `strip_hidden_html`; trafienia lądują w lokalnym **muzeum okazów** (`/muzeum`) |
| Krótkie/podejrzane linki | **link doctor** (`/api/linkcheck`): rozwija skracacze (bramka SSRF na każdym hopie), pyta Cloudflare security DNS i wiek domeny (RDAP), flaguje `.exe/.sh` i IDN — werdykt ok/ostrzeż/zablokuj, **nie pobiera treści** strony |
| Sekrety na dysku | vault Fernet; hasła nie są zapisywane wcale (leci tylko Set-Cookie do słoika) |
| Sesje do sklepów | jeden izolowany słoik na host **lub** tryb ulotny (RAM, 30 min, patrz rozdz. 6) |
| Baza przez UI | `/db` i `/api/db/*` tylko do odczytu; nazwy tabel z allowlisty |

Ścieżka czytania cudzych treści jest **deterministyczna**: parsowanie → sanityzacja →
weryfikacja → tagowanie. Żaden model językowy nie jest w nią wpięty na siłę; gdyby
kiedyś był, dostanie wyłącznie oczyszczone pola strukturalne (nigdy surowy tekst strony,
nigdy sieć, nigdy narzędzia), a jego wyjście traktujemy jako niezaufane. Powód: modele
doklejone „na siłę” do potoku zostały już przejęte przez wstrzyknięty tekst.

## 6. Prywatność i treści 18+

- Domyślnie 18+ jest niewidoczne: w UI, w API i w RSS.
- Odblokowanie wymaga kliknięcia **„MAM 18+”** w modalu (osobno na `/` i `/offers`);
  ukrycie zawsze na jeden klik. Szukajka znajduje dorosłe tylko po odblokowaniu.
- **Tryb ulotny** w `/view`: logowanie do sklepów bez śladu na dysku
  (słoik w RAM, 30 min bezczynności / restart / przycisk kasuje).
  Hasła nie są zapisywane w żadnym trybie.
- To chroni przed przypadkowym śladem, nie przed forensyką żywego RAM.

## 7. Retro i Flash

`/retro` to hub linków (emulatory, ROM-y, vault, delisted) — gier nie uruchamia.
Ma też **skan sprzętu**: WebGL, `hardwareConcurrency`, `deviceMemory`, Gamepad API
porównane z progami z `tools/emulator-db.js`. Granice uczciwości: RAM 0 = przeglądarka
ukrywa, RAM 8 GB = możliwy limit Chromium, Vulkan = UNKNOWN gdy niewykrywalny,
zamaskowany renderer GPU = wynik szacowany. Na Windows + Chrome wynik wiarygodny,
na Firefox/Safari pesymistyczny.

`/flash` osadza wybraną grę z Internet Archive. Nie wymaga pobierania ani
otwierania lokalnych plików; do działania potrzebuje połączenia z internetem.

## 8. Testy

```bash
.venv/bin/python -m pytest tests/ -q
node tools/smoke_render.js                  # render `/`, `/offers`, `/view` bez przeglądarki
./weryfikuj.sh                               # pełna weryfikacja z siecią (uwaga: start serwera = scrape, >120 s)
./sync.sh <katalog-docelowy>                # lustro do drugiej kopii (bez twardych ścieżek)
./tools/scan_wyciekow.sh                    # higiena przed pushem (sekrety, ścieżki)
```

| Plik | Co sprawdza |
|---|---|
| `tests/test_release_security.py` | regresje zabezpieczeń API, proxy i HTML |
| `tests/test_verify_seeds.py` | seed catalog: odrzucanie cen promocyjnych i brak potwierdzenia ceny |
| `tests/test_ceny.py` | niezmienniki cen na prawdziwych plikach i bazie (żadnego `Free` bez `api:*`) |
| `tests/test_niezmienniki.py` | filtry, baza, serwer, F2P/DLC |
| `tests/test_niezalezne.py` | zachowanie na spreparowanych danych: logika cen, SSRF, migracja, martwe linki, offline, punktacja JS, bramka 18+, parser Łowców, render frontendów, sklejanie bliźniaków, jeden `site.js`, kanon 10 linków + filtr źródeł, toggle PL/EN, sanityzer wstrzyknięć i muzeum okazów, link doctor |

Filozofia: test ma dać się złamać psując kod. Po tym, jak 52 testy przechodziły
przy żywym błędzie (`Deal.price` domyślnie `"Free"`), dopisaliśmy testy, które go łapią.

## 9. Struktura projektu

```
backend/            # FastAPI: main.py, scrapers/, cleaner, vault, sessions, DB
frontend/           # / i /offers (React zvendorowany) + vendor/ (Babel)
tools/              # strony /view /retro /wiki /flash /db /muzeum + skrypty (build, smoke, skan)
data/               # retro.json, bookmarks.json, seed_offers.json (36 zweryfikowanych tytułów F2P)
tests/              # testy jednostkowe, integracyjne i regresyjne
```

Runtime (gitignorowane, nie w repo): `.venv/`, `matrixhunt.db*`, `.cookies/`,
`.session_secret`, `.app_settings.json`, `.filterlists/`, `.specimens/`.

## 10. Ograniczenia

- GOG zwykle zwraca 0 — endpoint nie ma filtra darmowych; giveawaye wpadają parę razy do roku.
- itch.io zaparkowany (parser kłamał `price="Free"`).
- DLsite odrzucony jako źródło: sklep w większości 18+, brak publicznego API, gry jako `.exe`.
- `seed_offers.json`: 36 zweryfikowanych tytułów F2P (Steam API), ładuje się przy pustej bazie.
- Bez skonfigurowanego vault pliki ustawień i cookies są jawne (`PLAIN:`), ale
  mają uprawnienia właściciela. Po skonfigurowaniu vault blokada uniemożliwia
  odczyt i zapis, także starych plików jawnych; po odblokowaniu starsze pliki
  są przenoszone do formatu szyfrowanego. Proxy nie wraca po cichu do ruchu
  bezpośredniego.
- Proxy nieprzetestowane z prawdziwym logowaniem do sklepu; pad bez testów na sprzęcie.
- Odblokowanie vault i zapis wrażliwych plików używają atomowej podmiany;
  nieudane szyfrowanie przerywa odblokowanie.
- Historia: proxy zwracało kiedyś 403 na 3 sklepach (niezbadane, do powtórzenia).

## 10a. Self-hosting (opcjonalne)

MatrixHunt to aplikacja local-first. Jeśli chcesz ją wystawić (demo, self-hosting)
bez ujawniania IP:

- **Cloudflare Tunnel** + **tryb read-only**:
  ```bash
  MH_PUBLIC=1 MH_HOST=0.0.0.0 ./bootstrap.sh   # zablokuj zapisy/scrapowanie
  ./tools/cloudflared_setup.sh matrixhunt.twojadomena.pl
  ```
  Włącz **Cloudflare Access** (Zero Trust) — bez tego każdy kto zna URL ma dostęp.
- **Tailscale** (zalecane dla użytku prywatnego): mesh VPN, brak publicznego URL.
- **IP podczas scrapowania**: sklepy widzą Twoje IP — włącz tryb Tor w ustawieniach
  lub użyj upstream proxy (`socks5h://127.0.0.1:9050`).

Szczegóły: [SECURITY.md](SECURITY.md).

## 10b. Autor i podziękowania

Projekt stworzony przez **Arkadiusz Slowik** (CC BY-NC-SA 4.0).

Część kodu i poprawek (sanityzacja, testy niezmienników, audyt bezpieczeństwa,
seed catalog, CI, bootstrap) była pisana z pomocą **AI** (Claude / Anthropic) —
traktuj to jako narzędzie, nie autora. Cała odpowiedzialność za kod spoczywa
na autorze.

Pomoc AI w tym projekcie zawiodła: wcześniejsze odpowiedzi zbyt pewnie
sugerowały, że problemy rozwiązano, opierając się na testach bez pełnego
przeglądu logiki i działania aplikacji. To było niewystarczające i mogło
wprowadzić użytkownika w błąd. Zielone testy potwierdzają tylko sprawdzone
scenariusze — nie dowodzą, że aplikacja jest wolna od błędów ani że cały
projekt został przejrzany. AI nie zastępuje rzetelnej weryfikacji zmian.

## 11. Licencja

CC BY-NC-SA 4.0, autor: Arkadiusz Slowik. Oprogramowanie jest darmowe —
ktoś je sprzedaje, ten oszukuje. Tylko do użytku z grami, do których masz prawa.
