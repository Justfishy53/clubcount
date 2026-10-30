#!/usr/bin/env python3
"""Kogub klubide üritused ja kirjutab need failidesse events.json ja events-auto.js.

Allikad on failis sources.json (ics / json) ning käsitsi lisatud üritused
failis events_manual.json. events-auto.js on sama nimekiri rakenduse kujul;
üritused, mis on juba failis events.js, jäävad sealt välja.
Ainult Pythoni standardteek, lisapakette pole vaja.
"""
import hashlib
import html
import json
import re
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
TZ = ZoneInfo("Europe/Tallinn")
OUT = ROOT / "events.json"
APP_OUT = ROOT / "events-auto.js"
APP_EVENTS = ROOT / "events.js"
APP_VENUES = ROOT / "venues.js"
SOURCES = ROOT / "sources.json"
MANUAL = ROOT / "events_manual.json"
UA = {"User-Agent": "clubcount-events-bot/1.0"}


def today():
    return datetime.now(TZ).date()


def http_get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def make_id(club, title, start):
    raw = f"{club}|{title}|{start}".lower().encode()
    return hashlib.sha1(raw).hexdigest()[:12]


def norm_start(value):
    """Teeb sisendi ISO-kujule (kohalik Eesti aeg) või kuupäevaks."""
    if value is None:
        return None
    s = str(value).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return s
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)
    return dt.astimezone(TZ).isoformat(timespec="minutes")


def event_date(start):
    return date.fromisoformat(start[:10])


# ---------- ICS ----------
def unfold(text):
    return re.sub(r"\r?\n[ \t]", "", text)


def ics_unescape(v):
    return (v.replace("\\n", "\n").replace("\\,", ",")
             .replace("\\;", ";").replace("\\\\", "\\"))


def parse_ics_dt(prop, value):
    value = value.strip()
    if re.fullmatch(r"\d{8}", value):
        return f"{value[:4]}-{value[4:6]}-{value[6:8]}"
    m = re.fullmatch(r"(\d{8})T(\d{6})(Z?)", value)
    if not m:
        return None
    d, t, z = m.groups()
    dt = datetime.strptime(d + t, "%Y%m%d%H%M%S")
    tzid = re.search(r"TZID=([^;:]+)", prop)
    if z:
        dt = dt.replace(tzinfo=timezone.utc)
    elif tzid:
        try:
            dt = dt.replace(tzinfo=ZoneInfo(tzid.group(1)))
        except Exception:
            dt = dt.replace(tzinfo=TZ)
    else:
        dt = dt.replace(tzinfo=TZ)
    return dt.astimezone(TZ).isoformat(timespec="minutes")


def parse_ics(text, club, source_name):
    events = []
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", unfold(text), re.S):
        fields = {}
        for line in block.strip().splitlines():
            if ":" not in line:
                continue
            prop, _, val = line.partition(":")
            fields[prop.split(";")[0].upper()] = (prop, val)
        if "SUMMARY" not in fields or "DTSTART" not in fields:
            continue
        start = parse_ics_dt(*fields["DTSTART"])
        if not start:
            continue
        title = ics_unescape(fields["SUMMARY"][1]).strip()
        events.append({
            "club": club,
            "title": title,
            "start": start,
            "location": ics_unescape(fields.get("LOCATION", ("", ""))[1]).strip(),
            "url": fields.get("URL", ("", ""))[1].strip(),
            "source": source_name,
        })
    return events


# ---------- JSON ----------
def dig(obj, path):
    for part in path.split("."):
        if isinstance(obj, list):
            obj = obj[int(part)]
        else:
            obj = obj.get(part) if isinstance(obj, dict) else None
        if obj is None:
            return None
    return obj


def parse_json(text, src):
    data = json.loads(text)
    items = dig(data, src["items_path"]) if src.get("items_path") else data
    m = {"title": "title", "start": "start", "url": "url", "location": "location"}
    m.update(src.get("map", {}))
    events = []
    for it in items or []:
        start = norm_start(dig(it, m["start"]))
        title = dig(it, m["title"])
        if not start or not title:
            continue
        events.append({
            "club": src["club"],
            "title": str(title).strip(),
            "start": start,
            "location": str(dig(it, m["location"]) or src.get("location", "")).strip(),
            "url": str(dig(it, m["url"]) or "").strip(),
            "source": src["name"],
        })
    return events


# ---------- klubi oma leht ----------
def parse_wp(src):
    """WordPressi ürituste loend; kuupäev tuleb ürituse lehelt või pealkirja lõpust (30.10)."""
    items = json.loads(http_get(f"{src['url']}?per_page={src.get('count', 30)}"))
    events = []
    for it in items:
        title = html.unescape(it["title"]["rendered"]).strip()
        day = None
        m = re.search(r"\b(\d{1,2})\.(\d{1,2})\s*$", title)
        try:
            if m:
                posted = date.fromisoformat(it["date"][:10])
                day = date(posted.year, int(m[2]), int(m[1]))
                if day < posted - timedelta(days=30):  # aastavahetuse üle avaldatud üritus
                    day = day.replace(year=posted.year + 1)
                if day < today():
                    continue
            time.sleep(0.5)
            page = http_get(it["link"])
            m = re.search(r">\s*(\d{2})/(\d{2})/(\d{4})\s*<", page)
            if m:
                day = date(int(m[3]), int(m[2]), int(m[1]))
        except ValueError:
            continue
        if not day:
            continue
        if src.get("title_strip"):
            title = re.sub(src["title_strip"], "", title, flags=re.I).strip()
        t = re.search(r">\s*(\d{2}:\d{2})\s*<", page)
        events.append({
            "club": src["club"],
            "title": title,
            "start": norm_start(f"{day}T{t[1]}" if t else str(day)),
            "location": "",
            "url": it["link"],
            "source": src["name"],
        })
    return events


def parse_helitehas(text, src):
    """Helitehase avalehe kava; st:"ara" on ära jäänud üritus."""
    events = []
    for line in text.splitlines():
        m = re.search(r'\{d:"[^"]*",iso:"([^"]+)".*?,t:"((?:[^"\\]|\\.)*)"', line)
        if not m or 'st:"ara"' in line:
            continue
        start = norm_start(m[1])
        if not start:
            continue
        u = re.search(r',u:"([^"]*)"', line)
        events.append({
            "club": src["club"],
            "title": html.unescape(m[2]).strip(),
            "start": start,
            "location": "",
            "url": u[1] if u else "",
            "source": src["name"],
        })
    return events


def load_sources():
    if not SOURCES.exists():
        return [], 0
    cfg = json.loads(SOURCES.read_text(encoding="utf-8"))
    events, failures = [], 0
    for src in cfg.get("sources", []):
        if not src.get("enabled", True):
            continue
        try:
            if src["type"] == "wp":
                got = parse_wp(src)
            elif src["type"] == "ics":
                got = parse_ics(http_get(src["url"]), src["club"], src["name"])
            elif src["type"] == "json":
                got = parse_json(http_get(src["url"]), src)
            elif src["type"] == "helitehas":
                got = parse_helitehas(http_get(src["url"]), src)
            else:
                raise ValueError(f"tundmatu tüüp: {src['type']}")
            print(f"[ok] {src['name']}: {len(got)} üritust")
            events += got
        except Exception as e:  # üks katkine allikas ei tohi kõike peatada
            failures += 1
            print(f"[viga] {src.get('name')}: {e}", file=sys.stderr)
    return events, failures


def load_manual():
    if not MANUAL.exists():
        return []
    items = json.loads(MANUAL.read_text(encoding="utf-8"))
    out = []
    for it in items:
        start = norm_start(it.get("start"))
        if not start or not it.get("title") or not it.get("club"):
            print(f"[hoiatus] jätsin vahele puuduliku käsitsi ürituse: {it}", file=sys.stderr)
            continue
        out.append({
            "club": it["club"],
            "title": it["title"],
            "start": start,
            "location": it.get("location", ""),
            "url": it.get("url", ""),
            "source": "käsitsi",
        })
    return out


def title_key(date_str, title):
    return date_str, re.sub(r"\W+", "", title.casefold())


def write_app_events(events):
    """Kirjutab events-auto.js kujul, mida index.html ja sw.js loevad."""
    names = {}
    if APP_VENUES.exists():
        text = APP_VENUES.read_text(encoding="utf-8")
        for vid, name in re.findall(r'"id":"([^"]+)","name":"([^"]+)"', text):
            names[name.casefold()] = vid
    listed = set()
    if APP_EVENTS.exists():
        text = APP_EVENTS.read_text(encoding="utf-8")
        for d, t, v in re.findall(r'"date":"([^"]+)","time":"[^"]*",(?:"end":"[^"]*",)?"title":"((?:[^"\\]|\\.)*)","venue":(?:"([^"]+)"|null)', text):
            listed.add(title_key(d, t))
            if v:  # sama õhtu samas kohas võib olla eri nimega kirjas
                listed.add((d, v))

    rows = []
    for e in events:
        day = e["start"][:10]
        venue = names.get(e["club"].casefold())
        if title_key(day, e["title"]) in listed or (day, venue) in listed:
            continue
        url = e.get("url", "")
        rows.append(json.dumps({
            "id": "a-" + e["id"],
            "date": day,
            "time": e["start"][11:16],
            "title": e["title"],
            "venue": venue,
            "place": e["club"],
            "lineup": [],
            "price": None,
            "url": url if re.match(r"https?://", url, re.I) else "",
            "src": e["source"],
        }, ensure_ascii=False, separators=(",", ":")))
    new_text = ("/* Automaatne fail: selle kirjutab scripts/fetch_events.py. Ära muuda käsitsi. */\n"
                "window.CC_EVENTS_AUTO=[\n" + ",\n".join(rows) + "\n];\n")
    if not APP_OUT.exists() or APP_OUT.read_text(encoding="utf-8") != new_text:
        APP_OUT.write_text(new_text, encoding="utf-8")
        print(f"Kirjutasin {len(rows)} üritust faili events-auto.js")


def main():
    fetched, failures = load_sources()
    manual = load_manual()
    all_events = fetched + manual

    # Kaitse: kui kõik välised allikad ebaõnnestusid, ära kustuta vana faili
    cfg_has_sources = SOURCES.exists() and any(
        s.get("enabled", True) for s in json.loads(SOURCES.read_text(encoding="utf-8")).get("sources", [])
    )
    if cfg_has_sources and not fetched and failures and OUT.exists():
        print("Kõik allikad ebaõnnestusid, jätan olemasoleva events.json alles.", file=sys.stderr)
        return 0

    t = today()
    horizon = t + timedelta(days=180)
    seen, result = set(), []
    for e in all_events:
        d = event_date(e["start"])
        if d < t or d > horizon:
            continue
        e["id"] = make_id(e["club"], e["title"], e["start"])
        if e["id"] in seen:
            continue
        seen.add(e["id"])
        result.append(e)

    # Tänased ja tulevased kuupäeva ja kellaaja järgi
    result.sort(key=lambda e: (e["start"][:10], e["start"][11:16] or "00:00", e["title"].lower()))
    write_app_events(result)

    payload = {
        "updated": datetime.now(TZ).isoformat(timespec="minutes"),
        "count": len(result),
        "events": result,
    }
    new_text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

    # Ära tee uuendatud-aja pärast tühja commitit
    if OUT.exists():
        old = json.loads(OUT.read_text(encoding="utf-8"))
        if old.get("events") == result:
            print("Midagi pole muutunud.")
            return 0
    OUT.write_text(new_text, encoding="utf-8")
    print(f"Kirjutasin {len(result)} üritust faili events.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
