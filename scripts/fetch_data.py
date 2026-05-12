#!/usr/bin/env python3
"""
Daily news + data fetcher for the Hantavirus Tracker.

What this script does automatically every day
─────────────────────────────────────────────
1. Fetches the ECDC Andes hantavirus surveillance page (updated daily at 14:00 CET).
2. Parses case counts  →  updates sankey, snapshot, outbreaks table.
3. Parses "Latest updates" section  →  adds new timeline entries (deduplication by date).
4. Fetches the WHO Emergency Event page  →  cross-checks counts, adds WHO update entries.
5. Writes a data_fetch_log entry for traceability.
6. Saves changed JSON files (build_tracker.py is then run separately to rebuild HTML).

Run manually:
    python3 scripts/fetch_data.py

Run via GitHub Actions: see .github/workflows/daily_data_fetch.yml

What it does NOT touch
───────────────────────
• Individual outcome rows (Fatal/ICU/Transferred) — require per-patient detail
  not published by ECDC in machine-readable form.
• Any timeline entry already present for a given date.
• Any field that was unparseable (script exits safely without corrupting JSON).
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT        = Path(__file__).resolve().parents[1]
CRUISE_PATH = ROOT / "data" / "cruise_outbreak_2026.json"
OB_PATH     = ROOT / "data" / "outbreaks.json"

ECDC_SURVEILLANCE = (
    "https://www.ecdc.europa.eu/en/infectious-disease-topics/"
    "hantavirus-infection/surveillance-and-updates/andes-hantavirus-outbreak"
)
WHO_EVENT = "https://www.who.int/emergencies/emergency-events/item/2026-e000227"

# ── month maps ────────────────────────────────────────────────────────────────

_MONTH_NUM = {
    "Jan": 1,  "Feb": 2,  "Mar": 3,  "Apr": 4,
    "May": 5,  "Jun": 6,  "Jul": 7,  "Aug": 8,
    "Sep": 9,  "Oct": 10, "Nov": 11, "Dec": 12,
}
_MONTH_ZH = {
    "Jan": "1月",  "Feb": "2月",  "Mar": "3月",  "Apr": "4月",
    "May": "5月",  "Jun": "6月",  "Jul": "7月",  "Aug": "8月",
    "Sep": "9月",  "Oct": "10月", "Nov": "11月", "Dec": "12月",
}
_DOC_TYPE_ZH = {
    "Press release":        "新闻稿",
    "News":                 "消息",
    "Assessment":           "评估报告",
    "Guidance":             "指南",
    "Rapid scientific advice": "快速科学建议",
}

# ── network helpers ───────────────────────────────────────────────────────────

def _fetch(url: str, timeout: int = 20) -> str:
    """Return page HTML, or '' on any network error."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 HantavirusTrackerBot/1.0 (public-health)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as exc:
        print(f"[fetch_data] WARNING: could not fetch {url}: {exc}", file=sys.stderr)
        return ""


def _strip_tags(html: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"[ \t]+", " ", text)
    return text


# ── date helpers ──────────────────────────────────────────────────────────────

_DATE_RE = re.compile(
    r"\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(20\d{2})\b",
    re.IGNORECASE,
)


def _to_iso(date_str: str) -> str:
    """'11 May 2026'  →  '2026-05-11'  (for sorting/dedup)."""
    m = _DATE_RE.search(date_str)
    if not m:
        return date_str
    day, mon, year = int(m.group(1)), m.group(2).capitalize(), int(m.group(3))
    return f"{year:04d}-{_MONTH_NUM.get(mon, 0):02d}-{day:02d}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _today_display() -> str:
    """'11 May 2026' (UTC today)."""
    return datetime.now(timezone.utc).strftime("%-d %b %Y")


def _today_display_zh() -> str:
    """'2026年5月11日' (UTC today)."""
    d = datetime.now(timezone.utc)
    return f"{d.year}年{d.month}月{d.day}日"


# ── ECDC page parsers ─────────────────────────────────────────────────────────

def parse_ecdc_counts(html: str) -> dict[str, int] | None:
    """
    Extract confirmed / probable / suspected / deaths from the ECDC page.
    Tries two regex variants to handle minor page restructures.
    """
    plain = _strip_tags(html)
    patterns: dict[str, list[str]] = {
        "confirmed": [
            r"Confirmed\s+cases\*+\s+(\d+)",
            r"(\d+)\s+Confirmed",
        ],
        "probable": [
            r"Probable\s+cases\*+\s+(\d+)",
            r"(\d+)\s+Probable",
        ],
        "suspected": [
            r"Suspected\s+cases\*+\s+(\d+)",
            r"(\d+)\s+Suspected",
        ],
        "deaths": [
            r"Number\s+of\s+deaths\s+(\d+)",
            r"(\d+)\s+deaths?\b",
        ],
    }
    results: dict[str, int] = {}
    for key, pats in patterns.items():
        for pat in pats:
            m = re.search(pat, plain, re.IGNORECASE)
            if m:
                results[key] = int(m.group(1))
                break
    return results if len(results) >= 3 else None


def parse_ecdc_news_items(html: str) -> list[dict]:
    """
    Parse the 'Latest updates' section of the ECDC surveillance page.
    Returns a list of dicts: {date, date_iso, doc_type, title, url}
    """
    plain = _strip_tags(html)

    # Isolate the "Latest updates" section
    start = re.search(r"Latest\s+updates", plain, re.IGNORECASE)
    if not start:
        return []
    section = plain[start.start():]
    # Stop at "Multimedia" or "More on this topic" if present
    end = re.search(r"(Multimedia|More on this topic|Videos)", section, re.IGNORECASE)
    if end:
        section = section[:end.start()]

    # Document type labels we recognise
    type_pat = re.compile(
        r"\b(Press\s+release|News|Assessment|Guidance|Rapid\s+scientific\s+advice)\b",
        re.IGNORECASE,
    )
    # Date pattern
    date_pat = re.compile(
        r"\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+20\d{2})\b",
        re.IGNORECASE,
    )
    # URL extraction from original HTML (not stripped) for this section
    url_start = max(0, html.lower().find("latest updates"))
    url_html   = html[url_start:]
    url_end_m  = re.search(
        r"(Multimedia|More on this topic|Videos|<h2[^>]*>)", url_html, re.IGNORECASE
    )
    if url_end_m:
        url_html = url_html[: url_end_m.start()]
    href_re = re.compile(r'href="(https://www\.ecdc\.europa\.eu[^"]+)"', re.IGNORECASE)
    hrefs   = href_re.findall(url_html)

    # Split section into lines and group them
    items: list[dict] = []
    lines = [l.strip() for l in section.splitlines() if l.strip()]
    href_idx = 0
    i = 0
    while i < len(lines):
        type_m = type_pat.match(lines[i])
        if type_m:
            doc_type = type_m.group(1).strip()
            # Next non-empty line(s) up to a date are the title
            title_parts = []
            j = i + 1
            date_str = ""
            while j < len(lines):
                dm = date_pat.search(lines[j])
                if dm:
                    date_str = dm.group(1).capitalize()
                    j += 1
                    break
                title_parts.append(lines[j])
                j += 1
            title = " ".join(title_parts).strip()
            if title and date_str:
                url = hrefs[href_idx] if href_idx < len(hrefs) else ""
                href_idx += 1
                items.append({
                    "date":     date_str,
                    "date_iso": _to_iso(date_str),
                    "doc_type": doc_type,
                    "title":    title,
                    "url":      url,
                })
            i = j
        else:
            i += 1

    # Deduplicate by (date_iso, title[:40])
    seen: set[tuple] = set()
    unique = []
    for it in items:
        key = (it["date_iso"], it["title"][:40])
        if key not in seen:
            seen.add(key)
            unique.append(it)

    return unique


# ── WHO page parser ───────────────────────────────────────────────────────────

def parse_who_update(html: str) -> dict | None:
    """
    Check WHO emergency event page for a date and headline count.
    Returns {date, date_iso, summary} or None.
    """
    if not html:
        return None
    plain  = _strip_tags(html)
    # Look for a date that looks recent (2026)
    dates  = re.findall(r"\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+2026\b", plain, re.IGNORECASE)
    counts = re.findall(r"(\d+)\s+(?:confirmed|probable|suspected|cases)", plain, re.IGNORECASE)
    if not dates:
        return None
    latest_date = sorted(set(d.capitalize() for d in dates), key=_to_iso)[-1]
    summary = f"WHO Emergency Event page updated; {', '.join(counts[:4])} cases mentioned." if counts else f"WHO Emergency Event page updated ({latest_date})."
    return {
        "date":     latest_date,
        "date_iso": _to_iso(latest_date),
        "summary":  summary,
    }


# ── timeline updater ──────────────────────────────────────────────────────────

def _make_timeline_entry(
    date_str: str,
    event: str,
    event_zh: str,
    source: str = "auto",
) -> dict:
    """Return a single timeline dict. source tag is stored in the entry for transparency."""
    return {
        "date":      date_str,
        "event":     event,
        "event_zh":  event_zh,
        "_source":   source,   # won't appear in the UI — just for audit
    }


# ECDC press release titles that are purely organizational / administrative
# (describe ECDC's own activities rather than new clinical/epidemiological facts)
# — these are skipped when auto-populating the timeline.
_SKIP_TITLE_PHRASES: list[str] = [
    "continues working on the frontline",
    "response activated",
    "ecdc response",
    "working on the frontline",
    "ecdc continues",
]


def _is_org_only(title: str) -> bool:
    """Return True if the ECDC news title is purely organizational noise."""
    t = title.lower()
    return any(phrase in t for phrase in _SKIP_TITLE_PHRASES)


def update_timeline(
    ecdc_news: list[dict],
    who_info: dict | None,
    count_event: dict | None,
) -> bool:
    """
    Add new timeline entries derived from ECDC news items, WHO updates, and
    count changes.

    Rules to avoid noise / duplication:
    1. Skip any auto-entry whose date already has ONE OR MORE existing entries
       (manual or auto). Manual entries are authoritative for their date.
    2. Skip ECDC items whose titles are purely organizational (see _SKIP_TITLE_PHRASES).
    3. WHO page-update entries are never added — they duplicate count-change entries.
    4. Count-change entries are only added on dates with no existing entry.
    """
    with CRUISE_PATH.open(encoding="utf-8") as f:
        data = json.load(f)

    timeline: list[dict] = data.get("timeline", [])

    # Set of ISO dates that already have at least one entry
    occupied_dates: set[str] = {_to_iso(e["date"]) for e in timeline}

    # Set of ISO dates that already have an auto-count entry
    auto_count_dates: set[str] = {
        _to_iso(e["date"])
        for e in timeline
        if e.get("_source") == "auto-count"
    }

    new_entries: list[dict] = []

    # 1. ECDC news items — only for dates with NO existing entry
    for item in ecdc_news:
        if item["date_iso"] in occupied_dates:
            continue  # date already covered by a (manual) entry
        if _is_org_only(item["title"]):
            continue  # purely organizational press release — skip
        doc_zh   = _DOC_TYPE_ZH.get(item["doc_type"], item["doc_type"])
        event    = f"ECDC {item['doc_type'].lower()}: {item['title']}"
        event_zh = f"欧洲疾控中心{doc_zh}：{item['title'][:80]}"
        new_entries.append(_make_timeline_entry(item["date"], event, event_zh, "auto-ecdc"))
        occupied_dates.add(item["date_iso"])  # claim this date

    # 2. Count-change entry — only on dates not yet occupied
    if count_event:
        iso = count_event.get("date_iso") or _to_iso(count_event["date"])
        if iso not in occupied_dates and iso not in auto_count_dates:
            new_entries.append(count_event)
            occupied_dates.add(iso)
            auto_count_dates.add(iso)

    # 3. WHO updates — skip entirely (they only duplicate count-change entries)

    if not new_entries:
        return False

    # Merge + sort chronologically
    all_entries = timeline + new_entries
    all_entries.sort(key=lambda e: _to_iso(e["date"]))
    data["timeline"] = all_entries

    with CRUISE_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return True


# ── sankey + snapshot updater ─────────────────────────────────────────────────

def update_cruise_counts(counts: dict[str, int]) -> tuple[bool, dict | None]:
    """
    Update sankey numbers and situation snapshot from parsed counts.
    Returns (changed: bool, count_event: dict | None).
    count_event is a ready-made timeline entry if the total changed.
    """
    with CRUISE_PATH.open(encoding="utf-8") as f:
        data = json.load(f)

    sk   = data.setdefault("sankey", {})
    snap = data.setdefault("situation_snapshot", {})
    changed = False

    confirmed = counts.get("confirmed", int(sk.get("confirmed_n", 0)))
    probable  = counts.get("probable",  0)
    suspected = counts.get("suspected", 0)
    deaths    = counts.get("deaths",    0)
    total     = confirmed + probable + suspected
    ship_n    = int(sk.get("ship_n", 147))
    old_total = int(sk.get("cluster_n", 0))
    old_conf  = int(sk.get("confirmed_n", 0))

    count_event: dict | None = None

    # ── sankey ──────────────────────────────────────────────────────────────
    if confirmed != old_conf:
        sk["confirmed_n"] = confirmed
        changed = True

    if total > 0 and total != old_total:
        sk["cluster_n"]  = total
        sk["contacts_n"] = max(ship_n - total, 0)
        changed = True

        # Build a count-change timeline entry
        date_str = _today_display()
        event = (
            f"ECDC daily update ({date_str}): {confirmed} confirmed + {probable} probable"
            + (f" + {suspected} suspected" if suspected else "")
            + f" = {total} total cases; {deaths} deaths"
            + (f" (was {old_conf} confirmed + {old_total - old_conf} probable)" if old_total else "")
        )
        event_zh = (
            f"欧洲疾控中心每日更新（{_today_display_zh()}）："
            f"{confirmed}例确认+{probable}例可能"
            + (f"+{suspected}例疑似" if suspected else "")
            + f"=共{total}例；{deaths}例死亡"
        )
        count_event = _make_timeline_entry(date_str, event, event_zh, "auto-count")

    # ── snapshot ─────────────────────────────────────────────────────────────
    parts = [f"{total} cases total"]
    if confirmed: parts.append(f"{confirmed} confirmed (PCR/serology)")
    if probable:  parts.append(f"{probable} probable")
    if suspected: parts.append(f"{suspected} suspected")
    parts += [f"as of {_today_display()}", f"{deaths} deaths"]
    count_str = "; ".join(parts)

    d = datetime.now(timezone.utc)
    count_str_zh = (
        f"共{total}例；截至{d.year}年{d.month}月{d.day}日"
        f"{confirmed}例确认（PCR/血清学）+{probable}例可能"
        + (f"+{suspected}例疑似" if suspected else "")
        + f"；{deaths}例死亡"
    )

    if count_str != snap.get("counts_as_of_7_may", ""):
        snap["counts_as_of_7_may"]    = count_str
        snap["counts_as_of_7_may_zh"] = count_str_zh
        changed = True

    # ── fetch log ─────────────────────────────────────────────────────────────
    log = data.setdefault("data_fetch_log", [])
    log.append({
        "fetched_at":   _now_utc(),
        "source":       "ECDC surveillance page",
        "parsed":       counts,
        "data_changed": changed,
    })
    data["data_fetch_log"] = log[-60:]

    data["sankey"]             = sk
    data["situation_snapshot"] = snap

    with CRUISE_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return changed, count_event


def update_outbreaks_table(counts: dict[str, int]) -> bool:
    """Sync cases/deaths on the cruise row in outbreaks.json."""
    with OB_PATH.open(encoding="utf-8") as f:
        data = json.load(f)

    changed = False
    total  = counts.get("confirmed", 0) + counts.get("probable", 0)
    deaths = counts.get("deaths", 0)

    for ob in data.get("outbreaks", []):
        if ob.get("id") == "cruise-ship-2026-andv-cluster":
            if total > 0 and ob.get("cases") != total:
                ob["cases"]  = total
                changed = True
            if deaths > 0 and ob.get("deaths") != deaths:
                ob["deaths"] = deaths
                changed = True
            break

    if changed:
        with OB_PATH.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    return changed


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"[fetch_data] {_now_utc()}  Starting daily data + news fetch…")

    # ── 1. ECDC surveillance page ─────────────────────────────────────────────
    print("[fetch_data] Fetching ECDC surveillance page…")
    ecdc_html = _fetch(ECDC_SURVEILLANCE)

    counts     = parse_ecdc_counts(ecdc_html)   if ecdc_html else None
    ecdc_news  = parse_ecdc_news_items(ecdc_html) if ecdc_html else []

    if ecdc_news:
        print(f"[fetch_data] ECDC news items found: {len(ecdc_news)}")
        for item in ecdc_news:
            print(f"  [{item['date']}] {item['doc_type']}: {item['title'][:70]}")
    else:
        print("[fetch_data] No new ECDC news items parsed.")

    # ── 2. WHO emergency event page ───────────────────────────────────────────
    print("[fetch_data] Fetching WHO emergency event page…")
    who_html = _fetch(WHO_EVENT)
    who_info = parse_who_update(who_html) if who_html else None
    if who_info:
        print(f"[fetch_data] WHO update detected: {who_info['date']}")

    # ── 3. Update case counts ─────────────────────────────────────────────────
    count_event: dict | None = None
    counts_changed = False

    if counts:
        print(f"[fetch_data] Counts: {counts}")
        counts_changed, count_event = update_cruise_counts(counts)
        tbl_changed = update_outbreaks_table(counts)
        if counts_changed or tbl_changed:
            print("[fetch_data] ✓ Case counts updated in JSON.")
        else:
            print("[fetch_data] Case counts unchanged.")
    else:
        print("[fetch_data] WARNING: could not parse counts from ECDC page.", file=sys.stderr)

    # ── 4. Update timeline with news items + count change entry ───────────────
    tl_changed = update_timeline(ecdc_news, who_info, count_event)
    if tl_changed:
        print("[fetch_data] ✓ Timeline updated with new entries.")
    else:
        print("[fetch_data] Timeline unchanged (all items already present).")

    # ── Summary ───────────────────────────────────────────────────────────────
    if counts_changed or tl_changed:
        print("[fetch_data] Done — data changed. Run build_tracker.py to rebuild HTML.")
    else:
        print("[fetch_data] Done — no changes detected.")


if __name__ == "__main__":
    main()
