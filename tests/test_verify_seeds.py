import json

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "scripts"))
import verify_seeds


def test_steam_offer_requires_explicit_free_to_play_flag():
    assert verify_seeds.steam_offer(1, {
        "success": True,
        "data": {"name": "Discounted game", "type": "game", "is_free": False,
                 "price_overview": {"final": 0}},
    }) is None

    assert verify_seeds.steam_offer(1, {
        "success": True,
        "data": {"name": "Free game", "type": "game", "is_free": True},
    })["title"] == "Free game"

    assert verify_seeds.steam_offer(2, {
        "success": True,
        "data": {"name": "Free DLC", "type": "dlc", "is_free": True},
    }) is None


def test_page_checks_do_not_emit_unverified_prices(monkeypatch, capsys):
    offer = {"title": "Steam game", "price_source": "api:steam"}
    monkeypatch.setattr(verify_seeds, "STEAM_IDS", [1])
    monkeypatch.setattr(verify_seeds, "PAGES", [
        ("Page game", "https://example.com", "games", "Page game"),
    ])
    monkeypatch.setattr(verify_seeds, "verify_steam", lambda _appid: offer)
    monkeypatch.setattr(verify_seeds, "verify_page", lambda *_args: True)
    monkeypatch.setattr(verify_seeds.time, "sleep", lambda _seconds: None)

    assert verify_seeds.main() == 0

    captured = capsys.readouterr()
    assert json.loads(captured.out) == [offer]
    assert "cena niezweryfikowana; pominięto w JSON" in captured.err


def test_verification_errors_are_reported_with_nonzero_exit(monkeypatch, capsys):
    monkeypatch.setattr(verify_seeds, "STEAM_IDS", [1])
    monkeypatch.setattr(verify_seeds, "PAGES", [])

    def fail(_appid):
        raise TimeoutError("request timed out")

    monkeypatch.setattr(verify_seeds, "verify_steam", fail)
    monkeypatch.setattr(verify_seeds.time, "sleep", lambda _seconds: None)

    assert verify_seeds.main() == 1

    captured = capsys.readouterr()
    assert json.loads(captured.out) == []
    assert "[ERR ] 1 request timed out" in captured.err
