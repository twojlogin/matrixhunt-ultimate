"""Secure Steam sign-in via OpenID 2.0. No passwords, no API keys.

Why this shape: the project rule is zero accounts and zero secrets, so the
app must never see a Steam password. OpenID delegates the password to Valve:
Steam answers "yes, this browser owns SteamID X" and the app stores only that
ID in a signed session cookie. Epic/GOG offer nothing equivalent without a
registered developer client (secret), which is why only Steam is supported.
"""
import re
import sys
import time
import calendar
from urllib.parse import urlencode

import requests

STEAM_OPENID = "https://steamcommunity.com/openid/login"
CLAIMED_RE = re.compile(r"^https://steamcommunity\.com/openid/id/(\d+)$")
NONCE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)")

# response_nonce values already consumed. Tiny in-memory replay cache:
# (nonce -> expiry). Single-process app, more than enough.
_seen_nonces = {}


def build_login_url(realm, return_to):
    params = {
        "openid.ns": "http://specs.openid.net/auth/2.0",
        "openid.mode": "checkid_setup",
        "openid.return_to": return_to,
        "openid.realm": realm,
        "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
        "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select",
    }
    return f"{STEAM_OPENID}?{urlencode(params)}"


def _nonce_fresh(nonce):
    now = time.time()
    for n, exp in list(_seen_nonces.items()):
        if exp < now:
            del _seen_nonces[n]
    if nonce in _seen_nonces:
        return False
    m = NONCE_RE.match(nonce or "")
    if not m:
        return False
    try:
        # Nonce timestamps are UTC; mktime would misread them as local time.
        ts = calendar.timegm(time.strptime(m.group(1), "%Y-%m-%dT%H:%M:%SZ"))
    except ValueError:
        return False
    if abs(now - ts) > 600:
        return False
    _seen_nonces[nonce] = now + 600
    return True


def _dbg(msg):
    print(f"[steam-auth] {msg}", file=sys.stderr)


def verify_response(params, expected_host):
    """Validate an OpenID return against Steam. Returns steamid or None."""
    import sys
    if params.get("openid.mode") != "id_res":
        _dbg(f"bad mode: {params.get('openid.mode')!r}")
        return None
    if params.get("openid.op_endpoint") != STEAM_OPENID:
        _dbg(f"bad op_endpoint: {params.get('openid.op_endpoint')!r}")
        return None
    claimed = params.get("openid.claimed_id", "")
    m = CLAIMED_RE.match(claimed)
    if not m or params.get("openid.identity") != claimed:
        _dbg("bad claimed_id/identity")
        return None
    try:
        host = params.get("openid.return_to", "").split("/")[2]
    except IndexError:
        _dbg("bad return_to")
        return None
    if host != expected_host:
        _dbg(f"host mismatch: {host!r} != {expected_host!r}")
        return None
    if not _nonce_fresh(params.get("openid.response_nonce", "")):
        _dbg("stale or replayed nonce")
        return None
    # The actual proof: ask Steam directly whether it signed this.
    check = dict(params)
    check["openid.mode"] = "check_authentication"
    try:
        r = requests.post(STEAM_OPENID, data=check, timeout=15)
        body = r.text
    except Exception as e:
        _dbg(f"check_authentication request failed: {e}")
        return None
    if "is_valid:true" not in body.replace(" ", ""):
        _dbg(f"Steam rejected signature: {body.strip()[:200]!r}")
        return None
    return m.group(1)


def fetch_persona(steamid):
    """Public profile name, keyless XML endpoint. None when private/failing."""
    try:
        r = requests.get(f"https://steamcommunity.com/profiles/{steamid}/?xml=1",
                         timeout=15, headers={"User-Agent": "MatrixHunt/2.0"})
        if r.status_code != 200:
            return None
        m = re.search(r"<steamID><!\[CDATA\[(.*?)\]\]></steamID>", r.text)
        return m.group(1) if m else None
    except Exception:
        return None


def fetch_games_count(steamid):
    """Owned-games count via the keyless XML library feed.

    Returns (count, private): private is True when the profile hides games.
    """
    try:
        r = requests.get(
            f"https://steamcommunity.com/profiles/{steamid}/games/?tab=all&xml=1",
            timeout=20, headers={"User-Agent": "MatrixHunt/2.0"})
        if r.status_code != 200:
            return None, True
        if "<error>" in r.text[:500]:
            return None, True
        return len(re.findall(r"<game>", r.text)), False
    except Exception:
        return None, True
