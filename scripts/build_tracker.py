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
    Three-column flow diagram: HEAD → SPLIT → OUTCOMES.
    Legend is rendered as HTML below the SVG (see build_cruise_section).
    Bar heights are VISUAL — not proportional to population size.

    Layout philosophy
    -----------------
    • Wide column gaps (232 px HEAD→SPLIT, 192 px SPLIT→OUTCOMES) give each
      label column plenty of horizontal breathing room.
    • H_out=290 means the smallest outcome segment (1 case = 1/8 of 290 ≈ 36 px)
      can still hold two lines of text without overlap.
    • Outcome labels adapt: 3 lines when segment ≥ 60 px, 2 lines otherwise.
    • The top ≈ 270 px of the right column is reserved for the muted contacts
      monitoring note, well above the outcome band which starts at y≈278.
    """
    ship      = int(sk["ship_n"])
    cluster_n = int(sk["cluster_n"])
    contacts_n = int(sk["contacts_n"])
    outcomes  = sk["outcomes"]
    if sum(int(o["count"]) for o in outcomes) != cluster_n:
        raise ValueError("outcome counts must sum to cluster_n")

    W, H = 900, 630
    BAR  = 18
    F    = 'font-family="Arial,Helvetica,sans-serif"'

    # ── column x edges ────────────────────────────────────────────────────────
    x0l, x0r = 60.0, 78.0    # HEAD bar   (label starts at 94)
    x1l, x1r = 310.0, 328.0  # SPLIT bar  (232 px gap → 200 px HEAD label room)
    x2l, x2r = 520.0, 538.0  # OUTCOMES bar (192 px gap → 170 px SPLIT label room)
    #                           right label area: 554 → 890 (336 px — very spacious)

    # ── vertical layout ───────────────────────────────────────────────────────
    y_c0, y_c1 = 80.0, 270.0   # contacts band: 190 px visual
    y_k0, y_k1 = 278.0, 360.0  # cluster band:   82 px visual
    # outcome fan: 290 px total → 1 case = 36.25 px (fits 2 text lines)
    H_out = 290.0

    out_segs: list[tuple[float, float, dict]] = []
    y_cur = y_k0
    for o in outcomes:
        frac = int(o["count"]) / cluster_n
        out_segs.append((y_cur, y_cur + H_out * frac, o))
        y_cur += H_out * frac

    # ── ribbons ───────────────────────────────────────────────────────────────
    def ribbon(xa, xb, ya0, ya1, yb0, yb1, fill, op=0.80):
        d = _cubic_ribbon(xa, xb, ya0, ya1, yb0, yb1)
        return f'<path d="{d}" fill="{fill}" fill-opacity="{op:.2f}"/>'

    # HEAD → SPLIT: contacts pass-through + cluster pass-through
    ribs = [
        ribbon(x0r, x1l, y_c0, y_c1, y_c0, y_c1, "#e5dff4"),
        ribbon(x0r, x1l, y_k0, y_k1, y_k0, y_k1, "#d8d0ee"),
    ]
    # SPLIT → OUTCOMES: cluster fans out to each outcome band
    y_src = y_k0
    for y_a, y_b, o in out_segs:
        frac  = int(o["count"]) / cluster_n
        src_h = (y_k1 - y_k0) * frac
        ribs.append(ribbon(x1r, x2l, y_src, y_src + src_h, y_a, y_b, o["color"], 0.28))
        y_src += src_h
    ribs_s = "\n    ".join(ribs)

    # ── bars ──────────────────────────────────────────────────────────────────
    def rect(xl, y0, h, col):
        return (f'<rect x="{xl:.1f}" y="{y0:.2f}" width="{BAR}" '
                f'height="{h:.2f}" fill="{col}" rx="2"/>')

    pax   = int(sk.get("passengers_n", 88))
    crew  = int(sk.get("crew_n", 59))
    pax_h  = (y_c1 - y_c0) * pax  / ship
    crew_h = (y_c1 - y_c0) * crew / ship

    bars = [
        rect(x0l, y_c0,          pax_h,       "#57068c"),  # pax (HEAD)
        rect(x0l, y_c0 + pax_h,  crew_h,      "#9b5ec4"),  # crew (HEAD)
        rect(x0l, y_k0, y_k1-y_k0,            "#7b3aac"),  # cluster (HEAD)
        rect(x1l, y_c0, y_c1-y_c0,            "#57068c"),  # contacts (SPLIT)
        rect(x1l, y_k0, y_k1-y_k0,            "#7b3aac"),  # cluster (SPLIT)
    ]
    for y_a, y_b, o in out_segs:
        bars.append(rect(x2l, y_a, y_b - y_a, o["color"]))
    bars_s = "\n    ".join(bars)

    # ── text helpers ──────────────────────────────────────────────────────────
    LH = 14.0

    def txt(x, y, t, w="400", c="#121212", sz="10"):
        return (f'<text {F} font-size="{sz}px" font-weight="{w}" '
                f'fill="{c}" x="{x:.1f}" y="{y:.1f}">{esc(str(t))}</text>')

    def block(x, yc, rows):
        n  = len(rows)
        y0 = yc - n * LH / 2 + LH * 0.85
        return "\n    ".join(
            txt(x, y0 + i * LH, t, w, c, sz)
            for i, (t, w, c, sz) in enumerate(rows)
        )

    nat_note  = sk.get("nationalities_note", "23 nationalities")
    nat_short = nat_note.split(":")[1].strip() if ":" in nat_note else nat_note

    lbls = []

    # ── HEAD label (col0, right) — generous 200 px horizontal room ────────────
    lbls.append(block(x0r + 16, (y_c0 + y_k1) / 2, [
        (f"{ship} aboard",                     "700", "#121212", "11"),
        (f"{pax} pax \u00b7 {crew} crew",      "400", "#444",   "10"),
        (nat_short,                            "400", "#57068c", "8.5"),
        (f"EWRS: {sk['ewrs_notification']}",   "400", "#bbb",   "8"),
        (f"ECDC: {sk['ecdc_assessment']}",     "400", "#bbb",   "8"),
    ]))

    # ── SPLIT contacts label (col1, right, upper band) ────────────────────────
    lbls.append(block(x1r + 16, (y_c0 + y_c1) / 2, [
        ("Contacts",              "700", "#121212", "11"),
        (f"n = {contacts_n}",     "400", "#121212", "10"),
        ("Precautionary pool",    "400", "#5a5a5a", "9"),
        ("Predict: not infected", "400", "#57068c", "9"),
    ]))

    # ── SPLIT cluster label (col1, right, lower band) ─────────────────────────
    lbls.append(block(x1r + 16, (y_k0 + y_k1) / 2, [
        ("Cluster",                       "700", "#121212", "11"),
        (f"n = {cluster_n} \u00b7 5 PCR+","400", "#121212", "10"),
        ("Predict: ANDV",                 "700", "#8b1a1a", "9"),
    ]))

    # ── OUTCOMES contacts-end label (col2, right, upper band — muted) ─────────
    lbls.append(block(x2r + 16, (y_c0 + y_c1) / 2, [
        ("Under monitoring",       "700", "#bbb",  "10"),
        (f"n = {contacts_n}",      "400", "#bbb",  "9"),
        ("No infections confirmed","400", "#ccc",  "8.5"),
        ("as of 7 May 2026",       "400", "#ccc",  "8.5"),
    ]))

    # ── OUTCOMES outcome labels (col2, right, outcome bands) ──────────────────
    # Adaptive: 3 lines when segment ≥ 60 px, 2 lines for smaller segments
    for y_a, y_b, o in out_segs:
        seg_h    = y_b - y_a
        mid      = (y_a + y_b) / 2
        nat      = o.get("nat", "")
        nat_code = o.get("nat_code", "")
        detail   = o.get("detail", "")
        bar_col  = o["color"]
        nat_disp = f"{nat} [{nat_code}]" if nat else nat_code
        lbl_line = f"{o['label']} \u00b7 {int(o['count'])}"

        if seg_h >= 60:
            lh = 13.0
            y0 = mid - lh + lh * 0.15
            lbls.append(
                txt(x2r+16, y0,       lbl_line, "700", "#121212", "10")
                + "\n    " +
                txt(x2r+16, y0+lh,    nat_disp, "700", bar_col,   "10")
                + "\n    " +
                txt(x2r+16, y0+lh*2,  detail,   "400", "#666",    "8.5")
            )
        else:
            lh = 12.0
            y0 = mid - lh * 0.5 + lh * 0.1
            lbls.append(
                txt(x2r+16, y0,    lbl_line, "700", "#121212", "9.5")
                + "\n    " +
                txt(x2r+16, y0+lh, nat_disp, "700", bar_col,   "9.5")
            )

    lbls_s = "\n    ".join(lbls)

    # ── column headers ────────────────────────────────────────────────────────
    col_info = [
        (x0l + BAR/2, "HEAD",     f"n = {ship}"),
        (x1l + BAR/2, "SPLIT",    "Contacts / Cluster"),
        (x2l + BAR/2, "OUTCOMES", "7 May 2026"),
    ]
    hdrs = []
    for cx, title, sub in col_info:
        hdrs += [
            f'<text {F} font-size="8.5px" font-weight="700" fill="#bbb" '
            f'text-anchor="middle" x="{cx:.1f}" y="47">{esc(title)}</text>',
            f'<text {F} font-size="8px" fill="#ccc" '
            f'text-anchor="middle" x="{cx:.1f}" y="59">{esc(sub)}</text>',
            f'<line x1="{cx:.1f}" y1="63" x2="{cx:.1f}" y2="73" '
            f'stroke="#ddd" stroke-width="1"/>',
        ]
    hdrs_s = "\n    ".join(hdrs)

    deaths_total = sum(int(o["count"]) for o in outcomes if o.get("is_death"))
    note = (
        f'<text {F} font-size="7.5px" fill="#ccc" x="8" y="{H-8}">'
        f'Bar heights are visual \u2014 not proportional. '
        f'{cluster_n}/{ship} = {cluster_n/ship*100:.1f}% case rate. '
        f'\u2020 = fatal.</text>'
    )

    title_txt = esc(
        f"MV Hondius: {ship} aboard, {cluster_n} cases, "
        f"{deaths_total} deaths \u2014 {sk['ecdc_assessment']}"
    )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'role="img" aria-label="{title_txt}">'
        f'<title>{title_txt}</title>'
        f'<rect width="{W}" height="{H}" fill="#f9f9f7"/>'
        f'<g>\n    {ribs_s}\n  </g>'
        f'<g>\n    {bars_s}\n  </g>'
        f'<g>\n    {hdrs_s}\n  </g>'
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
        svg_str  = build_sankey_svg(sk, esc)
        pax_sk   = int(sk.get("passengers_n", 88))
        crew_sk  = int(sk.get("crew_n", 59))

        def chip(color: str, label: str) -> str:
            return (
                f'<span class="nat-item">'
                f'<span class="nat-chip" style="background:{color}"></span>'
                f'{esc(label)}'
                f'</span>'
            )

        leg_items = [
            chip("#57068c", f"Passengers ({pax_sk})"),
            chip("#9b5ec4", f"Crew ({crew_sk})"),
            '<span class="nat-div"></span>',
        ]
        for o in sk["outcomes"]:
            nat   = o.get("nat", o["label"])
            code  = o.get("nat_code", "")
            cnt   = int(o["count"])
            sfx   = " \u2020" if o.get("is_death") else ""
            olbl  = o["label"].lower()
            leg_items.append(chip(o["color"], f"{nat} [{code}] \u00b7 {cnt}{sfx} \u2014 {olbl}"))

        legend_html = (
            f'<div class="nat-legend" aria-label="Colour legend">'
            f'{"".join(leg_items)}'
            f'</div>'
        )

        svg_block = f"""
      <div class="flow-wrap" role="region" aria-labelledby="flow-heading">
        <h3 class="section-label" id="flow-heading">Population flow &amp; outcomes</h3>
        <div class="flow-svg">{svg_str}</div>
        <p class="fig-caption">
          Ribbon widths reflect ECDC counts: {esc(str(sk['contacts_n']))} contacts
          vs. {cluster_n} cluster cases. Bar heights are visual only.
        </p>
        {legend_html}
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
    /* ── nationality / outcome legend (HTML, below SVG) ───────────────────── */
    .nat-legend {{
      font-family: Arial, Helvetica, sans-serif;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 0.25rem 1rem;
      margin-top: 0.7rem;
      padding-top: 0.55rem;
      border-top: 1px solid var(--rule);
      font-size: 0.75rem;
      color: var(--ink-soft);
    }}
    .nat-item {{
      display: flex;
      align-items: center;
      gap: 5px;
      white-space: nowrap;
    }}
    .nat-chip {{
      display: inline-block;
      width: 10px;
      height: 10px;
      border-radius: 2px;
      flex-shrink: 0;
    }}
    .nat-div {{
      width: 1px;
      height: 1em;
      background: var(--rule);
      margin: 0 0.25rem;
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
