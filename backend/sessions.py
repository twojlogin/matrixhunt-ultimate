"""Separate cookie sessions for the viewer proxy.

Every external host gets its own cookie jar (own "container"), persisted as
backend/.cookies/<host>.json with owner-only permissions. Jars never mix:
a login on indiegala.com is invisible to gog.com and vice versa. Wiping one
file logs that site out without touching the rest.

Only session cookies are stored here. Passwords transit the local proxy on
login POSTs but are never written anywhere - the jar keeps Set-Cookie
responses, never form fields.
"""
import json
import re
import threading
import time
from pathlib import Path
from http.cookiejar import MozillaCookieJar

JAR_DIR = Path(__file__).parent / ".cookies"
SAFE_HOST = re.compile(r"[^a-z0-9.-]")


def jar_path(host):
    safe = SAFE_HOST.sub("_", (host or "").lower())[:100] or "unknown"
    return JAR_DIR / f"{safe}.json"


_SEAL_WARNED = set()


def load_jar(host):
    """Return a cookie jar. Reads sealed JSON, PLAIN: envelopes, or legacy
    Netscape-format files (migrated to sealed JSON on next save)."""
    from vault import vault, cookie_from_dict
    JAR_DIR.mkdir(mode=0o700, exist_ok=True)
    jar = MozillaCookieJar(str(jar_path(host)))
    path = jar_path(host)
    if not path.exists():
        return jar
    try:
        raw = path.read_bytes()
        data = vault.unseal(raw)
    except ValueError:
        # Vault locked on a sealed file: this is NOT an empty jar. Report it
        # so list_sessions can say "locked" instead of "logged out", and so
        # nobody concludes the sessions are gone.
        jar = MozillaCookieJar(str(path))
        jar.locked = True
        return jar
    except Exception as e:
        print(f"[sessions] could not read {path.name}; preserving it: "
              f"{type(e).__name__}: {e}")
        jar = MozillaCookieJar(str(path))
        jar.locked = True
        return jar
    try:
        try:
            items = json.loads(data.decode("utf-8"))
            if isinstance(items, list):
                for entry in items:
                    try:
                        jar.set_cookie(cookie_from_dict(entry))
                    except Exception:
                        continue
                return jar
        except (ValueError, AttributeError):
            pass
        # Legacy Netscape plaintext: load the old way.
        jar.load(ignore_discard=True, ignore_expires=True)
    except Exception as e:
        print(f"[sessions] invalid cookie data in {path.name}; preserving it: "
              f"{type(e).__name__}: {e}")
        jar = MozillaCookieJar(str(path))
        jar.locked = True
    return jar


def save_jar(jar):
    """Persist the jar. Refuses to downgrade a sealed file to plaintext.

    vault.seal() returns b"PLAIN:" + data while the vault is locked, and
    load_jar swallowed that as an empty jar, so locking the vault used to
    cause the next page load to overwrite the encrypted jar in the clear.
    If the file on disk is already sealed, we leave it alone.
    """
    from vault import VERIFIER_PATH, vault, cookie_to_dict
    import json as _json
    import os
    import tempfile
    try:
        JAR_DIR.mkdir(mode=0o700, exist_ok=True)
        JAR_DIR.chmod(0o700)
        path = jar_path(host_of(jar))
        if getattr(jar, "locked", False):
            print(f"[sessions] preserving unreadable jar "
                  f"{Path(jar.filename).name if getattr(jar, 'filename', None) else '?'}")
            return
        if vault.locked and VERIFIER_PATH.exists():
            print("[sessions] vault locked - refusing to write cookies in plaintext")
            return
        if path.exists() and path.read_bytes().startswith(b"VAULT1:") and vault.locked:
            global _SEAL_WARNED
            if path.name not in _SEAL_WARNED:
                _SEAL_WARNED.add(path.name)
                print(f"[sessions] vault locked - keeping {path.name} "
                      f"sealed, cookies not persisted until unlock")
            return
        payload = _json.dumps([cookie_to_dict(c) for c in jar]).encode("utf-8")
        sealed = vault.seal(payload)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as stream:
                fd = -1
                stream.write(sealed)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp, path)
        except Exception:
            if fd >= 0:
                os.close(fd)
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
            raise
    except Exception as e:
        print(f"[sessions] save failed for {getattr(jar, 'filename', '?')}: {e}")


def host_of(jar):
    name = Path(jar.filename).stem if getattr(jar, "filename", None) else "unknown"
    return name


def session_state(host):
    """Small public summary for the viewer badge. No cookie values leak."""
    jar = load_jar(host)
    cookies = [c for c in jar]
    return {"host": host, "cookies": len(cookies),
            "has_session": len(cookies) > 0,
            "names": sorted({c.name for c in cookies})[:10],
            "locked": bool(getattr(jar, "locked", False))}


def list_sessions():
    if not JAR_DIR.exists():
        return {}
    out = {}
    for f in JAR_DIR.glob("*.json"):
        try:
            host = f.stem.replace("_", ".")
            # stem mangling is lossy; prefer hosts remembered inside the jar.
            jar = load_jar(host)
            cookies = [c for c in jar]
            if not cookies:
                # try the literal stem (hosts with underscores are rare)
                jar = load_jar(f.stem)
                cookies = [c for c in jar]
            domains = sorted({c.domain for c in cookies if c.domain})
            out[f.stem] = {"cookies": len(cookies),
                           "has_session": len(cookies) > 0,
                           "domains": domains[:5],
                           "locked": bool(getattr(jar, "locked", False))}
        except Exception:
            continue
    return out


_HOST_OK = re.compile(r"^[a-z0-9.-]+$")


def forget_host(host):
    """Delete one site's jar = log that site out. Returns True if removed."""
    if not host or not _HOST_OK.fullmatch(host):
        return False
    if ".." in host or "/" in host or "\\" in host or "\x00" in host:
        return False
    safe = SAFE_HOST.sub("_", host.lower())[:100] or "unknown"
    target = f"{safe}.json"
    try:
        if not JAR_DIR.exists():
            return False
        for p in JAR_DIR.glob("*.json"):
            if p.name == target:
                p.unlink()
                return True
    except OSError:
        pass
    return False


def forget_all():
    """Wipe every site session. Returns the number of jars removed."""
    n = 0
    if JAR_DIR.exists():
        for f in JAR_DIR.glob("*.json"):
            try:
                f.unlink()
                n += 1
            except OSError:
                pass
    return n


def attach_to_requests(host, req_session):
    """Copy a host jar into a requests.Session (per-request, isolated)."""
    for cookie in load_jar(host):
        try:
            req_session.cookies.set_cookie(cookie)
        except Exception:
            continue


def persist_from_requests(host, req_session):
    """Merge a requests.Session's cookies back into the host jar."""
    jar = load_jar(host)
    try:
        for cookie in req_session.cookies:
            try:
                jar.set_cookie(cookie)
            except Exception:
                continue
        save_jar(jar)
    except Exception:
        pass
    return jar


# ================================================================ TRYB ULOTNY
# Logowanie bez śladu na dysku: słoik żyje tylko w RAM procesu, z limitem
# bezczynności. Restart serwera, przycisk "wyczyść" albo TTL kasują wszystko.
# Rozdzielone od słoików dyskowych celowo — tryb ulotny nigdy nie czyta ani
# nie pisze plików, więc nie da się go pomylić ze "zapamiętaną" sesją.
EPHEMERAL_TTL = 30 * 60  # sekund bezczynności, potem wyparowuje z RAM

_EPHEMERAL = {}
_EPH_LOCK = threading.Lock()


def _eph_key(host):
    return (host or "").lower()


def _sweep_ephemeral(now=None):
    now = time.time() if now is None else now
    with _EPH_LOCK:
        for host in [h for h, e in _EPHEMERAL.items()
                     if now - e["last"] > EPHEMERAL_TTL]:
            del _EPHEMERAL[host]


def load_ephemeral(host):
    """Słoik z RAM (pusty, gdy wygasł lub go nie było). Nigdy nie tyka dysku."""
    _sweep_ephemeral()
    key = _eph_key(host)
    with _EPH_LOCK:
        entry = _EPHEMERAL.get(key)
        if entry is None:
            entry = {"jar": MozillaCookieJar(), "last": time.time()}
            _EPHEMERAL[key] = entry
        else:
            entry["last"] = time.time()
        return entry["jar"]


def save_ephemeral(host, req_session):
    """Scal ciasteczka do słoika w RAM. Zwraca słoik; dysk nietknięty."""
    jar = load_ephemeral(host)
    try:
        for cookie in req_session.cookies:
            try:
                jar.set_cookie(cookie)
            except Exception:
                continue
    except Exception:
        pass
    return jar


def ephemeral_state(host):
    """Jak session_state, ale z RAM. Ten sam kształt, inna półka."""
    jar = load_ephemeral(host)
    cookies = [c for c in jar]
    return {"host": host, "cookies": len(cookies),
            "has_session": len(cookies) > 0,
            "names": sorted({c.name for c in cookies})[:10],
            "ephemeral": True}


def list_ephemeral():
    _sweep_ephemeral()
    with _EPH_LOCK:
        return {h: {"cookies": len([c for c in e["jar"]]),
                    "ephemeral": True}
                for h, e in _EPHEMERAL.items()
                if [c for c in e["jar"]]}


def forget_ephemeral(host):
    with _EPH_LOCK:
        return _EPHEMERAL.pop(_eph_key(host), None) is not None


def forget_ephemeral_all():
    with _EPH_LOCK:
        n = len(_EPHEMERAL)
        _EPHEMERAL.clear()
        return n


def attach_ephemeral(host, req_session):
    """Jak attach_to_requests, ale ze słoika w RAM. Dysk nietknięty."""
    for cookie in load_ephemeral(host):
        try:
            req_session.cookies.set_cookie(cookie)
        except Exception:
            continue


def persist_ephemeral(host, req_session):
    """Jak persist_from_requests, ale do RAM. Dysk nietknięty."""
    return save_ephemeral(host, req_session)
