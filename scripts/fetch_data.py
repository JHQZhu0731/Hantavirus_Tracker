#!/usr/bin/env python3
"""
Fetch the latest Andes hantavirus case counts from the ECDC daily surveillance
page and update data/cruise_outbreak_2026.json and data/outbreaks.json.

Run manually:
    python3 scripts/fetch_data.py

Run via GitHub Actions: see .github/workflows/daily_data_fetch.yml

What this script auto-updates
──────────────────────────────
• Confirmed cases, probable cases, suspected cases, deaths  (from ECDC page)
• sankey.confirmed_n, sankey.cluster_n, sankey.contacts_n  (derived)
• situation_snapshot counts string                          (derived)
• outbreaks.json entry for the cruise cluster              (cases + deaths)
• A data_fetch_log entry in cruise JSON for traceability

What it does NOT touch
───────────────────────
• The individual outcome rows (Fatal / ICU / Transferred / Post-disembark) —
  those require manual entry because ECDC does not publish per-person detail
  in machine-readable form.
• The timeline — new events must be added by hand.
• Any field that was not parseable from the ECDC page (script exits safely).
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

ECDC_SURVEILLANCE_URL = (
    "https://www.ecdc.europa.eu/en/infectious-disease-topics/"
    "hantavirus-infection/surveillance-and-updates/andes-hantavirus-outbreak"
)

# ── helpers ───────────────────────────────────────────────────────────────────

def _fetch(url: str, timeout: int = 20) -> str:
    """Return page text, or '' on any network error."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 HantavirusTrackerBot/1.0 (public-health)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        print(f"[fetch_data] WARNING: could not fetch {url}: {exc}", file=sys.stderr)
        return ""


def _strip_tags(text: str) -> str:
    """Remove HTML tags so we can regex on plain text."""
    return re.sub(r"<[^>]+>", " ", text)


def _parse_counts(html: str) -> dict[str, int] | None:
    """
    Extract confirmed / probable / suspected / deaths from the ECDC page.

    The page (as of May 2026) contains a data block like:
        Confirmed cases***   6
        Probable cases**     2
        Suspected cases*     0
        Number of deaths     3

    We strip HTML tags first so both the original and any future redesign
    that still contains those labels and numbers should parse correctly.
    """
    plain = _strip_tags(html)

    patterns: dict[str, str] = {
        "confirmed": r"Confirmed\s+cases\*+\s+(\d+)",
        "probable":  r"Probable\s+cases\*+\s+(\d+)",
        "suspected": r"Suspected\s+cases\*+\s+(\d+)",
        "deaths":    r"Number\s+of\s+deaths\s+(\d+)",
    }

    results: dict[str, int] = {}
    for key, pat in patterns.items():
        m = re.search(pat, plain, re.IGNORECASE)
        if m:
            results[key] = int(m.group(1))

    if len(results) < 3:
        # Also try more lenient patterns (some ECDC page variants)
        lenient: dict[str, str] = {
            "confirmed": r"(\d+)\s*Confirmed",
            "probable":  r"(\d+)\s*Probable",
            "suspected": r"(\d+)\s*Suspected",
            "deaths":    r"(\d+)\s*(?:deaths?|Deaths?)",
        }
        for key, pat in lenient.items():
            if key not in results:
                m = re.search(pat, plain, re.IGNORECASE)
                if m:
                    results[key] = int(m.group(1))

    return results if len(results) >= 2 else None


# ── updaters ─────────────────────────────────────────────────────────────────

def _today() -> str:
    return datetime.now(timezone.utc).strftime("%d %b %Y")


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def update_cruise_json(counts: dict[str, int]) -> bool:
    """Apply parsed counts to cruise_outbreak_2026.json. Returns True if changed."""
    with CRUISE_PATH.open(encoding="utf-8") as f:
        data = json.load(f)

    changed = False
    sk   = data.setdefault("sankey", {})
    snap = data.setdefault("situation_snapshot", {})

    confirmed = counts.get("confirmed", int(sk.get("confirmed_n", 0)))
    probable  = counts.get("probable",  0)
    suspected = counts.get("suspected", 0)
    deaths    = counts.get("deaths",    0)
    total     = confirmed + probable + suspected
    ship_n    = int(sk.get("ship_n", 147))

    # ── sankey numbers ──────────────────────────────────────────────────────
    if confirmed != int(sk.get("confirmed_n", -1)):
        sk["confirmed_n"] = confirmed
        changed = True

    if total > 0 and total != int(sk.get("cluster_n", -1)):
        sk["cluster_n"]  = total
        sk["contacts_n"] = max(ship_n - total, 0)
        changed = True

    # ── situation snapshot count string ─────────────────────────────────────
    parts = [f"{total} cases total"]
    if confirmed: parts.append(f"{confirmed} confirmed (PCR/serology)")
    if probable:  parts.append(f"{probable} probable")
    if suspected: parts.append(f"{suspected} suspected")
    parts.append(f"as of {_today()}")
    parts.append(f"{deaths} deaths")
    count_str = "; ".join(parts)
    count_str_zh = (
        f"共{total}例；截至{datetime.now(timezone.utc).strftime('%Y年%-m月%-d日')}"
        f"{confirmed}例确认（PCR/血清学）+{probable}例可能"
        + (f"+{suspected}例疑似" if suspected else "")
        + f"；{deaths}例死亡"
    )

    if count_str != snap.get("counts_as_of_7_may", ""):
        snap["counts_as_of_7_may"]    = count_str
        snap["counts_as_of_7_may_zh"] = count_str_zh
        changed = True

    # ── fetch log (always append, keep last 60 entries) ─────────────────────
    log = data.setdefault("data_fetch_log", [])
    log.append({
        "fetched_at": _now_utc(),
        "source": "ECDC surveillance page",
        "parsed": counts,
        "data_changed": changed,
    })
    data["data_fetch_log"] = log[-60:]

    data["sankey"]               = sk
    data["situation_snapshot"]   = snap

    with CRUISE_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return changed


def update_outbreaks_json(counts: dict[str, int]) -> bool:
    """Sync case/death counts for the cruise entry in outbreaks.json."""
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
    print(f"[fetch_data] {_now_utc()}  Starting data fetch…")

    html = _fetch(ECDC_SURVEILLANCE_URL)
    if not html:
        print("[fetch_data] Could not reach ECDC page — no changes made.", file=sys.stderr)
        sys.exit(0)

    counts = _parse_counts(html)
    if not counts:
        print(
            "[fetch_data] Could not parse case counts from ECDC page — "
            "page structure may have changed. No changes made.",
            file=sys.stderr,
        )
        sys.exit(0)

    print(f"[fetch_data] ECDC counts parsed: {counts}")

    c1 = update_cruise_json(counts)
    c2 = update_outbreaks_json(counts)

    if c1 or c2:
        print("[fetch_data] ✓ Data updated — files saved. Rebuild HTML next.")
    else:
        print("[fetch_data] No numeric changes detected — JSON unchanged.")


if __name__ == "__main__":
    main()
