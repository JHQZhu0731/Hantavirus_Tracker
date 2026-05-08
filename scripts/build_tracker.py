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
DATA_PATH  = ROOT / "data" / "outbreaks.json"
CRUISE_PATH = ROOT / "data" / "cruise_outbreak_2026.json"
OUT_HTML   = ROOT / "index.html"
OUT_HTML_ZH = ROOT / "zh" / "index.html"

# ── translated outcome / nationality labels ───────────────────────────────────
_OUTCOME_ZH: dict[str, str] = {
    "Fatal":         "死亡",
    "ICU":           "重症监护",
    "Transferred":   "转运",
    "Post-disembark":"下船后确诊",
}
_NAT_ZH: dict[str, str] = {
    "Netherlands":    "荷兰",
    "Germany":        "德国",
    "United Kingdom": "英国",
    "Nationality TBC":"国籍待定",
    "Switzerland":    "瑞士",
}

# ── UI string tables ──────────────────────────────────────────────────────────
STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "html_lang":       "en",
        "page_title_full": "Hantavirus Tracker \u2014 2026 cruise cluster &amp; R\u2080 context",
        "meta_desc":       "ECDC-sourced flow diagram and decision tree for the 2026 cruise-ship hantavirus cluster, plus R\u2080 data and historical outbreak table.",
        "skip":            "Skip to main content",
        "kicker":          "Zoonotic &amp; person-to-person context",
        "page_title":      "Hantavirus Tracker",
        "page_sub":        ("<strong>May\u202026 cruise-ship cluster</strong> &mdash; population flow diagram, "
                            "decision tree, and 45-day scenarios from ECDC&rsquo;s preliminary assessment. "
                            "Below: historical outbreak table and literature-based R&#x2080; context. "
                            "Page auto-refreshes every hour."),
        "switch_label":    "中文版",
        "switch_href_en":  "zh/index.html",
        "switch_href_zh":  "../index.html",
        "stat_aboard":     "Aboard",
        "stat_cases":      "Cases",
        "stat_deaths":     "Deaths",
        "stat_cfr":        "Case fatality",
        "flow_heading":    "Population flow &amp; outcomes",
        "fig_cap":         "Ribbon widths reflect ECDC counts: {cn} contacts vs. {kn} cluster cases. Bar heights are visual only.",
        "svg_head":        "HEAD",
        "svg_split":       "SPLIT",
        "svg_outcomes":    "OUTCOMES",
        "svg_split_sub":   "Contacts / Cluster",
        "contacts_lbl":    "Contacts",
        "contacts_p1":     "Precautionary pool",
        "contacts_p2":     "Predict: not infected",
        "cluster_lbl":     "Cluster",
        "cluster_p1":      "Predict: ANDV",
        "monitor_lbl":     "Under monitoring",
        "monitor_p1":      "No infections confirmed",
        "monitor_p2":      "as of 7 May 2026",
        "pax_lbl":         "pax",
        "crew_lbl":        "crew",
        "leg_pax":         "Passengers",
        "leg_crew":        "Crew",
        "scen_hz":         "{hz}-day cumulative infection scenarios",
        "scen_note":       "(illustrative \u2014 not ECDC/WHO forecasts)",
        "tl_heading":      "Outbreak timeline",
        "snap_heading":    "Situation snapshot",
        "snap_notif":      "Notification",
        "snap_vessel":     "Vessel",
        "snap_itinerary":  "Itinerary",
        "snap_persons":    "Persons aboard",
        "snap_counts":     "Cases (7 May)",
        "snap_lab":        "Laboratory",
        "snap_index":      "Index cases",
        "snap_hypo":       "Working hypothesis",
        "snap_risk":       "Population risk",
        "dt_heading":      "Decision tree for investigators and clinicians",
        "dt_explainer":    ("Each row is one branch: <em>if</em> the signal applies, take the control step. "
                            "Teaching schematic from ECDC&rsquo;s preliminary assessment &mdash; not a substitute "
                            "for national protocols or shipboard medical orders."),
        "dt_col_num":      "#",
        "dt_col_if":       "If you see\u2026",
        "dt_col_then":     "Then do\u2026",
        "dt_col_why":      "ECDC framing",
        "r0_heading":      "R&#x2080; &amp; Spread Speed",
        "r0_intro":        ("Orthohantaviruses are primarily <strong>rodent-borne</strong>. "
                            "Person-to-person transmission is documented for "
                            "<strong>Andes virus</strong> under close-contact conditions. "
                            "Sin&nbsp;Nombre&ndash;type HPS in the U.S. is treated as a dead-end zoonotic spillover."),
        "r0_pre_lbl":      "Andes (pre-control)",
        "r0_post_lbl":     "Andes (post-control)",
        "r0_dbl_lbl":      "Doubling (illustrative)",
        "r0_snv_lbl":      "Sin Nombre (U.S. HPS)",
        "r0_pre_val":      "<strong>{rp:g}</strong> &mdash; median R, Epu&yacute;n 2018&ndash;19",
        "r0_post_val":     "<strong>{ro:g}</strong> &mdash; after isolation &amp; quarantine",
        "r0_dbl_val":      "~{g}-day generations at R={rp:g} &rarr; scale &asymp; <strong>{td}</strong>",
        "r0_snv_val":      "Human-to-human R &asymp; <strong>0</strong> for sustained spread",
        "r0_src":          "Source",
        "r0_src_txt":      "Martinez et al., NEJM 2020 &mdash; Andes person-to-person transmission",
        "r0_src_note":     "R values describe the Epu&yacute;n outbreak, not a global constant.",
        "r0_proj_intro":   "Crude geometric branching from a seed of <strong>{seed}</strong> index cases; ~<strong>{g}</strong>-day generation interval. Illustrative only.",
        "r0_proj_cap":     "Cumulative modeled infections by generation",
        "r0_col_gen":      "Gen.",
        "r0_col_days":     "Days elapsed",
        "r0_col_cum":      "Cumulative (crude)",
        "src_heading":     "Public Sources to Monitor",
        "src_intro":       "No single live API covers all orthohantavirus events. Use these official feeds; edit <code>data/outbreaks.json</code> and rebuild when new data arrive.",
        "tbl_heading":     "Historical Outbreak Table",
        "tbl_caption":     "Curated events and sources",
        "tbl_event":       "Event",
        "tbl_country":     "Country",
        "tbl_year":        "Year",
        "tbl_cases":       "Cases",
        "tbl_deaths":      "Deaths",
        "tbl_virus":       "Virus / syndrome",
        "tbl_source":      "Source",
        "ft_built":        "Built",
        "ft_r0_lbl":       "R&#x2080; citation",
        "ft_r0_txt":       "Martinez et al., NEJM &mdash; Andes person-to-person transmission",
        "ft_cdc_lbl":      "CDC transmission",
        "ft_cdc_txt":      "HPS transmission overview",
        "ft_refresh":      "Hourly browser reload; data refresh requires running <code>scripts/build_tracker.py</code>.",
        "ft_disclaimer":   "Not medical advice; consult public health authorities for outbreak response.",
    },
    "zh": {
        "html_lang":       "zh-Hans",
        "page_title_full": "汉坦病毒追踪器 \u2014 2026年游轮群聚事件",
        "meta_desc":       "基于欧洲疾控中心评估的2026年游轮汉坦病毒群聚事件人口流向图与决策树，附基本再生数及历史疫情汇总。",
        "skip":            "跳至主要内容",
        "kicker":          "人畜共患与人传人背景",
        "page_title":      "汉坦病毒追踪器",
        "page_sub":        ("<strong>2026年游轮群聚事件</strong> &mdash; 人口流向图、"
                            "决策树及欧洲疾控中心初步评估的45天情景预测。"
                            "下方：历史疫情汇总表与文献基本再生数（R&#x2080;）背景。"
                            "页面每小时自动刷新。"),
        "switch_label":    "English",
        "switch_href_en":  "zh/index.html",
        "switch_href_zh":  "../index.html",
        "stat_aboard":     "在船人数",
        "stat_cases":      "病例数",
        "stat_deaths":     "死亡数",
        "stat_cfr":        "病死率",
        "flow_heading":    "人口流向图与结局",
        "fig_cap":         "色带宽度反映欧洲疾控中心计数：{cn}名接触者对比{kn}例群聚病例。柱状高度仅为视觉表示。",
        "svg_head":        "总体",
        "svg_split":       "分组",
        "svg_outcomes":    "结局",
        "svg_split_sub":   "接触者 / 病例群",
        "contacts_lbl":    "接触者",
        "contacts_p1":     "预防性隔离池",
        "contacts_p2":     "预测：未感染",
        "cluster_lbl":     "病例群",
        "cluster_p1":      "预测：安第斯病毒",
        "monitor_lbl":     "监测中",
        "monitor_p1":      "暂无确诊感染",
        "monitor_p2":      "截至2026年5月7日",
        "pax_lbl":         "乘客",
        "crew_lbl":        "船员",
        "leg_pax":         "乘客",
        "leg_crew":        "船员",
        "scen_hz":         "{hz}天累计感染情景",
        "scen_note":       "（仅供参考 \u2014 非欧洲疾控中心/世卫组织预测）",
        "tl_heading":      "疫情时间轴",
        "snap_heading":    "情况快报",
        "snap_notif":      "通报",
        "snap_vessel":     "船舶",
        "snap_itinerary":  "行程",
        "snap_persons":    "在船人数",
        "snap_counts":     "病例（5月7日）",
        "snap_lab":        "实验室",
        "snap_index":      "指示病例",
        "snap_hypo":       "工作假说",
        "snap_risk":       "人群风险",
        "dt_heading":      "调查人员和临床医生决策树",
        "dt_explainer":    ("每行为一个分支：若信号符合，则执行控制步骤。"
                            "本示意图基于欧洲疾控中心初步评估 &mdash; 不可替代国家协议或船上医疗指令。"),
        "dt_col_num":      "序",
        "dt_col_if":       "若发现\u2026",
        "dt_col_then":     "则\u2026",
        "dt_col_why":      "欧洲疾控中心依据",
        "r0_heading":      "基本再生数（R&#x2080;）与传播速度",
        "r0_intro":        ("正汉坦病毒主要为<strong>啮齿动物传播</strong>。"
                            "已记录<strong>安第斯病毒</strong>在密切接触条件下可发生人传人传播。"
                            "美国无名病毒（Sin Nombre）型HPS视为死端人畜共患溢出。"),
        "r0_pre_lbl":      "安第斯（干预前）",
        "r0_post_lbl":     "安第斯（干预后）",
        "r0_dbl_lbl":      "倍增时间（示意）",
        "r0_snv_lbl":      "无名病毒（美国HPS）",
        "r0_pre_val":      "<strong>{rp:g}</strong> &mdash; 埃普延2018–19年中位R值",
        "r0_post_val":     "<strong>{ro:g}</strong> &mdash; 隔离与检疫后",
        "r0_dbl_val":      "约{g}天一代，R={rp:g} &rarr; 规模约 &asymp; <strong>{td}</strong>",
        "r0_snv_val":      "持续人传人R &asymp; <strong>0</strong>",
        "r0_src":          "来源",
        "r0_src_txt":      "Martinez等，《新英格兰医学杂志》2020年 &mdash; 安第斯病毒人传人传播",
        "r0_src_note":     "R值描述埃普延疫情，非全球常数。",
        "r0_proj_intro":   "以<strong>{seed}</strong>个指示病例为种子的粗略几何分支；约<strong>{g}</strong>天一代；仅供参考。",
        "r0_proj_cap":     "按代次累计模型感染数",
        "r0_col_gen":      "代次",
        "r0_col_days":     "已过天数",
        "r0_col_cum":      "累计（粗略）",
        "src_heading":     "监测数据来源",
        "src_intro":       "目前无单一实时API覆盖全部正汉坦病毒事件。请使用以下官方渠道；有新数据时编辑<code>data/outbreaks.json</code>并重新构建。",
        "tbl_heading":     "历史疫情汇总表",
        "tbl_caption":     "精选事件与来源",
        "tbl_event":       "事件",
        "tbl_country":     "国家/地区",
        "tbl_year":        "年份",
        "tbl_cases":       "病例数",
        "tbl_deaths":      "死亡数",
        "tbl_virus":       "病毒/综合征",
        "tbl_source":      "来源",
        "ft_built":        "构建时间",
        "ft_r0_lbl":       "R&#x2080; 引用",
        "ft_r0_txt":       "Martinez等，《新英格兰医学杂志》 &mdash; 安第斯病毒人传人传播",
        "ft_cdc_lbl":      "美国疾控中心传播说明",
        "ft_cdc_txt":      "HPS传播概述",
        "ft_refresh":      "每小时浏览器自动刷新；需重新运行<code>scripts/build_tracker.py</code>以更新数据。",
        "ft_disclaimer":   "本页面不构成医疗建议；请咨询当地公共卫生机构进行疫情应对。",
    },
}


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


def build_sankey_svg(sk: dict, esc, S: dict, lang: str = "en") -> str:
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

    # Build a compact nationality string that fits in the ~200 px HEAD label zone.
    # e.g. "23 nationalities: NL · GB · DE · CH · ES · BE ..." → "NL · GB · DE · CH · ES + 18 more"
    nat_note = sk.get("nationalities_note", "")
    try:
        total_nat = int("".join(c for c in nat_note.split(":")[0] if c.isdigit()))
        raw       = nat_note.split(": ", 1)[1] if ": " in nat_note else nat_note
        codes     = [p.strip() for p in raw.split(" \u00b7 ") if 2 <= len(p.strip()) <= 3]
        shown     = 5
        nat_disp  = " \u00b7 ".join(codes[:shown])
        if total_nat > shown:
            nat_disp += f" + {total_nat - shown} more"
    except (ValueError, IndexError):
        nat_disp = nat_note[:40] if nat_note else "23 nationalities"

    lbls = []

    aboard_lbl = S.get("stat_aboard", "Aboard")
    pax_word   = S["pax_lbl"]
    crew_word  = S["crew_lbl"]

    # ── HEAD label (col0, right) — generous 200 px horizontal room ────────────
    lbls.append(block(x0r + 16, (y_c0 + y_k1) / 2, [
        (f"{ship} {aboard_lbl}",                           "700", "#121212", "11"),
        (f"{pax} {pax_word} \u00b7 {crew} {crew_word}",   "400", "#444",   "10"),
        (nat_disp,                                         "400", "#6a2fa0", "9"),
        (f"EWRS: {sk['ewrs_notification']}",               "400", "#bbb",   "8"),
        (f"ECDC: {sk['ecdc_assessment']}",                 "400", "#bbb",   "8"),
    ]))

    # ── SPLIT contacts label (col1, right, upper band) ────────────────────────
    lbls.append(block(x1r + 16, (y_c0 + y_c1) / 2, [
        (S["contacts_lbl"],       "700", "#121212", "11"),
        (f"n = {contacts_n}",     "400", "#121212", "10"),
        (S["contacts_p1"],        "400", "#5a5a5a", "9"),
        (S["contacts_p2"],        "400", "#57068c", "9"),
    ]))

    # ── SPLIT cluster label (col1, right, lower band) ─────────────────────────
    lbls.append(block(x1r + 16, (y_k0 + y_k1) / 2, [
        (S["cluster_lbl"],                "700", "#121212", "11"),
        (f"n = {cluster_n} \u00b7 5 PCR+","400", "#121212", "10"),
        (S["cluster_p1"],                 "700", "#8b1a1a", "9"),
    ]))

    # ── OUTCOMES contacts-end label (col2, right, upper band — muted) ─────────
    lbls.append(block(x2r + 16, (y_c0 + y_c1) / 2, [
        (S["monitor_lbl"],  "700", "#bbb",  "10"),
        (f"n = {contacts_n}","400", "#bbb", "9"),
        (S["monitor_p1"],   "400", "#ccc",  "8.5"),
        (S["monitor_p2"],   "400", "#ccc",  "8.5"),
    ]))

    # ── OUTCOMES outcome labels (col2, right, outcome bands) ──────────────────
    # Adaptive: 3 lines when segment ≥ 60 px, 2 lines for smaller segments
    for y_a, y_b, o in out_segs:
        seg_h    = y_b - y_a
        mid      = (y_a + y_b) / 2
        raw_lbl  = o["label"]
        lbl_str  = _OUTCOME_ZH.get(raw_lbl, raw_lbl) if lang == "zh" else raw_lbl
        nat      = o.get("nat", "")
        nat_code = o.get("nat_code", "")
        detail   = o.get("detail", "")
        bar_col  = o["color"]
        nat_str  = _NAT_ZH.get(nat, nat) if lang == "zh" else nat
        nat_disp = f"{nat_str} [{nat_code}]" if nat_str else nat_code
        lbl_line = f"{lbl_str} \u00b7 {int(o['count'])}"

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
        (x0l + BAR/2, S["svg_head"],     f"n = {ship}"),
        (x1l + BAR/2, S["svg_split"],    S["svg_split_sub"]),
        (x2l + BAR/2, S["svg_outcomes"], "7 May 2026"),
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

def build_cruise_section(c: dict, S: dict, lang: str = "en") -> str:
    esc = html_escape
    snap = c["situation_snapshot"]
    prim = c["primary_source"]
    sec = c.get("secondary_source", {})
    sk = c.get("sankey")

    # stat strip values
    ship      = int(sk["ship_n"])    if sk else 147
    cluster_n = int(sk["cluster_n"]) if sk else 8
    deaths    = sum(int(o["count"]) for o in sk["outcomes"] if o.get("is_death")) if sk else 3
    cfr_pct   = round(deaths / cluster_n * 100)

    sec_link = ""
    if sec:
        sec_link = (
            f'<p class="src-line">'
            f'<a href="{esc(sec["url"])}">{esc(sec["name"])}</a>'
            f'</p>'
        )

    svg_block = ""
    if sk:
        svg_str  = build_sankey_svg(sk, esc, S, lang)
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
            chip("#57068c", f"{S['leg_pax']} ({pax_sk})"),
            chip("#9b5ec4", f"{S['leg_crew']} ({crew_sk})"),
            '<span class="nat-div"></span>',
        ]
        for o in sk["outcomes"]:
            raw_nat = o.get("nat", o["label"])
            nat_l   = _NAT_ZH.get(raw_nat, raw_nat) if lang == "zh" else raw_nat
            raw_lbl = o["label"]
            lbl_l   = _OUTCOME_ZH.get(raw_lbl, raw_lbl) if lang == "zh" else raw_lbl
            code    = o.get("nat_code", "")
            cnt     = int(o["count"])
            sfx     = " \u2020" if o.get("is_death") else ""
            leg_items.append(chip(o["color"], f"{nat_l} [{code}] \u00b7 {cnt}{sfx} \u2014 {lbl_l}"))

        legend_html = (
            f'<div class="nat-legend" aria-label="Colour legend">'
            f'{"".join(leg_items)}'
            f'</div>'
        )

        fig_cap = S["fig_cap"].format(cn=sk["contacts_n"], kn=cluster_n)
        svg_block = f"""
      <div class="flow-wrap" role="region" aria-labelledby="flow-heading">
        <h3 class="section-label" id="flow-heading">{S['flow_heading']}</h3>
        <div class="flow-svg">{svg_str}</div>
        <p class="fig-caption">{fig_cap}</p>
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
            cls   = card_classes[i] if i < len(card_classes) else "scen-a"
            slbl  = s.get("label_zh", s["label"])  if lang == "zh" else s["label"]
            srule = s.get("rule_zh",  s["rule"])    if lang == "zh" else s["rule"]
            cards_html.append(
                f'<div class="scen-card {cls}">'
                f'<p class="scen-label">{esc(chr(65 + i))}. {esc(slbl)}</p>'
                f'<p class="scen-pred">{esc(s["predict"])}</p>'
                f'<p class="scen-rule">{esc(srule)}</p>'
                f'</div>'
            )
        cards_s = "\n        ".join(cards_html)
        scen_block = (
            f'<div class="scen-wrap">'
            f'<h3 class="section-label">{S["scen_hz"].format(hz=hz)} '
            f'<span class="label-note">{S["scen_note"]}</span></h3>'
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
            ev_text = evt.get("event_zh", evt["event"]) if lang == "zh" else evt["event"]
            items.append(
                f'<li class="tl-item">'
                f'<span class="tl-date">{esc(evt["date"])}</span>'
                f'<span class="tl-event">{esc(ev_text)}</span>'
                f'</li>'
            )
        timeline_html = (
            f'<div class="tl-wrap">'
            f'<h3 class="section-label">{S["tl_heading"]}</h3>'
            f'<ol class="tl-list">{"".join(items)}</ol>'
            f'</div>'
        )

    # Decision tree rows
    dt_rows = []
    for i, node in enumerate(c["decision_tree"], start=1):
        depth    = int(node["level"])
        pad      = 0.5 + depth * 1.1
        if_text  = node.get("if_zh",   node["if"])   if lang == "zh" else node["if"]
        then_text= node.get("then_zh", node["then"])  if lang == "zh" else node["then"]
        note_text= node.get("note_zh", node["note"])  if lang == "zh" else node["note"]
        dt_rows.append(
            f'<tr class="dt-d{depth}">'
            f'<th scope="row" class="dt-num">{i}</th>'
            f'<td class="dt-if" style="padding-left:{pad:.2f}rem">{esc(if_text)}</td>'
            f'<td class="dt-then">{esc(then_text)}</td>'
            f'<td class="dt-why">{esc(note_text)}</td>'
            f'</tr>'
        )
    dt_s = "\n          ".join(dt_rows)

    label_disp = c.get("label_zh", c["label"]) if lang == "zh" else c["label"]
    deck_disp  = c.get("deck_zh",  c["deck"])  if lang == "zh" else c["deck"]

    return f"""
  <section class="cruise-panel" aria-labelledby="cruise-heading">
    <div class="cruise-header">
      <p class="kicker-sm">MV Hondius · South Atlantic · May 2026</p>
      <h2 class="headline" id="cruise-heading">{esc(label_disp)}</h2>
      <p class="deck">{esc(deck_disp)}</p>
      <p class="src-line"><a href="{esc(prim["url"])}">{esc(prim["name"])}</a></p>
      {sec_link}
    </div>

    <div class="stat-strip" role="list" aria-label="Key figures">
      <div class="stat" role="listitem">
        <span class="stat-n">{ship}</span>
        <span class="stat-label">{S["stat_aboard"]}</span>
      </div>
      <div class="stat stat-cluster" role="listitem">
        <span class="stat-n">{cluster_n}</span>
        <span class="stat-label">{S["stat_cases"]}</span>
      </div>
      <div class="stat stat-fatal" role="listitem">
        <span class="stat-n">{deaths}</span>
        <span class="stat-label">{S["stat_deaths"]}</span>
      </div>
      <div class="stat stat-cfr" role="listitem">
        <span class="stat-n">{cfr_pct}%</span>
        <span class="stat-label">{S["stat_cfr"]}</span>
      </div>
    </div>
    {svg_block}
    {scen_block}

    {timeline_html}

    <div class="snapshot-grid">
      <div class="snapshot-block">
        <h3 class="section-label">{S["snap_heading"]}</h3>
        <dl class="snap-dl">
          <dt>{S["snap_notif"]}</dt><dd>{esc(snap.get("notification",""))}</dd>
          <dt>{S["snap_vessel"]}</dt><dd>{esc(snap.get("vessel", snap.get("setting","—")))}</dd>
          <dt>{S["snap_itinerary"]}</dt><dd>{esc(snap.get("itinerary","—"))}</dd>
          <dt>{S["snap_persons"]}</dt><dd>{esc(snap.get("persons_aboard","—"))}</dd>
          <dt>{S["snap_counts"]}</dt><dd>{esc(snap.get("counts_as_of_7_may", snap.get("counts_as_of_6_may","—")))}</dd>
          <dt>{S["snap_lab"]}</dt><dd>{esc(snap.get("laboratory",""))}</dd>
          <dt>{S["snap_index"]}</dt><dd>{esc(snap.get("index_cases","—"))}</dd>
          <dt>{S["snap_hypo"]}</dt><dd>{esc(snap.get("working_hypothesis",""))}</dd>
          <dt>{S["snap_risk"]}</dt><dd>{esc(snap.get("risk_eu_population",""))}</dd>
        </dl>
      </div>
    </div>

    <div class="dt-wrap">
      <h3 class="section-label">{S["dt_heading"]}</h3>
      <p class="explainer">{S["dt_explainer"]}</p>
      <div class="dt-scroll" role="region" aria-label="Decision tree" tabindex="0">
        <table class="dt-table">
          <thead>
            <tr>
              <th scope="col" class="dt-num">{S["dt_col_num"]}</th>
              <th scope="col" class="dt-if-h">{S["dt_col_if"]}</th>
              <th scope="col">{S["dt_col_then"]}</th>
              <th scope="col" class="dt-why-h">{S["dt_col_why"]}</th>
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

def build_table_rows(outbreaks: list, lang: str = "en") -> str:
    rows = []
    for o in outbreaks:
        cases    = o.get("cases")
        deaths   = o.get("deaths")
        cases_s  = f"{cases:,}"  if isinstance(cases, int)  else "\u2014"
        deaths_s = f"{deaths:,}" if isinstance(deaths, int) else "\u2014"
        raw_lbl  = o.get("label_zh", o.get("label", "")) if lang == "zh" else o.get("label", "")
        label    = html_escape(raw_lbl)
        country  = html_escape(o.get("country", ""))
        year     = html_escape(str(o.get("year", "")))
        virus    = html_escape(o.get("virus", ""))
        url      = html_escape(o.get("source_url", "#"))
        src      = html_escape(o.get("source_name", "Source"))
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
    built  = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    cruise = load_cruise()

    for lang in ("en", "zh"):
        S          = STRINGS[lang]
        OUT        = OUT_HTML if lang == "en" else OUT_HTML_ZH
        OUT.parent.mkdir(parents=True, exist_ok=True)
        switch_href = S["switch_href_en"] if lang == "en" else S["switch_href_zh"]
        lang_bar = (
            f'<div class="lang-bar">'
            f'<a href="{switch_href}">{S["switch_label"]}</a>'
            f'</div>'
        )
        cruise_html = (
            build_cruise_section(cruise, S, lang) if cruise
            else '<section class="cruise-panel"><p>Missing cruise_outbreak_2026.json.</p></section>'
        )
        table_body = build_table_rows(outbreaks, lang)

        # Extract R0 display strings for this language
        r0_pre_val  = S["r0_pre_val"].format(rp=r_pre)
        r0_post_val = S["r0_post_val"].format(ro=r_post)
        r0_dbl_val  = S["r0_dbl_val"].format(g=int(g), rp=r_pre, td=html_escape(td_s))
        r0_proj_intro = S["r0_proj_intro"].format(seed=seed, g=int(g))

        html = f"""<!DOCTYPE html>
<html lang="{S['html_lang']}">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <meta http-equiv="refresh" content="3600"/>
  <title>{S['page_title_full']}</title>
  <meta name="description" content="{S['meta_desc']}"/>
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
      min-width: 600px; /* keeps SVG legible on phones; .flow-svg scrolls */
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

    /* ── language switcher bar ──────────────────────────────────────────────── */
    .lang-bar {{
      font-family: Arial, Helvetica, sans-serif;
      background: var(--violet);
      text-align: right;
      padding: 0.3rem 1.5rem;
      font-size: 0.78rem;
    }}
    .lang-bar a {{
      color: #fff;
      text-decoration: none;
      font-weight: 700;
      letter-spacing: 0.05em;
    }}
    .lang-bar a:hover {{ text-decoration: underline; }}

    /* ── mobile-first responsive overrides ─────────────────────────────────── */
    @media (max-width: 640px) {{

      /* page header */
      .page-header {{ padding: 0.8rem 1rem; }}
      .page-title  {{ font-size: 1.2rem; }}
      .page-sub    {{ font-size: 0.82rem; }}

      /* main wrapper */
      main {{ padding: 0.65rem 0.65rem 2.5rem; gap: 0.65rem; }}

      /* panels */
      .panel         {{ padding: 0.8rem 0.85rem; }}
      .cruise-header {{ padding: 0.8rem 0.85rem 0.65rem; }}
      .headline      {{ font-size: clamp(1rem, 5vw, 1.35rem); }}

      /* stat strip: 2 × 2 grid on small screens */
      .stat-strip {{ flex-wrap: wrap; }}
      .stat       {{ flex: 0 0 50%; }}
      .stat:nth-child(2) {{ border-right: none; }}
      .stat-n     {{ font-size: 1.7rem; }}

      /* flow diagram: SVG has min-width 600px so it's readable; div scrolls */
      .flow-wrap  {{ padding: 0.8rem 0.85rem 0.6rem; }}
      .flow-svg   {{ overflow-x: auto; -webkit-overflow-scrolling: touch; }}

      /* colour legend below SVG */
      .nat-legend {{ font-size: 0.68rem; gap: 0.2rem 0.55rem; margin-top: 0.55rem; }}

      /* scenario cards: single column */
      .scen-wrap  {{ padding: 0.8rem 0.85rem; }}
      .scen-strip {{ grid-template-columns: 1fr; gap: 0.6rem; }}

      /* timeline: narrow date column */
      .tl-wrap {{ padding: 0.8rem 0.85rem; }}
      .tl-item {{ grid-template-columns: 5rem 1fr; gap: 0 0.5rem; }}
      .tl-date {{ font-size: 0.75rem; }}

      /* situation snapshot: single-column dl */
      .snapshot-grid {{ padding: 0.8rem 0.85rem 0.5rem; }}
      .snap-dl       {{ grid-template-columns: 1fr; gap: 0; }}
      .snap-dl dt    {{ margin-top: 0.7rem; font-size: 0.78rem; }}
      .snap-dl dd    {{ font-size: 0.86rem; }}

      /* decision tree already has horizontal scroll via .dt-scroll */
      .dt-wrap {{ padding: 0.8rem 0.85rem; }}

      /* sources grid: single column */
      .sources-ul {{ grid-template-columns: 1fr; }}

      /* R₀ panel: stacks naturally (already single-col on narrow grid) */

      /* footer */
      footer {{ padding: 0.8rem 1rem 2rem; }}
    }}

    /* slightly less padding on medium tablets too */
    @media (max-width: 900px) {{
      main {{ padding: 1rem 1rem 2.5rem; }}
      .panel, .cruise-header {{ padding: 0.9rem 1rem; }}
    }}
  </style>
</head>
<body>
  {lang_bar}
  <a class="skip" href="#main">{S["skip"]}</a>
  <header class="page-header">
    <p class="page-kicker">{S["kicker"]}</p>
    <h1 class="page-title">{S["page_title"]}</h1>
    <p class="page-sub">{S["page_sub"]}</p>
  </header>

  <main id="main">

    {cruise_html}

    <section class="panel" aria-labelledby="r0-heading">
      <h2 class="panel-title" id="r0-heading">{S["r0_heading"]}</h2>
      <div class="r0-inner">
        <div>
          <p style="margin:0 0 0.7rem;font-size:0.92rem;">{S["r0_intro"]}</p>
          <dl class="metrics-dl">
            <dt>{S["r0_pre_lbl"]}</dt>
            <dd>{r0_pre_val}</dd>
            <dt>{S["r0_post_lbl"]}</dt>
            <dd>{r0_post_val}</dd>
            <dt>{S["r0_dbl_lbl"]}</dt>
            <dd>{r0_dbl_val}</dd>
            <dt>{S["r0_snv_lbl"]}</dt>
            <dd>{S["r0_snv_val"]}</dd>
          </dl>
          <div class="callout">
            <strong>{S["r0_src"]}:</strong>
            <a href="{html_escape(rref["andes_url"])}">{S["r0_src_txt"]}</a>.
            {S["r0_src_note"]}
          </div>
        </div>
        <div>
          <p style="margin:0 0 0.5rem;font-size:0.88rem;">{r0_proj_intro}</p>
          <table class="data">
            <caption>{S["r0_proj_cap"]}</caption>
            <thead>
              <tr>
                <th scope="col">{S["r0_col_gen"]}</th>
                <th scope="col">{S["r0_col_days"]}</th>
                <th scope="col">{S["r0_col_cum"]}</th>
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
      <h2 class="panel-title" id="sources-heading">{S["src_heading"]}</h2>
      <p style="margin:0 0 0.75rem;font-size:0.88rem;">{S["src_intro"]}</p>
      <ul class="sources-ul">
        <li><a href="https://www.who.int/emergencies/disease-outbreak-news/item/2026-DON599">WHO DON599 &mdash; MV Hondius cluster (4 May 2026)</a></li>
        <li><a href="https://www.ecdc.europa.eu/en/publications-data/hantavirus-associated-cluster-illness-cruise-ship-ecdc-assessment-and">ECDC &mdash; Cruise ship cluster assessment (6 May 2026)</a></li>
        <li><a href="https://www.cdc.gov/hantavirus/hps/index.html">CDC &mdash; HPS overview</a></li>
        <li><a href="https://www.ecdc.europa.eu/en/infectious-disease-topics/hantavirus-infection">ECDC &mdash; Hantavirus factsheet</a></li>
        <li><a href="https://www.who.int/emergencies/disease-outbreak-news">WHO &mdash; Disease Outbreak News (all)</a></li>
        <li><a href="https://www.paho.org/en/topics/hantavirus">PAHO &mdash; Hantavirus Americas</a></li>
        <li><a href="https://promedmail.org/">ProMED-mail</a></li>
      </ul>
    </section>

    <section class="panel" aria-labelledby="table-heading">
      <h2 class="panel-title" id="table-heading">{S["tbl_heading"]}</h2>
      <div class="table-scroll-wrap">
        <table class="data">
          <caption>{S["tbl_caption"]}</caption>
          <thead>
            <tr>
              <th scope="col">{S["tbl_event"]}</th>
              <th scope="col">{S["tbl_country"]}</th>
              <th scope="col">{S["tbl_year"]}</th>
              <th scope="col">{S["tbl_cases"]}</th>
              <th scope="col">{S["tbl_deaths"]}</th>
              <th scope="col">{S["tbl_virus"]}</th>
              <th scope="col">{S["tbl_source"]}</th>
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
    <p><strong>{S["ft_built"]}:</strong> {html_escape(built)}</p>
    <p><strong>{S["ft_r0_lbl"]}:</strong>
      <a href="{html_escape(rref["andes_url"])}">{S["ft_r0_txt"]}</a>.
    </p>
    <p><strong>{S["ft_cdc_lbl"]}:</strong>
      <a href="{html_escape(rref["sin_nombre_url"])}">{S["ft_cdc_txt"]}</a>.
    </p>
    {"<p><strong>Network check:</strong> " + html_escape(network_note) + "</p>" if network_note else ""}
    <ul>
      <li>{S["ft_refresh"]}</li>
      <li>{S["ft_disclaimer"]}</li>
    </ul>
  </footer>
</body>
</html>
"""

        OUT.write_text(html, encoding="utf-8")
        print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
