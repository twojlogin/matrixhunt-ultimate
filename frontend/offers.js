const {
  useState,
  useEffect,
  useCallback,
  useRef
} = React;
const NAV_L = {
  color: '#0f0',
  textDecoration: 'none',
  fontSize: '0.72em',
  letterSpacing: 1,
  border: '1px solid var(--border)',
  padding: '6px 12px'
};

// Jeden deszcz z tools/site.js (było wklejone w 6 plików).
window.MH.matrixRain();

/* T_ czyta tools/lang.js, żeby słownik żył w jednym miejscu. */
function T_(key, fallback) {
  try {
    if (window.mhLang && typeof window.mhLang.t === 'function') {
      var v = window.mhLang.t(key);
      if (v && v !== key) return v;
    }
  } catch (e) {/* lang.js not loaded yet */}
  return fallback;
}
function App() {
  const [offers, setOffers] = useState([]);
  const [stats, setStats] = useState({
    total: 0,
    sources: 0,
    lastUpdate: 'N/A'
  });
  const [sourceFilter, setSourceFilter] = useState('ALL');
  const [search, setSearch] = useState('');
  const [showFavs, setShowFavs] = useState(false);
  const [showFresh, setShowFresh] = useState(false);
  const [watchlist, setWatchlist] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem('mh_watch') || '[]');
    } catch {
      return [];
    }
  });
  const [watchOnly, setWatchOnly] = useState(false);
  const [watchInput, setWatchInput] = useState('');

  // Watchlist matching: all significant words of the entry must
  // appear in the title (order-free, typo-tolerant-ish).
  const watchMatch = useCallback(title => {
    const t = (title || '').toLowerCase();
    return watchlist.some(w => {
      const words = w.toLowerCase().split(/\s+/).filter(s => s.length > 2);
      return words.length > 0 && words.every(s => t.includes(s));
    });
  }, [watchlist]);
  const isFresh = useCallback(created => {
    if (!created) return false;
    return Date.now() - new Date(created).getTime() < 24 * 3600 * 1000;
  }, []);
  useEffect(() => {
    localStorage.setItem('mh_watch', JSON.stringify(watchlist));
  }, [watchlist]);

  // Notify once per session about fresh watchlist hits.
  const notifiedRef = useRef({});
  useEffect(() => {
    if (!('Notification' in window) || Notification.permission !== 'granted') return;
    if (!watchlist.length) return;
    offers.forEach(o => {
      if (!isFresh(o.created_at) || !watchMatch(o.title)) return;
      const key = o.id || o.title;
      if (notifiedRef.current[key]) return;
      notifiedRef.current[key] = true;
      try {
        new Notification('MatrixHunt: ' + o.title, {
          body: (o.source || '') + ' - free now!'
        });
      } catch {}
    });
  }, [offers, watchlist, watchMatch, isFresh]);
  const [nsfwMode, setNsfwMode] = useState(() => localStorage.getItem('mh_nsfw') === 'true');
  // Bramka wieku jak na dashboardzie: odblokowanie tylko przez modal 18+.
  const [showAgeGate, setShowAgeGate] = useState(false);
  const confirmAgeGate = useCallback(() => {
    setNsfwMode(true);
    try {
      localStorage.setItem('mh_nsfw', 'true');
    } catch {}
    setShowAgeGate(false);
  }, []);
  const [theme, setTheme] = useState(() => window.mhTheme ? window.mhTheme.get() : 'night');
  const [lang, setLang] = useState(() => window.mhLang ? window.mhLang.get() : 'en');
  // Strings come from tools/lang.js so the dictionary lives in one place.
  const T = new Proxy({}, {
    get: function (_, k) {
      return T_('dash.' + k, k);
    }
  });
  const [favorites, setFavorites] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem('mh_favs') || '[]');
    } catch {
      return [];
    }
  });
  const [toast, setToast] = useState(null);
  // MUSI stać przed każdym useCallback, który wymienia showToast
  // w deps — inaczej TDZ i cała strona pada na biało przy starcie.
  const showToast = useCallback(msg => {
    setToast(msg);
    setTimeout(() => setToast(null), 2500);
  }, []);
  const [loading, setLoading] = useState(false);
  const [proxyOn, setProxyOn] = useState(true);
  const [cveQ, setCveQ] = useState('');
  const [cveItems, setCveItems] = useState(null);
  const [vulnInfo, setVulnInfo] = useState(null);
  const [vulnChecking, setVulnChecking] = useState(false);
  const [dataError, setDataError] = useState(false);
  const searchRef = useRef(null);

  // The shared theme controller owns [data-theme]; this only mirrors it
  // so the React-side label stays in sync. It persists via mhTheme.set.
  useEffect(() => {
    const onChange = e => setTheme(e.detail.theme);
    const onLang = e => setLang(e.detail.lang);
    document.addEventListener('mh:themechange', onChange);
    document.addEventListener('mh:langchange', onLang);
    return () => {
      document.removeEventListener('mh:themechange', onChange);
      document.removeEventListener('mh:langchange', onLang);
    };
  }, []);
  useEffect(() => {
    localStorage.setItem('mh_favs', JSON.stringify(favorites));
  }, [favorites]);

  // Egress proof: YOUR ip vs the EXIT ip, MANUAL check only.
  // No background polling - every check is one user click, so we
  // never hammer third parties (no accidental DDoS, no bans).
  // Direct mode shows the same IP twice - expected, not a bug.
  const [net, setNet] = useState(null);
  const checkNet = useCallback(() => {
    setNet({
      checking: true
    });
    fetch('/api/netcheck', {
      cache: 'no-store'
    }).then(r => r.ok ? r.json() : null).then(d => {
      setNet(d || {
        error: true
      });
    }).catch(() => setNet({
      error: true
    }));
  }, []);
  useEffect(() => {
    fetch('/api/settings').then(r => r.ok ? r.json() : null).then(s => {
      if (s && typeof s.proxy_clean === 'boolean') setProxyOn(s.proxy_clean);
    }).catch(() => {});
  }, []);
  const toggleProxy = useCallback(async () => {
    const next = !proxyOn;
    try {
      const res = await fetch('/api/settings', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          key: 'proxy_clean',
          value: next
        })
      });
      if (!res.ok) throw new Error('rejected');
    } catch (e) {
      showToast('PROXY TOGGLE FAILED');
      return;
    }
    setProxyOn(next);
    document.dispatchEvent(new CustomEvent('mh:settingschange', {
      detail: {
        proxy_clean: next
      }
    }));
    showToast(next ? 'ANTYSYF PROXY: ON' : 'ANTYSYF PROXY: OFF (raw links)');
  }, [proxyOn, showToast]);

  // Manual vuln audit + CVE feed. Both fetch on click only.
  const runVulnCheck = useCallback(async () => {
    setVulnChecking(true);
    setVulnInfo(lang === 'pl' ? 'SPRAWDZAM…' : 'CHECKING…');
    try {
      const res = await fetch('/api/vulncheck', {
        method: 'POST'
      });
      const d = await res.json();
      if (d.total === 0) {
        setVulnInfo((lang === 'pl' ? 'CZYSTO' : 'CLEAN') + ` (${Object.keys(d.packages || {}).length} paczek, ${d.checked_at || '?'})`);
      } else {
        const names = Object.entries(d.vulns || {}).filter(([, v]) => v.length).map(([k, v]) => `${k}(${v.length})`).join(', ');
        setVulnInfo(`⚠ ${d.total} CVE: ${names}`);
      }
    } catch (e) {
      setVulnInfo(lang === 'pl' ? 'AUDYT NIEUDANY' : 'AUDIT FAILED');
    }
    setVulnChecking(false);
  }, [showToast, lang]);
  const searchCve = useCallback(async () => {
    if (!cveQ.trim()) return;
    try {
      const res = await fetch('/api/cvefeed?q=' + encodeURIComponent(cveQ.trim()) + '&limit=10');
      const d = await res.json();
      setCveItems(d.items || []);
      if (!(d.items || []).length) setVulnInfo(lang === 'pl' ? 'BRAK WYNIKÓW' : 'NO RESULTS');else setVulnInfo(null);
    } catch (e) {
      setVulnInfo(lang === 'pl' ? 'FEED NIEUDANY' : 'FEED FAILED');
    }
  }, [cveQ, lang]);
  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      // Treści 18+ schodzą z API tylko po odblokowaniu bramki wieku.
      const url = nsfwMode ? '/api/offers?nsfw=1' : '/api/offers';
      const [offersRes, statsRes] = await Promise.all([fetch(url), fetch('/api/stats')]);
      if (!offersRes.ok || !statsRes.ok) {
        throw new Error(`offers=${offersRes.status}, stats=${statsRes.status}`);
      }
      const [offersData, statsData] = await Promise.all([offersRes.json(), statsRes.json()]);
      const nextOffers = Array.isArray(offersData) ? offersData : offersData && offersData.offers;
      if (!Array.isArray(nextOffers) || !statsData || typeof statsData !== 'object' || Array.isArray(statsData)) {
        throw new Error('Invalid response from offers or stats API');
      }
      setOffers(nextOffers);
      setStats(statsData);
      setDataError(false);
      showToast('DATA SYNCHRONIZED');
    } catch (error) {
      console.error('Data sync failed:', error);
      setDataError(true);
      showToast(lang === 'pl' ? 'BŁĄD ŁADOWANIA DANYCH' : 'DATA LOAD FAILED');
    } finally {
      setLoading(false);
    }
  }, [showToast, nsfwMode, lang]);
  const triggerScrape = useCallback(async () => {
    setLoading(true);
    showToast('INITIATING SCAN...');
    try {
      const res = await fetch('/api/scrape', {
        method: 'POST'
      });
      if (res.ok) {
        showToast('SCAN COMPLETE');
        await fetchData();
      }
    } catch (e) {
      showToast('SCAN FAILED');
    }
    setLoading(false);
  }, [fetchData, showToast]);
  const exportJSON = useCallback(() => {
    const filtered = getFiltered();
    const blob = new Blob([JSON.stringify(filtered, null, 2)], {
      type: 'application/json'
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `matrixhunt-export-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
    showToast('EXPORTED ' + filtered.length + ' OFFERS');
  }, [showToast]);
  const requestNotif = useCallback(() => {
    if ('Notification' in window) {
      Notification.requestPermission().then(p => {
        showToast(p === 'granted' ? 'NOTIFICATIONS ENABLED' : 'NOTIFICATIONS BLOCKED');
      });
    } else {
      showToast('NOTIFICATIONS NOT SUPPORTED');
    }
  }, [showToast]);

  // Steam OpenID session (passwordless). Epic/GOG logins happen
  // through the viewer proxy into isolated per-site jars instead -
  // see the viewer privacy panel for shortcuts.
  const [steam, setSteam] = useState({
    logged_in: false
  });
  useEffect(() => {
    fetch('/api/auth/steam/me').then(r => r.ok ? r.json() : null).then(s => {
      if (s) setSteam(s);
    }).catch(() => {});
  }, []);
  const steamLogout = useCallback(async () => {
    await fetch('/api/auth/steam/logout', {
      method: 'POST'
    }).catch(() => {});
    setSteam({
      logged_in: false
    });
    showToast(lang === 'pl' ? 'WYLOGOWANO STEAM' : 'STEAM LOGGED OUT');
  }, [showToast, lang]);
  const toggleFav = useCallback(id => {
    setFavorites(prev => prev.includes(id) ? prev.filter(f => f !== id) : [...prev, id]);
  }, []);
  useEffect(() => {
    fetchData();
  }, [fetchData]);
  useEffect(() => {
    const handler = e => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
      if (e.key === 'r' || e.key === 'R') {
        e.preventDefault();
        fetchData();
      }
      if (e.key === '/') {
        e.preventDefault();
        searchRef.current?.focus();
      }
      if (e.key === 'f' || e.key === 'F') {
        e.preventDefault();
        setShowFavs(p => !p);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [fetchData]);

  // Service Worker
  useEffect(() => {
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/sw.js').catch(() => {});
    }
  }, []);
  function getFiltered() {
    let list = offers;
    if (!nsfwMode) list = list.filter(o => !o.is_adult);
    if (sourceFilter !== 'ALL') list = list.filter(o => o.source === sourceFilter || o.source_name === sourceFilter);
    if (showFavs) list = list.filter(o => favorites.includes(o.id || o.title));
    if (showFresh) {
      const day = Date.now() - 24 * 3600 * 1000;
      list = list.filter(o => o.created_at && new Date(o.created_at).getTime() > day);
    }
    if (search) {
      const q = search.toLowerCase();
      list = list.filter(o => (o.title || '').toLowerCase().includes(q) || (o.description || '').toLowerCase().includes(q));
    }
    if (watchOnly) list = list.filter(o => watchMatch(o.title));
    return list;
  }
  const filtered = getFiltered();
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("header", null, /*#__PURE__*/React.createElement("nav", {
    style: {
      display: 'flex',
      gap: 14,
      flexWrap: 'wrap',
      marginBottom: 14,
      paddingBottom: 10,
      borderBottom: '1px solid var(--border)'
    }
  }, /*#__PURE__*/React.createElement("a", {
    href: "/",
    style: NAV_L
  }, "START"), /*#__PURE__*/React.createElement("a", {
    href: "/offers",
    style: {
      ...NAV_L,
      borderColor: '#0f0'
    }
  }, "OFERTY"), /*#__PURE__*/React.createElement("a", {
    href: "/view",
    style: NAV_L
  }, "VIEW"), /*#__PURE__*/React.createElement("a", {
    href: "/db",
    style: NAV_L
  }, "DB"), /*#__PURE__*/React.createElement("a", {
    href: "/retro",
    style: NAV_L
  }, "RETRO"), /*#__PURE__*/React.createElement("a", {
    href: "/pad",
    style: NAV_L
  }, "PAD"), /*#__PURE__*/React.createElement("a", {
    href: "/wiki",
    style: NAV_L
  }, "WIKI"), /*#__PURE__*/React.createElement("a", {
    href: "/bookmarks",
    style: NAV_L
  }, "BOOKMARKS"), /*#__PURE__*/React.createElement("a", {
    href: "/flash",
    style: NAV_L
  }, "FLASH"), /*#__PURE__*/React.createElement("a", {
    href: "/uwagi",
    style: NAV_L
  }, "UWAGI")), /*#__PURE__*/React.createElement("h1", null, "MATRIXHUNT ULTIMATE"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: '0.7em',
      marginTop: 8,
      cursor: 'pointer',
      opacity: nsfwMode ? 1 : 0.4,
      letterSpacing: 2
    },
    onClick: () => {
      if (nsfwMode) {
        setNsfwMode(false);
        try {
          localStorage.setItem('mh_nsfw', 'false');
        } catch {}
      } else {
        setShowAgeGate(true);
      }
    },
    title: lang === 'pl' ? 'Treści 18+ (za bramką wieku)' : '18+ content (age-gated)'
  }, nsfwMode ? T.nsfw_on : T.nsfw_off), nsfwMode && /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: '0.6em',
      marginTop: 4,
      color: '#f00',
      opacity: 0.7,
      letterSpacing: 1
    }
  }, "NSFW content is optional, hidden by default, and not hosted by this software. Users are responsible for complying with local laws.")), /*#__PURE__*/React.createElement("div", {
    className: "stats-bar"
  }, /*#__PURE__*/React.createElement("span", null, T.offers, ": ", stats.total || offers.length), /*#__PURE__*/React.createElement("span", null, T.sources, ": ", typeof stats.sources === 'object' ? Object.keys(stats.sources).length : stats.sources || '—'), /*#__PURE__*/React.createElement("span", null, T.updated, ": ", stats.last_update || stats.lastUpdate || '—'), loading && /*#__PURE__*/React.createElement("span", {
    style: {
      color: '#ff0'
    }
  }, "SCANNING...")), /*#__PURE__*/React.createElement("div", {
    className: "controls"
  }, /*#__PURE__*/React.createElement("div", {
    className: "ctl-search"
  }, /*#__PURE__*/React.createElement("select", {
    value: sourceFilter,
    onChange: e => setSourceFilter(e.target.value)
  }, window.MH.SOURCES.map(s => /*#__PURE__*/React.createElement("option", {
    key: s,
    value: s
  }, s === 'ALL' ? T.all : s))), /*#__PURE__*/React.createElement("input", {
    ref: searchRef,
    type: "text",
    placeholder: T.search_ph,
    value: search,
    onChange: e => setSearch(e.target.value)
  }), /*#__PURE__*/React.createElement("button", {
    onClick: () => setShowFavs(p => !p),
    className: showFavs ? 'btn-fav-active' : ''
  }, showFavs ? T.favs_on : T.favs_off), /*#__PURE__*/React.createElement("button", {
    onClick: () => setShowFresh(p => !p),
    className: showFresh ? 'btn-fav-active' : '',
    title: lang === 'pl' ? 'Oferty z ostatnich 24h' : 'Offers from the last 24h'
  }, lang === 'pl' ? showFresh ? '🆕 ŚWIEŻE WŁ.' : '🆕 ŚWIEŻE' : showFresh ? '🆕 FRESH ON' : '🆕 FRESH'), /*#__PURE__*/React.createElement("button", {
    onClick: () => setWatchOnly(p => !p),
    className: watchOnly ? 'btn-fav-active' : '',
    title: lang === 'pl' ? 'Tylko z watchlisty' : 'Watchlist hits only'
  }, lang === 'pl' ? watchOnly ? '👁 WATCH WŁ.' : '👁 WATCH' : watchOnly ? '👁 WATCH ON' : '👁 WATCH'), /*#__PURE__*/React.createElement("input", {
    type: "text",
    placeholder: lang === 'pl' ? '+ DO WATCHLISTY… (Enter)' : '+ WATCHLIST… (Enter)',
    value: watchInput,
    onChange: e => setWatchInput(e.target.value),
    onKeyDown: e => {
      if (e.key === 'Enter' && watchInput.trim()) {
        if (!watchlist.includes(watchInput.trim())) {
          setWatchlist(w => [...w, watchInput.trim()]);
          showToast((lang === 'pl' ? 'WATCHLISTA: ' : 'WATCHING: ') + watchInput.trim());
        }
        setWatchInput('');
      }
    },
    style: {
      minWidth: '130px',
      flex: '0 1 150px'
    }
  })), /*#__PURE__*/React.createElement("div", {
    className: "ctl-group"
  }, /*#__PURE__*/React.createElement("span", {
    className: "ctl-label"
  }, lang === 'pl' ? 'WIDOK' : 'VIEW'), /*#__PURE__*/React.createElement("button", {
    onClick: () => window.mhTheme && window.mhTheme.cycle(),
    title: "Cycle theme: matrix / night / day"
  }, window.MH.themeLabel(theme)), /*#__PURE__*/React.createElement("button", {
    onClick: () => window.mhLang && window.mhLang.toggle(),
    title: "PL/EN"
  }, lang === 'pl' ? 'PL ●' : 'EN ○'), /*#__PURE__*/React.createElement("button", {
    onClick: toggleProxy,
    title: "Route external links through the antysyf cleaner (viewer) or open them raw"
  }, proxyOn ? T.proxy_on : T.proxy_off), /*#__PURE__*/React.createElement("button", {
    onClick: checkNet,
    title: lang === 'pl' ? 'Sprawdź IP wyjścia (ręcznie, 1 klik = 1 pomiar)' : 'Check exit IP (manual, 1 click = 1 probe)'
  }, !net ? lang === 'pl' ? 'IP: SPRAWDŹ' : 'IP: CHECK' : net.checking ? 'IP…' : net.error ? 'IP ✗' : net.egress && net.egress.ip ? `EXIT ${net.egress.ip}${net.egress.is_tor ? ' [Tor ✓]' : ''} (${net.via})` : 'IP ✗')), /*#__PURE__*/React.createElement("div", {
    className: "ctl-group"
  }, /*#__PURE__*/React.createElement("span", {
    className: "ctl-label"
  }, lang === 'pl' ? 'DANE' : 'DATA'), /*#__PURE__*/React.createElement("button", {
    onClick: triggerScrape
  }, T.refresh), /*#__PURE__*/React.createElement("button", {
    onClick: exportJSON
  }, T.export), /*#__PURE__*/React.createElement("button", {
    onClick: requestNotif
  }, T.notify)), /*#__PURE__*/React.createElement("div", {
    className: "ctl-group"
  }, /*#__PURE__*/React.createElement("span", {
    className: "ctl-label"
  }, lang === 'pl' ? 'KONTO' : 'ACCOUNT'), "                            ", steam.logged_in ? /*#__PURE__*/React.createElement("button", {
    onClick: steamLogout,
    title: lang === 'pl' ? 'Wyloguj konto Steam' : 'Sign out Steam account'
  }, "\uD83D\uDC64 ", steam.persona || steam.steamid, steam.games_count != null ? ` (${steam.games_count})` : '') : /*#__PURE__*/React.createElement("button", {
    onClick: () => {
      window.location.href = '/api/auth/steam/login';
    },
    title: lang === 'pl' ? 'Zaloguj bez hasła przez Steam OpenID' : 'Passwordless sign-in via Steam OpenID'
  }, "\uD83D\uDC64 STEAM LOGIN")), /*#__PURE__*/React.createElement("div", {
    className: "ctl-group"
  }, /*#__PURE__*/React.createElement("span", {
    className: "ctl-label"
  }, lang === 'pl' ? 'CVE' : 'SEC'), /*#__PURE__*/React.createElement("button", {
    onClick: runVulnCheck,
    title: lang === 'pl' ? 'Audyt zależności (OSV) - ręcznie' : 'Dependency audit (OSV) - manual'
  }, vulnChecking ? '…' : lang === 'pl' ? '🛡 SPRAWDŹ' : '🛡 AUDIT'), /*#__PURE__*/React.createElement("input", {
    type: "text",
    placeholder: lang === 'pl' ? 'CVE np. steam…' : 'CVE e.g. steam…',
    value: cveQ,
    onChange: e => setCveQ(e.target.value),
    onKeyDown: e => {
      if (e.key === 'Enter') searchCve();
    },
    style: {
      minWidth: '130px',
      flex: '0 1 150px'
    }
  }), /*#__PURE__*/React.createElement("button", {
    onClick: searchCve
  }, "\u2315"))), vulnInfo && /*#__PURE__*/React.createElement("div", {
    style: {
      border: '1px solid var(--border)',
      background: 'var(--card)',
      padding: '10px 14px',
      margin: '0 0 12px',
      fontSize: '0.8em'
    }
  }, vulnInfo), cveItems && cveItems.length > 0 && /*#__PURE__*/React.createElement("div", {
    style: {
      border: '1px solid var(--border)',
      background: 'var(--card)',
      padding: '10px 14px',
      margin: '0 0 12px',
      fontSize: '0.78em',
      maxHeight: '220px',
      overflowY: 'auto'
    }
  }, cveItems.map(c => /*#__PURE__*/React.createElement("div", {
    key: c.cve,
    style: {
      marginBottom: '6px'
    }
  }, /*#__PURE__*/React.createElement("b", null, c.cve), " [", c.vendor, " / ", c.product, "] ", c.name, c.ransomware !== 'Unknown' && c.ransomware ? /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--bad)'
    }
  }, " \u26A0 RANSOMWARE") : null))), watchlist.length > 0 && /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: '8px',
      flexWrap: 'wrap',
      alignItems: 'center',
      margin: '0 0 12px',
      fontSize: '0.78em'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      opacity: 0.6
    }
  }, "\uD83D\uDC41 ", lang === 'pl' ? 'WATCHLISTA' : 'WATCHLIST', ":"), watchlist.map(w => /*#__PURE__*/React.createElement("span", {
    key: w,
    style: {
      border: '1px solid var(--border)',
      background: 'var(--card)',
      padding: '4px 6px 4px 10px'
    }
  }, w, " ", /*#__PURE__*/React.createElement("button", {
    onClick: () => setWatchlist(list => list.filter(x => x !== w)),
    style: {
      padding: '2px 8px',
      marginLeft: '4px'
    },
    title: "\xD7"
  }, "\xD7")))), /*#__PURE__*/React.createElement("div", {
    className: "games-grid"
  }, filtered.length === 0 && /*#__PURE__*/React.createElement("div", {
    style: {
      gridColumn: '1/-1',
      textAlign: 'center',
      padding: '40px',
      opacity: 0.5
    }
  },   loading ? T.loading : dataError ? T.fetch_failed : T.no_offers), filtered.map((offer, i) => {
    const id = offer.id || offer.title || i;
    const isFav = favorites.includes(id);
    // Cena bierze sie wylacznie z price_claim, ktore ma
    // zawsze towarzyszace price_source. 'Free' znaczy tylko
    // wtedy, gdy sklep to potwierdzil przez API — inaczej
    // strona wymienila to jako darmowe, a to nie jest pomiar.
    const claim = offer.price_claim;
    const src = offer.price_source || '';
    const isFree = claim === 'Free' || claim === '0';
    const zApi = src.startsWith('api:');
    const zListy = src.startsWith('listing:');
    const bezCeny = !claim;
    // Defence in depth: the DB is filtered on ingest, but a legacy
    // row (or a future bug) with a javascript:/data: URL must never
    // reach an href - React throws on it and kills the whole page.
    const rawUrl = offer.url || offer.open_url || '#';
    const safeUrl = /^https?:\/\//i.test(rawUrl) ? rawUrl : '#';
    // Thumbnails follow the proxy toggle: stores flag datacenter
    // fetches as hostile, so a direct load is one click away.
    const hasImg = /^https?:\/\//i.test(offer.image_url || '');
    const imgSrc = hasImg ? proxyOn ? '/api/img?url=' + encodeURIComponent(offer.image_url) : offer.image_url : '';
    return /*#__PURE__*/React.createElement("div", {
      className: "game-card",
      key: id
    }, hasImg && /*#__PURE__*/React.createElement("img", {
      src: imgSrc,
      alt: "",
      referrerPolicy: "no-referrer",
      loading: "lazy",
      style: {
        width: '100%',
        height: '140px',
        objectFit: 'cover',
        border: '1px solid #0a0'
      },
      onError: e => {
        e.target.style.display = 'none';
      }
    }), /*#__PURE__*/React.createElement("h3", {
      style: {
        fontSize: '1.05em',
        textShadow: '0 0 6px rgba(0,255,0,0.5)'
      }
    }, offer.title || 'Unknown Game'), /*#__PURE__*/React.createElement("div", {
      className: "meta"
    }, /*#__PURE__*/React.createElement("span", {
      className: "badge"
    }, offer.source || offer.source_name || 'Unknown'), isFree && zApi && /*#__PURE__*/React.createElement("span", {
      className: "badge badge-free",
      title: lang === 'pl' ? 'cena potwierdzona przez sklep (API)' : 'price confirmed by the store (API)'
    }, "FREE \\u2713"), isFree && !zApi && /*#__PURE__*/React.createElement("span", {
      className: "badge",
      style: {
        color: '#0f0',
        borderColor: '#0a0',
        opacity: 0.6
      },
      title: lang === 'pl' ? 'źródło podaje jako darmowe; sklep nie był pytany' : 'source lists it as free; the store was not asked'
    }, "FREE ?"), !isFree && claim && zApi && /*#__PURE__*/React.createElement("span", {
      className: "badge badge-price",
      title: lang === 'pl' ? 'cena potwierdzona przez sklep (API)' : 'price confirmed by the store (API)'
    }, claim, " \\u2713"), !isFree && claim && !zApi && /*#__PURE__*/React.createElement("span", {
      className: "badge",
      style: {
        opacity: 0.6
      },
      title: lang === 'pl' ? 'źródło podaje taką cenę; sklep nie był pytany' : 'source states this price; the store was not asked'
    }, claim, " ?"), bezCeny && /*#__PURE__*/React.createElement("span", {
      className: "badge",
      style: {
        opacity: 0.4
      },
      title: lang === 'pl' ? 'brak informacji o cenie — nikt nie sprawdził' : 'no price information — nobody checked'
    }, lang === 'pl' ? 'cena: ?' : 'price: ?'), isFresh(offer.created_at) && /*#__PURE__*/React.createElement("span", {
      className: "badge",
      style: {
        color: 'var(--ok)',
        borderColor: 'var(--ok)'
      }
    }, "NEW"), watchMatch(offer.title) && /*#__PURE__*/React.createElement("span", {
      className: "badge",
      style: {
        color: 'var(--cyan)',
        borderColor: 'var(--cyan)'
      }
    }, "\uD83D\uDC41"), offer.original_price && offer.original_price !== offer.price && /*#__PURE__*/React.createElement("span", {
      className: "badge",
      style: {
        textDecoration: 'line-through',
        opacity: 0.5
      }
    }, offer.original_price), offer.requires_login && /*#__PURE__*/React.createElement("span", {
      className: "badge badge-login"
    }, "LOGIN REQ"), offer.has_adfly && /*#__PURE__*/React.createElement("span", {
      className: "badge badge-adfly"
    }, "ADFLY"), offer.has_captcha && /*#__PURE__*/React.createElement("span", {
      className: "badge badge-captcha"
    }, "CAPTCHA"), offer.source === 'DelistedSteam' && /*#__PURE__*/React.createElement("span", {
      className: "badge badge-adfly"
    }, "DELISTED"), offer.is_adult && /*#__PURE__*/React.createElement("span", {
      className: "badge badge-captcha"
    }, "18+")), offer.description && /*#__PURE__*/React.createElement("div", {
      className: "desc"
    }, offer.description), /*#__PURE__*/React.createElement("div", {
      className: "actions"
    }, /*#__PURE__*/React.createElement("a", {
      href: safeUrl,
      rel: "noopener noreferrer",
      className: "btn btn-access",
      title: "Open in the in-app viewer (cleaned)"
    }, "[ ACCESS ]"), /*#__PURE__*/React.createElement("button", {
      className: "btn-fav",
      onClick: () => toggleFav(id)
    }, isFav ? '★' : '☆')));
  })), /*#__PURE__*/React.createElement("div", {
    className: "shortcuts-hint"
  }, T.shortcuts), /*#__PURE__*/React.createElement("footer", null, /*#__PURE__*/React.createElement("a", {
    href: "/"
  }, "HOME"), /*#__PURE__*/React.createElement("a", {
    href: "/offers"
  }, "OFERTY"), /*#__PURE__*/React.createElement("a", {
    href: "/view"
  }, "VIEW"), /*#__PURE__*/React.createElement("a", {
    href: "/db"
  }, "DB"), /*#__PURE__*/React.createElement("a", {
    href: "/retro"
  }, "RETRO"), /*#__PURE__*/React.createElement("a", {
    href: "/pad"
  }, "PAD"), /*#__PURE__*/React.createElement("a", {
    href: "/wiki"
  }, "WIKI"), /*#__PURE__*/React.createElement("a", {
    href: "/bookmarks"
  }, "BOOKMARKS"), /*#__PURE__*/React.createElement("a", {
    href: "/flash"
  }, "FLASH"), /*#__PURE__*/React.createElement("a", {
    href: "/uwagi"
  }, "UWAGI"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: '0.7em',
      opacity: 0.4,
      marginTop: '10px'
    }
  }, "MATRIXHUNT ULTIMATE v2.0 // License: CC BY-NC-SA 4.0 // Author: Arkadiusz Slowik", /*#__PURE__*/React.createElement("br", null), "This software is FREE. If someone is selling it, they are scammers.")), toast && /*#__PURE__*/React.createElement("div", {
    className: "toast"
  }, toast), showAgeGate && /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'fixed',
      top: 0,
      left: 0,
      width: '100%',
      height: '100%',
      background: 'rgba(0,0,0,0.85)',
      zIndex: 200,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center'
    },
    onClick: () => setShowAgeGate(false)
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      border: '2px solid var(--green)',
      background: 'var(--card)',
      padding: '30px',
      maxWidth: '420px',
      textAlign: 'center'
    },
    onClick: e => e.stopPropagation()
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: '2em'
    }
  }, "\uD83D\uDD1E"), /*#__PURE__*/React.createElement("h3", {
    style: {
      letterSpacing: 3,
      margin: '10px 0'
    }
  }, lang === 'pl' ? 'TREŚCI 18+' : 'ADULT CONTENT'), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: '0.8em',
      opacity: 0.8,
      marginBottom: '20px'
    }
  }, lang === 'pl' ? 'Ta sekcja zawiera gry dla dorosłych. Potwierdź, że masz ukończone 18 lat.' : 'This section lists adult games. Confirm you are 18 or older.'), /*#__PURE__*/React.createElement("button", {
    onClick: confirmAgeGate,
    style: {
      marginRight: '10px'
    }
  }, lang === 'pl' ? 'MAM 18+ — POKAŻ' : 'I AM 18+ — SHOW'), /*#__PURE__*/React.createElement("button", {
    onClick: () => setShowAgeGate(false)
  }, lang === 'pl' ? 'WRÓĆ' : 'GO BACK'))));
}
const root = ReactDOM.createRoot(document.getElementById('app'));
root.render( /*#__PURE__*/React.createElement(App, null));