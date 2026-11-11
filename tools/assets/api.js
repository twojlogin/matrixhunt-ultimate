/* MatrixHunt Ultimate - authenticated fetch wrapper.
 *
 * State-changing /api/* calls need the per-boot X-MH-Token (DNS-rebinding /
 * CSRF guard). This wrapper fetches it once from same-origin
 * /api/client-config and auto-attaches it to same-origin non-GET /api/*
 * requests. GETs and foreign URLs pass through untouched.
 */
(function () {
    'use strict';

    var tokenPromise = null;

    function getToken() {
        if (window.mhToken) return Promise.resolve(window.mhToken);
        if (!tokenPromise) {
            tokenPromise = fetch('/api/client-config', { cache: 'no-store' })
                .then(function (r) { return r.ok ? r.json() : null; })
                .then(function (d) {
                    if (d && d.token) {
                        window.mhToken = d.token;
                        return d.token;
                    }
                    return null;
                })
                .catch(function () { return null; });
        }
        return tokenPromise;
    }

    function needsToken(url, method) {
        if (method === 'GET' || method === 'HEAD' || method === 'OPTIONS') return false;
        try {
            var u = new URL(url, location.href);
            return u.origin === location.origin && u.pathname.indexOf('/api/') === 0;
        } catch (e) {
            return false;
        }
    }

    function withToken(headers, tok) {
        /* Never mutate the caller's container: pushing into a reused
         * options object appended the token twice, which serialised as
         * "TOK, TOK" and made the server's equality check fail with 403. */
        try {
            var h = new Headers(headers || {});
            h.set('X-MH-Token', tok);
            return h;
        } catch (e) {
            var plain = {};
            if (headers && typeof headers === 'object' && !Array.isArray(headers)) {
                Object.keys(headers).forEach(function (k) { plain[k] = headers[k]; });
            }
            plain['X-MH-Token'] = tok;
            return plain;
        }
    }

    if (!window.__mhFetchWrapped && window.fetch) {
        window.__mhFetchWrapped = true;
        var origFetch = window.fetch.bind(window);
        window.fetch = function (url, opts) {
            /* A Request carries its own method/headers, so reading opts
             * alone reported GET and sent it unauthenticated (403). */
            if (typeof Request !== 'undefined' && url instanceof Request) {
                var rq = url;
                if (!needsToken(rq.url, rq.method) || rq.headers.has('X-MH-Token')) {
                    return origFetch(rq);
                }
                return getToken().then(function (tok) {
                    if (!tok) return origFetch(rq);
                    var h = new Headers(rq.headers);
                    h.set('X-MH-Token', tok);
                    return origFetch(new Request(rq, { headers: h }));
                });
            }
            opts = opts || {};
            var method = (opts.method || 'GET').toUpperCase();
            var target = typeof url === 'string' ? url : (url && url.url) || '';
            if (!needsToken(target, method)) return origFetch(url, opts);
            return getToken().then(function (tok) {
                var next = opts;
                if (tok) next = Object.assign({}, opts, { headers: withToken(opts.headers, tok) });
                return origFetch(url, next);
            });
        };
    }

    window.mhApiReady = getToken;
})();
