# Plan porządkowania katalogu `tools/`

## Analiza

Katalog `tools/` miesza trzy kategorie:

1. **Strony HTML serwowane przez Flask** (route'y w `backend/main.py`):
   `uwagi.html`, `retro.html`, `wiki.html`, `bookmarks.html`,
   `flash_player.html`, `muzeum.html`, `sprzet.html`, `viewer.html`,
   `db.html`.
2. **Skrypty diagnostyczne/build** używane w testach i README:
   `smoke_render.js`, `i18n_check.js`, `emulator-db.js`, `site.js`,
   `build_frontend.js`, `verify_seeds.py`.
3. **Mikronarzędzia i powłoka**:
   `api.js`, `lang.js`, `theme.css`, `theme.js`, `outbound.js`,
   `hardware-detect.js`, `scan_wyciekow.sh`, `cloudflared_setup.sh`.

Backend mountuje `/tools` jako `StaticFiles` i testy odwołują się do ścieżek
`tools/...` (np. `tools/smoke_render.js`, `tools/site.js`). Przeniesienie
plików bez aktualizacji tych referencji zepsułoby testy i trasę `/tools`.

## Proponowana struktura (bez zmiany zachowania)

```
tools/
  pages/        # HTML serwowane przez Flask (uwagi, retro, wiki, ...)
  scripts/      # JS/Python używane w testach i buildzie
  shell/        # .sh (scan_wyciekow, cloudflared_setup)
  assets/       # theme.css/js, lang.js, outbound.js, hardware-detect.js, api.js
```

## Plan wykonania (etapami, z testami po każdym)

1. **Etap 0 (bezpieczny):** usunąć `tools/__pycache__/` i inne `__pycache__`
   (już w `.gitignore`). Nie wpływa na kod.
2. **Etap 1:** zaktualizować `backend/main.py`:
   - `TOOLS_DIR` → odpowiedni podkatalog dla stron HTML albo pozostawić
     mount `/tools` wskazujący na `tools/pages`.
   - zaktualizować wszystkie `FileResponse(TOOLS_DIR / "...")`.
3. **Etap 2:** zaktualizować testy (`tests/test_niezalezne.py`) i README.md
   z nowymi ścieżkami (`tools/scripts/...`).
4. **Etap 3:** przenieść pliki `git mv`.
5. **Etap 4:** uruchomić `pytest` i `node tools/scripts/smoke_render.js`,
   sprawdzić czy `/tools/*` działa.
6. **Etap 5:** zaktualizować `.github/workflows` jeśli referencje.

## Uwagi

- Nie ruszać `backend/`, `frontend/`, `tests/` poza aktualizacją ścieżek.
- Zachować brak zależności chmurowych.
- Każdy etap powinien być osobnym commitem, żeby łatwo cofnąć.
- Zanim ruszysz pliki, uruchom testy na baseline (`pytest -q`).

## Status

Plan wykonany. Zmiany zatwierdzone i wypchnięte (commit 70fdfb4 i kolejne).
