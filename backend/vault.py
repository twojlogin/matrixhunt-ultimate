"""At-rest encryption for the sensitive files.

What is protected: cookie jars (live session tokens), the session signing
secret, app settings. What is NOT: matrixhunt.db (public scraped listings -
encrypting it would be theater, and SQLAlchemy needs a plaintext file to open,
so "encryption" would just mean a plaintext temp copy).

Crypto: scrypt (n=2^15, r=8, p=1) derives a 32-byte key from the master
password; Fernet (AES-128-CBC + HMAC) envelopes each file with a random salt.
Wrong password -> InvalidToken, never partial plaintext.

Key provisioning: env MH_VAULT_PASSWORD, or POST /api/vault/unlock once per
process lifetime. Without a key everything works unencrypted (0600 files)
with a loud startup warning - fail-open for availability, never silent.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import tempfile

HERE = Path(__file__).parent
VERIFIER_PATH = HERE / ".vault_verifier"

_salt_len = 16


_fernet_cache = {}


def _fernet(password, salt):
    """Derive the Fernet key, cached per (password, salt).

    scrypt with n=2**15 costs ~0.6 s and 32 MiB per call, and seal/unseal
    ran on every settings read, every cookie-jar write and every proxied page
    load - read_settings() alone was called from four places per request.
    The salt changes when the password changes, so it belongs in the key."""
    key = hashlib.sha256(password.encode("utf-8") + b"\0" + salt).digest()
    hit = _fernet_cache.get(key)
    if hit is not None:
        return hit
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    from cryptography.fernet import Fernet
    kdf = Scrypt(salt=salt, length=32, n=2 ** 15, r=8, p=1)
    f = Fernet(base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8"))))
    # Bounded so a long-running process with a wrong password on every
    # unlock attempt cannot grow this without limit.
    if len(_fernet_cache) > 8:
        _fernet_cache.clear()
    _fernet_cache[key] = f
    return f


class Vault:
    """Process-wide key holder. Call unlock() once; lock() drops the key."""

    def __init__(self):
        self._password = None
        env = os.environ.get("MH_VAULT_PASSWORD")
        if env:
            if not self.unlock(env):
                raise RuntimeError("MH_VAULT_PASSWORD does not match the vault verifier")

    @property
    def locked(self):
        return not self._password

    def unlock(self, password):
        """Verify against the stored verifier (or create it on first use)."""
        if not password:
            return False
        if VERIFIER_PATH.exists():
            try:
                blob = json.loads(VERIFIER_PATH.read_text())
                salt = base64.b64decode(blob["salt"])
                _fernet(password, salt).decrypt(blob["token"].encode())
            except Exception:
                return False
        else:
            salt = os.urandom(_salt_len)
            token = _fernet(password, salt).encrypt(b"matrixhunt-vault")
            verifier = json.dumps({
                "salt": base64.b64encode(salt).decode(),
                "token": token.decode()}).encode("utf-8")
            fd, tmp = tempfile.mkstemp(
                dir=str(VERIFIER_PATH.parent), prefix=f".{VERIFIER_PATH.name}.")
            try:
                os.fchmod(fd, 0o600)
                with os.fdopen(fd, "wb") as stream:
                    fd = -1
                    stream.write(verifier)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(tmp, VERIFIER_PATH)
            except Exception:
                if fd >= 0:
                    os.close(fd)
                try:
                    os.unlink(tmp)
                except FileNotFoundError:
                    pass
                raise
        previous_password = self._password
        if previous_password != password:
            _fernet_cache.clear()
        self._password = password
        try:
            seal_plaintext_leftovers(self)
        except Exception:
            self._password = previous_password
            raise
        return True

    def lock(self):
        self._password = None
        _fernet_cache.clear()

    def seal(self, data: bytes) -> bytes:
        """Encrypt for disk; plaintext is allowed only before vault setup."""
        if self.locked:
            if VERIFIER_PATH.exists():
                raise ValueError("vault locked - unlock before writing sensitive data")
            return b"PLAIN:" + data
        salt = os.urandom(_salt_len)
        token = _fernet(self._password, salt).encrypt(data)
        return b"VAULT1:" + base64.b64encode(salt) + b":" + token

    def unseal(self, blob: bytes) -> bytes:
        if blob.startswith(b"VAULT1:"):
            if self.locked:
                raise ValueError("vault locked - unlock first")
            _, salt_b, token = blob.split(b":", 2)
            salt = base64.b64decode(salt_b)
            return _fernet(self._password, salt).decrypt(token)
        if self.locked and VERIFIER_PATH.exists():
            raise ValueError("vault locked - unlock before reading plaintext data")
        if blob.startswith(b"PLAIN:"):
            return blob[len(b"PLAIN:"):]
        # Legacy files written before the vault existed.
        return blob


vault = Vault()


def seal_plaintext_leftovers(v):
    """Encrypt pre-vault plaintext sensitive files in place (one-way)."""
    from sessions import JAR_DIR
    targets = list(JAR_DIR.glob("*.json"))
    for extra in (HERE / ".app_settings.json", HERE / ".session_secret"):
        if extra.exists():
            targets.append(extra)
    for path in targets:
        raw = path.read_bytes()
        if raw.startswith(b"VAULT1:"):
            continue
        sealed = v.seal(raw if raw.startswith(b"PLAIN:") else b"PLAIN:" + raw)
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


def cookie_to_dict(c):
    return {"name": c.name, "value": c.value or "", "domain": c.domain or "",
            "path": c.path or "/", "secure": bool(c.secure),
            "expires": c.expires, "discard": bool(c.discard)}


def cookie_from_dict(d):
    from http.cookiejar import Cookie
    return Cookie(version=0, name=d.get("name", ""), value=d.get("value", ""),
                  port=None, port_specified=False,
                  domain=d.get("domain", ""), domain_specified=bool(d.get("domain")),
                  domain_initial_dot=(d.get("domain") or "").startswith("."),
                  path=d.get("path", "/"), path_specified=True,
                  secure=bool(d.get("secure", False)), expires=d.get("expires"),
                  discard=bool(d.get("discard", True)), comment=None,
                  comment_url=None, rest={}, rfc2109=False)


def jar_fingerprint(path):
    """sha256 of a sealed file for the status endpoint. No content leaks."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]
