import asyncio
import socket
import sys
from pathlib import Path
from unittest.mock import patch

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
