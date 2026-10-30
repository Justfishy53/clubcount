# Clubcount üritused

Iga päev uuendatav klubiürituste nimekiri. GitHub Actions käivitab skripti, see kirjutab `events.json`, leht `uritused.html` näitab tänased üritused esimesena ja siis kuupäeva järgi edasi.

## Failid

| Fail | Mis see on |
|---|---|
| `.github/workflows/update-events.yml` | Ajastatud töövoog kolm korda päevas (04:00, 10:00 ja 15:00 UTC) |
| `scripts/fetch_events.py` | Kogub üritused, sorteerib, kirjutab `events.json` |
| `sources.json` | Automaatsed allikad (iCal või JSON) |
| `events_manual.json` | Käsitsi lisatud üritused |
| `events.json` | Skripti väljund, mida leht loeb (ära muuda käsitsi) |
| `events-auto.js` | Sama nimekiri rakenduse jaoks, ilma `events.js`-is juba olevate üritusteta (ära muuda käsitsi) |
| `uritused.html` | Eraldi leht, mis näitab üritusi |

## Paigaldus

1. Loo GitHubis repo ja lae kõik need failid sinna.
2. Repo **Settings → Actions → General → Workflow permissions**: vali **Read and write permissions**.
3. (Valikuline) **Settings → Pages**: vali haru `main` ja juurkaust, siis leht on avalik aadressil `https://<kasutaja>.github.io/<repo>/`.
4. Proovi: **Actions → Uuenda üritused → Run workflow**.

## Üritusi lisamine

**Käsitsi:** lisa rida faili `events_manual.json` (`club`, `title`, `start`, soovi korral `location`, `url`). `start` on `2026-11-06T22:00` või ainult kuupäev `2026-11-06`. Eesti aeg. Kui `club` on täpselt sama mis koha nimi failis `venues.js` (nt `D3`), seotakse üritus rakenduses selle kohaga.

**Automaatselt:** lisa allikas faili `sources.json` ja sea `"enabled": true`.
- `wp`: klubi WordPressi ürituste loend (praegu Club Studio ja D3). Kuupäev ja kellaaeg tulevad ürituse lehelt.
- `gateme`: korraldaja GateMe leht eesti keeles (praegu D3).
- `helitehas`: Helitehase avalehe kava. Kui nad lehte muudavad, tuleb see osa skriptis üle vaadata.
- `ics`: klubi või piletisüsteemi iCal-link.
- `json`: JSON-voog. `items_path` näitab, kus nimekiri asub, `map` seob väljad (`title`, `start`, `url`, `location`).

Kasuta ainult allikaid, mille kasutustingimused kogumist lubavad (nt klubi enda avalik kalender või API). Facebooki ja Instagrami automaatne kogumine ei ole lubatud.

## Piletihinnad

`wp`-allikate puhul loeb skript ürituse lehelt piletiread (nt `Early - 7€ (SOLD OUT)` või `15€ | Tavapilet`). Hetkehind on esimene veel müügil olev tavapilet. Hind on nii täpne, kui klubi oma lehte uuendab.

## Käitumine

- Täna ja tulevikus toimuvad üritused jäävad alles, möödunud kustutatakse. Vaatepiirang on 180 päeva.
- Kui kõik allikad ebaõnnestuvad, jääb eelmine `events.json` alles.
- Kui midagi ei muutu, commitit ei tehta.
- Avalikus repos lülitab GitHub ajastatud töövood 60 päeva tegevusetuse järel välja. Siis käivita töövoog käsitsi uuesti.
