#!/usr/bin/env python3
"""
Regenerate the static Hantavirus Tracker HTML from data/outbreaks.json and
data/cruise_outbreak_2026.json.  Run daily:

  0 6 * * * cd "/path/to/Hantavirus Tracker" && python3 scripts/build_tracker.py
"""

from __future__ import annotations

import json
import math
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "outbreaks.json"
CRUISE_PATH = ROOT / "data" / "cruise_outbreak_2026.json"
OUT_HTML = ROOT / "index.html"


# ── data loaders ─────────────────────────────────────────────────────────────

def load_data() -> dict:
    with DATA_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def load_cruise() -> dict | None:
    if not CRUISE_PATH.exists():
        return None
    with CRUISE_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def try_fetch_cdc_status() -> str | None:
    try:
        req = urllib.request.Request(
            "https://www.cdc.gov/hantavirus/hps/index.html",
            headers={"User-Agent": "HantavirusTrackerBuild/1.0"},
            method="HEAD",
        )
        with urllib.request.urlopen(req, timeout=12) as r:
            if 200 <= r.status < 400:
                return "CDC HPS page reachable — review for narrative updates."
    except Exception:
        pass
    return None


# ── math helpers ──────────────────────────────────────────────────────────────

def doubling_time_days(r0: float, generation_days: float) -> float | None:
    if r0 <= 1:
        return None
    return math.log(2) * generation_days / math.log(r0)


def html_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ── SVG flow diagram ──────────────────────────────────────────────────────────

def _cubic_ribbon(x0: float, x1: float,
                  y0a: float, y0b: float,
                  y1a: float, y1b: float) -> str:
    mx = (x0 + x1) / 2
    return (
        f"M{x0:.2f},{y0a:.2f} C{mx:.2f},{y0a:.2f} {mx:.2f},{y1a:.2f} {x1:.2f},{y1a:.2f} "
        f"L{x1:.2f},{y1b:.2f} C{mx:.2f},{y1b:.2f} {mx:.2f},{y0b:.2f} {x0:.2f},{y0b:.2f}Z"
    )


def build_sankey_svg(sk: dict, esc) -> str:
    """
    Three-column flow diagram (HEAD → SPLIT → OUTCOMES) with nationality colours.
    Bar heights are VISUAL (not proportional) — noted in the diagram.
    """
    ship = int(sk["ship_n"])
    cluster_n = int(sk["cluster_n"])
    contacts_n = int(sk["contacts_n"])
    outcomes = sk["outcomes"]
    if sum(int(o["count"]) for o in outcomes) != cluster_n:
        raise ValueError("outcome counts must sum to cluster_n")

    W, H = 840, 500
    BAR = 16
    F = 'font-family="Arial,Helvetica,sans-serif"'

    # ── bar x edges (3 columns) ───────────────────────────────────────────────
    x0l, x0r = 58.0, 74.0    # col0 HEAD
    x1l, x1r = 264.0, 280.0  # col1 SPLIT
    x2l, x2r = 470.0, 486.0  # col2 OUTCOMES

    # ── vertical layout: visual scale, NOT proportional ──────────────────────
    y_c0, y_c1 = 72.0, 292.0   # contacts segment  (220 px visual)
    y_k0, y_k1 = 300.0, 400.0  # cluster segment   (100 px visual)
    H_out = 180.0               # outcomes fan height
    out_segs: list[tuple[float, float, dict]] = []
    y_cur = y_k0
    for o in outcomes:
        frac = int(o["count"]) / cluster_n
        out_segs.append((y_cur, y_cur + H_out * frac, o))
        y_cur += H_out * frac

    # ── ribbon paths ─────────────────────────────────────────────────────────
    def ribbon(xa, xb, ya0, ya1, yb0, yb1, fill, op=0.80):
        d = _cubic_ribbon(xa, xb, ya0, ya1, yb0, yb1)
        return f'<path d="{d}" fill="{fill}" fill-opacity="{op:.2f}"/>'

    ribs = [
        ribbon(x0r, x1l, y_c0, y_c1, y_c0, y_c1, "#e5dff4"),
        ribbon(x0r, x1l, y_k0, y_k1, y_k0, y_k1, "#d8d0ee"),
    ]
    y_src = y_k0
    for y_a, y_b, o in out_segs:
        frac = int(o["count"]) / cluster_n
        src_h = (y_k1 - y_k0) * frac
        # tint ribbon with the outcome's nationality colour at low opacity
        ribs.append(ribbon(x1r, x2l, y_src, y_src + src_h, y_a, y_b, o["color"], 0.30))
        y_src += src_h
    ribs_s = "\n    ".join(ribs)

    # ── bars ─────────────────────────────────────────────────────────────────
    def rect(xl, y0, h, col):
        return f'<rect x="{xl:.1f}" y="{y0:.2f}" width="{BAR}" height="{h:.2f}" fill="{col}" rx="2"/>'

    # col0: split contacts bar into passengers (dark) / crew (lighter)
    pax  = int(sk.get("passengers_n", 88))
    crew = int(sk.get("crew_n", 59))
    pax_h  = (y_c1 - y_c0) * pax  / ship
    crew_h = (y_c1 - y_c0) * crew / ship

    bars = [
        rect(x0l, y_c0,          pax_h,  "#57068c"),   # passengers
        rect(x0l, y_c0 + pax_h,  crew_h, "#9b5ec4"),   # crew (lighter violet)
        rect(x0l, y_k0, y_k1 - y_k0, "#7b3aac"),        # cluster (col0)
        rect(x1l, y_c0, y_c1 - y_c0, "#57068c"),        # contacts (col1)
        rect(x1l, y_k0, y_k1 - y_k0, "#7b3aac"),        # cluster (col1)
    ]
    for y_a, y_b, o in out_segs:
        bars.append(rect(x2l, y_a, y_b - y_a, o["color"]))
    bars_s = "\n    ".join(bars)

    # ── text helpers ──────────────────────────────────────────────────────────
    LH = 14.0

    def line(x, y, txt, w="400", c="#121212", sz="10.5"):
        return (
            f'<text {F} font-size="{sz}px" font-weight="{w}" '
            f'fill="{c}" x="{x:.2f}" y="{y:.2f}">{esc(str(txt))}</text>'
        )

    def label_block(x, y_center, lines):
        n = len(lines)
        y0 = y_center - n * LH / 2 + LH * 0.85
        return "\n    ".join(
            line(x, y0 + i * LH, txt, w, c, sz)
            for i, (txt, w, c, sz) in enumerate(lines)
        )

    nat_note = sk.get("nationalities_note", "23 nationalities")
    # shorten for the bar label area (keep it concise)
    nat_short = nat_note.split(":")[1].strip() if ":" in nat_note else nat_note

    lbls = []

    # HEAD (col0) — pax/crew breakdown + nationality summary
    lbls.append(label_block(x0r + 14, (y_c0 + y_k1) / 2, [
        (f"{ship} aboard",                         "700", "#121212", "11"),
        (f"{pax} passengers \u00b7 {crew} crew",   "400", "#121212", "10.5"),
        (nat_short,                                "400", "#57068c", "9"),
        (f"EWRS: {sk['ewrs_notification']}",        "400", "#999",   "9"),
        (f"ECDC: {sk['ecdc_assessment']}",          "400", "#999",   "9"),
    ]))

    # Contacts (col1 upper)
    lbls.append(label_block(x1r + 14, (y_c0 + y_c1) / 2, [
        ("Contacts (monitoring)",    "700", "#121212", "11"),
        (f"n = {contacts_n}",        "400", "#121212", "10.5"),
        ("Precautionary pool",       "400", "#5a5a5a", "9.5"),
        ("Predict: not infected",    "400", "#57068c", "9.5"),
    ]))

    # Cluster (col1 lower)
    lbls.append(label_block(x1r + 14, (y_k0 + y_k1) / 2, [
        ("Cluster",                        "700", "#121212", "11"),
        (f"n = {cluster_n} \u00b7 5 PCR+", "400", "#121212", "10.5"),
        ("HPS-compatible illness",          "400", "#5a5a5a", "9.5"),
        ("Predict: ANDV",                   "700", "#8b1a1a", "9.5"),
    ]))

    # Contacts terminal (col2 area, top, muted)
    lbls.append(label_block(x2r + 14, (y_c0 + y_c1) / 2, [
        ("Under monitoring",          "700", "#bbb", "10"),
        (f"n = {contacts_n}",         "400", "#bbb", "9.5"),
        ("No confirmed infections",   "400", "#ccc", "9"),
        ("as of 7 May 2026",          "400", "#ccc", "9"),
    ]))

    # Outcome labels (col2 right) — nationality on line 2, detail on line 3
    for y_a, y_b, o in out_segs:
        seg_h = y_b - y_a
        sz = "9" if seg_h < 32 else "10"
        lh2 = 12.5 if seg_h < 32 else LH
        mid = (y_a + y_b) / 2
        nat      = o.get("nat", "")
        nat_code = o.get("nat_code", "")
        detail   = o.get("detail", "")
        bar_col  = o["color"]
        nat_disp = f"{nat} [{nat_code}]" if nat else nat_code
        y0 = mid - lh2 + lh2 * 0.10
        lbls.append(
            line(x2r + 14, y0,          f"{o['label']} \u00b7 {int(o['count'])}", "700", "#121212", sz)
            + "\n    " +
            line(x2r + 14, y0 + lh2,    nat_disp,  "700", bar_col, sz)
            + "\n    " +
            line(x2r + 14, y0 + lh2*2,  detail,    "400", "#5a5a5a", "8.5")
        )

    lbls_s = "\n    ".join(lbls)

    # ── nationality legend (upper-right whitespace, x≈510..840, y≈40..210) ──
    lx = 512.0
    legend_items = [
        f'<text {F} font-size="7.5px" font-weight="700" fill="#aaa" x="{lx}" y="52">OUTCOME BY NATIONALITY</text>',
        # pax/crew legend
        f'<rect x="{lx}" y="58" width="9" height="9" fill="#57068c" rx="1"/>',
        f'<text {F} font-size="8.5px" fill="#555" x="{lx+13}" y="66">Passengers ({pax})</text>',
        f'<rect x="{lx+110}" y="58" width="9" height="9" fill="#9b5ec4" rx="1"/>',
        f'<text {F} font-size="8.5px" fill="#555" x="{lx+123}" y="66">Crew ({crew})</text>',
        f'<line x1="{lx}" y1="73" x2="{lx+200}" y2="73" stroke="#e0e0e0" stroke-width="0.8"/>',
    ]
    for i, o in enumerate(outcomes):
        ry  = 82 + i * 19
        nat = o.get("nat", o["label"])
        code = o.get("nat_code", "")
        cnt  = int(o["count"])
        death_sfx = " \u2020" if o.get("is_death") else ""
        legend_items += [
            f'<rect x="{lx}" y="{ry - 7}" width="9" height="9" fill="{o["color"]}" rx="1"/>',
            f'<text {F} font-size="8.5px" fill="#333" x="{lx+13}" y="{ry}">'
            f'{esc(nat)}{esc(death_sfx)} [{esc(code)}] \u00b7 {cnt}</text>',
        ]
    legend_s = "\n    ".join(legend_items)

    # ── column headers ────────────────────────────────────────────────────────
    col_info = [
        (66.0,  "HEAD",     f"n = {ship}"),
        (272.0, "SPLIT",    "Contacts / Cluster"),
        (478.0, "OUTCOMES", "7 May 2026"),
    ]
    hdrs = []
    for cx, title, sub in col_info:
        hdrs += [
            f'<text {F} font-size="8.5px" font-weight="700" fill="#aaa" '
            f'text-anchor="middle" x="{cx:.1f}" y="47">{esc(title)}</text>',
            f'<text {F} font-size="8px" fill="#ccc" '
            f'text-anchor="middle" x="{cx:.1f}" y="59">{esc(sub)}</text>',
            f'<line x1="{cx:.1f}" y1="63" x2="{cx:.1f}" y2="72" '
            f'stroke="#ddd" stroke-width="1"/>',
        ]
    hdrs_s = "\n    ".join(hdrs)

    deaths_total = sum(int(o["count"]) for o in outcomes if o.get("is_death"))
    note = (
        f'<text {F} font-size="8px" fill="#ccc" x="8" y="{H - 8}">'
        f'Bar heights are visual \u2014 not proportional. '
        f'{cluster_n} cases / {ship} aboard = {cluster_n/ship*100:.1f}%. '
        f'\u2020 = fatal.</text>'
    )

    title_txt = esc(
        f"MV Hondius flow: {ship} aboard, {cluster_n} HPS-compatible cases, "
        f"{deaths_total} deaths \u2014 as of {sk['ecdc_assessment']}"
    )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'role="img" aria-label="{title_txt}">'
        f'<title>{title_txt}</title>'
        f'<rect width="{W}" height="{H}" fill="#f9f9f7"/>'
        f'<g>\n    {ribs_s}\n  </g>'
        f'<g>\n    {bars_s}\n  </g>'
        f'<g>\n    {hdrs_s}\n  </g>'
        f'<g>\n    {legend_s}\n  </g>'
        f'<g>\n    {lbls_s}\n  </g>'
        f'{note}'
        f'</svg>'
    )


# ── cruise section builder ────────────────────────────────────────────────────

def build_cruise_section(c: dict) -> str:
    esc = html_escape
    snap = c["situation_snapshot"]
    prim = c["primary_source"]
    sec = c.get("secondary_source", {})
    sk = c.get("sankey")

    # stat strip values
    ship = int(sk["ship_n"]) if sk else 147
    cluster_n = int(sk["cluster_n"]) if sk else 8
    deaths = sum(int(o["count"]) for o in sk["outcomes"] if o.get("is_death")) if sk else 3
    cfr_pct = round(deaths / cluster_n * 100)

    sec_link = ""
    if sec:
        sec_link = (
            f'<p class="src-line">'
            f'<a href="{esc(sec["url"])}">{esc(sec["name"])}</a>'
            f'</p>'
        )

    svg_block = ""
    if sk:
        svg_str = build_sankey_svg(sk, esc)
        svg_block = f"""
      <div class="flow-wrap" role="region" aria-labelledby="flow-heading">
        <h3 class="section-label" id="flow-heading">Population flow &amp; outcomes</h3>
        <div class="flow-svg">{svg_str}</div>
        <p class="fig-caption">
          Ribbon widths follow ECDC counts for the ship split
          ({esc(str(sk['contacts_n']))} contacts vs. {cluster_n} cluster).
          Bar heights are visual only.
        </p>
      </div>"""

    # 28-day scenario cards from JSON
    scen_cards = ""
    scenarios = sk.get("scenarios", []) if sk else []
    if scenarios:
        hz = int(sk.get("prediction_horizon_days", 28))
        cards_html = []
        card_classes = ["scen-a", "scen-b", "scen-c"]
        for i, s in enumerate(scenarios[:3]):
            cls = card_classes[i] if i < len(card_classes) else "scen-a"
            cards_html.append(
                f'<div class="scen-card {cls}">'
                f'<p class="scen-label">{esc(chr(65 + i))}. {esc(s["label"])}</p>'
                f'<p class="scen-pred">{esc(s["predict"])}</p>'
                f'<p class="scen-rule">{esc(s["rule"])}</p>'
                f'</div>'
            )
        cards_s = "\n        ".join(cards_html)
        scen_block = (
            f'<div class="scen-wrap">'
            f'<h3 class="section-label">{hz}-day cumulative infection scenarios '
            f'<span class="label-note">(illustrative — not ECDC/WHO forecasts)</span></h3>'
            f'<p class="explainer">{esc(sk["prediction_note"])}</p>'
            f'<div class="scen-strip">{cards_s}</div>'
            f'</div>'
        )
    else:
        scen_block = ""

    # Timeline
    timeline_html = ""
    if c.get("timeline"):
        items = []
        for evt in c["timeline"]:
            items.append(
                f'<li class="tl-item">'
                f'<span class="tl-date">{esc(evt["date"])}</span>'
                f'<span class="tl-event">{esc(evt["event"])}</span>'
                f'</li>'
            )
        timeline_html = (
            f'<div class="tl-wrap">'
            f'<h3 class="section-label">Outbreak timeline</h3>'
            f'<ol class="tl-list">{"".join(items)}</ol>'
            f'</div>'
        )

    # Decision tree rows
    dt_rows = []
    for i, node in enumerate(c["decision_tree"], start=1):
        depth = int(node["level"])
        pad = 0.5 + depth * 1.1
        dt_rows.append(
            f'<tr class="dt-d{depth}">'
            f'<th scope="row" class="dt-num">{i}</th>'
            f'<td class="dt-if" style="padding-left:{pad:.2f}rem">{esc(node["if"])}</td>'
            f'<td class="dt-then">{esc(node["then"])}</td>'
            f'<td class="dt-why">{esc(node["note"])}</td>'
            f'</tr>'
        )
    dt_s = "\n          ".join(dt_rows)

    return f"""
  <section class="cruise-panel" aria-labelledby="cruise-heading">
    <div class="cruise-header">
      <p class="kicker-sm">MV Hondius · South Atlantic · May 2026</p>
      <h2 class="headline" id="cruise-heading">{esc(c["label"])}</h2>
      <p class="deck">{esc(c["deck"])}</p>
      <p class="src-line"><a href="{esc(prim["url"])}">{esc(prim["name"])}</a></p>
      {sec_link}
    </div>

    <div class="stat-strip" role="list" aria-label="Key figures">
      <div class="stat" role="listitem">
        <span class="stat-n">{ship}</span>
        <span class="stat-label">Aboard</span>
      </div>
      <div class="stat stat-cluster" role="listitem">
        <span class="stat-n">{cluster_n}</span>
        <span class="stat-label">Cases</span>
      </div>
      <div class="stat stat-fatal" role="listitem">
        <span class="stat-n">{deaths}</span>
        <span class="stat-label">Deaths</span>
      </div>
      <div class="stat stat-cfr" role="listitem">
        <span class="stat-n">{cfr_pct}%</span>
        <span class="stat-label">Case fatality</span>
      </div>
    </div>
    {svg_block}
    {scen_block}

    {timeline_html}

    <div class="snapshot-grid">
      <div class="snapshot-block">
        <h3 class="section-label">Situation snapshot</h3>
        <dl class="snap-dl">
          <dt>Notification</dt><dd>{esc(snap.get("notification",""))}</dd>
          <dt>Vessel</dt><dd>{esc(snap.get("vessel", snap.get("setting","—")))}</dd>
          <dt>Itinerary</dt><dd>{esc(snap.get("itinerary","—"))}</dd>
          <dt>Persons aboard</dt><dd>{esc(snap.get("persons_aboard","—"))}</dd>
          <dt>Cases (7 May)</dt><dd>{esc(snap.get("counts_as_of_7_may", snap.get("counts_as_of_6_may","—")))}</dd>
          <dt>Laboratory</dt><dd>{esc(snap.get("laboratory",""))}</dd>
          <dt>Index cases</dt><dd>{esc(snap.get("index_cases","—"))}</dd>
          <dt>Working hypothesis</dt><dd>{esc(snap.get("working_hypothesis",""))}</dd>
          <dt>Population risk</dt><dd>{esc(snap.get("risk_eu_population",""))}</dd>
        </dl>
      </div>
    </div>

    <div class="dt-wrap">
      <h3 class="section-label">Decision tree for investigators and clinicians</h3>
      <p class="explainer">
        Each row is one branch: <em>if</em> the signal applies, take the control step.
        Teaching schematic from ECDC's preliminary assessment — not a substitute
        for national protocols or shipboard medical orders.
      </p>
      <div class="dt-scroll" role="region" aria-label="Decision tree" tabindex="0">
        <table class="dt-table">
          <thead>
            <tr>
              <th scope="col" class="dt-num">#</th>
              <th scope="col" class="dt-if-h">If you see&hellip;</th>
              <th scope="col">Then do&hellip;</th>
              <th scope="col" class="dt-why-h">ECDC framing</th>
            </tr>
          </thead>
          <tbody>
          {dt_s}
          </tbody>
        </table>
      </div>
    </div>
  </section>"""


# ── outbreak table ────────────────────────────────────────────────────────────

def build_table_rows(outbreaks: list) -> str:
    rows = []
    for o in outbreaks:
        cases = o.get("cases")
        deaths = o.get("deaths")
        cases_s = f"{cases:,}" if isinstance(cases, int) else "—"
        deaths_s = f"{deaths:,}" if isinstance(deaths, int) else "—"
        label = html_escape(o.get("label", ""))
        country = html_escape(o.get("country", ""))
        year = html_escape(str(o.get("year", "")))
        virus = html_escape(o.get("virus", ""))
        url = html_escape(o.get("source_url", "#"))
        src = html_escape(o.get("source_name", "Source"))
        rows.append(
            f'<tr><th scope="row">{label}</th><td>{country}</td>'
            f'<td>{year}</td><td>{cases_s}</td><td>{deaths_s}</td>'
            f'<td>{virus}</td><td><a href="{url}">{src}</a></td></tr>'
        )
    return "\n".join(rows)


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    data = load_data()
    outbreaks = data["outbreaks"]
    rref = data["r0_reference"]
    g = float(rref["generation_interval_days_assumption"])
    r_pre = float(rref["andes_pre_control"])
    r_post = float(rref["andes_post_control"])

    td = doubling_time_days(r_pre, g)
    td_s = f"{td:.1f} days" if td else "not above replacement"

    seed = 5
    proj_rows = []
    for k in range(5):
        if abs(r_pre - 1.0) < 1e-9:
            cum = seed * (k + 1)
        else:
            cum = seed * (r_pre ** (k + 1) - 1) / (r_pre - 1)
        proj_rows.append(
            f"<tr><td>{k}</td><td>{k * int(g)}</td><td>{cum:,.0f}</td></tr>"
        )
    proj_rows_s = "\n            ".join(proj_rows)

    network_note = try_fetch_cdc_status()
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    cruise = load_cruise()
    cruise_html = (
        build_cruise_section(cruise) if cruise
        else '<section class="cruise-panel"><p>Missing cruise_outbreak_2026.json.</p></section>'
    )
    table_body = build_table_rows(outbreaks)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <meta http-equiv="refresh" content="3600"/>
  <title>Hantavirus Tracker &mdash; 2026 cruise cluster &amp; R&#x2080; context</title>
  <meta name="description" content="ECDC-sourced flow diagram and decision tree for the 2026 cruise-ship hantavirus cluster, plus R\u2080 data and historical outbreak table."/>
  <style>
    :root {{
      --violet:      #57068c;
      --violet-dk:   #3d045f;
      --violet-md:   #7b3aac;
      --violet-lt:   #e8dff4;
      --ink:         #121212;
      --ink-soft:    #484848;
      --muted:       #727272;
      --rule:        #e2e2e2;
      --paper:       #faf9f7;
      --white:       #ffffff;
      --fatal:       #8b1a1a;
      --icu:         #cc4400;
    }}
    *, *::before, *::after {{ box-sizing: border-box; }}

    /* ── set Arial at the root so every element inherits it ─────────────── */
    html {{
      font-family: Arial, Helvetica, sans-serif;
    }}
    body {{
      margin: 0;
      font-family: Arial, Helvetica, sans-serif;
      font-size: 15px;
      line-height: 1.5;
      color: var(--ink);
      background: var(--paper);
    }}
    /* enforce Arial on elements browsers may not auto-inherit (table, caption, input…) */
    *, *::before, *::after {{ font-family: Arial, Helvetica, sans-serif; }}

    a {{ color: var(--violet-dk); }}
    a:focus-visible {{ outline: 2px solid var(--violet); outline-offset: 2px; }}

    .skip {{
      position: absolute; left: -9999px; top: auto; width: 1px; height: 1px;
      overflow: hidden;
    }}
    .skip:focus {{
      position: static; width: auto; height: auto;
      padding: 0.5rem 1rem; background: var(--white);
    }}

    /* ── page header ───────────────────────────────────────────────────────── */
    .page-header {{
      border-bottom: 3px solid var(--violet);
      background: var(--white);
      padding: 1.1rem 1.5rem 1rem;
    }}
    .page-kicker {{
      font-size: 0.7rem;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: var(--muted);
      margin: 0 0 0.3rem;
    }}
    .page-title {{
      margin: 0;
      font-size: 1.6rem;
      font-weight: 700;
      letter-spacing: -0.02em;
    }}
    .page-sub {{
      margin: 0.45rem 0 0;
      max-width: 52rem;
      color: var(--muted);
      font-size: 0.92rem;
    }}

    /* ── main wrapper ──────────────────────────────────────────────────────── */
    main {{
      max-width: 1100px;
      margin: 0 auto;
      padding: 1.25rem 1.5rem 3rem;
      display: flex;
      flex-direction: column;
      gap: 1.25rem;
    }}

    /* ── generic panel ─────────────────────────────────────────────────────── */
    .panel {{
      background: var(--white);
      border: 1px solid var(--rule);
      padding: 1.1rem 1.25rem;
    }}
    .panel-title {{
      font-size: 0.72rem;
      font-weight: 700;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--violet);
      border-bottom: 1px solid var(--rule);
      padding-bottom: 0.4rem;
      margin: 0 0 0.85rem;
    }}

    /* ── cruise panel ──────────────────────────────────────────────────────── */
    .cruise-panel {{
      background: var(--white);
      border: 1px solid var(--rule);
      border-top: 4px solid var(--ink);
    }}
    .cruise-header {{
      padding: 1.1rem 1.25rem 0.9rem;
      border-bottom: 1px solid var(--rule);
    }}
    .kicker-sm {{
      font-family: Arial, Helvetica, sans-serif;
      font-size: 0.7rem;
      font-weight: 700;
      letter-spacing: 0.11em;
      text-transform: uppercase;
      color: var(--muted);
      margin: 0 0 0.35rem;
    }}
    .headline {{
      font-family: Arial, Helvetica, sans-serif;
      font-size: clamp(1.2rem, 2.2vw, 1.65rem);
      font-weight: 700;
      line-height: 1.15;
      color: var(--ink);
      letter-spacing: -0.02em;
      margin: 0 0 0.55rem;
    }}
    .deck {{
      font-family: Arial, Helvetica, sans-serif;
      font-size: 0.97rem;
      color: var(--ink-soft);
      line-height: 1.5;
      margin: 0 0 0.6rem;
      max-width: 44rem;
    }}
    .src-line {{
      font-size: 0.82rem;
      color: var(--muted);
      margin: 0 0 0.2rem;
      line-height: 1.4;
    }}
    .src-line a {{ color: var(--ink); text-decoration: underline; text-underline-offset: 2px; }}

    /* ── stat strip ────────────────────────────────────────────────────────── */
    .stat-strip {{
      display: flex;
      gap: 0;
      border-bottom: 1px solid var(--rule);
    }}
    .stat {{
      flex: 1;
      padding: 0.9rem 1.25rem;
      border-right: 1px solid var(--rule);
      border-left: 4px solid var(--violet);
    }}
    .stat:last-child {{ border-right: none; }}
    .stat-cluster {{ border-left-color: var(--violet-md); }}
    .stat-fatal   {{ border-left-color: var(--fatal); }}
    .stat-cfr     {{ border-left-color: var(--icu); }}
    .stat-n {{
      display: block;
      font-size: 2.15rem;
      font-weight: 700;
      line-height: 1;
      letter-spacing: -0.03em;
      color: var(--ink);
    }}
    .stat-label {{
      display: block;
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.09em;
      color: var(--muted);
      margin-top: 0.25rem;
    }}

    /* ── flow diagram ──────────────────────────────────────────────────────── */
    .flow-wrap {{
      padding: 1.1rem 1.25rem 0.75rem;
      border-bottom: 1px solid var(--rule);
    }}
    .section-label {{
      font-family: Arial, Helvetica, sans-serif;
      font-size: 0.7rem;
      font-weight: 700;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: var(--ink);
      margin: 0 0 0.5rem;
    }}
    .label-note {{
      font-weight: 400;
      text-transform: none;
      letter-spacing: 0;
      color: var(--muted);
    }}
    .flow-svg {{
      width: 100%;
      max-width: 840px;
      overflow-x: auto;
    }}
    .flow-svg svg {{
      width: 100%;
      height: auto;
      display: block;
    }}
    .fig-caption {{
      font-family: Arial, Helvetica, sans-serif;
      font-size: 0.78rem;
      color: var(--muted);
      margin: 0.45rem 0 0;
      max-width: 52rem;
    }}
    .explainer {{
      font-family: Arial, Helvetica, sans-serif;
      font-size: 0.88rem;
      color: var(--ink-soft);
      max-width: 46rem;
      margin: 0 0 0.75rem;
      line-height: 1.5;
    }}

    /* ── scenario cards ────────────────────────────────────────────────────── */
    .scen-wrap {{
      padding: 1.1rem 1.25rem;
      border-bottom: 1px solid var(--rule);
    }}
    .scen-strip {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(13rem, 1fr));
      gap: 0.9rem;
    }}
    .scen-card {{
      padding: 0.8rem 1rem;
      background: var(--paper);
      border: 1px solid var(--rule);
      border-top: 3px solid;
    }}
    .scen-a {{ border-top-color: var(--violet); }}
    .scen-b {{ border-top-color: var(--violet-md); }}
    .scen-c {{ border-top-color: var(--icu); }}
    .scen-label {{
      font-size: 0.68rem;
      font-weight: 700;
      letter-spacing: 0.09em;
      text-transform: uppercase;
      color: var(--muted);
      margin: 0 0 0.4rem;
    }}
    .scen-pred {{
      font-size: 1.45rem;
      font-weight: 700;
      color: var(--ink);
      margin: 0 0 0.35rem;
      line-height: 1.1;
      letter-spacing: -0.02em;
    }}
    .scen-rule {{
      font-size: 0.82rem;
      color: var(--ink-soft);
      margin: 0;
      line-height: 1.45;
    }}

    /* ── snapshot ──────────────────────────────────────────────────────────── */
    .snapshot-grid {{
      padding: 1.1rem 1.25rem;
      border-bottom: 1px solid var(--rule);
    }}
    .snap-dl {{
      margin: 0;
      display: grid;
      grid-template-columns: minmax(8rem, 12rem) 1fr;
      gap: 0.4rem 1.25rem;
      font-size: 0.88rem;
      max-width: 52rem;
    }}
    .snap-dl dt {{ color: var(--muted); font-weight: 600; margin: 0; }}
    .snap-dl dd {{ margin: 0; line-height: 1.5; }}

    /* ── timeline ──────────────────────────────────────────────────────────── */
    .tl-wrap {{
      padding: 1.1rem 1.25rem;
      border-bottom: 1px solid var(--rule);
    }}
    .tl-list {{
      margin: 0;
      padding: 0;
      list-style: none;
    }}
    .tl-item {{
      display: grid;
      grid-template-columns: 7rem 1fr;
      gap: 0 1rem;
      padding: 0.42rem 0;
      border-bottom: 1px solid var(--rule);
      font-size: 0.88rem;
      align-items: baseline;
    }}
    .tl-item:last-child {{ border-bottom: none; }}
    .tl-date {{
      font-weight: 700;
      color: var(--violet);
      white-space: nowrap;
      font-size: 0.82rem;
    }}
    .tl-event {{ color: var(--ink); line-height: 1.45; }}

    /* ── decision tree ─────────────────────────────────────────────────────── */
    .dt-wrap {{
      padding: 1.1rem 1.25rem 1.25rem;
    }}
    .dt-scroll {{
      overflow-x: auto;
      -webkit-overflow-scrolling: touch;
      margin-top: 0.5rem;
    }}
    .dt-table {{
      width: 100%;
      min-width: 34rem;
      font-family: Arial, Helvetica, sans-serif;
      border-collapse: collapse;
      font-size: 0.88rem;
    }}
    .dt-table thead th {{
      font-family: Arial, Helvetica, sans-serif;
      font-size: 0.65rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
      font-weight: 700;
      text-align: left;
      padding: 0.55rem 0.6rem 0.45rem 0;
      border-bottom: 2px solid var(--ink);
      background: var(--paper);
    }}
    .dt-table th.dt-num {{ width: 2.5rem; }}
    .dt-table th.dt-if-h {{ width: 30%; }}
    .dt-table th.dt-why-h {{ width: 28%; }}
    .dt-table tbody tr {{ border-bottom: 1px solid var(--rule); }}
    .dt-table tbody tr:last-child {{ border-bottom: none; }}
    .dt-table tbody td, .dt-table tbody th {{
      font-family: Arial, Helvetica, sans-serif;
      padding: 0.7rem 0.6rem 0.7rem 0;
      vertical-align: top;
      line-height: 1.45;
    }}
    .dt-table .dt-num {{ color: var(--muted); font-weight: 700; }}
    .dt-table .dt-if {{ font-weight: 600; }}
    .dt-table .dt-why {{ font-size: 0.82rem; color: var(--ink-soft); }}
    tr.dt-d1 .dt-if {{ padding-left: 1.1rem; border-left: 3px solid #d9d9d9; }}
    tr.dt-d2 .dt-if {{ padding-left: 2.2rem; border-left: 3px solid #efefef; }}

    /* ── R0 panel ──────────────────────────────────────────────────────────── */
    .r0-inner {{
      display: grid;
      gap: 1.25rem;
    }}
    @media (min-width: 700px) {{
      .r0-inner {{ grid-template-columns: 1fr 1fr; }}
    }}
    .metrics-dl {{
      margin: 0;
      display: grid;
      grid-template-columns: auto 1fr;
      gap: 0.35rem 1rem;
      font-size: 0.88rem;
    }}
    .metrics-dl dt {{ color: var(--muted); font-weight: 600; margin: 0; }}
    .metrics-dl dd {{ margin: 0; }}
    .callout {{
      background: var(--violet-lt);
      border-left: 4px solid var(--violet);
      padding: 0.7rem 1rem;
      margin: 0.85rem 0 0;
      font-size: 0.88rem;
    }}

    /* ── generic data table ────────────────────────────────────────────────── */
    table.data {{
      width: 100%;
      border-collapse: collapse;
      font-family: Arial, Helvetica, sans-serif;
      font-size: 0.86rem;
    }}
    table.data caption {{
      font-family: Arial, Helvetica, sans-serif;
      text-align: left;
      font-size: 0.7rem;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: var(--muted);
      margin-bottom: 0.5rem;
    }}
    table.data th, table.data td {{
      font-family: Arial, Helvetica, sans-serif;
      border-bottom: 1px solid var(--rule);
      padding: 0.5rem 0.35rem;
      vertical-align: top;
      text-align: left;
    }}
    table.data thead th {{
      font-family: Arial, Helvetica, sans-serif;
      font-size: 0.68rem;
      text-transform: uppercase;
      letter-spacing: 0.07em;
      color: var(--muted);
      font-weight: 700;
      border-bottom: 2px solid var(--ink);
    }}
    table.data tbody th {{ font-weight: 600; }}
    .table-scroll-wrap {{ overflow-x: auto; -webkit-overflow-scrolling: touch; }}

    /* ── sources list ──────────────────────────────────────────────────────── */
    .sources-ul {{
      margin: 0;
      padding: 0;
      list-style: none;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));
      gap: 0.5rem;
      font-size: 0.88rem;
    }}
    .sources-ul li a {{
      display: block;
      padding: 0.5rem 0.65rem;
      border: 1px solid var(--rule);
      background: var(--paper);
      color: var(--violet-dk);
      text-decoration: none;
    }}
    .sources-ul li a:hover {{ background: var(--violet-lt); }}

    /* ── footer ────────────────────────────────────────────────────────────── */
    footer {{
      border-top: 1px solid var(--rule);
      padding: 1rem 1.5rem 2rem;
      font-size: 0.8rem;
      color: var(--muted);
      max-width: 1100px;
      margin: 0 auto;
    }}
    footer p {{ margin: 0.25rem 0; }}
    footer ul {{ margin: 0.5rem 0 0; padding-left: 1.1rem; }}
  </style>
</head>
<body>
  <a class="skip" href="#main">Skip to main content</a>
  <header class="page-header">
    <p class="page-kicker">Zoonotic &amp; person-to-person context</p>
    <h1 class="page-title">Hantavirus Tracker</h1>
    <p class="page-sub">
      <strong>May 2026 cruise-ship cluster</strong> &mdash; population flow diagram,
      decision tree, and 28-day scenarios from ECDC&rsquo;s preliminary assessment.
      Below: historical outbreak table and literature-based R&#x2080; context.
      Page auto-refreshes every 24 h; rebuild the HTML daily to update the timestamp.
    </p>
  </header>

  <main id="main">

    {cruise_html}

    <section class="panel" aria-labelledby="r0-heading">
      <h2 class="panel-title" id="r0-heading">R&#x2080; &amp; Spread Speed</h2>
      <div class="r0-inner">
        <div>
          <p style="margin:0 0 0.7rem;font-size:0.92rem;">
            Orthohantaviruses are primarily <strong>rodent-borne</strong>.
            Person-to-person transmission is documented for
            <strong>Andes virus</strong> under close-contact conditions.
            Sin&nbsp;Nombre&ndash;type HPS in the U.S. is treated as
            a dead-end zoonotic spillover.
          </p>
          <dl class="metrics-dl">
            <dt>Andes (pre-control)</dt>
            <dd><strong>{r_pre:g}</strong> &mdash; median R, Epu&yacute;n 2018&ndash;19</dd>
            <dt>Andes (post-control)</dt>
            <dd><strong>{r_post:g}</strong> &mdash; after isolation &amp; quarantine</dd>
            <dt>Doubling (illustrative)</dt>
            <dd>~{int(g)}-day generations at R={r_pre:g} &rarr; scale &asymp; <strong>{html_escape(td_s)}</strong></dd>
            <dt>Sin Nombre (U.S. HPS)</dt>
            <dd>Human-to-human R &asymp; <strong>0</strong> for sustained spread</dd>
          </dl>
          <div class="callout">
            <strong>Source:</strong>
            Martinez et al., NEJM 2020 &mdash;
            <a href="{html_escape(rref["andes_url"])}">Andes person-to-person transmission</a>.
            R values describe the Epu&yacute;n outbreak, not a global constant.
          </div>
        </div>
        <div>
          <p style="margin:0 0 0.5rem;font-size:0.88rem;">
            Crude geometric branching from a seed of <strong>{seed}</strong> index cases;
            ~<strong>{int(g)}</strong>-day generation interval. Illustrative only.
          </p>
          <table class="data">
            <caption>Cumulative modeled infections by generation</caption>
            <thead>
              <tr>
                <th scope="col">Gen.</th>
                <th scope="col">Days elapsed</th>
                <th scope="col">Cumulative (crude)</th>
              </tr>
            </thead>
            <tbody>
              {proj_rows_s}
            </tbody>
          </table>
        </div>
      </div>
    </section>

    <section class="panel" aria-labelledby="sources-heading">
      <h2 class="panel-title" id="sources-heading">Public Sources to Monitor</h2>
      <p style="margin:0 0 0.75rem;font-size:0.88rem;">
        No single live API covers all orthohantavirus events.
        Use these official feeds; edit <code>data/outbreaks.json</code> and rebuild when new data arrive.
      </p>
      <ul class="sources-ul">
        <li><a href="https://www.who.int/emergencies/disease-outbreak-news/item/2026-DON599">WHO DON599 &mdash; MV Hondius cluster (4 May 2026)</a></li>
        <li><a href="https://www.ecdc.europa.eu/en/publications-data/hantavirus-associated-cluster-illness-cruise-ship-ecdc-assessment-and">ECDC &mdash; Cruise ship cluster assessment (6 May 2026)</a></li>
        <li><a href="https://www.cdc.gov/hantavirus/hps/index.html">CDC &mdash; HPS overview</a></li>
        <li><a href="https://www.ecdc.europa.eu/en/infectious-disease-topics/hantavirus-infection">ECDC &mdash; Hantavirus factsheet</a></li>
        <li><a href="https://www.who.int/emergencies/disease-outbreak-news">WHO &mdash; Disease Outbreak News (all)</a></li>
        <li><a href="https://www.paho.org/en/topics/hantavirus">PAHO &mdash; Hantavirus Americas</a></li>
        <li><a href="https://promedmail.org/">ProMED-mail (search &ldquo;hantavirus&rdquo;)</a></li>
      </ul>
    </section>

    <section class="panel" aria-labelledby="table-heading">
      <h2 class="panel-title" id="table-heading">Historical Outbreak Table</h2>
      <div class="table-scroll-wrap">
        <table class="data">
          <caption>Curated events and sources</caption>
          <thead>
            <tr>
              <th scope="col">Event</th>
              <th scope="col">Country</th>
              <th scope="col">Year</th>
              <th scope="col">Cases</th>
              <th scope="col">Deaths</th>
              <th scope="col">Virus / syndrome</th>
              <th scope="col">Source</th>
            </tr>
          </thead>
          <tbody>
            {table_body}
          </tbody>
        </table>
      </div>
    </section>

  </main>

  <footer>
    <p><strong>Built:</strong> {html_escape(built)}</p>
    <p><strong>R&#x2080; citation:</strong>
      <a href="{html_escape(rref["andes_url"])}">Martinez et al., NEJM &mdash; Andes person-to-person transmission</a>.
    </p>
    <p><strong>CDC transmission:</strong>
      <a href="{html_escape(rref["sin_nombre_url"])}">HPS transmission overview</a>.
    </p>
    {"<p><strong>Network check:</strong> " + html_escape(network_note) + "</p>" if network_note else ""}
    <ul>
      <li>Daily browser reload set to 24 h; data refresh requires running <code>scripts/build_tracker.py</code>.</li>
      <li>Not medical advice; consult public health authorities for outbreak response.</li>
    </ul>
  </footer>
</body>
</html>
"""

    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"Wrote {OUT_HTML}")


if __name__ == "__main__":
    main()
