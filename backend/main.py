import asyncio
import aiohttp
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape
from types import SimpleNamespace
from urllib.parse import urljoin, urlparse, urlsplit

from cleaner import is_url_allowed, clean_html, MAX_BYTES, new_safe_session
from steam_auth import build_login_url, verify_response, fetch_persona, fetch_games_count

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from database import init_db, Offer, PriceHistory
from sqlalchemy import text

from scrapers.gamerpower import GamerpowerScraper
from scrapers.epic import EpicScraper
from scrapers.steam import SteamScraper
from scrapers.gog import GOGScraper
from scrapers.itch import ItchScraper
from scrapers.indiegala import IndieGalaScraper
from scrapers.freetogame import FreeToGameScraper
from scrapers.freesteamkeys import FreeSteamKeysScraper
from scrapers.nebula import NebulaScraper
from scrapers.shareware import SharewareScraper
from scrapers.humble import HumbleScraper
from scrapers.gamejolt import GameJoltScraper
from scrapers.giveawayradar import GiveawayRadarScraper
from scrapers.reddit import RedditScraper
from scrapers.lowcygier import LowcyGierScraper

BASE_DIR = Path(__file__).parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"
TOOLS_DIR = BASE_DIR.parent / "tools"
DATA_DIR = BASE_DIR.parent / "data"

app = FastAPI(title="MatrixHunt Ultimate", version="1.0.0")
# The dashboard is served same-origin, so no cross-origin access is needed at
# all. CORSMiddleware is therefore configured to emit nothing, and _api_guard
# echoes the origin back only when it is EXACTLY this app's own origin.
# An "any loopback port" regex used to sit here, which let a page served by
# any other local app read /api/client-config and drive every state-changing
# endpoint - a local-origin hijack. Pinning it from a startup hook did not
# work either: Starlette builds the middleware stack before startup events
# run, so mutating the kwargs there was a silent no-op.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_origin_regex="",
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-MH-Token"],
)

# Tryb publiczny (MH_PUBLIC=1): aplikacja tylko do odczytu — blokuje zapisy,
# scrapowanie i zmiany stanu. Przydatne przy wystawianiu przez Cloudflare
# Tunnel, żeby nie udostępniać jednoosobowej aplikacji całemu internetowi.
import os as _os
_MH_PUBLIC = _os.environ.get("MH_PUBLIC", "").strip() in ("1", "true", "yes")

if _MH_PUBLIC:
    print("[MH_PUBLIC] tryb tylko-do-odczytu: zapisy i scrapowanie zablokowane")
app.mount("/tools", StaticFiles(directory=str(TOOLS_DIR)), name="tools")
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend-static")
# /data is NOT a blanket static mount. It held data/vulncheck.json, which
# pins the exact version of every installed dependency, and that file was
# served to anyone who asked for /data/vulncheck.json with no token. Only the
# four public catalogues are exposed, by explicit name.
_PUBLIC_DATA = ("seed_offers.json", "retro.json", "bookmarks.json")
_DATA_PATHS = {
    "seed_offers.json": DATA_DIR / "seed_offers.json",
    "retro.json": DATA_DIR / "retro.json",
    "bookmarks.json": DATA_DIR / "bookmarks.json",
}


@app.get("/data/{name}")
async def data_file(name: str):
    path = _DATA_PATHS.get(name)
    if path is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    if not path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(str(path), media_type="application/json")


def _session_secret():
    """Signing key for the login cookie. Env wins; otherwise a file created
    once with owner-only permissions, sealed by the vault when unlocked.
    Never hardcoded, never logged.

    Three ways this used to end up with an EMPTY key, which signs happily and
    lets anyone mint a valid mh_session as any SteamID:
      * a crash between write_bytes truncation and write left a 0-byte file,
        and vault.unseal(b"") falls through to the legacy passthrough -> b""
      * a corrupt sealed file raised Fernet's InvalidToken, which is NOT a
        ValueError, so it escaped and killed startup instead of falling back
      * the file was written before chmod, leaving a window at 0644
    So: atomic write via temp+replace, reject anything short, catch broadly.
    """
    import os
    import secrets
    import tempfile
    if os.environ.get("MH_SECRET_KEY"):
        return os.environ["MH_SECRET_KEY"]
    from vault import vault
    path = BASE_DIR / ".session_secret"
    try:
        if path.exists():
            stored = vault.unseal(path.read_bytes()).decode("utf-8", "replace").strip()
            if stored:
                return stored
            print("[session_secret] stored secret is empty - generating a fresh one")
            return secrets.token_hex(32)
        secret = secrets.token_hex(32)
        # Create with 0600 from the start, then rename: os.replace is atomic,
        # so a crash can never leave a truncated secret behind.
        fd, tmp = tempfile.mkstemp(dir=str(BASE_DIR), prefix=".session_secret.")
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as fh:
                fh.write(vault.seal(secret.encode("utf-8")))
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        return secret
    except Exception:
        # Locked vault, corrupt file, unreadable disk: fresh ephemeral key.
        # Sessions from before the restart simply invalidate - safe default.
        return secrets.token_hex(32)


from starlette.middleware.sessions import SessionMiddleware
app.add_middleware(SessionMiddleware, secret_key=_session_secret(),
                   session_cookie="mh_session", max_age=30 * 24 * 3600,
                   same_site="lax", https_only=_MH_PUBLIC)


def _api_token():
    """Mutation token (Jupyter-style). Env wins, else random per boot -
    printed nowhere, fetched by the same-origin UI via /api/client-config."""
    import os
    import secrets
    return os.environ.get("MH_API_TOKEN") or secrets.token_hex(16)


API_TOKEN = _api_token()


def _is_loopback_host(host):
    if not host or "," in host:
        return False
    try:
        authority = urlsplit("//" + host)
        name = authority.hostname
        port = authority.port
    except ValueError:
        return False
    if not name or (port is not None and not 1 <= port <= 65535):
        return False
    if name.lower() == "localhost":
        return True
    import ipaddress
    try:
        address = ipaddress.ip_address(name)
        mapped = getattr(address, "ipv4_mapped", None)
        return address.is_loopback or bool(mapped and mapped.is_loopback)
    except ValueError:
        return False


def _is_loopback_client(request):
    client = request.client
    if not client or not client.host:
        return False
    import ipaddress
    try:
        address = ipaddress.ip_address(client.host.split("%", 1)[0])
        mapped = getattr(address, "ipv4_mapped", None)
        return address.is_loopback or bool(mapped and mapped.is_loopback)
    except ValueError:
        return False


def _token_ok(candidate):
    """Constant-time compare, so a wrong token cannot be discovered by
    timing the response."""
    import hmac as _hmac
    return _hmac.compare_digest(candidate, API_TOKEN)


@app.middleware("http")
async def _api_guard(request, call_next):
    """DNS-rebinding + CSRF guard for the API, and the ONLY place CORS is
    granted. Predictable loopback ports are trivially probed, so:

      * local mode checks both the actual peer address and loopback Host
      * state-changing calls need the per-boot token (header, or the
        server-generated form action for proxied forms)
      * browser API calls must be same-origin; proxy GETs also require a
        same-origin Fetch Metadata signal when Origin is omitted
    """
    if request.url.path.startswith("/api/"):
        # Tryb publiczny (MH_PUBLIC=1): aplikacja tylko-do-odczytu.
        if _MH_PUBLIC and request.method in ("POST", "PUT", "PATCH", "DELETE"):
            return JSONResponse({"error": "read-only mode (MH_PUBLIC=1)"}, status_code=403)
        if not _MH_PUBLIC:
            if not _is_loopback_client(request):
                return JSONResponse({"error": "loopback client only"}, status_code=403)
            if not _is_loopback_host(request.headers.get("host")):
                return JSONResponse({"error": "loopback host only"}, status_code=403)

        origin = request.headers.get("origin")
        fetch_site = request.headers.get("sec-fetch-site", "").lower()
        same_origin = bool(origin and _is_own_origin(origin, request))
        if origin and not same_origin:
            return JSONResponse({"error": "cross-origin blocked"}, status_code=403)
        if fetch_site and fetch_site not in ("same-origin", "none"):
            return JSONResponse({"error": "cross-origin blocked"}, status_code=403)

        token = request.headers.get("x-mh-token", "")
        if not token and request.url.path == "/api/clean":
            token = request.query_params.get("token", "")
        token_valid = bool(token and _token_ok(token))

        # A proxy fetch stores upstream cookies, so even GET must prove that
        # the caller is this app's page, not a cross-site image/iframe.
        if (request.url.path in ("/api/clean", "/api/img")
                and request.method == "GET"
                and not (same_origin or fetch_site == "same-origin" or token_valid)):
            return JSONResponse({"error": "same-origin proxy request required"}, status_code=403)

        if request.method not in ("GET", "HEAD", "OPTIONS"):
            if not token_valid:
                return JSONResponse({"error": "missing or bad api token"}, status_code=403)
        if (_MH_PUBLIC and not (same_origin or fetch_site == "same-origin"
                                or token_valid)):
            return JSONResponse({"error": "same-origin or api token required"}, status_code=403)
    response = await call_next(request)
    origin = request.headers.get("origin")
    if origin and _is_own_origin(origin, request):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        if request.method == "OPTIONS" and request.url.path.startswith("/api/"):
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-MH-Token"
            response.headers["Access-Control-Max-Age"] = "600"
    return response


def _is_own_origin(origin, request):
    try:
        parsed_origin = urlsplit(origin)
        request_host = urlsplit("//" + request.headers.get("host", ""))
        origin_host = parsed_origin.hostname
        host = request_host.hostname
        origin_port = parsed_origin.port
        host_port = request_host.port
    except ValueError:
        return False
    if (parsed_origin.username is not None or parsed_origin.password is not None
            or parsed_origin.path not in ("", "/")
            or parsed_origin.query or parsed_origin.fragment
            or not origin_host or not host or origin_host.lower() != host.lower()):
        return False
    if host_port is not None:
        if origin_port != host_port:
            return False
    elif origin_port not in (None, 80, 443):
        return False
    if _MH_PUBLIC:
        return parsed_origin.scheme in ("http", "https")
    expected_port = request.url.port or (443 if request.url.scheme == "https" else 80)
    actual_port = origin_port or (443 if parsed_origin.scheme == "https" else 80)
    return parsed_origin.scheme == request.url.scheme and actual_port == expected_port


@app.get("/api/client-config")
async def client_config():
    """Token + port for the same-origin UI, guarded by peer and origin checks."""
    return {"token": API_TOKEN, "port": getattr(app.state, "port", 8000)}

DB_PATH = f"sqlite:///{BASE_DIR / 'matrixhunt.db'}"
SessionFactory = init_db(DB_PATH)

SCRAPER_CLASSES = [
    GamerpowerScraper, EpicScraper, SteamScraper, GOGScraper,
    IndieGalaScraper, RedditScraper, LowcyGierScraper,
]
# Every scraper file is present and imported. The ones below are opt-in
# because they returned 0 or timed out, and their hanging timeouts dominated
# every scrape. They are NOT dead code and NOT deleted - /api/scrapers reports
# them so the list is visible instead of a comment nobody reads.
# FreeToGame is disabled for a different reason: freetogame.com only indexes
# free-to-play, which is not free-to-keep, so every entry was rejected anyway.
DISABLED_SCRAPERS = {
    "FreeSteamKeys": FreeSteamKeysScraper,
    "Nebula": NebulaScraper,
    "SharewareOnSale": SharewareScraper,
    "Humble": HumbleScraper,
    "GameJolt": GameJoltScraper,
    "GiveawayRadar": GiveawayRadarScraper,
    "FreeToGame": FreeToGameScraper,
    # itch.io: /games/free returns author pages, not giveaways, and
    # the parser stamped price="Free" on every row without reading the
    # store page. That is a false statement in the database, not a
    # cosmetic bug - parked until the price is verified per entry.
    "Itch.io": ItchScraper,
}

# Why each one is parked. This was a comment in the source, and /api/scrapers
# returned status="parked" with no reason, so the dashboard could not tell the
# user anything except that something was off. Comments are not an interface.
PARKED_REASON = {
    "FreeSteamKeys": "zwraca 0 ofert albo timeout — czas oczekiwania dominował każdy przebieg",
    "Nebula": "zwraca 0 ofert albo timeout",
    "SharewareOnSale": "zwraca 0 ofert albo timeout",
    "Humble": "zwraca 0 ofert albo timeout",
    "GameJolt": "zwraca 0 ofert albo timeout",
    "GiveawayRadar": "zwraca 0 ofert albo timeout",
    "FreeToGame": "indeksuje tylko free-to-play, a to nie jest free-to-keep — każdy wpis i tak był odrzucany",
    "Itch.io": "/games/free zwraca strony autorów, nie giveawayy; parser stawiał price=\"Free\" bez czytania strony sklepu",
}


@app.get("/api/scrapers")
async def scrapers_status():
    """Which sources run, which are parked, and why. Exists so the parked
    list is visible somewhere real instead of only in a source comment."""
    active = []
    for cls in SCRAPER_CLASSES:
        active.append({"name": cls.__name__, "module": cls.__module__.split(".")[-1],
                       "status": "active"})
    parked = [{"name": n, "module": c.__module__.split(".")[-1], "status": "parked",
               "reason": PARKED_REASON.get(n, "brak zanotowanego powodu")}
              for n, c in DISABLED_SCRAPERS.items()]
    return {"active": active, "parked": parked,
            "counts": {"active": len(active), "parked": len(parked)}}


async def run_all_scrapers():
    # One hanging source must never stall the whole run (that was the
    # Nebula/GiveawayRadar story: two dead timeouts dominated every scrape
    # and stacked /api/scrape calls could pile up indefinitely).
    async with aiohttp.ClientSession() as session:
        all_deals = []
        refreshed_sources = set()
        for cls in SCRAPER_CLASSES:
            try:
                scraper = cls(session=session)
                deals = await asyncio.wait_for(scraper.scrape(), timeout=45)
                all_deals.extend(deals)
                refreshed_sources.update(
                    deal.source for deal in deals if getattr(deal, "source", None))
                print(f"[{scraper.name}] Found {len(deals)} deals")
            except asyncio.TimeoutError:
                print(f"[{cls.__name__}] Timeout after 45s, skipped")
            except Exception as e:
                print(f"[{cls.__name__}] Error: {e}")
        return all_deals, refreshed_sources


_scrape_lock = asyncio.Lock()


async def guarded_scrape():
    """A scrape is already expensive; never stack two. Concurrent callers
    get 409 instead of queueing another multi-minute run."""
    if _scrape_lock.locked():
        return None
    async with _scrape_lock:
        deals, refreshed_sources = await run_all_scrapers()
        return save_deals_to_db(deals, refresh_sources=refreshed_sources)


def load_seed_catalog():
    """Insert the curated permanent-free catalog when the DB is near-empty.

    Only 1-2 scrapers return live deals on a good day, so a fresh install
    would otherwise show a near-empty page. Seeds are verified (Steam API
    is_free / live page check at build time) and idempotent via URL dedupe.
    Normal operation (DB >= 20 rows) is untouched.
    """
    import json as _json
    try:
        seeds = _json.loads((DATA_DIR / "seed_offers.json").read_text())
    except Exception as e:
        print(f"Seed catalog unreadable: {e}")
        return 0
    return save_deals_to_db([
        SimpleNamespace(title=s["title"], url=s["url"],
                        price=s.get("price", ""),
                        price_claim=s.get("price_claim") or s.get("price") or "Free",
                        price_source=s.get("price_source", "listing:seed-catalog"),
                        original_price="", category=s.get("category", "games"),
                        source=s.get("source", "SeedCatalog"),
                        description=s.get("description", ""), image_url="",
                        requires_login=False, has_adfly=False, has_captcha=False,
                        is_adult=False)
        for s in seeds if s.get("title") and s.get("url")
    ])


def _apply_price(offer, deal):
    """Przepisuje cene na istniejacym wierszu. True, gdy cos sie zmienilo.

    Wiersze trzymaja sie po URL, wiec bez tego poprawiony scraper nigdy nie
    naprawilby ceny zapisanej wczesniej zle. Nie pozwalamy tez, by twierdzenie
    ze strony zrodlowej nadpisalo pomiar z API sklepu.
    """
    stare_api = (offer.price_source or "").startswith("api:")
    nowe_api = (getattr(deal, "price_source", "") or "").startswith("api:")
    if stare_api and not nowe_api:
        return False
    nowe = (deal.price, getattr(deal, "price_claim", None),
            getattr(deal, "price_source", None))
    if nowe == (offer.price, offer.price_claim, offer.price_source):
        return False
    offer.price, offer.price_claim, offer.price_source = nowe
    offer.price_checked = datetime.now(timezone.utc)
    return True


# Linki do plików wykonywalnych i archiwów nigdy nie są ofertami ze sklepu,
# tylko śmieciem albo wektorem malwaru (szczególnie z Reddita, gdzie postuje
# każdy). Testy D4/D5 pilnowały tego na gotowej bazie, czyli na gapę —
# ta zapora stoi na wejściu i taki URL w ogóle nie dociera do INSERT.
_UNSAFE_FILE_EXT = (".exe", ".msi", ".bat", ".cmd", ".sh", ".scr", ".com",
                    ".pif", ".jar", ".zip", ".rar", ".7z", ".tar", ".gz")


def _is_unsafe_file_url(url):
    """True, gdy URL wskazuje wprost plik wykonywalny / archiwum."""
    try:
        from urllib.parse import unquote
        path = unquote(urlsplit(url).path).lower()
    except Exception:
        return True
    return path.endswith(_UNSAFE_FILE_EXT)


def _safe_offer_url(url):
    try:
        parts = urlsplit(url)
    except (TypeError, ValueError):
        return False
    return bool(
        parts.scheme.lower() in ("http", "https")
        and parts.hostname
        and parts.username is None
        and parts.password is None
        and not _is_unsafe_file_url(url)
    )


# Śmieciowe parametry, które mnożą "różne" URLe do tej samej strony.
_TRACKING_PARAMS = ("utm_source", "utm_medium", "utm_campaign", "utm_term",
                    "utm_content", "fbclid", "gclid", "msclkid")


def _canonical_url(url):
    """Jedna postać URL-a do porównań i zapisu: mały host, bez zbędnego
    slasha na końcu, bez parametrów śledzących, bez kotwicy. Bez tego ten sam
    giveaway spod .../gra/?utm_source=x i .../gra/ lądował w bazie dwa razy
    i dashboard pokazywał bliźniaki jeden pod drugim."""
    try:
        from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        if not host:
            return url
        netloc = f"[{host}]" if ":" in host else host
        default_port = {"http": 80, "https": 443}.get(parts.scheme.lower())
        if parts.port and parts.port != default_port:
            netloc += f":{parts.port}"
        path = parts.path or ""
        if len(path) > 1 and path.endswith("/"):
            path = path[:-1]
        q = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if k.lower() not in _TRACKING_PARAMS]
        q.sort()
        return urlunsplit((parts.scheme.lower(), netloc, path,
                           urlencode(q), ""))
    except Exception:
        return url


def _norm_title(title):
    """Tytuł do porównań: małe litery, bez interpunkcji, pojedyncze spacje."""
    import re as _re
    t = (_re.sub(r"[^\w\s]", "", (title or "").lower(), flags=_re.UNICODE))
    return _re.sub(r"\s+", " ", t).strip()


def _merge_twins(offers):
    """Skleja bliźniaki między źródłami: ta sama gra z Epic (api:) i opisana
    w artykule Łowców / GamerPower (listing:) to jeden wiersz na stronie.
    Zostaje pomiar ze sklepu albo nowszy wpis; artykuły znikają z listy,
    ale ich URLe dalej żyją w bazie (nic nie kasujemy).

    Ostrożnie z podciągami: krótszy tytuł musi mieć min. 8 znaków i pasować
    na granicach słów, żeby "Doom" nie zjadł "Doom 2016".
    """
    import re as _re
    if len(offers) < 2:
        return offers
    norm = [_norm_title(o.title) for o in offers]
    keep = [True] * len(offers)

    def _rank(i):
        o = offers[i]
        api = 1 if (o.price_source or "").startswith("api:") else 0
        ts = o.created_at.isoformat() if o.created_at else ""
        return (api, ts)

    # 1) dokładne duplikaty znormalizowanego tytułu: jeden zostaje.
    seen_title = {}
    for i, n in enumerate(norm):
        if not n:
            continue
        if n in seen_title:
            j = seen_title[n]
            kill = i if _rank(i) < _rank(j) else j
            keep[kill] = False
            seen_title[n] = j if kill == i else i
        else:
            seen_title[n] = i
    # 2) artykuł (listing) opisujący grę ze sklepu (api:) znika z listy.
    prim = [i for i in range(len(offers))
            if keep[i] and (offers[i].price_source or "").startswith("api:")
            and len(norm[i]) >= 8]
    for i in range(len(offers)):
        if not keep[i] or (offers[i].price_source or "").startswith("api:"):
            continue
        for j in prim:
            if _re.search(r"(?<!\w)" + _re.escape(norm[j]) + r"(?!\w)", norm[i]):
                keep[i] = False
                break
    return [o for k, o in enumerate(offers) if keep[k]]


def save_deals_to_db(deals, refresh_sources=()):
    session = SessionFactory()
    new_count = 0
    updated_count = 0
    try:
        # Only the URLs this batch actually collides with need checking.
        # Pulling every stored URL into a set loaded the whole column into
        # memory on each scrape, then copied it a second time into `seen`;
        # on a large catalog that is tens of thousands of rows for nothing.
        batch_urls = set()
        for d in deals:
            if getattr(d, "url", None):
                batch_urls.add(_canonical_url(d.url))
        existing = {}
        if batch_urls:
            for o in session.query(Offer).filter(Offer.url.in_(batch_urls)):
                existing[_canonical_url(o.url)] = o
        seen = set()
        seen_by_source = {}

        for deal in deals:
            if not deal.url or _canonical_url(deal.url) in seen:
                continue
            # Scrapers parse hostile third-party markup; only http(s) links
            # may reach the DB. Anything else (javascript:, data:, ...) would
            # flow into href/src attributes on the dashboard. Host check too:
            # "http://" passes a prefix test and is not a usable link.
            if not _safe_offer_url(deal.url):
                continue
            canon = _canonical_url(deal.url)
            seen.add(canon)
            source = getattr(deal, "source", None)
            if source:
                seen_by_source.setdefault(source, set()).add(canon)

            znany = existing.get(canon)
            if znany is not None:
                znany.is_active = True
                # Re-running a scrape has to refresh the price. Keys are URLs,
                # and skipping known ones meant a scraper fixed today could
                # never repair a price it wrote wrong yesterday. Only a deal
                # that carries a source may overwrite, so a scraper that did
                # not check cannot wipe a figure another source did measure.
                if getattr(deal, "price_source", None) and _apply_price(znany, deal):
                    # Historia zapisuje stan PO zmianie; poprzedni wiersz
                    # historii alba poprzednia wartosc oferty sa punktem
                    # odniesienia. Bez tego "sprawdz zmiany" nie mialoby czego
                    # pokazac, bo oferta trzyma tylko biezaca cene.
                    session.add(PriceHistory(
                        offer_id=znany.id,
                        price_claim=znany.price_claim,
                        price_source=znany.price_source,
                    ))
                    updated_count += 1
                continue

            offer = Offer(
                title=deal.title, url=canon, price=deal.price,
                price_claim=getattr(deal, "price_claim", None),
                price_source=getattr(deal, "price_source", None),
                price_checked=(datetime.now(timezone.utc)
                               if getattr(deal, "price_source", None) else None),
                original_price=deal.original_price, category=deal.category,
                source=deal.source, description=deal.description,
                image_url=deal.image_url, requires_login=deal.requires_login,
                has_adfly=deal.has_adfly, has_captcha=deal.has_captcha,
                is_adult=deal.is_adult,
            )
            session.add(offer)
            existing[canon] = offer
            new_count += 1

        # A non-empty scraper result is a usable snapshot for that source.
        # Retire its old URLs that have disappeared, but keep the last-known
        # catalog when a scraper times out, fails, or returns no valid deals.
        for source in refresh_sources:
            current_urls = seen_by_source.get(source)
            if not current_urls:
                continue
            stale = (session.query(Offer)
                     .filter(Offer.source == source, Offer.is_active == True)
                     .all())
            for offer in stale:
                if _canonical_url(offer.url) not in current_urls:
                    offer.is_active = False

        session.commit()
    except Exception as e:
        session.rollback()
        # Swallowing this made /api/scrape answer {"status":"ok","new":0}
        # with HTTP 200 after a total write failure, so a broken DB looked
        # exactly like a quiet night. Report it.
        print(f"DB Error: {e}")
        raise
    finally:
        session.close()
    return new_count, updated_count


@app.get("/", response_class=HTMLResponse)
async def root():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.get("/offers", response_class=HTMLResponse)
async def offers_page():
    # Osobna trasa, bo strona glowna (sprzet + statystyki) jest zwyklym HTML-em
    # bez Reacta, a lista ofert to komponent. Trzymanie ich razem zmuszalo
    # kazde wejscie do sciagania i kompilowania calego JSX.
    return FileResponse(str(FRONTEND_DIR / "offers.html"))


@app.get("/uwagi", response_class=HTMLResponse)
async def uwagi_page():
    return FileResponse(str(TOOLS_DIR / "uwagi.html"))


MAX_OFFERS_LIMIT = 1000


@app.get("/api/offers")
async def get_offers(source: str = None, search: str = None, limit: int = 1000,
                     nsfw: int = 0):
    # Unbounded limit meant ?limit=1000000000 pulled the whole table into a
    # JSON list; filterlog and db_rows already clamp, this one did not.
    limit = max(1, min(int(limit), MAX_OFFERS_LIMIT))
    session = SessionFactory()
    try:
        query = session.query(Offer).filter(Offer.is_active == True)
        if not int(nsfw or 0):
            # Treści 18+ tylko na wyraźne żądanie (?nsfw=1 po bramce wieku
            # w UI). Default milczy, żeby przypadkowy rzut oka na API/RSS
            # nie pokazywał dorosłych tytułów. isnot(True) łapie też NULL
            # ze starych wierszy sprzed kolumny.
            query = query.filter(Offer.is_adult.isnot(True))
        if source:
            query = query.filter(Offer.source == source)
        if search:
            # Escape LIKE wildcards, otherwise a search for "_" matches every
            # row and "%" is a full table scan.
            pattern = (search.replace("\\", "\\\\")
                              .replace("%", r"\%")
                              .replace("_", r"\_"))
            query = query.filter(Offer.title.ilike(f"%{pattern}%"))
        # LIMIT w SQL przed sklejaniem obcinałby losowy podzbiór bliźniaków.
        # Przy setkach wierszy taniej dobrać w pamięci i przyciąć po mergu.
        offers = _merge_twins([
            offer for offer in query.order_by(Offer.created_at.desc()).all()
            if _safe_offer_url(offer.url)
        ])[:limit]
        return [
            {
                  "id": o.id, "title": o.title, "url": o.url, "price": o.price,
                  "price_claim": o.price_claim,
                  "price_source": o.price_source,
                  "price_checked": o.price_checked.isoformat() if o.price_checked else None,
                  "original_price": o.original_price, "category": o.category,
                "source": o.source, "description": o.description,
                "image_url": o.image_url, "requires_login": o.requires_login,
                "has_adfly": o.has_adfly, "has_captcha": o.has_captcha,
                "is_adult": o.is_adult,
                "created_at": o.created_at.isoformat() if o.created_at else "",
            }
            for o in offers
        ]
    finally:
        session.close()


@app.get("/api/price-changes")
async def price_changes(limit: int = 30):
    """Ostatnie zmiany cen, najnowsze pierwsze.

    To jedyne miejsce, gdzie widac, ze cena sie zmienila — oferta trzyma
    tylko biezaca wartosc. Bez ruchu sieciowego: czyta to, co zapisal scrape.
    """
    limit = max(1, min(int(limit), 200))
    session = SessionFactory()
    try:
        rows = (session.query(PriceHistory, Offer)
                .join(Offer, Offer.id == PriceHistory.offer_id)
                .order_by(PriceHistory.seen_at.desc())
                .limit(limit).all())
        rows = [(history, offer) for history, offer in rows
                if _safe_offer_url(offer.url)]
        return {"count": len(rows), "changes": [
            {"offer_id": h.offer_id, "title": o.title, "source": o.source,
             "url": o.url, "price": o.price, "price_claim": h.price_claim,
             "price_source": h.price_source,
             "seen_at": h.seen_at.isoformat() if h.seen_at else None}
            for h, o in rows
        ]}
    finally:
        session.close()


@app.get("/api/stats")
async def get_stats():
    session = SessionFactory()
    try:
        active = session.query(Offer).filter(Offer.is_active == True).count()
        visible_offers = _merge_twins(
            session.query(Offer)
            .filter(Offer.is_active == True, Offer.is_adult.isnot(True))
            .all())
        total = len(visible_offers)
        sources = {}
        for offer in visible_offers:
            sources[offer.source] = sources.get(offer.source, 0) + 1
        # Ile cen jest zmierzonych, ile tylko zgloszonych, a ile wcale.
        # Strona glowna pokazuje te trzy liczby osobno, bo "darmowe" bez
        # informacji, kto to sprawdzil, jest tym samym klamstwem co kiedys.
        measured = sum((o.price_source or "").startswith("api:")
                       for o in visible_offers)
        claimed = sum((o.price_source or "").startswith("listing:")
                      for o in visible_offers)
        return {
            "total": total, "active": active,
            "sources": sources,
            "price_measured": measured,
            "price_claimed": claimed,
            "price_unknown": total - measured - claimed,
            "last_update": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        session.close()


@app.post("/api/scrape")
async def trigger_scrape():
    wynik = await guarded_scrape()
    if wynik is None:
        return JSONResponse({"status": "busy", "detail": "scrape already running"}, status_code=409)
    new, updated = wynik
    return {"status": "ok", "new": new, "updated": updated}


@app.get("/api/favorites")
async def get_favorites():
    return {"favorites": []}


@app.get("/pad")
async def pad_test():
    return FileResponse(str(FRONTEND_DIR / "pad_test.html"))


@app.get("/retro")
async def retro_hub():
    return FileResponse(str(TOOLS_DIR / "retro.html"))


@app.get("/wiki")
async def wiki_hub():
    return FileResponse(str(TOOLS_DIR / "wiki.html"))


@app.get("/bookmarks")
async def bookmarks_hub():
    return FileResponse(str(TOOLS_DIR / "bookmarks.html"))


@app.get("/flash")
async def flash_player():
    return FileResponse(str(TOOLS_DIR / "flash_player.html"))


@app.get("/muzeum")
async def muzeum():
    """Muzeum okazów: lokalna kolekcja ataków złapanych przez sanityzer."""
    return FileResponse(str(TOOLS_DIR / "muzeum.html"))


@app.get("/api/specimens")
async def specimens_list(limit: int = 200):
    """Okazy ataków (najnowsze pierwsze) + zestawienie. Tylko loopback."""
    import specimens
    return {"stats": specimens.stats(),
            "items": specimens.tail(limit=max(1, min(limit, 1000)))}


@app.get("/api/linkcheck")
async def linkcheck(url: str):
    """Werdykt dla adresu (link doctor). Nie pobiera treści strony. Loopback."""
    import linkdoctor
    return await asyncio.to_thread(linkdoctor.check_url, url)


@app.get("/sw.js")
async def service_worker():
    # Served from the root so the worker gets "/" scope rather than "/static/".
    return FileResponse(
        str(FRONTEND_DIR / "sw.js"),
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"},
    )


@app.get("/manifest.json")
async def web_manifest():
    return FileResponse(str(FRONTEND_DIR / "manifest.json"), media_type="application/manifest+json")


@app.api_route("/api/clean", methods=["GET", "POST"])
async def clean_proxy(url: str, request: Request, ephemeral: int = 0):
    """Fetch an external page, strip ads/trackers/scripts, return clean HTML.

    Separate cookie session per host: logins stay in backend/.cookies/ and
    never mix between sites. Login POSTs pass through (passwords are never
    stored - only Set-Cookie responses land in the jar). Every hop (including
    redirects) passes the SSRF gate. Non-HTML answers 415 so the viewer can
    fall back to a direct link instead of framing a download.

    ?ephemeral=1 to tryb ulotny: słoik żyje tylko w RAM (30 min bezczynności
    albo restart/wyczyszczenie), dysk nietknięty. Do logowania "na raz".
    """
    import asyncio
    post_body = await request.body() if request.method == "POST" else None
    return await asyncio.to_thread(
        _clean_sync, url, request.method,
        {"content-type": request.headers.get("content-type", "")},
        dict(request.query_params), post_body, bool(int(ephemeral or 0)))


def _clean_sync(url, method, headers, query_params, post_body, ephemeral=False):
    from fastapi.responses import JSONResponse
    from sessions import persist_from_requests, session_state, attach_to_requests

    target = url
    body, fwd_ctype = None, None
    if method == "POST":
        if post_body is None or len(post_body) > MAX_BYTES:
            return JSONResponse({"error": "form too large"}, status_code=413)
        ctype = headers.get("content-type", "")
        if not ctype.startswith(("application/x-www-form-urlencoded",
                                 "multipart/form-data", "text/plain")):
            return JSONResponse({"error": "form type not proxied"}, status_code=415)
        body, fwd_ctype = post_body, ctype
    else:
        # GET forms (search boxes) arrive with extra query params - merge
        # them into the target instead of dropping the user's input.
        # "url", auth token and "ephemeral" are ours, never the target's.
        extra = [(k, v) for k, v in query_params.items()
                 if k not in ("url", "token", "ephemeral")]
        if extra:
            from urllib.parse import urlencode
            sep = "&" if "?" in target else "?"
            target = target + sep + urlencode(extra)

    try:
        host = urlparse(target).hostname or ""
    except (TypeError, ValueError):
        return JSONResponse({"error": "invalid URL"}, status_code=400)
    if method == "POST" and urlparse(target).scheme != "https":
        return JSONResponse(
            {"error": "login forms require an HTTPS destination"},
            status_code=403,
        )
    from settings_store import read_settings, effective_proxies
    settings = read_settings()
    if settings.get("settings_locked"):
        return JSONResponse(
            {"error": "settings unavailable; unlock the vault before proxying"},
            status_code=423,
        )
    if not settings.get("proxy_clean", True):
        return JSONResponse({"error": "cleaner disabled in settings"}, status_code=403)
    proxies = effective_proxies(settings)
    sess = new_safe_session(proxies)
    sess.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MatrixHunt-Viewer/2.0",
        "Accept": "text/html,application/xhtml+xml",
    })
    # DNS is resolved by the proxy/exit in proxy mode; direct connections are
    # pinned by the safe adapter after the same public-address validation.
    check_dns = not bool(proxies)
    if ephemeral:
        from sessions import attach_ephemeral as _attach_eph
        _attach_eph(host, sess)
    else:
        attach_to_requests(host, sess)

    current, cur_method, cur_body = target, method, body
    try:
        for _ in range(4):
            ok, reason = is_url_allowed(current, check_dns=check_dns)
            if not ok:
                return JSONResponse({"error": f"blocked: {reason}"}, status_code=403)
            if cur_method == "POST" and urlparse(current).scheme != "https":
                return JSONResponse(
                    {"error": "login forms require an HTTPS destination"},
                    status_code=403,
                )
            req_headers = {}
            if cur_body is not None and fwd_ctype:
                req_headers["Content-Type"] = fwd_ctype
            try:
                r = sess.request(cur_method, current, data=cur_body,
                                 headers=req_headers, timeout=15,
                                 allow_redirects=False, stream=True)
            except Exception:
                return JSONResponse({"error": "fetch failed"}, status_code=502)
            if r.status_code in (301, 302, 303, 307, 308):
                location = r.headers.get("Location", "")
                r.close()
                if not location:
                    return JSONResponse({"error": "empty redirect"}, status_code=502)
                redirect_target = urljoin(current, location)
                if (r.status_code in (307, 308) and cur_method == "POST"
                        and not _same_url_origin(current, redirect_target)):
                    return JSONResponse(
                        {"error": "login form redirect changed origin"},
                        status_code=403,
                    )
                current = redirect_target
                if r.status_code in (301, 302, 303) and cur_method == "POST":
                    cur_method, cur_body = "GET", None
                continue
            if r.status_code != 200:
                # 403/429 from the target means the store blocked the fetch,
                # not that something broke here. Epic Games in particular
                # refuses datacenter requests outright. The viewer shows this
                # message, so it must name the real cause or the user goes
                # looking for a bug that does not exist.
                why = {
                    401: "the store requires a login for this page",
                    403: "the store blocked the request (bot/datacenter filter)",
                    404: "page not found at the store",
                    429: "rate limited by the store, try again later",
                    451: "blocked for legal reasons at the store",
                }.get(r.status_code, "the store returned an error")
                r.close()
                return JSONResponse(
                    {"error": f"upstream {r.status_code}", "reason": why,
                     "url": current},
                    status_code=502)
            ctype = r.headers.get("Content-Type", "")
            if "html" not in ctype.lower():
                r.close()
                return JSONResponse(
                    {"error": "not HTML", "content_type": ctype, "url": current},
                    status_code=415,
                )
            # Bounded read: never buffer an unbounded upstream body. Without
            # stream=True a remote page (or a CSRF-triggered GET /api/clean
            # aimed at an attacker URL) could stream gigabytes into RAM before
            # the old post-hoc len(r.content) check ever ran.
            chunks, total, too_big = [], 0, False
            for chunk in r.iter_content(65536):
                if not chunk:
                    continue
                total += len(chunk)
                if total > MAX_BYTES:
                    too_big = True
                    break
                chunks.append(chunk)
            encoding = r.encoding or "utf-8"
            r.close()
            if too_big:
                return JSONResponse({"error": "page too large"}, status_code=413)
            html_text = b"".join(chunks).decode(encoding, "replace")
            # Persist against the host we actually ended on. Using the host
            # from the ORIGINAL url merged every cookie a redirect target set
            # into the first host's jar, which broke the per-site isolation
            # the viewer promises, and "forget this site" then logged the
            # other site out too.
            final_host = urlparse(current).hostname or host
            if ephemeral:
                from sessions import persist_ephemeral as _persist_eph
                from sessions import ephemeral_state as _eph_state
                _persist_eph(final_host, sess)
                state = _eph_state(final_host)
            else:
                persist_from_requests(final_host, sess)
                state = session_state(final_host)
            from filterlists import get_engine, custom_engine, elog
            if settings.get("filters_enabled", True):
                flt = {"engine": get_engine(),
                       "custom": custom_engine(settings),
                       "enabled": frozenset(lid for lid, on in
                                            settings.get("filter_lists", {}).items() if on),
                       "log": True}
                # Page-level $network rules (badware list): refuse known-filthy
                # pages outright with 451 instead of framing them.
                blocked, rule = flt["engine"].check(current, current, "document",
                                                    enabled=flt["enabled"])
                if blocked and getattr(rule, "network", False):
                    elog.add(current, current, rule, "blocked-page")
                    return JSONResponse(
                        {"error": "page blocked by filter list",
                         "rule": rule.raw[:160], "list": rule.list_id},
                        status_code=451)
            else:
                flt = None
            cleaned, removed, filtered = clean_html(
                html_text, current, flt=flt, token=API_TOKEN)
            return HTMLResponse(
                content=cleaned,
                headers={"X-MH-Cleaned": str(removed), "X-MH-Source": current,
                         "X-MH-Filtered": str(filtered),
                         "X-MH-Host": final_host,
                         "X-MH-Session": "active" if state["has_session"] else "none",
                         "X-MH-Ephemeral": "1" if ephemeral else "0",
                         "Content-Security-Policy": (
                             "default-src 'none'; img-src 'self'; "
                             "form-action 'self'; base-uri 'none'; "
                             "object-src 'none'; frame-src 'none'; "
                             "script-src 'none'; style-src 'none'"
                         )},
            )
        return JSONResponse({"error": "too many redirects"}, status_code=502)
    finally:
        sess.close()


def _same_url_origin(first, second):
    def origin(url):
        try:
            parts = urlsplit(url)
            scheme = parts.scheme.lower()
            hostname = parts.hostname
            port = parts.port
        except ValueError:
            return None
        if (scheme not in ("http", "https") or not hostname
                or parts.username is not None or parts.password is not None):
            return None
        return (scheme, hostname.lower(),
                port if port is not None else (443 if scheme == "https" else 80))

    first_origin = origin(first)
    return first_origin is not None and first_origin == origin(second)




@app.get("/view")
async def viewer():
    return FileResponse(str(TOOLS_DIR / "viewer.html"))


@app.get("/api/sessions")
async def sessions_list():
    """Which external sites hold a cookie session. Counts only, no values."""
    from sessions import list_sessions
    return list_sessions()


@app.delete("/api/sessions/{host}")
async def sessions_forget(host: str):
    """Wipe one site's cookies = log that site out. Others untouched."""
    from sessions import forget_host
    if not re.fullmatch(r"[A-Za-z0-9.-]{1,100}", host):
        raise HTTPException(status_code=400, detail="bad host")
    return {"forgotten": forget_host(host.lower()), "host": host.lower()}


@app.delete("/api/sessions")
async def sessions_forget_all():
    from sessions import forget_all
    return {"forgotten_sites": forget_all()}


@app.get("/api/sessions-ephemeral")
async def sessions_ephemeral_list():
    """Sesje ulotne (RAM): co żyje w tej chwili. Liczniki, nie wartości."""
    from sessions import list_ephemeral
    return {"ephemeral": list_ephemeral()}


@app.delete("/api/sessions-ephemeral")
async def sessions_ephemeral_forget_all():
    """Wyczyść WSZYSTKIE sesje ulotne z RAM. Dysk i tak jest nietknięty."""
    from sessions import forget_ephemeral_all
    return {"forgotten_ephemeral": forget_ephemeral_all()}


@app.delete("/api/sessions-ephemeral/{host}")
async def sessions_ephemeral_forget(host: str):
    """Wyczyść ulotną sesję jednego hosta z RAM."""
    from sessions import forget_ephemeral
    if not re.fullmatch(r"[A-Za-z0-9.-]{1,100}", host):
        raise HTTPException(status_code=400, detail="bad host")
    return {"forgotten": forget_ephemeral(host.lower()), "host": host.lower()}


@app.get("/api/filterlists")
async def filterlists_status():
    """Subscription lists: rule counts, last update, on/off state, custom lists."""
    from filterlists import get_engine, custom_engine, custom_file_id, LISTS
    from settings_store import read_settings
    eng = get_engine()
    settings = read_settings()
    enabled = settings.get("filter_lists", {})
    cent = custom_engine(settings)
    custom_n = len([l for l in (settings.get("custom_rules") or "").splitlines()
                    if l.strip() and not l.strip().startswith("!")])
    return {
        "filters_enabled": bool(settings.get("filters_enabled", True)),
        "lists": [
            {"id": lid, "name": meta["name"], "url": meta["url"],
             "enabled": bool(enabled.get(lid, True)),
             "rules": eng.stats.get(lid, {}).get("network", 0),
             "exceptions": eng.stats.get(lid, {}).get("exceptions", 0),
             "updated": eng.loaded.get(lid, {}).get("updated", 0),
             "error": eng.loaded.get(lid, {}).get("error")}
            for lid, meta in LISTS.items()],
        "custom_lists": [
            {"id": custom_file_id(lst["url"]), "name": lst.get("name", ""),
             "url": lst["url"], "enabled": bool(lst.get("enabled", True)),
             "rules": cent.stats.get(custom_file_id(lst["url"]), {}).get("network", 0),
             "updated": cent.loaded.get(custom_file_id(lst["url"]), {}).get("updated", 0)}
            for lst in settings.get("custom_lists", [])],
        "custom_rules": custom_n}


@app.post("/api/filterlists/refresh")
async def filterlists_refresh():
    """Force re-download of all subscription lists (built-in + custom)."""
    def _work():
        from filterlists import reset_engine, get_engine, download_custom_lists
        reset_engine()
        eng = get_engine()
        errors = {lid: v.get("error") for lid, v in eng.loaded.items()
                  if v.get("error")}
        errors.update(download_custom_lists())
        return {"lists": len(eng.loaded), "errors": errors}
    return await asyncio.to_thread(_work)


@app.get("/api/filterlog")
async def filterlog(host: str = "", limit: int = 100):
    """What got blocked, where, by which exact rule. Newest last."""
    from filterlists import elog
    return elog.tail(limit=max(1, min(limit, 500)), host=host or None)


IMG_MAX = 5 * 1024 * 1024
IMG_MAGIC = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"GIF87a": "image/gif",
    b"GIF89a": "image/gif",
    b"RIFF": "image/webp",  # + b"WEBP" at offset 8, checked below
    b"\x00\x00\x01\x00": "image/x-icon",
    b"BM": "image/bmp",
}


_HTML_MARKERS = (b"<script", b"<html", b"<iframe", b"<svg", b"<body",
                 b"<?php", b"<object", b"<embed")


def validate_image(blob, ctype):
    """Magic-byte sniff. Returns media type or None. Kills polyglots:
    HTML/JS served as .jpg must never reach the browser as an image
    (mime-sniffing XSS) - hence strict magic + nosniff on serve.

    Magic bytes alone are not enough: a valid PNG header followed by
    <script> passed the header check, so a valid image carrying an HTML
    payload is rejected too. No legitimate thumbnail contains these
    markers, and nosniff stays as the second layer.
    """
    if not blob or len(blob) > IMG_MAX:
        return None
    low = blob[:4096].lower() + blob[-4096:].lower() if len(blob) > 8192 else blob.lower()
    if any(m in low for m in _HTML_MARKERS):
        return None
    for magic, mime in IMG_MAGIC.items():
        if blob.startswith(magic):
            if magic == b"RIFF" and blob[8:12] != b"WEBP":
                return None
            if "image/" not in (ctype or "").lower() and ctype:
                return None
            return mime
    return None


@app.get("/api/img")
async def img_proxy(url: str):
    """Image-only proxy for offer thumbnails. The browser never touches
    third-party image hosts directly: no referrer leak, no malicious
    payload reaches Chrome's codecs unless it is byte-valid image data."""
    import asyncio
    return await asyncio.to_thread(_img_sync, url)


def _img_sync(url):
    session = new_safe_session()
    try:
        return _img_sync_with_session(url, session)
    finally:
        session.close()


def _img_sync_with_session(url, session):
    from fastapi.responses import JSONResponse, Response
    from urllib.parse import urljoin
    # Re-validate every hop: requests follows redirects by default, so a
    # public URL could 302 to 127.0.0.1 or 169.254.169.254 and the single
    # upfront check would never see it. Same guard as _clean_sync.
    target, r = url, None
    for _hop in range(6):
        ok, reason = is_url_allowed(target)
        if not ok:
            if r is not None:
                r.close()
            return JSONResponse({"error": f"blocked: {reason}"}, status_code=403)
        try:
            r = session.get(target, timeout=15, stream=True, allow_redirects=False, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MatrixHunt-Viewer/2.0",
                "Accept": "image/*",
            })
        except Exception:
            if r is not None:
                r.close()
            return JSONResponse({"error": "fetch failed"}, status_code=502)
        if r.status_code in (301, 302, 303, 307, 308):
            loc = r.headers.get("Location", "")
            r.close()
            if not loc:
                return JSONResponse({"error": "redirect without Location"}, status_code=502)
            target = urljoin(target, loc)
            continue
        break
    else:
        if r is not None:
            r.close()
        return JSONResponse({"error": "too many redirects"}, status_code=502)
    try:
        if r.status_code != 200:
            return JSONResponse({"error": f"upstream {r.status_code}"}, status_code=502)
        chunks, size = [], 0
        for chunk in r.iter_content(65536):
            size += len(chunk)
            if size > IMG_MAX:
                return JSONResponse({"error": "image too large"}, status_code=413)
            chunks.append(chunk)
        blob = b"".join(chunks)
    finally:
        r.close()
    mime = validate_image(blob, r.headers.get("Content-Type", ""))
    if not mime:
        return JSONResponse({"error": "not a valid image"}, status_code=415)
    return Response(content=blob, media_type=mime, headers={
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "public, max-age=86400",
    })


@app.get("/api/vulncheck")
async def vulncheck_cached():
    """Last dependency audit (cached, zero traffic)."""
    from vulncheck import cached_audit
    return cached_audit()


@app.post("/api/vulncheck")
async def vulncheck_run():
    """Run the dependency audit now. Manual trigger only - OSV + KEV stay
    untouched until you click. May take ~30s (one OSV batch + KEV fetch)."""
    import asyncio
    from fastapi.responses import JSONResponse
    from vulncheck import run_audit
    report = await asyncio.to_thread(run_audit)
    # A failed run is a failure, not a clean result. 200 with total:0 used to
    # tell the dashboard "0 vulnerabilities" when OSV was unreachable.
    if not report.get("ok", True):
        return JSONResponse(report, status_code=502)
    return report


@app.get("/api/vault/status")
async def vault_status():
    """Locked? Which sensitive files exist and are they sealed?"""
    from vault import vault, jar_fingerprint
    from sessions import JAR_DIR
    files = []
    for p in [BASE_DIR / ".session_secret", BASE_DIR / ".app_settings.json"]:
        if p.exists():
            raw = p.read_bytes()
            files.append({"file": p.name,
                          "sealed": raw.startswith(b"VAULT1:"),
                          "fp": jar_fingerprint(p)})
    if JAR_DIR.exists():
        for f in sorted(JAR_DIR.glob("*.json")):
            raw = f.read_bytes()
            files.append({"file": f"cookies/{f.name}",
                          "sealed": raw.startswith(b"VAULT1:"),
                          "fp": jar_fingerprint(f)})
    return {"locked": vault.locked,
            "env_key": bool(__import__("os").environ.get("MH_VAULT_PASSWORD")),
            "files": files}


@app.post("/api/vault/unlock")
async def vault_unlock(request: Request):
    from fastapi.responses import JSONResponse
    from vault import vault
    try:
        password = (await request.json()).get("password", "")
    except Exception:
        raise HTTPException(status_code=400, detail="JSON {password} required")
    try:
        if vault.unlock(password):
            return {"locked": False}
    except OSError as exc:
        print(f"[vault] plaintext sealing failed: {exc}")
        return JSONResponse(
            {"error": "could not securely seal existing sensitive files"},
            status_code=500,
        )
    return JSONResponse({"error": "wrong password"}, status_code=403)


@app.post("/api/vault/lock")
async def vault_lock():
    from vault import vault
    vault.lock()
    return {"locked": True}


@app.get("/api/cvefeed")
async def cvefeed(q: str = "", limit: int = 30):
    """Actively-exploited CVEs (CISA KEV) matching q. Empty q -> newest."""
    import asyncio
    from vulncheck import kev_search
    return await asyncio.to_thread(kev_search, q, max(1, min(limit, 100)))


def _db_ro():
    """Read-only connection to the app DB. No writes, ever."""
    import sqlite3
    return sqlite3.connect(f"file:{BASE_DIR / 'matrixhunt.db'}?mode=ro", uri=True)


def _db_tables():
    con = _db_ro()
    try:
        return [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    finally:
        con.close()


@app.get("/db")
async def db_viewer():
    return FileResponse(str(TOOLS_DIR / "db.html"))


@app.get("/api/db/tables")
async def db_tables():
    con = _db_ro()
    try:
        out = []
        for t in _db_tables():
            n = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            cols = [r[1] for r in con.execute(f'PRAGMA table_info("{t}")')]
            out.append({"table": t, "rows": n, "columns": cols})
        return out
    finally:
        con.close()


def _qident(name: str) -> str:
    """Quote an SQL identifier safely (double-quote, escape inner quotes).
    Only called after table name has been allowlisted + regex-validated."""
    return '"' + name.replace('"', '""') + '"'


@app.get("/api/db/rows")
async def db_rows(table: str, search: str = "", page: int = 1, limit: int = 100):
    # Table names can never be bound parameters - allowlist against the
    # schema instead (the desktop original interpolated them raw).
    # Re-derive table from the schema so user-controlled input never
    # reaches the SQL string - only validated names from the database do.
    _valid_tables = set(_db_tables())
    if table not in _valid_tables:
        raise HTTPException(status_code=400, detail="unknown table")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
        raise HTTPException(status_code=400, detail="unknown table")
    limit = max(1, min(limit, 200))
    page = max(1, page)
    con = _db_ro()
    try:
        cols = [r[1] for r in con.execute(f'PRAGMA table_info({_qident(table)})')]
        where, params = "", []
        if search:
            text_cols = [c for c in cols]
            where = "WHERE " + " OR ".join(f'CAST("{c}" AS TEXT) LIKE ?' for c in text_cols)
            params = [f"%{search}%"] * len(text_cols)
        total = con.execute(f'SELECT COUNT(*) FROM {_qident(table)} {where}', params).fetchone()[0]
        rows = con.execute(
            f'SELECT * FROM {_qident(table)} {where} LIMIT ? OFFSET ?',
            params + [limit, (page - 1) * limit]).fetchall()
        return {"table": table, "columns": cols, "total": total,
                "page": page, "limit": limit,
                "rows": [list(r) for r in rows]}
    finally:
        con.close()


@app.get("/api/settings")
async def settings_get():
    """Public runtime settings + live Tor reachability. No secrets."""
    from settings_store import read_settings, tor_available
    data = read_settings()
    data["tor_reachable"] = tor_available()
    return data


@app.post("/api/settings")
async def settings_set(request: Request):
    from fastapi.responses import JSONResponse
    from settings_store import write_setting
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON body required")
    key, value = payload.get("key"), payload.get("value")
    try:
        return write_setting(key, value)
    except PermissionError:
        return JSONResponse({"error": "vault locked or settings unavailable"},
                            status_code=423)
    except ValueError:
        return JSONResponse({"error": "invalid setting"}, status_code=400)


@app.get("/api/netcheck")
async def netcheck():
    """Proof the proxy/Tor path is real: your direct IP vs the egress IP.

    Fetches an IP-echo API twice - once direct, once through the configured
    route (Tor/upstream/direct) - so the UI can show "YOU x.x.x.x -> EXIT
    y.y.y.y (via Tor)". No sciema: if both match and Tor was requested,
    Tor is NOT working and the UI says so.
    """
    import asyncio
    return await asyncio.to_thread(_netcheck_sync)


def _netcheck_sync():
    import requests as _requests
    from settings_store import read_settings, effective_proxies

    def fetch(proxies):
        try:
            r = _requests.get("https://check.torproject.org/api/ip", timeout=12,
                              proxies=proxies or None)
            d = r.json() if r.ok else {}
            return {"ip": d.get("IP"), "is_tor": bool(d.get("IsTor")), "ok": True}
        except Exception as e:
            return {"ip": None, "is_tor": False, "ok": False,
                    "error": str(e)[:100]}

    settings = read_settings()
    direct = fetch(None)
    egress = fetch(effective_proxies(settings))
    via = "tor" if settings.get("tor") else (
        "upstream" if settings.get("upstream_proxy") else "direct")
    routed = egress.get("ok") and egress.get("ip") != direct.get("ip")
    tor_claim_ok = (not settings.get("tor")) or bool(egress.get("is_tor"))
    return {"direct": direct, "egress": egress, "via": via,
            "proxies_configured": effective_proxies(settings),
            "routed": routed, "tor_claim_ok": tor_claim_ok}


def _auth_base(request):
    """Scheme+host the browser used. Only loopback on OUR bound port."""
    host = (request.headers.get("host") or "").split(",")[0].strip()
    port = getattr(app.state, "port", 8000)
    if host not in (f"127.0.0.1:{port}", f"localhost:{port}"):
        return None
    return f"http://{host}"


@app.get("/api/auth/steam/login")
async def steam_login(request: Request):
    from fastapi.responses import RedirectResponse, JSONResponse
    base = _auth_base(request)
    if not base:
        return JSONResponse({"error": "unexpected host"}, status_code=400)
    url = build_login_url(realm=base + "/", return_to=base + "/api/auth/steam/return")
    return RedirectResponse(url)


@app.get("/api/auth/steam/return")
async def steam_return(request: Request):
    import asyncio
    from fastapi.responses import RedirectResponse, JSONResponse
    base = _auth_base(request)
    if not base:
        return JSONResponse({"error": "unexpected host"}, status_code=400)
    # verify_response does a blocking POST with timeout=15. In an async def
    # that stalls the whole event loop, so every other endpoint froze for the
    # duration of a login attempt.
    steamid = await asyncio.to_thread(
        verify_response, dict(request.query_params), base.split("://")[1])
    if not steamid:
        return JSONResponse({"error": "Steam did not confirm this login"}, status_code=403)
    request.session.clear()
    request.session["steamid"] = steamid
    return RedirectResponse("/?steam=1")


@app.get("/api/auth/steam/me")
async def steam_me(request: Request):
    import asyncio
    import time
    steamid = request.session.get("steamid")
    if not steamid:
        return {"logged_in": False}
    cached = request.session.get("persona")
    games = request.session.get("games_count")
    # Time-based only. "not cached" fired on every request for an account
    # with no persona name, so each /me re-ran up to 35s of blocking I/O.
    if time.time() - request.session.get("games_at", 0) > 3600:
        persona, gameinfo = await asyncio.gather(
            asyncio.to_thread(fetch_persona, steamid),
            asyncio.to_thread(fetch_games_count, steamid),
        )
        cached = persona or cached or steamid
        # fetch_games_count returns a (count, private) tuple; guard it, a
        # future refactor returning a bare int would raise here.
        if isinstance(gameinfo, tuple) and len(gameinfo) == 2:
            games, private = gameinfo
        else:
            games, private = (gameinfo if gameinfo is not None else games), \
                request.session.get("games_private", True)
        request.session["persona"] = cached
        request.session["games_count"] = games
        request.session["games_private"] = private
        request.session["games_at"] = time.time()
    return {"logged_in": True, "steamid": steamid, "persona": cached,
            "games_count": games, "games_private": request.session.get("games_private", True)}


@app.post("/api/auth/steam/logout")
async def steam_logout(request: Request):
    request.session.clear()
    return {"logged_in": False}


@app.get("/api/rss")
async def rss_feed():
    session = SessionFactory()
    try:
        # RSS nie ma bramki wieku, więc 18+ nigdy tu nie trafia.
        offers = session.query(Offer).filter(Offer.is_active == True,
                                             Offer.is_adult.isnot(True)
                                             ).order_by(Offer.created_at.desc()).limit(50).all()
        offers = [offer for offer in offers if _safe_offer_url(offer.url)]
        # Titles/URLs come from third-party markup. Without escaping, a title
        # like "</title></item><item><title>x" forges feed entries and a
        # "<script>" title lands raw in reader DOMs (confirmed live).
        items = "\n".join([
            f'<item><title>{escape(o.title or "")}</title>'
            f'<link>{escape(o.url or "")}</link>'
            f'<source>{escape(o.source or "")}</source></item>'
            for o in offers
        ])
        rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>MatrixHunt Ultimate</title>
<description>Free games aggregator</description>
{items}</channel></rss>"""
        return HTMLResponse(content=rss, media_type="application/xml")
    finally:
        session.close()


@asynccontextmanager
async def lifespan(app):
    from vault import vault, seal_plaintext_leftovers
    if not vault.locked:
        seal_plaintext_leftovers(vault)
    # CORS must be pinned to the port we actually listen on, and it has to
    # happen for EVERY launch method. It used to run only under
    # `python main.py`, so `uvicorn main:app` - the documented FastAPI way -
    # kept the permissive "any loopback port" regex and steam_login returned
    # 400 "unexpected host" on any other port. Resolve the real port from the
    # server socket, and fall back to the 8000 default when it is not
    # bound yet (e.g. tests importing the app).
    port = getattr(app.state, "port", None)
    if not port:
        srv = getattr(app, "server", None)
        sockets = getattr(srv, "sockets", None) if srv is not None else None
        if sockets:
            try:
                port = sockets[0].getsockname()[1]
            except (OSError, IndexError, TypeError):
                port = None
    if port:
        app.state.port = port
        _lock_cors_to_port(port)
    # try/finally on the first session too: an exception between here and the
    # close() leaked the connection, unlike the second block which had one.
    session = SessionFactory()
    try:
        count = session.query(Offer).count()
    finally:
        session.close()
    if count == 0:
        print("Empty DB, running initial scrape...")
        deals, refreshed_sources = await run_all_scrapers()
        try:
            save_deals_to_db(deals, refresh_sources=refreshed_sources)
        except Exception as e:
            print(f"Initial scrape write failed: {e}")
    else:
        print(f"DB has {count} offers, skipping initial scrape.")
    session = SessionFactory()
    try:
        if session.query(Offer).count() < 20:
            try:
                n, _ = load_seed_catalog()
                print(f"Seed catalog: {n} permanent-free titles ensured.")
            except Exception as e:
                print(f"Seed catalog write failed: {e}")
    finally:
        session.close()
    bound = getattr(app.state, "port", None) or 8000
    print(f"MatrixHunt Ultimate ready on http://localhost:{bound}")
    yield


app.router.lifespan_context = lifespan


def probe_app(port):
    """Who lives on 127.0.0.1:port? 'matrixhunt', 'foreign' or 'closed'.

    TCP first: a cheap connect tells us the port is even taken. Only then
    is HTTP worth probing - doing it the other way round burned two full
    HTTP timeouts on every non-HTTP listener and mislabelled a port with a
    full accept backlog as 'closed'."""
    import socket as _socket
    try:
        s = _socket.create_connection(("127.0.0.1", port), timeout=1)
        s.close()
    except OSError:
        return "closed"

    import json as _json
    from urllib.request import urlopen as _urlopen
    try:
        with _urlopen(f"http://127.0.0.1:{port}/api/stats", timeout=2) as r:
            d = _json.load(r)
            if isinstance(d, dict) and "total" in d and "sources" in d:
                return "matrixhunt"
    except Exception:
        pass
    try:
        with _urlopen(f"http://127.0.0.1:{port}/", timeout=2) as r:
            body = r.read(4000).decode("utf-8", "replace")
            if "MATRIXHUNT" in body:
                return "matrixhunt"
    except Exception:
        pass
    return "foreign"


def find_port(start=8000, tries=20):
    """First free loopback port. Occupied ones are identified out loud:
    another MatrixHunt or a foreign app - either way we move on."""
    import socket as _socket
    for port in range(start, start + tries):
        s = _socket.socket()
        try:
            s.bind(("127.0.0.1", port))
            s.close()
            if port != start:
                print(f"Port {start} busy, using {port} instead.")
            return port
        except OSError:
            try:
                owner = probe_app(port)
            except Exception:
                owner = "unknown"
            print(f"Port {port} busy (held by: {owner}), trying next…")
        finally:
            try:
                s.close()
            except Exception:
                pass
    raise RuntimeError("no free loopback port found")


def _lock_cors_to_port(port):
    """Pin CORS to the port we actually bound.

    The original regex allowed ANY loopback port, so a page served by any
    other local app (localhost:9999) could read /api/client-config and then
    drive every state-changing endpoint with the token - a local-origin
    hijack. The UI is served same-origin, so it never needed CORS at all;
    this only keeps a dev server on the same port working.
    """
    from starlette.middleware.cors import CORSMiddleware
    for mw in app.user_middleware:
        if mw.cls is CORSMiddleware:
            mw.kwargs["allow_origin_regex"] = rf"http://(localhost|127\.0\.0\.1):{port}"
            mw.kwargs["allow_origins"] = []
            return True
    return False


if __name__ == "__main__":
    import os as _os
    import uvicorn
    _host = _os.environ.get("MH_HOST", "127.0.0.1").strip() or "127.0.0.1"
    if not _MH_PUBLIC and not _is_loopback_host(_host):
        raise SystemExit("MH_HOST must be loopback unless MH_PUBLIC=1")
    port = find_port()
    app.state.port = port
    _lock_cors_to_port(port)
    print(f"MatrixHunt Ultimate ready on http://{_host}:{port}")
    uvicorn.run(app, host=_host, port=port)
