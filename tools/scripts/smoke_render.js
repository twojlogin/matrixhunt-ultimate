/* Render-smoke obu frontendów: łapie błędy klasy "biała strona"
 * (np. TDZ w deps useCallback), bez przeglądarki.
 *
 * Uruchomienie:  node tools/smoke_render.js   (0 = oba renderują)
 * Hooke są stubami no-op, efekty nie odpalają się — leci sama ścieżka
 * renderu App(), czyli dokładnie to, co wywalało pusty ekran.
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.join(__dirname, "..");

const stubs = `
const __el = () => ({ style: {}, appendChild(){}, addEventListener(){},
  removeEventListener(){}, setAttribute(){}, getContext: () => null,
  querySelector: () => __el(), textContent: "", value: "", className: "" });
global.window = { addEventListener(){}, removeEventListener(){},
  innerWidth: 1280, innerHeight: 800, devicePixelRatio: 1,
  mhTheme: { get: () => "matrix" }, mhLang: { get: () => "en", t: (k) => k },
  MH: { SOURCES: ["ALL", "Reddit", "LowcyGier"],
        themeLabel: (t) => t, matrixRain: () => {} } };
global.document = { getElementById: () => __el(), createElement: () => __el(),
  addEventListener(){}, removeEventListener(){},
  documentElement: { setAttribute(){} } };
global.localStorage = { _s: {},
  getItem(k){ return this._s[k] ?? null; }, setItem(k,v){ this._s[k]=String(v); } };
global.navigator = { language: "pl-PL", userAgent: "node-smoke", hardwareConcurrency: 4 };
global.location = { search: "", href: "http://127.0.0.1:8000/view" };
global.fetch = () => Promise.resolve({ ok: true, json: async () => ({}) });
global.alert = () => {};
global.screen = { width: 1280, height: 800 };
global.React = { createElement: (...a) => a,
  useState: (i) => [typeof i === "function" ? i() : i, () => {}],
  useEffect: () => {}, useCallback: (f) => f, useRef: (v) => ({ current: v }) };
global.ReactDOM = { createRoot: () => ({ render: () => {} }) };
`;
eval(stubs);

let fail = 0;

// 1) /offers — gotowy offers.js
try {
  eval(fs.readFileSync(path.join(ROOT, "frontend", "offers.js"), "utf8") + ";App();");
  console.log("OFFERS-RENDER-OK");
} catch (e) {
  console.error("OFFERS-RENDER-FAIL:", e.message);
  fail = 1;
}

// 2) / — inline JSX z index.html przez zvendorowany Babel
try {
  const html = fs.readFileSync(path.join(ROOT, "frontend", "index.html"), "utf8");
  const m = html.match(/<script type="text\/babel">([\s\S]*?)<\/script>/);
  if (!m) throw new Error("brak bloku text/babel w index.html");
  const ctx = { window: {}, console, setTimeout, clearTimeout,
    document: { addEventListener() {} }, navigator: {} };
  ctx.self = ctx;
  ctx.globalThis = ctx;
  vm.createContext(ctx);
  vm.runInContext(
    fs.readFileSync(path.join(ROOT, "frontend", "vendor", "babel.min.js"), "utf8"), ctx);
  const js = ctx.Babel.transform(m[1], { presets: ["react"] }).code;
  eval(js + ";App();");
  console.log("INDEX-RENDER-OK");
} catch (e) {
  console.error("INDEX-RENDER-FAIL:", e.message);
  fail = 1;
}

// 3) /view — inline skrypt viewer.html na gołym ?search (ekran startowy)
try {
  const vhtml = fs.readFileSync(path.join(ROOT, "tools", "viewer.html"), "utf8");
  const m2 = vhtml.match(/<script>\n([\s\S]*?)\n\s*<\/script>/);
  if (!m2) throw new Error("brak bloku <script> w viewer.html");
  eval(stubs);
  global.location = { search: "", href: "http://127.0.0.1:8000/view" };
  eval(m2[1]);
  console.log("VIEWER-RENDER-OK");
} catch (e) {
  console.error("VIEWER-RENDER-FAIL:", e.message);
  fail = 1;
}
process.exit(fail);
