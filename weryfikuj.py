#!/usr/bin/env python3
"""Weryfikacja aplikacji — niezależne sprawdzenia.

Uruchom:  ./weryfikuj.sh
Koniec na liscie plikow, do uruchomienia recznie przez ciebie.

Kazda funkcja zwraca (opis, czy_ok, liczba_ok, liczba_sprawdzonych).
Zero zaleznosci poza standardowa biblioteka i tym co juz jest w .venv.
Nic nie modyfikuje - tylko czyta i odpytuje uruchomiona aplikacje.
"""
import json
import re
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"


def _run_dir():
    """Katalog na log/port — przenośny, bez /home/... na sztywno."""
    import os
    import tempfile
    env = os.environ.get("MH_RUN_DIR", "").strip()
    if env:
        return Path(env)
    user = os.environ.get("USER", "u") or "u"
    return Path(os.environ.get("TMPDIR") or tempfile.gettempdir()) / f"matrixhunt-{user}"


def _port():
    """Port z env, potem z pliku, potem z logu startu, fallback 8000."""
    import os
    env = os.environ.get("MH_PORT", "").strip()
    if env.isdigit():
        return int(env)
    run = _run_dir()
    for pt in (run / "port.txt",
               ROOT / ".tmp" / "port.txt"):
        try:
            if pt.exists() and pt.read_text().strip().isdigit():
                return int(pt.read_text().strip())
        except OSError:
            pass
    for log in (run / "vp.log",
                ROOT / ".tmp" / "vp.log"):
        try:
            if log.exists():
                m = re.search(r"127\.0\.0\.1:(\d+)", log.read_text(errors="replace"))
                if m:
                    return int(m.group(1))
        except OSError:
            pass
    return 8000


PORT = _port()
BASE = f"http://127.0.0.1:{PORT}"
results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"  {'OK  ' if ok else 'ZLE '} {name}" + (f"  — {detail}" if detail else ""))
    return ok


def get(path, timeout=20):
    try:
        with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
            return r.getcode(), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception:
        return 0, ""


def proxy_get(url, timeout=20):
    status, config = get("/api/client-config")
    token = json.loads(config).get("token", "") if status == 200 else ""
    if not token:
        return status or 0, config
    query = urllib.parse.urlencode({"url": url, "token": token})
    return get("/api/clean?" + query, timeout=timeout)


# ---------------------------------------------------------------- trasy
def v_trasy():
    print("\n[1] Trasy HTTP")
    for r in ["/", "/retro", "/pad", "/db", "/view", "/wiki", "/bookmarks", "/flash",
              "/manifest.json", "/sw.js"]:
        c, body = get(r)
        check(f"{r} -> 200 i niepuste", c == 200 and len(body) > 200, f"{c}, {len(body)}B")


# ---------------------------------------------------------------- api
def v_api():
    print("\n[2] API")
    c, b = get("/api/stats")
    d = json.loads(b) if c == 200 else {}
    check("/api/stats zwraca oferty", d.get("total", 0) > 0, f"total={d.get('total')}, zrodel={len(d.get('sources', {}))}")
    c, _ = get("/api/scrapers")
    check("/api/scrapers istnieje", c == 200)
    # limit
    c, b = get("/api/offers?limit=1000000000")
    n = len(json.loads(b)) if c == 200 else -1
    check("limit=1e9 przycięty do 1000", 0 < n <= 1000, f"{n} ofert")
    # LIKE wildcards
    c1, b1 = get("/api/offers?search=_&limit=1000")
    c2, b2 = get("/api/offers?search=dark&limit=1000")
    n1 = len(json.loads(b1)) if c1 == 200 else -1
    n2 = len(json.loads(b2)) if c2 == 200 else -1
    check("search=_ nie lapie wszystkiego", 0 <= n1 < max(n2, 1) or n1 == 0, f"_={n1}, dark={n2}")


# ---------------------------------------------------------------- token
def v_token():
    print("\n[3] Token i CORS")
    try:
        req = urllib.request.Request(BASE + "/api/scrape", method="POST", data=b"")
        urllib.request.urlopen(req, timeout=10)
        check("POST bez tokenu odrzucony", False, "przeszedł!")
    except urllib.error.HTTPError as e:
        check("POST bez tokenu -> 403", e.code == 403, str(e.code))
    except Exception as e:
        check("POST bez tokenu", False, str(e))

    c, b = get("/api/client-config")
    tok = json.loads(b).get("token", "") if c == 200 else ""
    check("client-config zwraca token", len(tok) == 32, f"dlugosc={len(tok)}")

    try:
        req = urllib.request.Request(BASE + "/api/scrape", method="POST", data=b"",
                                     headers={"X-MH-Token": "zly" * 16})
        urllib.request.urlopen(req, timeout=10)
        check("zly token odrzucony", False)
    except urllib.error.HTTPError as e:
        check("zly token -> 403", e.code == 403, str(e.code))

    for o in ("http://localhost:9999", "http://evil.com"):
        try:
            req = urllib.request.Request(BASE + "/api/stats",
                                         headers={"Origin": o})
            with urllib.request.urlopen(req, timeout=10) as r:
                acao = r.headers.get("Access-Control-Allow-Origin")
            check(f"obcy origin {o} bez CORS", not acao, str(acao))
        except Exception as e:
            check(f"obcy origin {o}", False, str(e))


# ---------------------------------------------------------------- proxy
def v_proxy():
    print("\n[4] Proxy i SSRF")
    c, body = proxy_get("https://example.com/")
    check("proxy zwraca 200", c == 200, str(c))
    check("proxy zachowuje tresc", "Example Domain" in body)
    check("proxy usuwa skrypty", "<script" not in body.lower())

    for u in ("http://127.0.0.1:8000/api/stats",
              "http://169.254.169.254/latest/meta-data/",
              "file:///etc/passwd",
              "http://localhost:8000/"):
        c, body = proxy_get(u, timeout=25)
        check(f"SSRF blokowany: {u[:34]}",
              c == 403 and "blocked" in body.lower(), f"{c}: {body[:80]}")


# ---------------------------------------------------------------- filtry
def v_filtry():
    print("\n[5] Filtry (niezmiennik na prawdziwych plikach list)")
    sys.path.insert(0, str(BACKEND))
    import filterlists as fl
    e = fl.get_engine()
    p = "https://shop.example.com/game"
    ginie = ["https://www.google-analytics.com/analytics.js",
             "https://static.hotjar.com/hj.js",
             "https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js"]
    zyja = ["https://cdn.jsdelivr.net/npm/react@18/umd/react.production.min.js",
            "https://d1.cloudfront.net/a.js",
            "https://storage.googleapis.com/cdn/s.css",
            "https://s3.amazonaws.com/b/s.js",
            "https://www.youtube.com/embed/x"]
    ok = sum(1 for u in ginie if e.check(p, u, "script")[0])
    check("trackery blokowane", ok == len(ginie), f"{ok}/{len(ginie)}")
    ok = sum(1 for u in zyja if not e.check(p, u, "script")[0])
    check("zdrowe hosty przepuszczone", ok == len(zyja), f"{ok}/{len(zyja)}")

    zaw = 0
    zle = 0
    for d, rules in e.domain_rules.items():
        for r in rules:
            if r.regex is None and r.path in (None, "", "/"):
                continue
            zaw += 1
            if r.matches(f"https://{d}/", "other.example", "script"):
                zle += 1
    check("zadna zawezona regula nie blokuje calego hosta", zle == 0,
          f"{zaw} sprawdzonych, {zle} zlych")
    print(f"       (silnik: {len(e.domain_rules)} domen, {len(e.regex_rules)} regex, "
          f"{len(e.exceptions)} wyjatow)")


# ---------------------------------------------------------------- f2p
def v_f2p():
    print("\n[6] F2P i dodatki")
    sys.path.insert(0, str(BACKEND))
    from scrapers.base import is_f2p_or_addon as f
    f2p = ["Valorant", "Lost Ark", "Marvel Rivals", "Wuthering Waves", "PUBG",
           "Roblox", "Destiny 2", "Fortnite", "Genshin Impact", "Dota 2",
           "Warframe", "Overwatch 2", "Counter-Strike 2", "Path of Exile",
           "Apex Legends", "Delta Force", "Neverness to Everness",
           "PUBG: BATTLEGROUNDS", "Naraka Bladepoint", "Call of Duty Warzone"]
    gry = ["Celeste", "Hollow Knight", "Hotline Miami", "Night in the Woods",
           "Hades", "Dead Cells", "Stardew Valley", "Undertale", "Katana ZERO",
           "Cuphead", "Wuthering Heights", "Pathologic", "Prologue",
           "The Finals Girls", "Portal 2", "Half-Life 2", "Doom Eternal",
           "Outer Wilds", "Returnal", "Hades II"]
    ok = sum(1 for t in f2p if f(t))
    check("F2P odsiane", ok == len(f2p), f"{ok}/{len(f2p)}")
    ok = sum(1 for t in gry if not f(t))
    check("prawdziwe gry przepuszczone", ok == len(gry), f"{ok}/{len(gry)}")


# ---------------------------------------------------------------- baza
def v_baza():
    print("\n[7] Baza danych")
    db = sqlite3.connect(BACKEND / "matrixhunt.db")
    c = db.cursor()
    c.execute("SELECT title,description,url,source FROM offers")
    rows = c.fetchall()
    check("baza niepusta", len(rows) > 0, f"{len(rows)} wierszy")
    f2p = sum(1 for t, d, u, s in rows
              if s != "SeedCatalog" and re.search(r"free.to.play|freemium|gacha", f"{t} {d or ''}", re.I))
    check("zero F2P w bazie", f2p == 0, f"{f2p} znalezionych")
    pref = sum(1 for t, d, u, s in rows if t.startswith("["))
    check("zero prefiksow [..] w tytulach", pref == 0, f"{pref} znalezionych")
    EXE = re.compile(r"\.(exe|msi|bat|cmd|scr|ps1|jar|apk|deb|rpm|dmg|pkg|sh)$", re.I)
    exe = sum(1 for t, d, u, s in rows if EXE.search((u or "").split("?")[0]))
    check("zero linkow do wykonywalnych", exe == 0, f"{exe} znalezionych")
    bez = sum(1 for t, d, u, s in rows if not (u or "").startswith(("http://", "https://")))
    check("zero URL-i bez http(s)", bez == 0, f"{bez} znalezionych")
    db.close()


# ---------------------------------------------------------------- wyciek
def v_wyciek():
    print("\n[8] Wyciek danych")
    c, _ = get("/data/vulncheck.json")
    check("/data/vulncheck.json nie wystawiony", c == 404, str(c))
    c, _ = get("/data/seed_offers.json")
    check("/data/seed_offers.json dostępny", c == 200, str(c))
    c, _ = get("/data/..%2Fmatrixhunt.db")
    check("traversal /data zablokowany", c == 404, str(c))
    # secret nie w odpowiedziach
    import os
    for f_ in (".session_secret", ".app_settings.json"):
        p = BACKEND / f_
        if p.exists():
            tok = p.read_bytes()
            for ep in ("/api/stats", "/api/settings", "/api/client-config", "/api/offers"):
                _, body = get(ep)
                seg = tok[:24]
                if seg and seg in body.encode("utf-8", "replace"):
                    check(f"secret nie wycieka przez {ep}", False, f_)


# ---------------------------------------------------------------- realne sklepy
def v_sklepy():
    """Prawdziwe strony przez proxy. example.com nie ma formularza logowania,
    ciasteczek ani skryptow trackingowych, więc nie wykryje takich problemów —
    te strony je mają."""
    print("\n[9] Realne strony przez proxy (wolne, ~40s)")
    for u in ("https://www.gog.com", "https://itch.io",
              "https://www.humblebundle.com"):
        c, body = proxy_get(u, timeout=60)
        low = body.lower()
        tyt = re.search(r"<title[^>]*>(.*?)</title>", body, re.S)
        tyt = (tyt.group(1).strip()[:44] if tyt else "")
        n_a = len(re.findall(r"<a ", low))
        n_img = len(re.findall(r"<img", low))
        n_script = len(re.findall(r"<script", low))
        n_iframe = len(re.findall(r"<iframe", low))
        n_on = len(re.findall(r"\son\w+=", low))
        # Treść realna: dużo linków i obrazów, zero skryptów
        ok = (c == 200 and n_a > 20 and n_script == 0 and n_on == 0
              and n_iframe == 0 and not re.search(r"\bundefined\b", low))
        check(f"{u.split('//')[1][:22]} przez proxy", ok,
              f"{c}, {len(body)}B, a={n_a} img={n_img} script={n_script} "
              f"iframe={n_iframe} on*={n_on} tytul={tyt!r}")


# ---------------------------------------------------------------- podsumowanie
def main():
    print(f"Port: {PORT}  ({BASE})")
    for fn in (v_trasy, v_api, v_token, v_proxy, v_filtry, v_f2p, v_baza,
               v_wyciek, v_sklepy):
        try:
            fn()
        except Exception as e:
            check(f"{fn.__name__} wywalilo sie", False, f"{type(e).__name__}: {e}")

    zle = [r for r in results if not r[1]]
    print("\n" + "=" * 60)
    print(f"  {len(results) - len(zle)}/{len(results)} sprawdzen przeszlo")
    if zle:
        print("  NIEUDANE:")
        for name, _, detail in zle:
            print(f"    - {name}  {detail}")
        return 1
    print("  Wszystko zielone.")
    print("  UWAGA: to sa sprawdzenia ktore ISTNIEJA, nie te ktore mogliby")
    print("  wskazac jeszcze inne. Zielony wynik nie znaczy 'ukończone'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
