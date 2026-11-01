# GDZIE TEN KOD WYCHODZI DO SIECI

Audyt wykonany na plikach, nie deklarowany. Wszystko poniżej to lista, nie
opinia. Weryfikowalne: każdy punkt ma plik i linię.

Wykonane: `./.venv/bin/python`, `grep`, bez uruchamiania ruchu sieciowego poza
pobraniem filtrów i odpowiedzi testowych.

---

## 1. HOSTY, DO KTÓRYCH APLIKACJA SIĘ ŁĄCZY

Sklepy i źródła danych — to po to istnieje aplikacja:

```
www.gamerpower.com          store.steampowered.com    steamcommunity.com
www.gog.com                 store.epicgames.com       itch.io
freebies.indiegala.com      www.humblebundle.com      www.freetogame.com
www.freesteamkeys.com       sharewareonsale.com       games.nebula.app
gamejolt.com                giveawayradar.com         www.reddit.com
arctic-shift.photon-reddit.com                       web.archive.org
archive.org                 raw.githubusercontent.com
```

Listy filtrów (subskrypcje, odświeżane co 24 h):
```
easylist.to
```

Audyt bezpieczeństwa (tylko po Twoim kliknięciu):
```
api.osv.dev                  www.cisa.gov              check.torproject.org
```

Logowanie Steam:
```
steamcommunity.com           specs.openid.net
```

Hosty docelowe nie są ograniczone do powyższej listy: użytkownik może wskazać
adres przez `/api/clean`, `/api/linkcheck` lub własną listę filtrów, a także
ustawić własny upstream proxy. To są jawne funkcje aplikacji, nie telemetria.

**Nie ma w kodzie:** żadnego hosta analitycznego, telemetrycznego, żadnego
LLM/AI API, żadnego webhooka, webhooks.discord, ngrok, requestbin, pipedream.
Sprawdzone grepem po `google-analytics`, `googletagmanager`, `gtag`, `segment.io`,
`mixpanel`, `amplitude`, `sentry`, `datadog`, `openai`, `anthropic`, `huggingface`,
`cohere`, `ollama` — jedyne trafienia to nazwy w filtrach reklamowych EasyList,
czyli lista reguł blokujących, nie kod analityczny.

---

## 2. CO WYCHODZI Z TWOJEGO WEJŚCIA

`POST /api/clean` może przekazać formularz logowania do wskazanej strony,
łącznie z wpisanym hasłem; POST jest blokowany dla HTTP i przy przekierowaniu
POST do HTTP. Aplikacja zapisuje z odpowiedzi wyłącznie `Set-Cookie`, nie
treść formularza. Zapis cookies jest per host.

Są też żądania wychodzące wywoływane przez funkcje użytkownika: `/api/linkcheck`
sprawdza podany URL, a pobranie własnej listy filtrów pobiera wskazany plik.
Te funkcje wysyłają URL/żądanie pobrania, nie zawartość formularza. URL-e są
sprawdzane przed połączeniem i przy przekierowaniach.

To nie jest pełny spis ruchu sieciowego ani dowód, że dane nie mogą trafić
do hosta docelowego przez treść strony.

---

## 3. CO SIEDZI NA DYSKU

| Plik | Zawartość |
|---|---|
| `backend/.session_secret` | klucz podpisu ciasteczka sesji |
| `backend/.app_settings.json` | ustawienia proxy/Tor/list filtrów |
| `backend/.cookies/*.json` | ciasteczka per witryna |
| `backend/matrixhunt.db` | lokalne oferty i historia |
| `backend/.filterlists/*.txt` | pobrane listy filtrów |
| `backend/.kev.json` | katalog CVE CISA KEV |

Bez skonfigurowanego weryfikatora vault pliki wrażliwe są jawne (`PLAIN:`)
i mają uprawnienia właściciela. Po skonfigurowaniu vault jego blokada odmawia
odczytu i zapisu, również dla starszych plików jawnych; odblokowanie migruje
takie pliki do formatu szyfrowanego. Nie umieszczaj tych plików w repozytorium.

---

## 4. CO NIE ROBI

| Nie ma | Sprawdzone |
|---|---|
| wbudowanej analityki/telemetrii/webhooków | grep po analytics, webhook, ngrok, discord, telegram, beacon |
| wysyłania haseł do serwera analitycznego | hasło z formularza idzie do wskazanego celu `/api/clean` |
| automatycznych pobrań w tle poza odświeżeniem list filtrów | `_maybe_refresh_background` w `filterlists.py` |
| automatycznego uruchamiania testów w tle | testy w `tests/` uruchamia się ręcznie |

---

## 5. CZEGO NIE SPRAWDZIŁEM

Podaję, żeby ta lista nie udawała kompletności:

- **Nie uruchamiałem aplikacji pod ruchem sieciowym i nie monitorowałem pakietów.**
  Analiza jest statyczna — czytanie kodu. Dynamicznie (wireshark/tcpdump) nie
  robiłem.
- **Testy automatyczne nie są testem ruchu sieciowego ani dowodem braku błędów.**
  Ostatni przebieg lokalny: `115 passed, 10 skipped`; nie testuje prawdziwego
  logowania do sklepu ani wszystkich zachowań w przeglądarce.
- **Nie sprawdzałem skryptów vendored** (`frontend/vendor/`): React 18.3.1,
  ReactDOM, Babel — pliki pobrane wcześniej, weryfikacja sumy kontrolnej
  nie była przeze mnie robiona.
- **Proxy nie przeszło przez prawdziwy sklep z prawdziwym logowaniem.**
  `example.com` nie ma formularza ani ciasteczek. Maszyneria jest napisana, ale
  nie była przetestowana end-to-end z prawdziwym kontem.
