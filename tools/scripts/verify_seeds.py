"""Verify seed-catalog candidates.

Steam offers are emitted only when the official API explicitly marks them as
free-to-play. Other sites are checked for reachability and page identity only;
that does not verify their price, so those candidates are never emitted.
JSON goes to stdout and diagnostics go to stderr.
"""
import json
import sys
import time
import urllib.request

UA = {"User-Agent": "MatrixHunt/2.0 (free games aggregator)",
      "Accept-Language": "en-US,en;q=0.9"}

STEAM_IDS = [570, 440, 230410, 238960, 730, 1172470, 578080, 1085660, 1599340,
             2357570, 2767030, 2507950, 2943650, 1222670, 1665460, 1782210,
             1677740, 1240440, 1286830, 1284210, 8500, 109600, 9900, 24200,
             218230, 386360, 394360, 813810, 291550, 2073850, 2139460, 336530,
             236390, 386260, 1120680, 823130, 438100, 471710, 2051620]

PAGES = [
    ("Fortnite", "https://store.epicgames.com/en-US/p/fortnite", "shooter", "Fortnite"),
    ("Rocket League", "https://store.epicgames.com/en-US/p/rocket-league", "sports", "Rocket League"),
    ("Fall Guys", "https://store.epicgames.com/en-US/p/fall-guys", "action", "Fall Guys"),
    ("League of Legends", "https://www.leagueoflegends.com/en-us/", "moba", "League of Legends"),
    ("Valorant", "https://playvalorant.com/en-us/", "shooter", "VALORANT"),
    ("Roblox", "https://www.roblox.com/", "social", "Roblox"),
]


def get(url, timeout=25):
    req = urllib.request.Request(url, headers={**UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return (response.status, response.geturl(),
                response.read(80000).decode("utf-8", "replace"))


def steam_offer(appid, result):
    """Return a seed offer only for an explicitly free-to-play Steam game."""
    if not isinstance(result, dict) or result.get("success") is not True:
        return None
    data = result.get("data")
    if (not isinstance(data, dict) or data.get("type") != "game"
            or data.get("is_free") is not True):
        return None
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    return {"title": name, "url": f"https://store.steampowered.com/app/{appid}",
            "price": "Free", "price_claim": "Free",
            "price_source": "api:steam", "source": "SeedCatalog",
            "category": "games",
            "description": "Free-to-play title verified by Steam API at catalog generation."}


def verify_steam(appid):
    req = urllib.request.Request(
        f"https://store.steampowered.com/api/appdetails?appids={appid}",
        headers=UA)
    with urllib.request.urlopen(req, timeout=25) as response:
        payload = json.loads(response.read().decode("utf-8", "replace"))
    if not isinstance(payload, dict):
        return None
    return steam_offer(appid, payload.get(str(appid)))


def verify_page(url, marker):
    status, _final_url, body = get(url)
    return status == 200 and len(body) > 5000 and marker.lower() in body.lower()


def main():
    kept = []
    errors = 0

    print("== Steam API (is_free) ==", file=sys.stderr)
    for appid in STEAM_IDS:
        try:
            offer = verify_steam(appid)
            print(f"  [{'OK ' if offer else 'DROP'}] {appid}"
                  f"{' ' + offer['title'] if offer else ''}", file=sys.stderr)
            if offer:
                kept.append(offer)
        except Exception as error:
            errors += 1
            print(f"  [ERR ] {appid} {str(error)[:160]}", file=sys.stderr)
        time.sleep(0.4)

    print("== strony (dostępność, nie cena) ==", file=sys.stderr)
    for title, url, _category, marker in PAGES:
        try:
            available = verify_page(url, marker)
            print(f"  [{'OK ' if available else 'DROP'}] {title}"
                  " (cena niezweryfikowana; pominięto w JSON)", file=sys.stderr)
        except Exception as error:
            errors += 1
            print(f"  [ERR ] {title} {str(error)[:160]}", file=sys.stderr)
        time.sleep(0.5)

    print(f"kept {len(kept)}; errors {errors}", file=sys.stderr)
    print(json.dumps(kept, indent=1, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
