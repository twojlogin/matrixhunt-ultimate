/*
Buduje frontend/offers.js z offers.jsx.
Kompilacja JSX w przeglądarce kosztowała 749 ms i 2,93 MB na każdym wejściu
(zmierzone: boot babel.min.js 287 ms + kompilacja 462 ms). Robimy to raz,
przy budowaniu, i dokladamy 28 KB zwyklego JS.
*/
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const DIR = path.join(__dirname, '..', 'frontend');
const SRC = path.join(DIR, 'offers.jsx');
const OUT = path.join(DIR, 'offers.js');

const ctx = { window: {}, console, setTimeout, clearTimeout, document: { addEventListener(){} }, navigator: {} };
ctx.self = ctx; ctx.globalThis = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(DIR, 'vendor', 'babel.min.js'), 'utf8'), ctx);

const zrodlo = fs.readFileSync(SRC, 'utf8');
let wynik;
try {
  wynik = ctx.Babel.transform(zrodlo, { presets: ['react'] }).code;
} catch (e) {
  console.error('Blad kompilacji:', e.message);
  process.exit(1);
}
fs.writeFileSync(OUT, wynik, 'utf8');
const kb = (fs.statSync(OUT).size / 1024).toFixed(1);
const skad = (fs.statSync(SRC).size / 1024).toFixed(1);
console.log(`offers.js  ${kb} KB  (z ${skad} KB JSX)`);
