"""Link doctor: rozwija skrocone linki i wystawia werdykt o adresie.

Deterministyczny, flag-not-block: nic nie kasuje, tylko opisuje ryzyko.
Zasada "nieznane != OK": werdykt "ok" znaczy "nie znalazlem czerwonych flag",
a gdy zadnego sprawdzenia nie udalo sie wykonac, werdykt to "nieznany".

Bezpieczenstwo: zadnego pobierania TRESCI strony (tylko naglowki/redirecty,
kazdy hop przez bramke SSRF cleaner.is_url_allowed), zero auto-pobierania,
zero telemetrii. Kazde wywolanie sieci jest opt-in (uzytkownik pyta o link).
"""
import datetime as _dt
import re
from urllib.parse import unquote, urljoin, urlparse

from scrapers.base import DANGEROUS_EXT

UA = "MatrixHunt/2.0 (linkdoctor)"

# Skracacze, ktore same w sobie nic nie mowia o celu - trzeba je rozwinac.
SHORTENERS = {
    "bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly", "is.gd", "buff.ly",
    "rebrand.ly", "cutt.ly", "shorturl.at", "rb.gy", "tiny.cc", "s.id",
    "bl.ink", "lnkd.in", "t.ly", "shorte.st", "adf.ly", "ouo.io", "linkvertise.com",
    "bc.vc", "shrinkme.io", "clck.ru", "vk.cc", "dlvr.it", "soo.gd",
}

CLOUDFLARE_SECURITY_DOH = "https://security.cloudflare-dns.com/dns-query"
RDAP_TEMPLATE = "https://rdap.verisign.com/{tld}/v1/domain/{domain}"
RDAP_TLDS = {"com", "net"}

NEW_DOMAIN_DAYS = 30
MAX_HOPS = 5

_SEV = {"ok": 0, "info": 1, "ostrzez": 2, "zablokuj": 3}
_VERDICT_NAMES = {0: "ok", 1: "ok", 2: "ostrzez", 3: "zablokuj"}


def _host(url):
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _registrable(host):
    """Przyblizenie: ostatnie dwie etykiety (dla naszych potrzeb wystarcza)."""
    parts = [p for p in host.split(".") if p]
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host


def is_shortener(host):
    return host in SHORTENERS


def _dangerous_ext(url):
    """Ostatni segment sciezki z rozszerzeniem wykonawczym."""
    path = unquote(urlparse(url).path or "")
    last = path.rsplit("/", 1)[-1].lower()
    if "." not in last:
        return None
    ext = "." + last.rsplit(".", 1)[-1]
    return ext if ext in DANGEROUS_EXT else None


def _idn_flags(host):
    """Punycode lub nieascii = mozliwe podszywanie sie (IDN)."""
    if not host:
        return None
    if any(label.startswith("xn--") for label in host.split(".")):
        return "IDN/punycode w nazwie domeny (mozliwe podszywanie sie)"
    if any(ord(c) > 127 for c in host):
        return "nieascii znaki w nazwie domeny (mozliwe podszywanie sie)"
    return None


def _resolve_redirects(url, max_hops=MAX_HOPS):
    """Reczne rozwiazywanie przekierowan z bramka SSRF na KAZDYM hopie.

    GET w trybie stream, cialo od razu zamykane - nie czytamy tresci.
    Zwraca (final_url, hops, error|None).
    """
    from cleaner import is_url_allowed, new_safe_session
    cur = url
    with new_safe_session() as session:
        for hop in range(max_hops + 1):
            ok, why = is_url_allowed(cur)
            if not ok:
                return cur, hop, f"zablokowane przez bramke SSRF: {why}"
            r = None
            try:
                r = session.get(cur, timeout=10, allow_redirects=False, stream=True,
                                headers={"User-Agent": UA})
                if r.status_code in (301, 302, 303, 307, 308):
                    loc = r.headers.get("Location")
                    if not loc:
                        return cur, hop, "przekierowanie bez celu"
                    cur = urljoin(cur, loc)
                    continue
                return cur, hop, None
            except Exception as e:
                return cur, hop, f"blad sieci: {type(e).__name__}"
            finally:
                if r is not None:
                    r.close()
    return cur, max_hops, "za duzo przekierowan"


def _doh_security(host):
    """Cloudflare security DoH: blokada = 0.0.0.0 + EDE(16). Bez konta/klicza."""
    import requests
    r = requests.get(CLOUDFLARE_SECURITY_DOH, timeout=8,
                     headers={"accept": "application/dns-json",
                              "User-Agent": UA},
                     params={"name": host, "type": "A"})
    r.raise_for_status()
    d = r.json()
    answers = d.get("Answer") or []
    comment = " ".join(d.get("Comment") or [])
    zeroed = any(a.get("data") == "0.0.0.0" for a in answers)
    if zeroed or "EDE(16)" in comment or "Censored" in comment:
        return True
    return False


def _domain_age_days(host):
    """Wiek domeny przez RDAP Verisign (tylko .com/.net). None = nieznane."""
    import requests
    registrable = _registrable(host)
    tld = registrable.rsplit(".", 1)[-1]
    if tld not in RDAP_TLDS:
        return None
    url = RDAP_TEMPLATE.format(tld=tld, domain=registrable)
    r = requests.get(url, timeout=8, headers={"User-Agent": UA,
                                              "accept": "application/rdap+json"})
    if r.status_code == 404:
        return None
    r.raise_for_status()
    for ev in r.json().get("events", []):
        if ev.get("eventAction") == "registration":
            dt = _dt.datetime.fromisoformat(ev["eventDate"].replace("Z", "+00:00"))
            now = _dt.datetime.now(_dt.timezone.utc)
            return max(0, (now - dt).days)
    return None


def check_url(url):
    """Werdykt dla adresu. Zwraca dict gotowy do JSON."""
    reasons = []
    checked = []

    def add(level, code, text):
        reasons.append({"level": level, "code": code, "text": text})
        return _SEV[level]

    host0 = _host(url)
    if not host0:
        add("zablokuj", "no-host", "adres bez nazwy hosta")
        return _pack(url, url, reasons, checked)

    from cleaner import is_url_allowed
    ok, why = is_url_allowed(url)
    checked.append("ssrf")
    if not ok:
        add("zablokuj", "ssrf", f"bramka SSRF blokuje ten adres: {why}")
        return _pack(url, url, reasons, checked)

    final_url, hops, err = _resolve_redirects(url)
    checked.append("redirecty")
    host = _host(final_url) or host0
    if err:
        add("ostrzez", "redirect", err)
    if hops:
        add("info", "redirect", f"rozwinięto {hops} przekierowanie(a) do: {host}")

    ext = _dangerous_ext(final_url)
    if ext:
        add("ostrzez", "ext", f"link konczy sie plikiem wykonywalnym ({ext}) - nie pobieraj")
    checked.append("rozszerzenie")

    idn = _idn_flags(host)
    if idn:
        add("ostrzez", "idn", idn)
    checked.append("idn")

    try:
        if _doh_security(host):
            add("zablokuj", "doh", "Cloudflare security DNS oznacza host jako zlosliwy/phishing")
        checked.append("dns-security")
    except Exception:
        add("info", "dns-security", "nie udało się sprawdzić DNS security (sieć)")

    try:
        age = _domain_age_days(host)
        if age is None:
            add("info", "age", "wiek domeny nieznany (RDAP tylko dla .com/.net)")
        elif age < NEW_DOMAIN_DAYS:
            add("ostrzez", "age", f"domena ma {age} dni (< {NEW_DOMAIN_DAYS}) - typowe dla oszustw")
        else:
            add("info", "age", f"domena ma {age} dni")
        checked.append("wiek")
    except Exception:
        add("info", "age", "nie udało się sprawdzić wieku domeny (sieć)")

    return _pack(url, final_url, reasons, checked)


def _pack(url, final_url, reasons, checked):
    top = max([_SEV[r["level"]] for r in reasons] or [0])
    verdict = _VERDICT_NAMES[top]
    # "nieznane != OK": jesli nic nie sprawdzono pozytywnie, nie udawaj OK.
    if verdict == "ok" and not checked:
        verdict = "nieznany"
    return {
        "url": url,
        "final_url": final_url,
        "host": _host(final_url) or _host(url),
        "verdict": verdict,
        "reasons": reasons,
        "checked": checked,
    }
