/* MatrixHunt Ultimate - outbound link router.
 *
 * Every click on a cross-origin http(s) link opens inside the in-app viewer
 * (/view?url=…) instead of a raw tab, so untrusted game sites always pass
 * the antysyf cleaner first. Same-window, no new tabs.
 *
 * Opt out per link with data-direct (downloads, magnet:, …). Links already
 * inside the viewer break out to the top window instead of nesting frames.
 */
(function () {
    'use strict';

    function targetWindow() {
        try {
            return (window.top && window.top !== window.self) ? window.top : window;
        } catch (e) {
            return window;
        }
    }

    function isExternal(href) {
        if (!href || !/^https?:\/\//i.test(href)) return false;
        try {
            return new URL(href, location.href).origin !== location.origin;
        } catch (e) {
            return false;
        }
    }

    /* The cleaner is a privacy control, so it fails CLOSED: until we know
     * the real setting we do not rewrite links. The old code started at
     * proxyOn = true and only downgraded when the fetch resolved, so any
     * click before the response - and every click at all if the request
     * failed - got forced through /view. With the proxy explicitly OFF that
     * is the opposite of what the user asked for. */
    var proxyOn = null;
    try {
        fetch('/api/settings', { cache: 'no-store' }).then(function (r) {
            return r.ok ? r.json() : null;
        }).then(function (s) {
            if (s && typeof s.proxy_clean === 'boolean') proxyOn = s.proxy_clean;
        }).catch(function () { proxyOn = null; });
        document.addEventListener('mh:settingschange', function (e) {
            if (e.detail && typeof e.detail.proxy_clean === 'boolean') {
                proxyOn = e.detail.proxy_clean;
            }
        });
    } catch (e) {}

    document.addEventListener('click', function (ev) {
        // Let modified clicks (new tab on purpose) and opt-outs through.
        if (ev.defaultPrevented || ev.button !== 0 || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) return;
        if (proxyOn !== true) return;
        var a = ev.target && ev.target.closest ? ev.target.closest('a[href]') : null;
        if (!a || a.hasAttribute('data-direct') || a.hasAttribute('download')) return;
        // Everything cross-origin goes through the viewer, even links marked
        // target="_blank": same window, cleaned content. (The viewer's own
        // "OPEN ORIGINAL" carries data-direct so it really opens raw.)
        var href = a.getAttribute('href');
        if (!isExternal(href)) return;
        ev.preventDefault();
        targetWindow().location.href = '/view?url=' + encodeURIComponent(href);
    }, true);

    window.mhOutbound = { isExternal: isExternal };
})();
