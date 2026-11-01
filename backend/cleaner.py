"""Antysyf: fetch + sanitise untrusted external game pages.

The viewer (/view) serves third-party sites through here so visitors never
touch raw ad-/tracker-laden markup. Two layers:

1. SSRF guard (is_url_allowed) - only public http(s) hosts, ports 80/443,
   every redirect hop re-validated. The app binds 127.0.0.1, so an open
   fetch would otherwise reach the visitor's LAN.
2. clean_html - strips executable/active markup and styles, proxies images,
   removes untrusted subresources and applies a strict browser CSP.
"""
import ipaddress
import re
import socket
from urllib.parse import urlencode, urljoin, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.exceptions import ConnectTimeoutError, NewConnectionError
from urllib3.util import connection

ALLOWED_PORTS = {80, 443}
MAX_BYTES = 2 * 1024 * 1024

# Host substrings: ad/tracker delivery domains. These are matched against the
# HOSTNAME only, never the whole URL - matching the full URL deleted real
# content, because "beacon" and "pixel" are ordinary words in link slugs.
TRACKER_HOSTS = (
    "doubleclick.net", "googlesyndication.com", "google-analytics.com",
    "googletagmanager.com", "googleadservices.com", "facebook.net",
    "fbcdn.net", "hotjar.com", "crazyegg.com", "mixpanel.com",
    "segment.io", "newrelic.com", "scorecardresearch.com", "quantserve.com",
    "outbrain.com", "taboola.com", "criteo.com", "adservice.", "adsystem",
)
# Path forms that are unambiguous tracking endpoints. Deliberately NOT
# included: bare "/ads/" and "/track", because /ads/pricing is a real pricing
# page and /tracklist a real slug. Real ad URLs are already covered properly
# by the EasyList subscriptions, so the heuristic only needs the cases where
# a path IS the tracker.
TRACKER_PATH_PREFIXES = (
    "/pixel.", "/tracking-pixel", "/tracking/", "/telemetry/", "/beacon/",
    "/g/collect", "/stats/collect",
)
# Path tokens, only at a clean segment boundary. A dash is NOT a boundary:
# "/pixel-art-guide" is a guide, "/pixel.gif" is a pixel.
TRACKER_PATH_TOKENS = ("/pixel", "/beacon")

STRIP_TAGS = {"script", "iframe", "object", "embed", "applet", "svg", "math",
              "template", "style", "meta", "link", "base"}
# Form controls stay: logins must work through the proxy. The server never
# stores submitted values - only Set-Cookie responses land in the host jar.
FORM_TAGS = {"form", "input", "button", "select", "textarea", "label",
             "option", "fieldset", "legend"}

_DANGEROUS_SCHEMES = ("javascript:", "data:", "vbscript:")
# Browsers strip ASCII tab/newline (and other C0 controls/space at the edges)
# from a URL BEFORE reading its scheme, so "java\tscript:alert(1)" and
# "\x01javascript:…" execute as javascript:. The old check compared the raw
# value with startswith, so those survived and /api/clean is same-origin -
# real script in the viewer. Normalise controls/space away BEFORE the test.
_CTRL_SPACE = re.compile(r"[\x00-\x20\x7f]")


def _dangerous_scheme(val):
    if not isinstance(val, str):
        return False
    return _CTRL_SPACE.sub("", val).lower().startswith(_DANGEROUS_SCHEMES)


def _is_global_ip(host):
    """Return one public address only if every DNS answer is public."""
    try:
        literal = ipaddress.ip_address(host)
        return str(literal) if literal.is_global else None
    except ValueError:
        pass

    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError:
        return None
    addresses = []
    for info in infos:
        ip = info[4][0]
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return None
        if not addr.is_global:
            return None
        if str(addr) not in addresses:
            addresses.append(str(addr))
    return addresses[0] if addresses else None


class _PinnedHTTPConnection(HTTPConnection):
    def __init__(self, *args, pinned_ip, **kwargs):
        self._pinned_ip = pinned_ip
        super().__init__(*args, **kwargs)

    def _new_conn(self):
        try:
            return connection.create_connection(
                (self._pinned_ip, self.port), self.timeout,
                source_address=self.source_address,
                socket_options=self.socket_options,
            )
        except (socket.timeout, TimeoutError) as exc:
            raise ConnectTimeoutError(
                self, f"Connection to {self.host} timed out."
            ) from exc
        except OSError as exc:
            raise NewConnectionError(
                self, f"Failed to establish a connection: {exc}"
            ) from exc


class _PinnedHTTPSConnection(HTTPSConnection):
    def __init__(self, *args, pinned_ip, **kwargs):
        self._pinned_ip = pinned_ip
        super().__init__(*args, **kwargs)

    def _new_conn(self):
        try:
            return connection.create_connection(
                (self._pinned_ip, self.port), self.timeout,
                source_address=self.source_address,
                socket_options=self.socket_options,
            )
        except (socket.timeout, TimeoutError) as exc:
            raise ConnectTimeoutError(
                self, f"Connection to {self.host} timed out."
            ) from exc
        except OSError as exc:
            raise NewConnectionError(
                self, f"Failed to establish a connection: {exc}"
            ) from exc


class _PinnedHTTPConnectionPool(HTTPConnectionPool):
    ConnectionCls = _PinnedHTTPConnection


class _PinnedHTTPSConnectionPool(HTTPSConnectionPool):
    ConnectionCls = _PinnedHTTPSConnection


class _PinnedHTTPAdapter(HTTPAdapter):
    def _pool_for(self, url):
        parts = urlparse(url)
        host = parts.hostname or ""
        pinned_ip = _is_global_ip(host)
        if not pinned_ip:
            raise ValueError("non-public host")
        port = parts.port or (443 if parts.scheme == "https" else 80)
        pool = (_PinnedHTTPSConnectionPool if parts.scheme == "https"
                else _PinnedHTTPConnectionPool)
        kwargs = {"host": host, "port": port, "pinned_ip": pinned_ip}
        if parts.scheme == "https":
            kwargs.update(server_hostname=host, assert_hostname=host)
        return pool(**kwargs)

    def get_connection(self, url, proxies=None):
        if proxies:
            return super().get_connection(url, proxies)
        return self._pool_for(url)

    def get_connection_with_tls_context(self, request, verify, proxies=None, cert=None):
        if proxies:
            return super().get_connection_with_tls_context(
                request, verify, proxies, cert)
        return self._pool_for(request.url)


def new_safe_session(proxies=None):
    """Create a Requests session that pins direct connections to checked DNS."""
    session = requests.Session()
    session.trust_env = False
    session.mount("http://", _PinnedHTTPAdapter())
    session.mount("https://", _PinnedHTTPAdapter())
    if proxies:
        session.proxies.update(proxies)
    return session


def is_url_allowed(url, check_dns=True):
    """SSRF gate for the /api/clean proxy. Returns (ok, reason).

    check_dns=False skips local resolution (used when traffic goes through
    Tor/upstream: resolving locally would leak the hostname to the local
    resolver AND answer differently than the exit sees). Scheme/port/host
    syntax checks always apply.
    """
    try:
        parts = urlparse(url)
        host = parts.hostname or ""
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except (AttributeError, TypeError, ValueError):
        return False, "unparseable URL"
    if parts.scheme not in ("http", "https"):
        return False, "only http(s) allowed"
    if not host or parts.username is not None or parts.password is not None:
        return False, "missing host"
    if port not in ALLOWED_PORTS:
        return False, "port not allowed"
    host_lower = host.lower().rstrip(".")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if (literal is not None and not literal.is_global) or (
            literal is None and (host_lower == "localhost"
                                 or host_lower.endswith((".localhost", ".local",
                                                         ".internal", ".test")))):
        return False, "non-public host"
    if check_dns and not _is_global_ip(host):
        return False, "non-public host"
    return True, ""


def _is_tracker(url):
    """True for known tracking endpoints, matched on the right component.

    Previously every entry was a substring test over the whole URL, so
    /pixel-art-guide, /beacon-training.html and /ads/pricing were treated as
    trackers and tag.decompose() deleted the element - including real <a>
    links, because src fell back to href."""
    if not url:
        return False
    from urllib.parse import urlparse
    try:
        parts = urlparse(url)
    except Exception:
        return False
    host = (parts.hostname or "").lower()
    if any(t in host for t in TRACKER_HOSTS):
        return True
    path = (parts.path or "").lower()
    if any(path.startswith(p) for p in TRACKER_PATH_PREFIXES):
        return True
    for tok in TRACKER_PATH_TOKENS:
        # boundary before and after the token, so /pixel-art is fine but
        # /px/pixel.gif and /img/pixel/track are not
        i = path.find(tok)
        while i != -1:
            before_ok = i == 0 or path[i - 1] in "/.-_"
            end = i + len(tok)
            after_ok = end >= len(path) or path[end] in "/._?&"
            if before_ok and after_ok:
                return True
            i = path.find(tok, i + 1)
    return False


def _filter_check(flt, page_url, resource_url, res_type):
    """(blocked, rule) via custom engine first, then subscriptions."""
    if not flt or not resource_url:
        return False, None
    custom = flt.get("custom")
    if custom is not None:
        blocked, rule = custom.check(page_url, resource_url, res_type)
        if blocked:
            return True, rule
    eng = flt.get("engine")
    if eng is not None:
        return eng.check(page_url, resource_url, res_type,
                         enabled=flt.get("enabled"))
    return False, None


def clean_html(html, base_url, flt=None, token=None):
    """Return (clean_html, removed_count, blocked_count). Pure function,
    fully unit-tested.

    flt: optional {"engine", "custom", "enabled", "log"} - when given,
    subresource URLs are additionally judged by the filter engine and every
    block is recorded in the shared filter log with the exact rule + list.
    """
    from bs4 import BeautifulSoup
    from filterlists import elog

    soup = BeautifulSoup(html, "html.parser")
    removed = 0
    filtered = 0

    for tag in soup.find_all(True):
        if not tag.name:
            continue
        name = tag.name.lower()
        if name in STRIP_TAGS:
            if name == "meta":
                if (tag.get("charset") or tag.get("http-equiv", "").lower() == "content-type"):
                    continue
                tag.decompose()
                removed += 1
                continue
            tag.decompose()
            removed += 1
            continue

        # Event handler attributes (onclick=…) execute - strip them all.
        for attr in [a for a in tag.attrs if a.lower().startswith("on")]:
            del tag.attrs[attr]
            removed += 1

        # formaction would bypass the rewritten form action below.
        for attr in ("formaction", "srcdoc", "ping", "style", "background",
                     "dynsrc", "lowsrc", "data", "cite", "poster", "xlink:href"):
            if tag.has_attr(attr):
                del tag.attrs[attr]
                removed += 1

        if name == "form":
            action = tag.get("action", "") or ""
            # Percent-encode the proxied target. Concatenation lost every
            # "?" inside the action, so checkout?step=2&lang=en#pay became
            # url=...checkout?step=2 with "lang=en" and the fragment
            # orphaned onto our own endpoint.
            target = urljoin(base_url, action) if action else base_url
            params = {"url": target}
            if token:
                params["token"] = token
            tag["action"] = "/api/clean?" + urlencode(params)
            if not tag.get("method"):
                tag["method"] = "get"

        # Only image resources are loaded, through the validating image proxy.
        # All other external subresources are removed rather than fetched by
        # the browser outside the SSRF gate.
        for attr in ("href", "src", "action", "srcset"):
            val = tag.get(attr)
            if isinstance(val, str):
                low = val.strip().lower()
                if attr == "srcset":
                    rebuilt = []
                    for part in val.split(","):
                        bits = part.strip().split()
                        if not bits or _dangerous_scheme(bits[0]):
                            continue
                        image_url = _proxy_image_url(bits[0], base_url)
                        if image_url:
                            desc = " " + bits[1] if len(bits) > 1 else ""
                            rebuilt.append(image_url + desc)
                    if rebuilt:
                        tag[attr] = ", ".join(rebuilt)
                    else:
                        del tag.attrs[attr]
                        removed += 1
                elif attr == "src":
                    if name != "img":
                        del tag.attrs[attr]
                        removed += 1
                    else:
                        image_url = _proxy_image_url(val, base_url)
                        if image_url:
                            tag[attr] = image_url
                        else:
                            del tag.attrs[attr]
                            removed += 1
                elif attr == "href":
                    if _dangerous_scheme(val):
                        del tag.attrs[attr]
                        removed += 1
                    elif val and not low.startswith(("#", "mailto:")):
                        target = urljoin(base_url, val)
                        allowed, _reason = is_url_allowed(target, check_dns=False)
                        if not allowed:
                            del tag.attrs[attr]
                            removed += 1
                        else:
                            tag[attr] = target
                elif _dangerous_scheme(val):
                    del tag.attrs[attr]
                    removed += 1

        # Tracking pixels and ad hosts (legacy heuristics).
        src = tag.get("src", "")
        if src and _is_tracker(src):
            tag.decompose()
            removed += 1
            continue
        if tag.name == "img":
            try:
                w, h = int(tag.get("width", 0) or 0), int(tag.get("height", 0) or 0)
            except (ValueError, TypeError):
                w = h = 0
            if w == 1 and h == 1:
                tag.decompose()
                removed += 1
                continue

        # Subscription filter lists (uBlock-style): judge subresource loads.
        # Anchors are deliberately NOT removed - clicking stays the user's
        # choice (and outbound routes it through the viewer anyway).
        res_type = {"img": "image", "source": "media", "video": "media",
                    "audio": "media", "link": "stylesheet"}.get(tag.name, "other")
        for attr in ("src", "poster"):
            val = tag.get(attr)
            if isinstance(val, str) and val.startswith(("http://", "https://")):
                blocked, rule = _filter_check(flt, base_url, val, res_type)
                if blocked:
                    if flt.get("log", True):
                        from filterlists import elog as _elog
                        _elog.add(base_url, val, rule, "blocked-load")
                    tag.decompose()
                    removed += 1
                    filtered += 1
                    break

    return str(soup), removed, filtered


def _proxy_image_url(value, base_url):
    if not isinstance(value, str) or _dangerous_scheme(value):
        return None
    target = urljoin(base_url, value.strip())
    try:
        parts = urlparse(target)
        if (parts.scheme not in ("http", "https") or not parts.hostname
                or parts.username is not None or parts.password is not None):
            return None
    except ValueError:
        return None
    allowed, _reason = is_url_allowed(target, check_dns=False)
    if not allowed or _is_tracker(target):
        return None
    return "/api/img?" + urlencode({"url": target})
