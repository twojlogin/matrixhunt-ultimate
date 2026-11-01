"""Deterministyczny sanityzer tekstu + detektor prompt-injection.

Zero sieci, zero modelu. Uruchamiany PRZED zapisem albo pokazaniem niezaufanego
tekstu, żeby zdrapana strona nie przemyciła instrukcji (prompt injection),
tekstu ukrytego (zerowa szerokość / bidi / display:none) ani niewidzialnych
znaczników do czegokolwiek, co potem to czyta. NEUTRALIZUJE i FLAGUJE — nie
kasuje po cichu i sam niczym nie steruje.

Wzorce są celowo wąskie. Wolno przepuścić, niż fałszywie oskarżyć zwykły tekst:
tytuł gry "Ignore the Past" nie jest atakiem, dopóki nie ma czasownika+celu
("ignore ... previous ... instructions").
"""
import re
import unicodedata

# Niewidzialne znaki formatujące. Zerowa szerokość potrafi rozspójnić wzorzec
# ("ig<ZWSP>nore") albo ukryć dodatkową treść.
_INVISIBLE = ("\u200b", "\u200c", "\u200d", "\u2060", "\u180e",
              "\ufeff", "\u00ad")
# Znaki sterujące kierunkiem (atak trojan-source: tekst WYGLĄDA inaczej, niż jest).
_BIDI = ("\u202a", "\u202b", "\u202c", "\u202d", "\u202e",
         "\u2066", "\u2067", "\u2068", "\u2069", "\u200e", "\u200f")
# Unicode "tag block": niewidzialne kopie znaków ASCII (przemyt tekstu).
_TAGCH = "".join(chr(c) for c in range(0xE0000, 0xE0080))
_STRIP = "".join(_INVISIBLE) + "".join(_BIDI) + _TAGCH

_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_HIDDEN_STYLE = re.compile(
    r"(?:^|;)\s*(?:display\s*:\s*none|visibility\s*:\s*hidden)"
    r"\s*(?:!\s*important\s*)?(?:;|$)", re.I)

_INJECTION = (
    ("ignore-prev", re.compile(
        r"\b(?:ignore|disregard|forget|override)\b[^.\n]{0,40}"
        r"\b(?:previous|above|prior|earlier|all)\b[^.\n]{0,20}"
        r"\b(?:instruction|rule|prompt|context|message)s?\b", re.I)),
    ("new-instructions", re.compile(
        r"\b(?:new|updated|real)\s+(?:system\s+)?instructions?\b", re.I)),
    ("role-reassign", re.compile(
        r"\b(?:you are now|from now on|act as|pretend to be|roleplay as)\b", re.I)),
    ("role-marker", re.compile(
        r"(?:^|\n)\s*(?:system|assistant|developer)\s*[:>]", re.I)),
    ("chat-template", re.compile(
        r"<\|(?:im_start|im_end|system|assistant|user)\|>", re.I)),
    ("llama-inst", re.compile(r"\[\s*/?(?:inst|sys)\s*\]", re.I)),
    ("jailbreak", re.compile(
        r"\b(?:jailbreak|do anything now|dan mode|developer mode enabled)\b", re.I)),
    ("exfil-inst", re.compile(
        r"\b(?:send|post|upload|leak|exfiltrate|curl|wget)\b[^.\n]{0,40}"
        r"\b(?:token|key|secret|password|cookie|env|credential)s?\b", re.I)),
)


def _count(text, chars):
    return sum(text.count(c) for c in chars)


def sanitize_text(text):
    """Zwraca (czysty_tekst, findings).

    findings: lista {"detector", "pattern", ...}. Puste = nic nie znaleziono.
    """
    if not isinstance(text, str):
        return "", []
    findings = []
    n_inv = _count(text, _INVISIBLE)
    n_bidi = _count(text, _BIDI)
    n_tag = _count(text, _TAGCH)
    if n_inv:
        findings.append({"detector": "invisible", "pattern": "zero-width",
                         "count": n_inv})
    if n_bidi:
        findings.append({"detector": "bidi", "pattern": "trojan-source",
                         "count": n_bidi})
    if n_tag:
        findings.append({"detector": "unicode-tags", "pattern": "tag-block",
                         "count": n_tag})

    clean = text
    if n_inv or n_bidi or n_tag:
        clean = clean.translate({ord(c): None for c in _STRIP})
    clean = _CTRL_RE.sub("", clean)
    clean = unicodedata.normalize("NFC", clean)

    # Wykrywanie po neutralizacji: gdyby zerowa szerokość rozspójniała wzorzec,
    # gracz "ig<ZWSP>nore previous instructions" i tak tu wpadnie.
    for pid, rx in _INJECTION:
        m = rx.search(clean)
        if m:
            findings.append({"detector": "injection", "pattern": pid,
                             "match": m.group(0)[:200]})
    return clean, findings


def strip_hidden_html(html):
    """Usuwa ukryte węzły (script/style/noscript/display:none/hidden) z HTML.

    Zwraca (widoczny_tekst, findings). Używane, gdy sanityzujemy treść STRONY,
    nie pole z API — atakujący chowa instrukcje w węźle, którego człowiek nie
    widzi, a parser tak.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise RuntimeError("BeautifulSoup is required to inspect untrusted HTML") from exc
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    hidden = []
    for el in soup.find_all(True):
        st = el.get("style") or ""
        if (_HIDDEN_STYLE.search(st) or el.has_attr("hidden")
                or (el.get("aria-hidden") or "").strip().lower() == "true"):
            hidden.append(el.get_text(" ", strip=True)[:200])
            el.decompose()
    text = soup.get_text(" ", strip=True)
    clean, findings = sanitize_text(text)
    if hidden:
        findings.append({"detector": "hidden-html", "pattern": "display-none",
                         "count": len(hidden),
                         "match": " | ".join(h for h in hidden if h)[:500]})
    return clean, findings
