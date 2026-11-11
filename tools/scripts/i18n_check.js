/* Smoke tłumaczeń PL/EN: przełącznik, placeholdery, strażnik dzieci,
 * nieznane klucze, pamięć wyboru. Uruchomienie: node tools/i18n_check.js
 */
const fs = require("fs");
const path = require("path");

function mkEl(attrs, text, ph, kids) {
  return {
    attrs: { ...attrs }, textContent: text, placeholder: ph || "",
    children: kids || [],
    getAttribute(k) { return this.attrs[k] ?? null; },
    setAttribute(k, v) {
      this.attrs[k] = String(v);
      if (k === "placeholder") this.placeholder = String(v);
    },
    hasAttribute(k) { return k in this.attrs; },
  };
}

function bootStore(browserLang, preset) {
  const elText = mkEl({ "data-i18n": "dash.offers" }, "OFFERS");
  const elPh = mkEl({ "data-i18n-ph": "dash.search_ph" }, "", "old");
  const elUnknown = mkEl({ "data-i18n": "dash.nie-ma-takiego" }, "X");
  const elKids = mkEl({ "data-i18n": "dash.offers" }, "Y", "", [{}]);
  const store = { _s: { ...(preset || {}) } };
  const doc = {
    documentElement: mkEl({}, ""),
    querySelectorAll(sel) {
      if (sel === "[data-i18n]") return [elText, elUnknown, elKids];
      if (sel === "[data-i18n-ph]") return [elPh];
      if (sel === "[data-mh-lang-toggle]") return [];
      return [];
    },
    querySelector() { return null; },
    getElementById() { return null; },
    createElement() {
      return { setAttribute() {}, addEventListener() {}, style: {}, id: "" };
    },
    addEventListener() {},
    readyState: "complete",
    body: { appendChild() {} },
    dispatchEvent() {},
  };
  global.document = doc;
  global.window = {};
  // Node 24 ma wbudowany getter-only navigator (locale systemu!) — zwykłe
  // przypisanie cicho nie działa, więc podmieniamy deskryptorem.
  Object.defineProperty(globalThis, "navigator",
    { value: { language: browserLang }, configurable: true, writable: true });
  global.localStorage = {
    getItem(k) { return store._s[k] ?? null; },
    setItem(k, v) { store._s[k] = String(v); },
  };
  global.CustomEvent = function () {};
  eval(fs.readFileSync(path.join(__dirname, "lang.js"), "utf8"));
  return { elText, elPh, elUnknown, elKids, store };
}

let fail = 0;
const ok = (cond, msg) => {
  if (!cond) {
    console.error("FAIL " + msg);
    fail = 1;
  }
};

// 1) start z przeglądarki PL, tekst + placeholder po polsku
let s = bootStore("pl-PL");
ok(window.mhLang.get() === "pl", "start-pl");
ok(window.mhLang.t("dash.offers") === "OFERTY", "t-pl");
// 2) toggle -> en flippuje wszystko
window.mhLang.toggle();
ok(window.mhLang.get() === "en", "toggle-en");
ok(s.elText.textContent === "OFFERS", "el-en");
ok(s.elPh.placeholder === "SEARCH GAMES... ( / )", "ph-en: " + s.elPh.placeholder);
// 3) nieznany klucz: t() oddaje klucz, elementu nie rusza
ok(window.mhLang.t("dash.nie-ma-takiego") === "dash.nie-ma-takiego", "unknown-passthrough");
ok(s.elUnknown.textContent === "X", "unknown-el-untouched");
// 4) element z dziećmi pomijany (strażnik innerHTML)
ok(s.elKids.textContent === "Y", "kids-skipped");
// 5) powrót + pamięć
window.mhLang.toggle();
ok(window.mhLang.get() === "pl" && s.store._s["mh_lang"] === "pl", "roundtrip-persist");
ok(s.elPh.placeholder === "SZUKAJ GIER... ( / )", "ph-pl");
// 6) śmieć w storage -> en (preset PRZED startem)
s = bootStore("en-US", { mh_lang: "xx" });
ok(window.mhLang.get() === "en", "garbage-stored-en");

if (!fail) console.log("I18N-OK");
process.exit(fail);
