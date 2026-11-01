"""uBlock-style filter engine for the antysyf proxy.

Subscribes to real-world lists (EasyList, EasyPrivacy, Polish filters, uBlock
Badware), compiles the network-rule subset, and decides per subresource.
Every block is logged with the exact rule + list, so a broken page is
debuggable ("what blocked it?") instead of a guessing game.

Supported syntax (deliberate subset, documented in README):
  ||domain^  /  ||domain/path  (+$options)  - block rules
  @@...                              - exceptions (win over normal blocks)
  |http...  /  plain *patterns*      - substring rules
Options honored: third-party, ~third-party, script/image/stylesheet/font/
media/object/subdocument/xmlhttprequest/other/document/popup (+ ~negations),
important (beats exceptions), $network (page-level refuse -> HTTP 451).
Skipped: cosmetic (##), scriptlets (#$#), domain=, csp/redirect/replace/
removeparam and other advanced modifiers (counted, never silently half-met).
"""
import re
import time
import json
import hashlib
import threading
from pathlib import Path
from collections import deque, Counter
from urllib.parse import urlparse, urljoin

CACHE_DIR = Path(__file__).parent / ".filterlists"
REFRESH_SECS = 24 * 3600

LISTS = {
    "easylist": {
        "name": "EasyList (ads, worldwide)",
        "url": "https://easylist.to/easylist/easylist.txt",
    },
    "easyprivacy": {
        "name": "EasyPrivacy (trackers, worldwide)",
        "url": "https://easylist.to/easylist/easyprivacy.txt",
    },
    "polish": {
        "name": "Polish filters (PL ads)",
        "url": "https://raw.githubusercontent.com/MajkiIT/polish-ads-filter/master/polish-adblock-filters/adblock.txt",
    },
    "badware": {
        "name": "uBlock Badware (malware/scam sites)",
        "url": "https://raw.githubusercontent.com/uBlockOrigin/uAssets/master/filters/badware.txt",
    },
}

# Resource types we evaluate. Cosmetic/script rules never reach us: scripts
# and iframes are stripped wholesale by the cleaner before this runs.
TYPES = {"script", "image", "stylesheet", "font", "media", "object",
         "subdocument", "xmlhttprequest", "other", "document", "popup"}

# uBO aliases for the option set above.
OPT_ALIASES = {"doc": "document", "3p": "third-party", "1p": "~third-party",
               "frame": "subdocument", "xhr": "xmlhttprequest",
               "popunder": "popup"}
# Options understood well enough to ignore (no blocking impact for us).
IGNORED_OPTS = {"all", "empty", "mp4", "donottrack", "match-case", "websocket",
                "inline-script", "inline-font", "webrtc", "ping"}
KNOWN_OPTS = TYPES | {"third-party", "~third-party", "important", "network"} | \
    set(OPT_ALIASES) | IGNORED_OPTS | {f"~{t}" for t in TYPES}

SEP = r"[^a-zA-Z0-9_.%-]"


def _pattern_to_regex(pattern):
    out, i = [], 0
    anchored_left = pattern.startswith("|")
    anchored_right = pattern.endswith("|")
    if anchored_left:
        pattern = pattern[1:]
    if anchored_right:
        pattern = pattern[:-1]
    while i < len(pattern):
        c = pattern[i]
        if c == "*":
            out.append(".*")
        elif c == "^":
            out.append(SEP)
        else:
            out.append(re.escape(c))
        i += 1
    rx = "".join(out)
    if anchored_left:
        rx = "^" + rx
    if anchored_right:
        rx = rx + "$"
    return rx


def _literal_token(pattern):
    """Longest alphanumeric run - used to prefilter regex candidates."""
    runs = re.findall(r"[a-z0-9]{4,}", pattern.lower())
    return max(runs, key=len) if runs else ""


class Rule:
    __slots__ = ("raw", "list_id", "allow", "important", "network",
                 "domain", "path", "regex", "token", "third_party",
                 "types")

    def __init__(self, raw, list_id, allow, important, network, domain,
                 path, regex, token, third_party, types):
        self.raw = raw
        self.list_id = list_id
        self.allow = allow
        self.important = important
        self.network = network
        self.domain = domain
        self.path = path
        self.regex = re.compile(regex, re.I) if regex else None
        self.token = token
        self.third_party = third_party  # True / False / None
        self.types = types  # None = all types

    def matches(self, url, page_host, res_type):
        parts = urlparse(url)
        host = (parts.hostname or "").lower()
        if self.domain:
            if not (host == self.domain or host.endswith("." + self.domain)):
                return False
            if self.path and self.path not in (parts.path or ""):
                return False
            if self.regex is not None and not self.regex.search(url):
                return False
        elif self.regex is not None:
            if self.token and self.token not in url.lower():
                return False
            if not self.regex.search(url):
                return False
        if self.third_party is not None:
            third = page_host and host != page_host.lower() and \
                not host.endswith("." + page_host.lower())
            if bool(third) != self.third_party:
                return False
        if self.types is not None and res_type not in self.types:
            return False
        return True


def parse_line(line, list_id):
    """Parse one filter line. Returns Rule, 'cosmetic', 'skipped' or None."""
    line = line.strip()
    if not line or line.startswith("!") or line.startswith("["):
        return None
    if "##" in line or "#@#" in line or "#$#" in line or "#?#" in line:
        return "cosmetic"
    allow = line.startswith("@@")
    if allow:
        line = line[2:]
    if "$" in line:
        pattern, _, opts_raw = line.partition("$")
        raw_opts = [o.strip().lower() for o in opts_raw.split(",")]
        # Resolve uBO aliases first (doc, 3p, 1p, frame, xhr, popunder).
        opts = [OPT_ALIASES.get(o, o) for o in raw_opts]
        # Anything we cannot evaluate (ipaddress=, denyallow=, from=, ...)
        # fails CLOSED: the rule is skipped, never half-applied. A skipped
        # rule blocks nothing; a misunderstood one broke real pages
        # (||com^$doc,ipaddress=… nuked every .com image once).
        for o in opts:
            base = o.split("=", 1)[0]
            if o in KNOWN_OPTS or base in KNOWN_OPTS:
                continue
            # Anything we cannot evaluate is skipped whole. The explicit
            # startswith() list this used to have was dead code: both branches
            # returned "skipped", so it read as a curated allowlist while
            # behaving as a blanket deny.
            return "skipped"
        important = "important" in opts
        network = "network" in opts
        third_party = None
        if "third-party" in opts:
            third_party = True
        if "~third-party" in opts:
            third_party = False
        types = set()
        neg = set()
        for o in opts:
            if o in TYPES:
                types.add(o)
            elif o.startswith("~") and o[1:] in TYPES:
                neg.add(o[1:])
        if neg and not types:
            types = set(TYPES) - neg
        types = types or None
    else:
        pattern, important, network, third_party, types = line, False, False, None, None

    domain, path, regex, token = None, None, None, ""
    if pattern.startswith("||"):
        rest = pattern[2:]
        raw_domain = re.split(r"[\^/*|$?]", rest, maxsplit=1)[0]
        domain = raw_domain.lower().rstrip(".")
        if not domain:
            return "skipped"
        if "." not in domain:
            # ||keyword/… is a HOSTNAME FRAGMENT, not a real domain
            # (||businessclick.*/ must hit businessclick.pl, ad.businessclick.com).
            # Treating it as a literal domain matched only the degenerate host
            # "businessclick" and never fired on anything real, so the rule was
            # dead weight. Match the fragment anywhere in the host instead.
            frag = re.escape(domain)
            regex = (r"(?:[a-z0-9-]+\.)*" + frag + r"[a-z0-9-]*"
                     + _pattern_to_regex(rest[len(raw_domain):]))
            token = domain
            return Rule(line, list_id, allow, important, network, None, None,
                        regex, token, third_party, types)
        # Slice on the RAW domain: using the rstripped one shifts the index
        # whenever the rule ends in a dot (||142.91.159.), leaving a stray
        # "." as the "tail" and compiling it to a regex that matches ANY url
        # on that host.
        tail = rest[len(raw_domain):]
        if tail and tail[0] == "/":
            # ^ ends the path, * makes the rest a wildcard (handled below as
            # a regex). Dropping the ^ split here turns an exception like
            # @@||host/ok^ into path "/ok^", which never matches anything.
            path = tail.split("^")[0].split("*")[0]
        # A wildcarded tail narrows the rule to a PATH. Discarding it used
        # to silently WIDEN the rule to the whole domain, so
        # ||jsdelivr.net^*/fp.min.js blocked every React CDN asset, and the
        # same shape hit cloudfront.net, youtube.com, amazonaws.com and
        # 1279 other hosts. Keep the domain as a prefilter, but also keep
        # the pattern so matches() can require both.
        if tail and re.search(r"[*|?]", tail.lstrip("/^$")):
            regex = _pattern_to_regex(tail.lstrip("^$"))
            token = _literal_token(pattern)
    elif pattern.startswith("|"):
        regex = _pattern_to_regex(pattern)
        token = _literal_token(pattern)
    else:
        if not any(c.isalnum() for c in pattern):
            return "skipped"
        regex = _pattern_to_regex(pattern)
        token = _literal_token(pattern)
    return Rule(line, list_id, allow, important, network, domain, path,
                regex, token, third_party, types)


class Engine:
    def __init__(self):
        self.domain_rules = {}   # domain -> [Rule]
        self.regex_rules = []    # [Rule] with token prefilter
        self.exceptions = []
        self.stats = Counter()
        self.loaded = {}         # list_id -> {rules, updated, url}

    def add_text(self, text, list_id):
        n_net = n_exc = n_cos = n_skip = 0
        for line in text.splitlines():
            r = parse_line(line, list_id)
            if r is None:
                continue
            if r == "cosmetic":
                n_cos += 1
            elif r == "skipped":
                n_skip += 1
            else:
                if r.allow:
                    self.exceptions.append(r)
                    n_exc += 1
                elif r.domain:
                    self.domain_rules.setdefault(r.domain, []).append(r)
                    n_net += 1
                else:
                    self.regex_rules.append(r)
                    n_net += 1
        self.stats[list_id] = {"network": n_net, "exceptions": n_exc,
                               "cosmetic_skipped": n_cos, "advanced_skipped": n_skip}
        return n_net

    def _candidates(self, host):
        out = []
        labels = host.lower().split(".")
        for i in range(len(labels)):
            suffix = ".".join(labels[i:])
            if suffix in self.domain_rules:
                out.extend(self.domain_rules[suffix])
        return out

    def check(self, page_url, resource_url, res_type="other", enabled=None):
        """Return (blocked, rule_or_None). Exceptions win, important wins all.

        enabled: set of list ids allowed to block (None = all). The custom
        user engine is always fully enabled - user rules win, like uBlock.
        """
        try:
            page_host = (urlparse(page_url).hostname or "").lower()
            host = (urlparse(resource_url).hostname or "").lower()
        except Exception:
            return False, None
        if not host:
            return False, None
        hit = None
        for rule in self._candidates(host):
            if enabled is not None and rule.list_id not in enabled:
                continue
            if rule.matches(resource_url, page_host, res_type):
                hit = rule
                break
        if hit is None:
            for rule in self.regex_rules:
                if enabled is not None and rule.list_id not in enabled:
                    continue
                if rule.matches(resource_url, page_host, res_type):
                    hit = rule
                    break
        if hit is None:
            return False, None
        for exc in self.exceptions:
            if enabled is not None and exc.list_id not in enabled:
                continue
            if exc.matches(resource_url, page_host, res_type):
                if not hit.important:
                    return False, exc
                break
        return True, hit


class FilterLog:
    """Ring buffer: what got blocked, where, by which exact rule."""

    def __init__(self, size=500):
        self.buf = deque(maxlen=size)

    def add(self, page, resource, rule, action):
        self.buf.append({"ts": time.time(), "page": page, "resource": resource,
                         "rule": rule.raw[:160], "list": rule.list_id,
                         "action": action})

    def tail(self, limit=100, host=None):
        items = list(self.buf)
        if host:
            items = [e for e in items if host in (e["page"] or "")]
        return items[-limit:]


_engine = None
_engine_lock = threading.Lock()
elog = FilterLog()


def _fetch_list(list_id, meta):
    return _safe_fetch(meta["url"], max_bytes=20 * 1024 * 1024)


def get_engine():
    """Singleton with the cached subscription lists (24h refresh).

    Custom user rules live in a separate tiny engine built per request -
    they always win, like uBlock user rules.
    """
    global _engine
    # Fast path first, entirely outside the lock: a warm engine is handed back
    # without acquiring anything. Rebuilding the engine recompiles ~100k rules
    # and that used to happen while holding _engine_lock across four network
    # fetches of up to 40s each, so a cold start blocked every caller for
    # minutes.
    eng = _engine
    if eng is not None and all((CACHE_DIR / f"{lid}.txt").exists() for lid in LISTS):
        _maybe_refresh_background()
        return eng
    with _engine_lock:
        # Re-check under the lock: another thread may have built it meanwhile.
        if _engine is not None and all((CACHE_DIR / f"{lid}.txt").exists()
                                       for lid in LISTS):
            return _engine
        need = _engine is None
        if not need:
            for list_id in LISTS:
                f = CACHE_DIR / f"{list_id}.txt"
                if not f.exists():
                    need = True
                    break
        if not need:
            eng = Engine()
            for list_id, meta in LISTS.items():
                f = CACHE_DIR / f"{list_id}.txt"
                eng.add_text(f.read_text(encoding="utf-8", errors="replace"), list_id)
                eng.loaded[list_id] = {"updated": f.stat().st_mtime, "url": meta["url"]}
            _maybe_refresh_background()
        else:
            CACHE_DIR.mkdir(exist_ok=True)
            # Downloads happen BEFORE the lock is taken, never inside it.
            # Four fetches of up to 40s each under a lock froze every
            # /api/clean, /api/offers and /api/filterlists for the duration.
            errors = {}
            for list_id, meta in LISTS.items():
                f = CACHE_DIR / f"{list_id}.txt"
                try:
                    if not f.exists() or time.time() - f.stat().st_mtime > REFRESH_SECS:
                        f.write_text(_fetch_list(list_id, meta), encoding="utf-8")
                except Exception as e:
                    errors[list_id] = str(e)[:80]
            eng = Engine()
            for list_id, meta in LISTS.items():
                f = CACHE_DIR / f"{list_id}.txt"
                try:
                    if not f.exists():
                        raise FileNotFoundError(f)
                    eng.add_text(f.read_text(encoding="utf-8", errors="replace"), list_id)
                    eng.loaded[list_id] = {"updated": f.stat().st_mtime, "url": meta["url"]}
                except Exception as e:
                    eng.loaded[list_id] = {"updated": 0, "url": meta["url"],
                                           "error": errors.get(list_id, str(e)[:80])}
        _engine = eng
        return eng


CUSTOM_MAX_BYTES = 5 * 1024 * 1024


def custom_file_id(url):
    """Stabilny id pliku cache dla subskrybowanej listy (jak LISTS keys)."""
    return "custom-" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def _safe_fetch(url, max_bytes=CUSTOM_MAX_BYTES, max_hops=5):
    """Pobiera subskrybowaną listę z bramką SSRF na KAŻDYM hopie.

    Ręczna pętla przekierowań: requests z allow_redirects=True poszłoby do
    127.0.0.1 mimo publicznego startu (redirect SSRF). Limit rozmiaru i
    timeout - to dane wprowadzone przez użytkownika.
    """
    from cleaner import is_url_allowed, new_safe_session
    cur, hops = url, 0
    with new_safe_session() as session:
        while True:
            ok, why = is_url_allowed(cur)
            if not ok:
                raise ValueError(f"blocked: {why}")
            r = session.get(cur, timeout=40, allow_redirects=False, stream=True,
                            headers={"User-Agent": "MatrixHunt/2.0 (filterlists)"})
            if r.status_code in (301, 302, 303, 307, 308):
                loc = r.headers.get("Location")
                r.close()
                if not loc or hops >= max_hops:
                    raise ValueError("too many redirects")
                cur = urljoin(cur, loc)
                hops += 1
                continue
            r.raise_for_status()
            chunks, total = [], 0
            for chunk in r.iter_content(65536):
                total += len(chunk)
                if total > max_bytes:
                    r.close()
                    raise ValueError("list too large")
                chunks.append(chunk)
            r.close()
            return b"".join(chunks).decode("utf-8", "replace")


def download_custom_lists(settings=None):
    """Ściąga (i cache'uje) włączone subskrybowane listy. Zwraca {id: błąd}."""
    if settings is None:
        from settings_store import read_settings
        settings = read_settings()
    CACHE_DIR.mkdir(exist_ok=True)
    errors = {}
    for lst in settings.get("custom_lists", []):
        if not lst.get("enabled", True):
            continue
        url = lst["url"]
        fid = custom_file_id(url)
        try:
            (CACHE_DIR / f"{fid}.txt").write_text(_safe_fetch(url), encoding="utf-8")
        except Exception as e:
            errors[fid] = str(e)[:80]
    return errors


def custom_engine(src):
    """Reguły użytkownika: ręczne reguły + ściągnięte własne listy.

    Przyjmuje dict ustawień (nowe) albo sam tekst reguł (kompatybilnie).
    Zawsze w pełni włączony, sprawdzany przed subskrypcjami - jak user rules
    w uBlock. Pobierania tu NIE ma: tylko pliki z cache, żeby hot-path
    /api/clean nigdy nie czekał na sieć.
    """
    eng = Engine()
    if isinstance(src, dict):
        rules_text = src.get("custom_rules", "")
        lists = src.get("custom_lists", [])
    else:
        rules_text, lists = src or "", []
    if rules_text and rules_text.strip():
        eng.add_text(rules_text, "custom")
    for lst in lists:
        if not lst.get("enabled", True):
            continue
        fid = custom_file_id(lst.get("url", ""))
        f = CACHE_DIR / f"{fid}.txt"
        try:
            if f.exists():
                eng.add_text(f.read_text(encoding="utf-8", errors="replace"), fid)
                eng.loaded[fid] = {"updated": f.stat().st_mtime,
                                   "url": lst.get("url", ""),
                                   "name": lst.get("name", "")}
        except OSError:
            pass
    return eng


def _maybe_refresh_background():
    def _run():
        for list_id, meta in LISTS.items():
            f = CACHE_DIR / f"{list_id}.txt"
            try:
                if f.exists() and time.time() - f.stat().st_mtime > REFRESH_SECS:
                    f.write_text(_fetch_list(list_id, meta), encoding="utf-8")
            except Exception:
                pass
    t = threading.Thread(target=_run, daemon=True)
    t.start()


def reset_engine():
    global _engine
    with _engine_lock:
        _engine = None


def cached_engine():
    """Engine from already-downloaded lists only. Returns None when the
    cache is missing (e.g. fresh install) - callers must treat that as
    'no reputation data', never as an error, and never trigger a download
    from a scraper hot path."""
    with _engine_lock:
        files = [(lid, CACHE_DIR / f"{lid}.txt") for lid in LISTS]
        if not all(f.exists() for _, f in files):
            return None
        eng = Engine()
        try:
            for lid, f in files:
                eng.add_text(f.read_text(encoding="utf-8", errors="replace"), lid)
        except Exception:
            return None
        return eng
