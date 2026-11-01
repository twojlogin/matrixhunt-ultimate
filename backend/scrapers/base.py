from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from typing import List, Optional
from datetime import datetime, timezone
import hashlib
import re

# Words that unambiguously mean "no cost". Matched on word boundaries so that
# titles like "Freedom Fighters" are not misread as free.
_FREE_WORDS = ("free", "gratis", "za darmo", "darmowa", "darmowe", "bezplatne")

# Release-status markers. A bare word match is not enough: "alpha", "beta",
# "prologue" and "trial" are ordinary words in shipped titles, and \b boundaries
# do not help ("Alpha Protocol", "Prologue", "Serious Sam: Alpha",
# "Alpha Centauri" were all silently dropped by 8 scrapers). So a word only
# counts as a status marker next to qualifier context, or as a trailing tag.
_GARBAGE_PHRASES = (
    "free to play", "test server", "test build", "early access",
    "open beta", "closed beta", "public beta", "beta version",
    "alpha build", "alpha version", "beta build", "demo version",
    "trial version", "prologue only", "play trial", "free demo",
    "demo pack", "demo version", "server browser", "crowdfunded",
)
# Status words that are safe to reject on their own as a TRAILING tag.
# "demo"/"demos"/"f2p" essentially never end a shipped title ("Demonschool"
# does not end in "demo"). The other status words DO: "Serious Sam: Alpha",
# "The Beta", "Trials of Mana", "Prologue" are real games, so they need the
# explicit markers below and are never judged by position alone.
_GARBAGE_TAIL = ("demo", "demos", "f2p")
_GARBAGE_TAIL_RE = re.compile(
    r"(?:^|[\s\(\[/_-])(?:" + "|".join(_GARBAGE_TAIL) + r")[\s\]).!?,]?$")
# Qualifier + status: "Alpha 3", "Beta 2", "Demo v1.2"
_GARBAGE_NUMBERED = re.compile(
    r"\b(?:alpha|beta|demo|trial|prologue)\s*[v\d]|\b(?:alpha|beta|demo|trial)\s+\d+")

# Free-to-play is NOT free. A F2P title is a storefront: you get a client and
# a promise, and the game itself lives behind a purchase, a battle pass, gacha
# or an energy timer. This aggregator exists for the other kind of "free":
# something you download and keep. Phrases are matched against title AND
# description, because stores put the label in either place.
_F2P_PHRASES = (
    "free-to-play", "free to play", "freemium", "f2p",
    "free trial available", "try it free", "play for free",
    "microtransactions", "in-app purchases", "in game purchases",
    "gacha", "season pass", "battle pass", "loot box",
    "earn money in-game", "play-to-earn",
)
_F2P_RE = re.compile("|".join(re.escape(p) for p in _F2P_PHRASES), re.I)

# Known F2P by title. Phrase matching is not enough: plenty of stores ship a
# F2P game with an empty description, so Valorant, Lost Ark and Marvel Rivals
# came through clean. Matched on the normalised title (see _norm_title).
# Kept short and explicit on purpose - a fuzzy list would start eating real
# games, which is the exact bug this filter is meant to avoid.
_KNOWN_F2P = (
    "valorant", "lost ark", "marvel rivals", "delta force", "wuthering waves",
    "neverness to everness", "arknights", "battlefield redsec", "roblox",
    "gloria victis", "overwatch", "apex legends", "destiny 2",
    "pubg", "world of tanks", "where winds meet",
    "counter strike 2", "dota 2", "team fortress 2",
    "path of exile", "warframe", "genshin impact", "honkai", "league of legends",
    "call of duty warzone", "fortnite", "fall guys", "rocket league",
    "dauntless", "brawlhalla", "splitgate",
    "paladins", "smite 2", "dc universe online", "multiverse of enemies",
    "eidolons", "farlight 84", "franzen",
    "naraka bladepoint", "tower of fantasy", "eternium 4", "guild wars 2",
    "planetary annihilation", "unturned", "eve online",
)
_KNOWN_F2P_RE = re.compile(
    r"^(?:" + "|".join(re.escape(t) for t in _KNOWN_F2P) + r")\b", re.I)

_TRACKING_RE = re.compile(r"[^a-z0-9]+")
# Store prefixes that sit in front of the real title: "[Steam] (Game) X",
# "[iOS/Android] (Other) Y". Stripped before the F2P check, otherwise the
# lookup anchors on "[steam]" and never reaches the title.
_STORE_PREFIX_RE = re.compile(
    r"^\s*[\[(]\s*(?:[^\])]{0,40})\s*[\])]\s*"
    r"(?:\(\s*(?:game|other|dlc|app|epic|gog|beta|demo)\s*\)\s*)+", re.I)


def _norm_title(title):
    t = _STORE_PREFIX_RE.sub("", title or "")
    return _TRACKING_RE.sub(" ", t.lower()).strip()

# Payable add-ons. A giveaway key for "Supporter Pack" or "Untold Tales DLC"
# is not a game, and the base game it is attached to usually is not either.
_DLC_RE = re.compile(
    r"\b(?:supporter\s*pack|dlc\b|digital\s+edition|deluxe\s+edition|"
        r"ultimate\s+edition|collector'?s\s+edition|season\s+pass|ost\b|"
        r"original\s+soundtrack|game\s+soundtrack|soundtrack\s+edition|"
        r"art\s?book|bonus\s+content|"
    r"playtest|in-game\s+item|wallpaper|avatar|skin\s+pack|"
    # Named expansions carry no "DLC" in the title - these four slipped
    # through into the database before the invariant test existed.
    r"phantom\s+liberty|shadow\s+of\s+the\s+erdtree|separate\s+ways|"
    r"stay\s+human|weapon\s+pack|combat\s+bundle|soldier\s+bundle)\b", re.I)


def is_f2p_or_addon(title, description=""):
    """True when this is not a free-to-keep game. F2P first, then add-ons."""
    # The add-on check ran on the TITLE ONLY, while F2P ran on title+description.
    # GamerPower puts the giveaway in the title and "(DLC) - requires the base
    # game" in the description, so 8 add-ons sat in the database with a
    # description that said "DLC" in plain words. Found by the invariant test.
    if _F2P_RE.search(f"{title or ''} {description or ''}"):
        return True
    if _DLC_RE.search(title or "") or _DLC_RE.search(description or ""):
        return True
    # Title check on the normalised form, so "[Steam] (Game) Lost Ark" and
    # "Lost Ark™" both match, not just the bare name.
    norm = _norm_title(title)
    if not norm:
        return False
    # A trailing store tag is noise: strip it, then do the ONE title check
    # below. There used to be an extra `_KNOWN_F2P_RE.match(norm): return True`
    # up here, which short-circuited the tail validation entirely - that is
    # why "eve online tactics" and "roblox studio" were both rejected.
    stripped = re.sub(
        r"\s+(?:tm|reg|playstation|xbox|steam|epic|game pass)\s*$", "", norm).strip()
    if not stripped or not _KNOWN_F2P_RE.match(stripped):
        return False
    # Prefix match alone is too greedy: "eve online tactics" and
    # "farlight 84 quest" are not those F2P games. Require the match to END
    # the title, or to be followed only by a known qualifier (edition, beta,
    # "2", a colon, or a store tag). Anything else is a different game.
    m = _KNOWN_F2P_RE.match(stripped)
    consumed = m.group(0).rstrip()
    rest = stripped[len(consumed):].strip()
    if not rest:
        return True
    # Qualifier after the matched F2P name. Store tags count too: stores put
    # "[Steam] (Game)" AFTER the title, so normalising gives "lost ark steam
    # game" and the match has to swallow that. "battlegrounds" is the game's
    # own subtitle, not a different game.
    return bool(re.match(
        r"^(?:2|ii|iii|iv|beta|alpha|remastered|mobile|lite|chapter|chapters|"
        r"server|global|battlegrounds|battle royale|br|"
        r"tm|reg|steam|xbox|playstation|psn|pc|game|games|epic|gog|"
        r"app|install|client|launcher)(?:\b|$)", rest))


# Executable/script suffixes that must never become offer links. Matched
# against the FINAL path segment only - matching the whole URL flags every
# ".com" domain on Earth (noise). Archives (.zip/.rar/7z) stay allowed:
# they cannot self-execute and the viewer never auto-opens downloads.
# ".com" is deliberately NOT here: it is a DOS executable extension that
# means nothing on the platforms this runs on, and as a path suffix it
# rejected real links whose last segment merely ends in ".com"
# (https://example.com/a.com, and archive.org snapshot URLs).
DANGEROUS_EXT = (
    ".exe", ".msi", ".bat", ".cmd", ".scr", ".pif", ".ps1", ".vbs",
    ".vbe", ".jse", ".wsf", ".wsh", ".lnk", ".reg", ".cpl", ".msc",
    ".gadget", ".dll", ".sys", ".drv",
    # Linux/macOS/mobile payloads this tool can plausibly be pointed at.
    ".sh", ".run", ".bin", ".deb", ".rpm", ".appimage", ".dmg", ".pkg",
    ".jar", ".apk", ".app", ".command", ".desktop", ".hta", ".msu", ".appx",
)

@dataclass
class Deal:
    title: str
    url: str
    # price is the store's own figure when we asked it, and only then. Empty
    # means nobody measured it. price_claim is what the source stated,
    # price_source says which of the two it is: "api:steam" was read from the
    # store, "listing:itch.io/games/free" was taken from the page the item
    # appeared on. An empty price with a claim is the honest default; a literal
    # "Free" here was the lie the whole test file exists to catch.
    price: str = ""
    price_claim: str = None
    price_source: str = None
    original_price: str = ""
    category: str = "games"
    source: str = ""
    description: str = ""
    image_url: str = ""
    requires_login: bool = False
    has_adfly: bool = False
    has_captcha: bool = False
    is_adult: bool = False
    id: str = ""
    scraped_at: str = ""

    def __post_init__(self):
        # Sanityzacja w JEDNYM miejscu, przez które przechodzi każdy scraper:
        # neutralizuje ukryty tekst i wykrywa próby prompt-injection, ZANIM
        # cokolwiek to przeczyta. Do bazy idzie tekst czysty, ale do muzeum
        # okazów trafia próbka SUROWA (z zachowanym trikiem).
        raw_title, raw_desc = self.title or "", self.description or ""
        try:
            from sanitize_text import sanitize_text
            self.title, tf = sanitize_text(raw_title)
            self.description, df = sanitize_text(raw_desc)
            if tf or df:
                import specimens
                if tf:
                    specimens.record_findings(self.source, "title", tf, raw_title)
                if df:
                    specimens.record_findings(self.source, "description", df, raw_desc)
        except Exception:
            pass
        if not self.id:
            self.id = hashlib.md5(f"{self.title}{self.url}{self.source}".encode()).hexdigest()[:12]
        if not self.scraped_at:
            self.scraped_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return asdict(self)


class BaseScraper(ABC):
    def __init__(self, name: str, base_url: str, session=None):
        self.name = name
        self.base_url = base_url
        self.session = session
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/html, */*',
            'Accept-Language': 'en-US,en;q=0.9',
        }

    @abstractmethod
    async def scrape(self) -> List[Deal]:
        pass

    def listed_as_free(self, listing_path=""):
        """Cena zgłoszona przez stronę źródłową, niepotwierdzona w sklepie.

        "listing:" znaczy dokładnie tyle: ta strona wymieniła to jako darmowe.
        To nie jest pomiar ceny i nie może być tak opisywane w interfejsie.
        Scraper, który naprawdę pyta API sklepu, nie używa tego — używa
        api:<sklep> z odpowiedzi, którą faktycznie dostał.

        price zostaje puste: to pole znaczy "ile sklep powiedział", a nikt
        sklepu nie pytał. Wpisanie tu "Free" byłoby właśnie tym kłamstwem,
        które łapie test_P7.
        """
        return {
            "price": "",
            "price_claim": "Free",
            "price_source": f"listing:{self.base_url}{listing_path}",
        }

    def clean_title(self, title: str) -> str:
        """Trim, collapse whitespace and drop store prefixes.

        Reddit titles arrive as "[Steam] (Game) Sputnika Game" and that
        bracket was stored verbatim, so the dashboard listed a row whose title
        began with markup rather than the game. The same normaliser the F2P
        check uses removes the prefix, which also makes titles searchable by
        the plain game name."""
        if not title:
            return "Unknown"
        import re as _re
        t = _STORE_PREFIX_RE.sub("", str(title))
        t = _re.sub(r"\s+", " ", t).strip()
        return t[:200] if t else "Unknown"

    def clean_price(self, price_text: str) -> str:
        """Normalise a price string, collapsing genuine zero-cost offers to "Free".

        Keyword matching is word-boundary based so that titles like "Freedom
        Fighters" or "$10.00" are not mistaken for free offers.
        """
        if not price_text:
            return "Free"

        text = price_text.strip()
        low = text.lower()

        for word in _FREE_WORDS:
            if re.search(rf'\b{re.escape(word)}\b', low):
                return "Free"

        # "100% off" / "-100%" means the full price is discounted away.
        if re.search(r'\b100\s*%', text) and re.search(r'\b(off|%\s*off|rabat)\b', low):
            return "Free"

        # A numeric price is free only when the amount is exactly zero.
        numbers = re.findall(r'\d+(?:[.,]\d+)?', text)
        if numbers:
            first = numbers[0].replace(",", ".")
            try:
                if float(first) == 0.0:
                    return "Free"
            except ValueError:
                pass

        return text

    def is_valid(self, deal: Deal) -> bool:
        if not (deal.title and deal.url and deal.source):
            return False
        # Free-to-play and paid add-ons are not free-to-keep. Enforced here,
        # in the single place every scraper's output passes through, so no
        # source can reintroduce them.
        if is_f2p_or_addon(deal.title, getattr(deal, "description", "")):
            return False
        if self.is_garbage(deal.title):
            return False
        # Scrapers parse hostile third-party markup. A stored javascript: or
        # data: URL would execute from dashboard href/src attributes, and
        # React turns it into a full render crash (app-wide DoS).
        # A prefix test is not a URL parse: "http://", "https://#" and
        # "https://." all pass it, and a hostless link then lands in the DB
        # where new URL() throws and the row is misrouted. Reject URL userinfo
        # too: it can disguise the actual destination in a displayed link.
        from urllib.parse import urlparse
        try:
            parts = urlparse(deal.url)
        except (TypeError, ValueError):
            return False
        if (parts.scheme.lower() not in ("http", "https")
                or not parts.hostname or not parts.hostname.strip(".")
                or parts.username is not None or parts.password is not None):
            return False
        return self.is_safe_url(deal.url)

    @staticmethod
    def is_safe_url(url: str) -> bool:
        """Reject direct executables. Suffix match on the FINAL path segment
        only: matching the whole URL flags every '.com' domain (noise), and
        matching the query string flags tracking params like '?format=exe'.
        """
        from urllib.parse import unquote, urlparse
        try:
            path = urlparse(url).path
        except Exception:
            return False
        # A trailing slash empties the last segment, so /dir.exe/ used to
        # pass. Strip slashes, then percent-decoding so dropper%2Eexe does
        # not slip through either.
        seg = unquote(path).rstrip("/").rsplit("/", 1)[-1].lower()
        if "." not in seg:
            return True
        suffix = "." + seg.rsplit(".", 1)[-1]
        return suffix not in DANGEROUS_EXT

    def is_garbage(self, title: str) -> bool:
        """Reject demos/beta/prologue entries without eating real titles.

        Three generations of this filter:
          * plain substring matching ate "Demonschool", "Betrayal at Club Low"
          * word boundaries ate "Alpha Protocol", "Prologue", "Alpha Centauri"
        Now a status word only counts with qualifier context around it or as a
        trailing tag, so those titles survive.
        """
        if not title:
            return True
        low = title.lower().strip()
        for phrase in _GARBAGE_PHRASES:
            if phrase in low:
                return True
        # Explicit tag markers only. A bare trailing status word is AMBIGUOUS
        # and cannot be told apart from a real title: "Serious Sam: Alpha",
        # "The Beta" and "Prologue" are all shipped games, while "X - Beta"
        # is a beta build. So a tag counts when it is bracketed, dash- or
        # slash-separated, or numbered - and we fail open otherwise, because
        # dropping a real game is worse than showing one beta.
        if re.search(r"[\(\[\{]\s*(?:demo|beta|alpha|trial|prologue|f2p)\s*[\)\]\}]", low):
            return True
        if re.search(r"[-–—/|]\s*(?:demo|beta|alpha|trial|prologue)\b", low):
            return True
        # Safe trailing tags: a shipped title does not end in "Demo"/"f2p".
        if _GARBAGE_TAIL_RE.search(low):
            return True
        if _GARBAGE_NUMBERED.search(low):
            return True
        # f2p alone is a tag, not a word in a title
        if re.search(r"(?:^|\s)f2p(?:\s|$)", low):
            return True
        return False

    def resolve_url(self, href: str) -> str:
        """Turn a possibly relative href into an absolute URL.

        Three scrapers (FreeSteamKeys, GiveawayRadar, …) stored raw hrefs, so
        the DB silently filled with unusable "/post/xyz" links. This makes
        resolution the default instead of remembering it per scraper.
        """
        if not href:
            return ""
        href = href.strip()
        if href.startswith(("http://", "https://")):
            return href
        if href.startswith("//"):
            return f"https:{href}"
        return f"{self.base_url.rstrip('/')}/{href.lstrip('/')}"

    @staticmethod
    def nested(data, *keys, default=None):
        """Null-safe deep dict lookup.

        External APIs routinely return explicit nulls in the middle of the
        path (Epic's "originalPrice": null killed the whole Epic scraper with
        a TypeError). Plain .get() chains do not survive that.
        """
        cur = data
        for key in keys:
            if not isinstance(cur, dict):
                return default
            cur = cur.get(key)
            if cur is None:
                return default
        return cur
