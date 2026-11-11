/* MatrixHunt Ultimate - language controller (EN/PL).
 *
 * Static pages mark translatable chrome with data-i18n="key" (textContent)
 * or data-i18n-ph="key" (placeholder). Game data itself is never translated.
 * Choice persists in localStorage as mh_lang; first visit follows the browser.
 */
(function () {
    'use strict';

    var STORAGE_KEY = 'mh_lang';

    var STR = {
        en: {
            'nav.dashboard': 'DASHBOARD',
            'nav.retro': 'RETRO',
            'nav.pad': 'PAD TEST',
            'nav.wiki': 'WIKI',
            'nav.bookmarks': 'BOOKMARKS',
            'nav.flash': 'FLASH PLAYER',
            'nav.home': 'MATRIXHUNT',

            'pad.gamepad': 'GAMEPAD',
            'pad.microphone': 'MICROPHONE',
            'pad.audio': 'AUDIO',
            'pad.keyboard': 'KEYBOARD',
            'pad.mouse': 'MOUSE',
            'pad.display': 'DISPLAY',
            'pad.system': 'SYSTEM',
            'pad.drivers': 'DRIVERS',

            'retro.emulators': 'EMULATORS',
            'retro.roms': 'ROM SOURCES',
            'retro.vault': 'ARCHIVE.VAULT',
            'retro.delisted': 'DELISTED STEAM',
            'retro.flash': 'FLASH GAMES',
            'retro.hash': 'HASH VERIFIER',
            'retro.cyie': 'CAN YOU EMULATE IT?',
            'retro.scan': 'SCAN MY HARDWARE',
            'retro.scanning': 'SCANNING...',
            'retro.rescan': 'RESCAN',
            'retro.export': 'EXPORT PROFILE',
            'retro.copy': 'COPY TO CLIPBOARD',
            'retro.verify': 'VERIFY HASH',
            'retro.openflash': 'OPEN FLASH PLAYER »',

            'dash.offers': 'OFFERS',
            'dash.sources': 'SOURCES',
            'dash.updated': 'UPDATED',
            'dash.search_ph': 'SEARCH GAMES... ( / )',
            'dash.favs_on': '★ FAVS ON',
            'dash.favs_off': '☆ FAVS OFF',
            'dash.refresh': '⟳ REFRESH (R)',
            'dash.export': '⬇ EXPORT',
            'dash.notify': '🔔 NOTIFY',
            'dash.proxy_on': '🛡 PROXY ON',
            'dash.proxy_off': '○ PROXY OFF',
            'dash.no_offers': 'NO OFFERS FOUND',
            'dash.loading': 'LOADING DATA...',
            'dash.fetch_failed': 'COULD NOT LOAD OFFERS',
            'dash.nsfw_on': '[ STEALTH_NSFW: ACTIVE ]',
            'dash.nsfw_off': '[ PROMPT: ACTIVATE Stealth_NSFW ]',
            'dash.shortcuts': '[R] Refresh   [/] Search   [F] Toggle Favorites',
            'dash.all': 'ALL',

            'viewer.internal': 'INTERNAL',
            'viewer.cleaned': 'CLEANED',
            'viewer.antysyf': 'ANTYSYF ON',
            'viewer.original': 'OPEN ORIGINAL ↗',
            'viewer.nopage': 'NO PAGE: use /view?page=/wiki or /view?url=https://…',
            'viewer.start': 'VIEWER',
            'viewer.paste': 'PASTE A STORE URL',

            'db.sub': 'Read-only view of the app database. No SQLite tools needed. Writes are impossible.',
            'db.search_ph': 'SEARCH ALL COLUMNS... (Enter)',
            'db.search': 'SEARCH',
            'db.prev': '← PREV',
            'db.next': 'NEXT →'
        },
        pl: {
            'nav.dashboard': 'PANEL',
            'nav.retro': 'RETRO',
            'nav.pad': 'TEST PADA',
            'nav.wiki': 'WIKI',
            'nav.bookmarks': 'ZAKŁADKI',
            'nav.flash': 'FLASH PLAYER',
            'nav.home': 'MATRIXHUNT',

            'pad.gamepad': 'GAMEPAD',
            'pad.microphone': 'MIKROFON',
            'pad.audio': 'DŹWIĘK',
            'pad.keyboard': 'KLAWIATURA',
            'pad.mouse': 'MYSZ',
            'pad.display': 'EKRAN',
            'pad.system': 'SYSTEM',
            'pad.drivers': 'STEROWNIKI',

            'retro.emulators': 'EMULATORY',
            'retro.roms': 'ŹRÓDŁA ROMÓW',
            'retro.vault': 'ARCHIWUM.VAULT',
            'retro.delisted': 'WYCOFANE ZE STEAM',
            'retro.flash': 'GRY FLASH',
            'retro.hash': 'WERYFIKATOR HASHY',
            'retro.cyie': 'CZY UDA MI SIĘ EMULACJA?',
            'retro.scan': 'SKANUJ MÓJ SPRZĘT',
            'retro.scanning': 'SKANOWANIE...',
            'retro.rescan': 'SKANUJ PONOWNIE',
            'retro.export': 'EKSPORTUJ PROFIL',
            'retro.copy': 'KOPIUJ DO SCHOWKA',
            'retro.verify': 'WERYFIKUJ HASH',
            'retro.openflash': 'OTWÓRZ FLASH PLAYER »',

            'dash.offers': 'OFERTY',
            'dash.sources': 'ŹRÓDŁA',
            'dash.updated': 'AKTUALIZACJA',
            'dash.search_ph': 'SZUKAJ GIER... ( / )',
            'dash.favs_on': '★ ULUBIONE WŁ.',
            'dash.favs_off': '☆ ULUBIONE WYŁ.',
            'dash.refresh': '⟳ ODŚWIEŻ (R)',
            'dash.export': '⬇ EKSPORT',
            'dash.notify': '🔔 POWIADOMIENIA',
            'dash.proxy_on': '🛡 PROXY WŁ.',
            'dash.proxy_off': '○ PROXY WYŁ.',
            'dash.no_offers': 'BRAK OFERT',
            'dash.loading': 'ŁADOWANIE DANYCH...',
            'dash.fetch_failed': 'NIE UDAŁO SIĘ POBRAĆ OFERT',
            'dash.nsfw_on': '[ STEALTH_NSFW: AKTYWNE ]',
            'dash.nsfw_off': '[ PROMPT: WŁĄCZ Stealth_NSFW ]',
            'dash.shortcuts': '[R] Odśwież   [/] Szukaj   [F] Ulubione',
            'dash.all': 'WSZYSTKIE',

            'viewer.internal': 'WEWNĘTRZNA',
            'viewer.cleaned': 'OCZYSZCZONA',
            'viewer.antysyf': 'ANTYSYF WŁ.',
            'viewer.original': 'OTWÓRZ ORYGINAŁ ↗',
            'viewer.nopage': 'BRAK STRONY: użyj /view?page=/wiki lub /view?url=https://…',
            'viewer.start': 'PRZEGLĄDARKA',
            'viewer.paste': 'WKLEJ ADRES SKLEPU',

            'db.sub': 'Podgląd bazy aplikacji tylko do odczytu. Bez narzędzi SQLite. Zapis niemożliwy.',
            'db.search_ph': 'SZUKAJ WE WSZYSTKICH KOLUMNACH... (Enter)',
            'db.search': 'SZUKAJ',
            'db.prev': '← WSTECZ',
            'db.next': 'DALEJ →'
        }
    };

    function valid(lang) {
        return lang === 'pl' ? 'pl' : 'en';
    }

    function readStored() {
        try {
            var v = localStorage.getItem(STORAGE_KEY);
            if (v === 'pl' || v === 'en') return v;
        } catch (e) {}
        try {
            var nav = (navigator.language || 'en').toLowerCase();
            return nav.indexOf('pl') === 0 ? 'pl' : 'en';
        } catch (e) {
            return 'en';
        }
    }

    function current() {
        return valid(document.documentElement.getAttribute('data-lang') || readStored());
    }

    function apply(lang) {
        lang = valid(lang);
        document.documentElement.setAttribute('data-lang', lang);
        var dict = STR[lang];
        document.querySelectorAll('[data-i18n]').forEach(function (el) {
            var v = dict[el.getAttribute('data-i18n')];
            if (typeof v !== 'string') return;
            // textContent replaces the whole subtree, so the first
            // <span data-i18n="nav.home">MATRIX<b>HUNT</b></span> would
            // silently lose its <b>. Opt in per element with data-i18n-html,
            // and only for dictionary values we control (no page content).
            if (el.hasAttribute('data-i18n-html')) {
                el.innerHTML = v;
            } else if (el.children.length === 0) {
                el.textContent = v;
            }
        });
        document.querySelectorAll('[data-i18n-ph]').forEach(function (el) {
            var v = dict[el.getAttribute('data-i18n-ph')];
            if (typeof v === 'string') el.setAttribute('placeholder', v);
        });
        var btn = document.getElementById('mh-lang-toggle');
        if (btn) btn.textContent = lang === 'pl' ? 'PL ●' : 'EN ○';
        return lang;
    }

    window.applyStoredLang = function () {
        apply(readStored());
    };

    function setLang(lang) {
        lang = apply(lang);
        try {
            localStorage.setItem(STORAGE_KEY, lang);
        } catch (e) {}
        document.dispatchEvent(new CustomEvent('mh:langchange', { detail: { lang: lang } }));
    }

    function toggle() {
        setLang(current() === 'pl' ? 'en' : 'pl');
    }

    window.mhLang = {
        set: setLang,
        get: current,
        toggle: toggle,
        t: function (key) { return STR[current()][key] || key; }
    };

    function mount() {
        if (document.getElementById('mh-lang-toggle')) return;
        // Same opt-out as the theme controller: a page that ships its own
        // language control was getting a second floating button on top.
        if (document.documentElement.hasAttribute('data-mh-no-float')) return;
        if (document.querySelector('[data-mh-lang-toggle]')) return;
        var btn = document.createElement('button');
        btn.id = 'mh-lang-toggle';
        btn.type = 'button';
        btn.setAttribute('data-mh-lang-toggle', '');
        btn.title = 'Przełącz język / Switch language (PL/EN)';
        btn.setAttribute('aria-label', 'Change language');
        btn.addEventListener('click', toggle);
        // Next to the theme toggle: same look, stacked below it.
        btn.style.cssText = 'position:fixed;top:52px;right:12px;z-index:9998;' +
            "font-family:'Courier New',monospace;font-size:0.72em;letter-spacing:0.08em;" +
            'padding:8px 14px;cursor:pointer;background:var(--card);color:var(--text);' +
            'border:1px solid var(--border);border-radius:3px;box-shadow:var(--shadow);';
        document.body.appendChild(btn);
        apply(current());
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', mount);
    } else {
        mount();
    }
})();
