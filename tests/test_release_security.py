import asyncio
import socket
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from starlette.requests import Request
from starlette.responses import Response

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))


def _request(path, *, method="GET", client="127.0.0.1",
             host="127.0.0.1:8000", scheme="http", query=b"", headers=None):
    pairs = [(b"host", host.encode())]
    pairs.extend((key.lower().encode(), value.encode())
                 for key, value in (headers or {}).items())
    return Request({
        "type": "http",
        "method": method,
        "path": path,
        "query_string": query,
        "scheme": scheme,
        "server": ("127.0.0.1", 8000),
        "client": (client, 43210),
        "headers": pairs,
    })


def _run_guard(request):
    import main

    async def call_next(_request):
        return Response("ok")

    return asyncio.run(main._api_guard(request, call_next))


def test_api_guard_rejects_remote_peer_with_forged_loopback_host(monkeypatch):
    import main

    monkeypatch.setattr(main, "_MH_PUBLIC", False)
    response = _run_guard(_request("/api/client-config", client="203.0.113.20"))
    assert response.status_code == 403


def test_api_guard_requires_same_origin_for_proxy_get(monkeypatch):
    import main

    monkeypatch.setattr(main, "_MH_PUBLIC", False)
    response = _run_guard(_request("/api/clean"))
    assert response.status_code == 403

    response = _run_guard(_request(
        "/api/clean",
        headers={"Origin": "http://127.0.0.1:8000",
                 "Sec-Fetch-Site": "same-origin"},
    ))
    assert response.status_code == 200

    response = _run_guard(_request(
        "/api/clean",
        headers={"Origin": "http://evil.example",
                 "Sec-Fetch-Site": "cross-site"},
    ))
    assert response.status_code == 403


def test_api_mutations_require_token_and_public_mode_stays_read_only(monkeypatch):
    import main

    monkeypatch.setattr(main, "_MH_PUBLIC", False)
    response = _run_guard(_request("/api/settings", method="POST"))
    assert response.status_code == 403
    response = _run_guard(_request(
        "/api/settings", method="POST",
        headers={"X-MH-Token": main.API_TOKEN},
    ))
    assert response.status_code == 200

    monkeypatch.setattr(main, "_MH_PUBLIC", True)
    response = _run_guard(_request(
        "/api/settings", method="POST",
        headers={"X-MH-Token": main.API_TOKEN},
    ))
    assert response.status_code == 403
    response = _run_guard(_request("/api/settings"))
    assert response.status_code == 403


def test_clean_proxy_form_token_is_consumed_by_guard(monkeypatch):
    import main

    monkeypatch.setattr(main, "_MH_PUBLIC", False)
    response = _run_guard(_request(
        "/api/clean", method="POST", query=f"token={main.API_TOKEN}".encode(),
        headers={"Origin": "http://127.0.0.1:8000",
                 "Sec-Fetch-Site": "same-origin"},
    ))
    assert response.status_code == 200


def test_pinned_adapter_never_connects_to_dns_rebinding_private_ip(monkeypatch):
    import cleaner

    public = [(socket.AF_INET, socket.SOCK_STREAM, 6, "",
               ("93.184.216.34", 0))]
    private = [(socket.AF_INET, socket.SOCK_STREAM, 6, "",
                ("127.0.0.1", 0))]
    answers = iter((public, private))
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: next(answers))

    assert cleaner.is_url_allowed("http://rebind.example/")[0]
    adapter = cleaner._PinnedHTTPAdapter()
    with patch("cleaner.connection.create_connection") as connect:
        try:
            adapter.get_connection("http://rebind.example/")
        except ValueError as exc:
            assert str(exc) == "non-public host"
        else:
            raise AssertionError("private DNS answer was accepted")
        connect.assert_not_called()


def test_pinned_adapter_connects_to_the_checked_public_ip(monkeypatch):
    import cleaner

    answer = [(socket.AF_INET, socket.SOCK_STREAM, 6, "",
               ("93.184.216.34", 0))]
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: answer)
    adapter = cleaner._PinnedHTTPAdapter()
    pool = adapter.get_connection("https://safe.example/")
    connection = pool.ConnectionCls(
        host=pool.host, port=pool.port, pinned_ip=pool.conn_kw["pinned_ip"])

    with patch("cleaner.connection.create_connection") as connect:
        connection._new_conn()
    assert connect.call_args.args[0] == ("93.184.216.34", 443)
    assert pool.conn_kw["server_hostname"] == "safe.example"
    assert pool.assert_hostname == "safe.example"


def test_steam_drops_search_results_not_confirmed_free_by_api(monkeypatch):
    from scrapers.steam import SteamScraper

    class Response:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def text(self):
            return (
                '<a class="search_result_row" href="https://store.steampowered.com/app/100/">'
                '<div class="title">Verified Game</div></a>'
                '<a class="search_result_row" href="https://store.steampowered.com/app/101/">'
                '<div class="title">Paid Search Result</div></a>'
            )

    class Session:
        def get(self, *_args, **_kwargs):
            return Response()

    async def details(self, appid):
        return {"type": "game", "is_free": appid == "100"}

    monkeypatch.setattr(SteamScraper, "_details", details)
    deals = asyncio.run(SteamScraper(Session()).scrape())
    assert [deal.title for deal in deals] == ["Verified Game"]


def test_canonical_url_keeps_nondefault_scheme_ports_distinct():
    import main

    assert main._canonical_url("http://store.example:443/game") != \
        main._canonical_url("http://store.example/game")
    assert main._canonical_url("https://store.example:80/game") != \
        main._canonical_url("https://store.example/game")
    assert main._canonical_url("https://[2001:4860:4860::8888]:8443/game") == \
        "https://[2001:4860:4860::8888]:8443/game"


def test_offer_urls_reject_unsafe_or_credentialed_legacy_rows():
    import main

    assert main._safe_offer_url("https://store.example/game")
    assert not main._safe_offer_url("javascript:alert(1)")
    assert not main._safe_offer_url("https://store.example/download%2Eexe")
    assert not main._safe_offer_url("https://user:pass@store.example/game")


def test_proxy_refuses_to_forward_post_body_over_http():
    import main

    response = main._clean_sync(
        "http://store.example/login", "POST",
        {"content-type": "application/x-www-form-urlencoded"},
        {}, b"password=secret")
    assert response.status_code == 403
    assert b"HTTPS" in response.body


def test_vault_locked_does_not_encrypt_by_plaintext_fallback(tmp_path, monkeypatch):
    import vault

    monkeypatch.setattr(vault, "VERIFIER_PATH", tmp_path / ".vault_verifier")
    v = vault.Vault()
    assert v.seal(b"public mode") == b"PLAIN:public mode"

    vault.VERIFIER_PATH.write_text("configured")
    with pytest.raises(ValueError, match="vault locked"):
        v.seal(b"secret")
    with pytest.raises(ValueError, match="vault locked"):
        v.unseal(b"PLAIN:legacy secret")
    with pytest.raises(ValueError, match="vault locked"):
        v.unseal(b"legacy plaintext secret")


def test_vault_lock_drops_cached_derived_keys():
    import vault

    vault._fernet_cache.clear()
    vault._fernet("test password", b"0123456789abcdef")
    assert vault._fernet_cache
    vault.Vault().lock()
    assert not vault._fernet_cache


def test_vault_unlock_encrypts_and_rejects_wrong_password(tmp_path, monkeypatch):
    import vault

    monkeypatch.delenv("MH_VAULT_PASSWORD", raising=False)
    monkeypatch.setattr(vault, "VERIFIER_PATH", tmp_path / ".vault_verifier")
    monkeypatch.setattr(vault, "seal_plaintext_leftovers", lambda _vault: None)
    v = vault.Vault()
    assert v.unlock("test-vault-password")
    encrypted = v.seal(b"private settings")
    assert encrypted.startswith(b"VAULT1:")
    assert b"private settings" not in encrypted
    v.lock()

    locked = vault.Vault()
    assert not locked.unlock("wrong password")
    assert locked.unlock("test-vault-password")
    assert locked.unseal(encrypted) == b"private settings"


def test_locked_vault_blocks_settings_fallback_and_cookie_writes(tmp_path, monkeypatch):
    import settings_store
    import sessions
    import vault

    verifier = tmp_path / ".vault_verifier"
    monkeypatch.setattr(vault, "VERIFIER_PATH", verifier)
    monkeypatch.setattr(settings_store, "STORE", tmp_path / ".app_settings.json")
    monkeypatch.setattr(sessions, "JAR_DIR", tmp_path / ".cookies")
    vault.vault.lock()
    verifier.write_text("configured")
    settings_store.STORE.write_bytes(b"VAULT1:unreadable")

    assert settings_store.read_settings()["settings_locked"] is True
    settings_store.STORE.write_bytes(b"PLAIN:{\"tor\":true}")
    assert settings_store.read_settings()["settings_locked"] is True
    with pytest.raises(PermissionError):
        settings_store.write_setting("tor", True)

    from http.cookiejar import MozillaCookieJar
    sessions.JAR_DIR.mkdir(mode=0o700)
    cookie_path = sessions.jar_path("shop.example")
    cookie_path.write_bytes(b"PLAIN:[]")
    locked_jar = sessions.load_jar("shop.example")
    assert locked_jar.locked
    sessions.save_jar(locked_jar)
    assert cookie_path.read_bytes() == b"PLAIN:[]"

    jar = MozillaCookieJar(str(sessions.jar_path("shop.example")))
    sessions.save_jar(jar)
    assert cookie_path.read_bytes() == b"PLAIN:[]"


def test_osv_missing_package_results_are_not_clean(monkeypatch):
    import vulncheck

    monkeypatch.setattr(vulncheck, "_post_json", lambda *_args, **_kwargs: {
        "results": [{}]})
    assert vulncheck.check_osv({"package": "1.0"}) == {
        "_error": "invalid OSV vulnerability list"}

    monkeypatch.setattr(vulncheck, "_post_json", lambda *_args, **_kwargs: {
        "results": [{"vulns": []}]})
    assert vulncheck.check_osv({"package": "1.0"}) == {"package": []}


def test_legacy_osv_error_cache_cannot_be_reported_as_clean(tmp_path, monkeypatch):
    import json
    import vulncheck

    cache = tmp_path / "vulncheck.json"
    cache.write_text(json.dumps({"vulns": {"_error": "network failed"}, "total": 0}))
    monkeypatch.setattr(vulncheck, "AUDIT_CACHE", cache)
    report = vulncheck.cached_audit()
    assert report["ok"] is False
    assert report["errors"]["_error"] == "network failed"


def test_clean_html_only_exposes_checked_image_proxy_urls():
    from cleaner import clean_html

    html, _, _ = clean_html(
        '<style>body{background:url(https://evil.example/x)}</style>'
        '<svg onload="alert(1)"><script>alert(1)</script></svg>'
        '<math><mtext>x</mtext></math>'
        '<img src="https://cdn.example/image.png">'
        '<img src="http://127.0.0.1/private.png">'
        '<a href="javascript:alert(1)">bad</a>'
        '<form action="/login" method="post"></form>',
        "https://shop.example/games",
        token="form-token",
    )
    assert "<style" not in html.lower()
    assert "<svg" not in html.lower()
    assert "<math" not in html.lower()
    assert 'src="/api/img?url=https%3A%2F%2Fcdn.example%2Fimage.png"' in html
    assert "127.0.0.1" not in html
    assert "javascript:" not in html.lower()
    assert "token=form-token" in html
