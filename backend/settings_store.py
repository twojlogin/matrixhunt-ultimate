"""Runtime settings: proxy on/off, Tor, upstream proxy. No secrets here.

Stored as backend/.app_settings.json (NOT under a static mount - an upstream
proxy URL could embed credentials). Only allowlisted keys are accepted and
upstream URLs are re-validated on every read.
"""
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import urlparse

STORE = Path(__file__).parent / ".app_settings.json"

DEFAULTS = {
    "proxy_clean": True,    # antysyf cleaner in /api/clean + viewer routing
    "tor": False,           # route cleaner traffic via Tor SOCKS (if reachable)
    "upstream_proxy": "",   # e.g. http://127.0.0.1:8080 (empty = direct)
    "filters_enabled": True,  # globalny wyłącznik filtrowania (uBlock-style power)
    "filter_lists": {"easylist": True, "easyprivacy": True,
                     "polish": True, "badware": True},
    "custom_lists": [],     # subskrybowane listy: [{"url","name","enabled"}]
    "custom_rules": "",     # user filter rules, uBlock syntax, max 64KB
}

TOR_SOCKS = "socks5h://127.0.0.1:9050"


def _validate_upstream(value):
    value = (value or "").strip()
    if not value:
        return ""
    try:
        parts = urlparse(value)
    except Exception:
        raise ValueError("unparseable proxy URL")
    if parts.scheme not in ("http", "https", "socks5", "socks5h"):
        raise ValueError("proxy scheme must be http(s) or socks5(h)")
    if not parts.hostname:
        raise ValueError("proxy needs a host")
    if parts.username or parts.password:
        raise ValueError("no credentials in proxy URL - run an unauthenticated local forwarder instead")
    return value


_LOCK_WARNED = False


def read_settings():
    global _LOCK_WARNED
    from vault import vault
    data = dict(DEFAULTS)
    locked = False
    try:
        if STORE.exists():
            raw = json.loads(vault.unseal(STORE.read_bytes()).decode("utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("settings must be an object")
            for key in DEFAULTS:
                if key in raw:
                    data[key] = raw[key]
    except Exception as e:
        # A corrupt or locked settings file must not silently route traffic
        # directly or be overwritten by a subsequent setting change.
        locked = True
        if not _LOCK_WARNED:
            _LOCK_WARNED = True
            print(f"[settings] unavailable ({type(e).__name__}: {e}); "
                  "proxy traffic and settings writes are blocked")
    if locked:
        data["settings_locked"] = True
    data["proxy_clean"] = bool(data.get("proxy_clean", True))
    data["tor"] = bool(data.get("tor", False))
    try:
        data["upstream_proxy"] = _validate_upstream(data.get("upstream_proxy", ""))
    except ValueError as e:
        data["upstream_proxy"] = ""
        data["settings_locked"] = True
        if not _LOCK_WARNED:
            _LOCK_WARNED = True
            print(f"[settings] invalid upstream proxy ({e}); "
                  "proxy traffic and settings writes are blocked")
    data["filter_lists"] = _validate_lists(data.get("filter_lists"))
    data["filters_enabled"] = bool(data.get("filters_enabled", True))
    data["custom_lists"] = _validate_custom_lists(data.get("custom_lists", []))
    data["custom_rules"] = _validate_custom(data.get("custom_rules", ""))
    return data


def _as_bool(value):
    """Strict boolean. bool("false") is True, so a JSON client sending
    {"key":"tor","value":"false"} switched Tor ON. Only real booleans, and
    the strings a form actually submits, are accepted."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("true", "1", "yes", "on"):
            return True
        if v in ("false", "0", "no", "off", ""):
            return False
    raise ValueError("expected a boolean value")


def _validate_lists(value):
    from filterlists import LISTS
    out = {lid: True for lid in LISTS}
    if isinstance(value, dict):
        for lid in LISTS:
            if lid in value:
                out[lid] = _as_bool(value[lid])
    return out


def _validate_custom(value):
    if not isinstance(value, str):
        raise ValueError("custom_rules must be text")
    if len(value) > 65536:
        raise ValueError("custom_rules too large (64KB max)")
    return value


def _validate_custom_lists(value):
    """Subskrybowane listy filtrów: [{"url","name","enabled"}].

    Trzyma się tylko HTTP(S) z hostem - właściwa bramka SSRF (zakaz hostów
    prywatnych + rewalidacja każdego przekierowania) jest w cleanroomie
    pobierania, bo walidacja przy zapisie nie rozstrzygnie DNS.
    """
    if not isinstance(value, list):
        raise ValueError("custom_lists must be a list")
    out, seen = [], set()
    for item in value[:50]:
        if not isinstance(item, dict):
            raise ValueError("custom list must be an object")
        url = str(item.get("url", "")).strip()
        if not url or len(url) > 2048:
            raise ValueError("bad list url")
        parts = urlparse(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError("list url must be http(s)")
        if url in seen:
            continue
        seen.add(url)
        name = str(item.get("name") or parts.hostname)[:80]
        out.append({"url": url, "name": name,
                    "enabled": _as_bool(item.get("enabled", True))})
    return out


def write_setting(key, value):
    if key not in DEFAULTS:
        raise ValueError(f"unknown setting: {key}")
    if key in ("proxy_clean", "tor", "filters_enabled"):
        value = _as_bool(value)
    elif key == "upstream_proxy":
        value = _validate_upstream(value)
    elif key == "filter_lists":
        value = _validate_lists(value)
    elif key == "custom_lists":
        value = _validate_custom_lists(value)
    elif key == "custom_rules":
        value = _validate_custom(value)
    data = read_settings()
    from vault import VERIFIER_PATH, vault
    if data.get("settings_locked") or (vault.locked and VERIFIER_PATH.exists()):
        raise PermissionError("vault locked or settings unavailable")
    data[key] = value
    payload = vault.seal(json.dumps(data, indent=1).encode("utf-8"))
    fd, tmp = tempfile.mkstemp(dir=str(STORE.parent), prefix=f".{STORE.name}.")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            fd = -1
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, STORE)
    except Exception:
        if fd >= 0:
            os.close(fd)
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
    return data


def tor_available(timeout=8):
    """True only when traffic actually exits via Tor (not just an open port)."""
    try:
        import requests as _requests
        r = _requests.get("https://check.torproject.org/api/ip", timeout=timeout,
                          proxies={"http": TOR_SOCKS, "https": TOR_SOCKS})
        return bool(r.ok and r.json().get("IsTor") is True)
    except Exception:
        return False


def effective_proxies(settings=None):
    """Proxy dict for requests, or None for a direct connection."""
    settings = settings or read_settings()
    if settings.get("tor"):
        return {"http": TOR_SOCKS, "https": TOR_SOCKS}
    upstream = settings.get("upstream_proxy") or ""
    if upstream:
        return {"http": upstream, "https": upstream}
    return None
