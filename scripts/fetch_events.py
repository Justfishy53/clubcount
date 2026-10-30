#!/usr/bin/env python3
"""Kogub klubide üritused ja kirjutab need faili events.json.

Allikad on failis sources.json (ics / json) ning käsitsi lisatud üritused
failis events_manual.json. Ainult Pythoni standardteek, lisapakette pole vaja.
"""
import hashlib
import json
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
TZ = ZoneInfo("Europe/Tallinn")
OUT = ROOT / "events.json"
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


def load_sources():
    if not SOURCES.exists():
        return [], 0
    cfg = json.loads(SOURCES.read_text(encoding="utf-8"))
    events, failures = [], 0
    for src in cfg.get("sources", []):
        if not src.get("enabled", True):
            continue
        try:
            text = http_get(src["url"])
            if src["type"] == "ics":
                got = parse_ics(text, src["club"], src["name"])
            elif src["type"] == "json":
                got = parse_json(text, src)
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
