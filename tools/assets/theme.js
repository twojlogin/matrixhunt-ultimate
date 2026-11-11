/* MatrixHunt Ultimate - shared theme controller.
 *
 * Sets [data-theme] on <html>, persists the choice in localStorage, and mounts
 * a toggle button. Applied before first paint by an inline snippet on each
 * page (see applyStoredTheme) so there is no flash of the wrong palette.
 */
(function () {
    'use strict';

    var STORAGE_KEY = 'mh_theme';
    var THEMES = ['matrix', 'night', 'day'];
    var LABELS = { matrix: '◐ MATRIX', night: '● NIGHT', day: '○ DAY' };
    var DEFAULT_THEME = 'night';

    function isValid(theme) {
        return THEMES.indexOf(theme) !== -1;
    }

    function readStored() {
        try {
            var v = localStorage.getItem(STORAGE_KEY);
            return isValid(v) ? v : DEFAULT_THEME;
        } catch (e) {
            return DEFAULT_THEME;
        }
    }

    function apply(theme) {
        if (!isValid(theme)) theme = DEFAULT_THEME;
        document.documentElement.setAttribute('data-theme', theme);
        return theme;
    }

    /* Called from an inline <head> snippet to avoid a flash of wrong colours. */
    window.applyStoredTheme = function () {
        apply(readStored());
    };

    function current() {
        return document.documentElement.getAttribute('data-theme') || readStored();
    }

    function setTheme(theme) {
        // Use the value apply() settled on. It normalised the argument, so
        // mhTheme.set('neon') used to paint matrix, persist "neon" and write
        // the string "undefined" into the button, because LABELS['neon'] is
        // undefined and apply's return value was discarded.
        var applied = apply(theme);
        try {
            localStorage.setItem(STORAGE_KEY, applied);
        } catch (e) {
            /* private mode - the choice simply will not persist */
        }
        var btn = document.getElementById('mh-theme-toggle');
        if (btn) btn.textContent = LABELS[applied];
        document.dispatchEvent(new CustomEvent('mh:themechange', { detail: { theme: applied } }));
    }

    function cycle() {
        var order = THEMES;
        var next = order[(order.indexOf(current()) + 1) % order.length];
        setTheme(next);
    }

    function mount() {
        if (document.getElementById('mh-theme-toggle')) return;
        // Opt out where the page already provides its own control, so a
        // dashboard with a theme button in its toolbar does not end up with a
        // second floating one from this module. Any of these markers is enough.
        if (document.documentElement.hasAttribute('data-mh-no-float')) return;
        if (document.querySelector('[data-mh-theme-toggle]')) return;
        var btn = document.createElement('button');
        btn.id = 'mh-theme-toggle';
        btn.type = 'button';
        btn.setAttribute('data-mh-theme-toggle', '');
        btn.textContent = LABELS[current()];
        btn.title = 'Cycle theme: matrix / night / day';
        btn.setAttribute('aria-label', 'Change colour theme');
        btn.addEventListener('click', cycle);
        document.body.appendChild(btn);
    }

    /* The matrix rain is hidden with display:none on the plain palettes, but
       the animation loops keep running and burn CPU. Pages guard their draw
       loops with this predicate. */
    function isMatrix() {
        return current() === 'matrix';
    }

    window.mhTheme = {
        set: setTheme,
        get: current,
        cycle: cycle,
        isMatrix: isMatrix,
        themes: THEMES.slice()
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', mount);
    } else {
        mount();
    }
})();
