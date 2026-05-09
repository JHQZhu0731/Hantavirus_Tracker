# Hantavirus Tracker — Build-From-Scratch Tutorial

A hands-on guide to building and maintaining this site yourself — no prior web-development experience required. By the end you will understand every file in this project and be able to build similar data-driven public-health dashboards.

---

## Table of Contents

1. [What this site actually is](#1-what-this-site-actually-is)
2. [The mental model: static site generation](#2-the-mental-model-static-site-generation)
3. [Prerequisites](#3-prerequisites)
4. [Project structure explained](#4-project-structure-explained)
5. [Step 1 — Set up your project folder and Git](#5-step-1--set-up-your-project-folder-and-git)
6. [Step 2 — Create your data files (JSON)](#6-step-2--create-your-data-files-json)
7. [Step 3 — Write the Python build script](#7-step-3--write-the-python-build-script)
8. [Step 4 — Write the HTML template](#8-step-4--write-the-html-template)
9. [Step 5 — Add CSS styling](#9-step-5--add-css-styling)
10. [Step 6 — Build visualisations in SVG](#10-step-6--build-visualisations-in-svg)
11. [Step 7 — Multi-language support](#11-step-7--multi-language-support)
12. [Step 8 — Deploy to GitHub Pages](#12-step-8--deploy-to-github-pages)
13. [Step 9 — Automate hourly rebuilds with GitHub Actions](#13-step-9--automate-hourly-rebuilds-with-github-actions)
14. [Step 10 — Keep the site updated](#14-step-10--keep-the-site-updated)
15. [Key concepts reference](#15-key-concepts-reference)
16. [Troubleshooting](#16-troubleshooting)

---

## 1. What this site actually is

The live site at `https://JHQZhu0731.github.io/Hantavirus_Tracker/` is a **single HTML file** (`index.html`). There is no server, no database, and no JavaScript framework. It is just one self-contained webpage that a browser reads directly.

A second file (`zh/index.html`) is the Chinese Simplified version of the same content.

Both files are **generated automatically** by a Python script every time new data arrives.

---

## 2. The mental model: static site generation

Think of this project as a **mail-merge**:

```
Data (JSON files)  +  Template (Python script)  →  Output (index.html)
```

| Piece | What it does | Real file |
|---|---|---|
| **Data** | Stores outbreak facts, timeline events, scenario numbers | `data/outbreaks.json`, `data/cruise_outbreak_2026.json` |
| **Builder** | Reads the data, formats it as HTML, writes the output file | `scripts/build_tracker.py` |
| **Output** | The finished webpage the browser reads | `index.html`, `zh/index.html` |

**Why not use a live server?** Static files are free to host (GitHub Pages), load instantly, and never go down. For public-health dashboards where data changes daily, this is ideal.

---

## 3. Prerequisites

You need three things installed on your computer:

### Python 3
Check if you have it:
```bash
python3 --version
```
If not, download from [python.org](https://www.python.org/downloads/).

> This project uses **only Python standard library** modules (`json`, `math`, `pathlib`, `datetime`, `urllib`). You do not need to install any packages with `pip`.

### Git
```bash
git --version
```
Install from [git-scm.com](https://git-scm.com/) if needed.

### A text editor
[VS Code](https://code.visualstudio.com/) or [Cursor](https://cursor.sh/) are good choices.

---

## 4. Project structure explained

```
Hantavirus Tracker/
│
├── data/
│   ├── outbreaks.json            ← Historical outbreak table data
│   └── cruise_outbreak_2026.json ← Everything about the 2026 cruise ship cluster
│
├── scripts/
│   └── build_tracker.py          ← The builder: reads data → writes HTML
│
├── .github/
│   └── workflows/
│       └── hourly_update.yml     ← GitHub Actions: auto-rebuild every hour
│
├── index.html                    ← Generated English page (DO NOT edit by hand)
├── zh/
│   └── index.html                ← Generated Chinese page (DO NOT edit by hand)
│
├── auto_push.sh                  ← Optional: local cron script for rebuilding
├── refresh_daily.sh              ← Optional: local rebuild helper
└── README.md                     ← This file
```

**The golden rule:** Never edit `index.html` or `zh/index.html` directly. Always edit the data files or the build script, then run the builder. This is because any manual edit gets overwritten the next time the builder runs.

---

## 5. Step 1 — Set up your project folder and Git

```bash
# Create your project directory
mkdir "My Health Tracker"
cd "My Health Tracker"

# Initialize a Git repository
git init
git branch -M main

# Connect to GitHub (create the repo on GitHub first)
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
```

Create a `.gitignore` file to exclude unwanted files:
```
__pycache__/
*.pyc
.DS_Store
```

---

## 6. Step 2 — Create your data files (JSON)

JSON (JavaScript Object Notation) is the standard format for structured data. Think of it as a spreadsheet that can also store nested information.

### What is JSON?

```json
{
  "name": "Example outbreak",
  "year": 2026,
  "cases": 42,
  "deaths": 3,
  "is_confirmed": true,
  "sources": ["WHO", "ECDC"]
}
```

Rules:
- Keys must be in `"double quotes"`
- Strings use `"double quotes"`
- Numbers have no quotes
- Booleans are `true` or `false` (lowercase)
- Arrays use `[square brackets]`
- Objects use `{curly braces}`
- **No trailing commas** — the last item in a list has no comma after it

### `data/outbreaks.json` structure

```json
{
  "meta": {
    "description": "Curated outbreak data",
    "last_reviewed": "2026-05-09"
  },
  "outbreaks": [
    {
      "id": "unique-slug",
      "label": "Event name in English",
      "label_zh": "事件中文名称",
      "country": "Country name",
      "year": 2026,
      "cases": 8,
      "deaths": 3,
      "virus": "Andes virus (ANDV)",
      "source_name": "WHO DON599",
      "source_url": "https://..."
    }
  ],
  "r0_reference": {
    "andes_pre_control": 2.12,
    "andes_post_control": 0.96,
    "generation_interval_days_assumption": 14,
    "andes_url": "https://...",
    "sin_nombre_url": "https://..."
  }
}
```

**To add a new outbreak row:** Copy an existing entry inside `"outbreaks": [...]`, paste it, change the values, and run the builder. The table updates automatically.

### `data/cruise_outbreak_2026.json` structure

This file describes the detailed 2026 cruise-ship case. Key sections:

| Section | Purpose |
|---|---|
| `label` / `label_zh` | Headline title |
| `deck` / `deck_zh` | One-paragraph summary |
| `situation_snapshot` | Key facts (vessel, itinerary, case counts, lab findings) |
| `timeline` | Chronological events, each with `date`, `event`, `event_zh` |
| `sankey` | Numbers for the population flow diagram |
| `decision_tree` | Branch-by-branch clinical/investigator guidance |

---

## 7. Step 3 — Write the Python build script

`scripts/build_tracker.py` is the heart of the project. Here is how it works, section by section.

### Loading data

```python
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # go up one level from /scripts/

def load_data():
    with open(ROOT / "data" / "outbreaks.json", encoding="utf-8") as f:
        return json.load(f)  # converts JSON text → Python dict
```

`Path` is Python's modern way to handle file paths — it works on Mac, Windows, and Linux without you having to think about `/` vs `\`.

### Building HTML strings

In Python, you build HTML by writing strings. The modern way is **f-strings** (formatted string literals):

```python
name = "Andes virus"
cases = 8

# f-string: anything inside { } is evaluated as Python
html = f"<p>There are <strong>{cases}</strong> cases of {name}.</p>"
# Result: <p>There are <strong>8</strong> cases of Andes virus.</p>
```

For long HTML blocks, use triple-quoted f-strings:
```python
html = f"""
<section>
  <h2>{heading}</h2>
  <p>{body_text}</p>
</section>
"""
```

### Escaping user data

Always escape text that came from a data file before putting it into HTML. This prevents special characters like `<`, `>`, `&` from breaking your page:

```python
from html import escape as html_escape

user_text = "Cases > 10 & rising"
safe = html_escape(user_text)
# Result: "Cases &gt; 10 &amp; rising"  ← browser displays it correctly
```

### The `main()` function flow

```
main()
 │
 ├── load_data()           → reads outbreaks.json
 ├── load_cruise()         → reads cruise_outbreak_2026.json
 ├── build_sankey_svg()    → creates the flow diagram SVG
 ├── build_cruise_section()→ assembles the full cruise HTML block
 ├── build_table_rows()    → builds the <tr> rows for the outbreak table
 │
 ├── for lang in ("en", "zh"):    ← loop runs TWICE: once English, once Chinese
 │     S = STRINGS[lang]          ← pick the right language strings
 │     html = f"""...{cruise_html}..."""  ← assemble full page
 │     OUT.write_text(html)       ← write the file
```

### R₀ (Basic Reproduction Number) calculation

```python
import math

def doubling_time_days(r0: float, generation_interval: float) -> float:
    """How many days until the infected count doubles?"""
    if r0 <= 1:
        return None  # not growing
    return generation_interval * math.log(2) / math.log(r0)

# Example: R0 = 2.12, generation interval = 14 days
# doubling_time = 14 × ln(2) / ln(2.12) ≈ 12.9 days
```

The geometric projection table works the same way:
```python
seed = 5  # starting infected cases
for generation in range(5):
    # Each generation: multiply by R0
    cumulative = seed * (r0 ** (generation + 1) - 1) / (r0 - 1)
```

---

## 8. Step 4 — Write the HTML template

The final HTML is assembled inside one large f-string. Here is the minimal skeleton:

```python
html = f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <meta http-equiv="refresh" content="3600"/>  <!-- auto-refresh every hour -->
  <title>{page_title}</title>
  <style>
    /* CSS goes here */
  </style>
</head>
<body>
  <header>
    <h1>{page_title}</h1>
  </header>
  <main>
    {cruise_html}
    {table_section}
  </main>
  <footer>
    <p>Built: {built_timestamp}</p>
  </footer>
</body>
</html>
"""

# Write the file
output_path = ROOT / "index.html"
output_path.write_text(html, encoding="utf-8")
```

**Important HTML tags to know:**

| Tag | Purpose |
|---|---|
| `<h1>` to `<h6>` | Headings (h1 = biggest) |
| `<p>` | Paragraph |
| `<strong>` | Bold / important text |
| `<a href="url">text</a>` | Hyperlink |
| `<table>`, `<tr>`, `<th>`, `<td>` | Table structure |
| `<dl>`, `<dt>`, `<dd>` | Definition list (term + description) |
| `<section>`, `<main>`, `<footer>` | Semantic page regions |

**Accessibility attributes:** add these to make your page usable with screen readers:
```html
<section aria-labelledby="my-heading">
  <h2 id="my-heading">Section title</h2>
</section>
<table>
  <th scope="col">Column name</th>
  <th scope="row">Row name</th>
</table>
```

---

## 9. Step 5 — Add CSS styling

CSS (Cascading Style Sheets) controls colours, fonts, spacing, and layout. In this project it lives inside `<style>` tags in the HTML `<head>`.

### CSS variables (custom properties)

Define your colour palette once and reuse it everywhere:
```css
:root {
  --violet:    #57068c;   /* NYU Langone purple */
  --ink:       #121212;   /* near-black for body text */
  --paper:     #faf9f7;   /* warm white background */
  --rule:      #e2e2e2;   /* light grey borders */
}

.page-header {
  border-bottom: 3px solid var(--violet);  /* reference the variable */
  background: white;
}
```

### Layout with Flexbox and Grid

```css
/* Flexbox: arrange children in a row */
.stat-strip {
  display: flex;
  gap: 1rem;
}
.stat {
  flex: 1;  /* each stat takes equal space */
}

/* Grid: two-column layout */
.r0-inner {
  display: grid;
  grid-template-columns: 1fr 1fr;  /* two equal columns */
  gap: 2rem;
}
```

### Mobile-responsive design

Use `@media` queries to change layout on small screens:
```css
/* Default: desktop layout */
.stat-strip { display: flex; }

/* Override on phones (screens ≤ 640px wide) */
@media (max-width: 640px) {
  .stat-strip {
    flex-wrap: wrap;        /* items wrap to next line */
  }
  .stat {
    flex: 0 0 50%;          /* 2 items per row */
  }
}
```

---

## 10. Step 6 — Build visualisations in SVG

SVG (Scalable Vector Graphics) is XML-based graphics that lives directly in HTML. This project uses it for the population flow (Sankey-style) diagram.

### Basic SVG shapes

```xml
<svg width="400" height="200">
  <!-- Rectangle -->
  <rect x="10" y="10" width="100" height="50" fill="#57068c"/>

  <!-- Text -->
  <text x="120" y="40" font-size="14" fill="#121212">Label</text>

  <!-- Path (curve between two points) -->
  <path d="M 110,20 C 150,20 150,80 190,80" 
        fill="none" stroke="#57068c" stroke-width="20" opacity="0.3"/>
</svg>
```

### The Sankey diagram in this project

The flow diagram has three columns:
1. **HEAD** — one tall bar representing all 147 people aboard
2. **SPLIT** — two bars: 139 contacts + 8 cases
3. **OUTCOMES** — five bars: deaths, ICU, transferred, etc.

The ribbons connecting columns are SVG `<path>` elements with cubic Bézier curves:
```python
def ribbon(x0, y0_top, y0_bot, x1, y1_top, y1_bot, color, opacity=0.35):
    """Draw a tapered ribbon between two vertical bars."""
    mid = (x0 + x1) / 2  # control point x (halfway between columns)
    return (
        f'<path d="'
        f'M {x0},{y0_top} C {mid},{y0_top} {mid},{y1_top} {x1},{y1_top} '  # top edge
        f'L {x1},{y1_bot} C {mid},{y1_bot} {mid},{y0_bot} {x0},{y0_bot} Z" '  # bottom edge
        f'fill="{color}" opacity="{opacity}"/>'
    )
```

**Understanding the `d=` path command:**
- `M x,y` — Move to point (start here)
- `C cx1,cy1 cx2,cy2 x,y` — Cubic Bézier curve (smooth S-curve)
- `L x,y` — Line to point
- `Z` — Close path (connect back to start)

---

## 11. Step 7 — Multi-language support

This project supports English and Chinese Simplified using a `STRINGS` dictionary.

### The pattern

```python
STRINGS = {
    "en": {
        "page_title": "Hantavirus Tracker",
        "stat_cases": "Cases",
        "stat_deaths": "Deaths",
    },
    "zh": {
        "page_title": "汉坦病毒追踪器",
        "stat_cases": "病例数",
        "stat_deaths": "死亡数",
    },
}

# In main():
for lang in ("en", "zh"):
    S = STRINGS[lang]                  # S is now a dict of strings for this language
    out_path = ROOT / "index.html" if lang == "en" else ROOT / "zh" / "index.html"

    html = f"""
    <h1>{S['page_title']}</h1>
    <span class="stat-label">{S['stat_cases']}</span>
    """
    out_path.write_text(html)
```

### Translating dynamic data (JSON fields)

For data stored in JSON, add a `_zh` version of each field:
```json
{
  "event": "Case 1 dies aboard",
  "event_zh": "1号病例在船上死亡"
}
```

Then in Python, use the Chinese version when available:
```python
text = evt.get("event_zh", evt["event"]) if lang == "zh" else evt["event"]
```

### Date formatting

For dates like `"9 May 2026"` → `"2026年5月9日"`:
```python
MONTH_ZH = {"Jan":"1月","Feb":"2月","Mar":"3月","Apr":"4月",
            "May":"5月","Jun":"6月","Jul":"7月","Aug":"8月",
            "Sep":"9月","Oct":"10月","Nov":"11月","Dec":"12月"}

def format_date_zh(date_str):
    day, month, year = date_str.split()
    return f"{year}年{MONTH_ZH[month]}{day}日"
```

---

## 12. Step 8 — Deploy to GitHub Pages

GitHub Pages hosts your `index.html` for free at `https://YOUR_USERNAME.github.io/YOUR_REPO/`.

### One-time setup

1. **Create a GitHub repository** at [github.com/new](https://github.com/new)

2. **Connect your local project to GitHub:**
   ```bash
   git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
   ```

3. **Create a Personal Access Token (PAT)** so Git can push:
   - Go to GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
   - Click *Generate new token*
   - Select scope: `repo` (full control)
   - Copy the token (you only see it once)

4. **Set the remote URL with your token embedded:**
   ```bash
   git remote set-url origin https://YOUR_USERNAME:YOUR_TOKEN@github.com/YOUR_USERNAME/YOUR_REPO.git
   ```

5. **Enable GitHub Pages:**
   - Go to your repo → Settings → Pages
   - Under *Source*, select **Deploy from a branch**
   - Branch: `main`, folder: `/ (root)`
   - Click Save

6. **Push your first commit:**
   ```bash
   git add .
   git commit -m "Initial commit"
   git push -u origin main
   ```

Your site goes live at `https://YOUR_USERNAME.github.io/YOUR_REPO/` within a few minutes.

---

## 13. Step 9 — Automate hourly rebuilds with GitHub Actions

GitHub Actions is a free automation service that runs code on GitHub's servers on a schedule. This project uses it to rebuild the HTML every hour.

### The workflow file: `.github/workflows/hourly_update.yml`

```yaml
name: Hourly rebuild

on:
  schedule:
    - cron: '0 * * * *'   # Run at minute 0 of every hour
  workflow_dispatch:        # Also allow manual runs

permissions:
  contents: write           # Allow the action to push to the repo

jobs:
  rebuild:
    runs-on: ubuntu-latest
    steps:
      - name: Check out code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Rebuild HTML
        run: python3 scripts/build_tracker.py

      - name: Commit and push if changed
        run: |
          git config user.name  "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add index.html zh/index.html
          git diff --cached --quiet || git commit -m "Auto-update $(date -u +'%Y-%m-%d %H:%M UTC')"
          git push
```

**Understanding the cron syntax `0 * * * *`:**
```
┌─ minute (0–59)
│ ┌─ hour (0–23)
│ │ ┌─ day of month (1–31)
│ │ │ ┌─ month (1–12)
│ │ │ │ ┌─ day of week (0–7, 0=Sunday)
│ │ │ │ │
0 * * * *   ← at minute 0, every hour, every day
```

### How to trigger a manual rebuild

In your GitHub repository, go to **Actions** → select *Hourly rebuild* → click **Run workflow**.

---

## 14. Step 10 — Keep the site updated

When new outbreak information is published (e.g., new WHO DON, ECDC update):

### Add a timeline event

Open `data/cruise_outbreak_2026.json` and append to the `"timeline"` array:
```json
{"date": "10 May 2026",
 "event": "MV Hondius arrives Tenerife. Passengers disembark under medical escort.",
 "event_zh": "MV Hondius抵达特内里费。乘客在医疗人员陪同下下船。"}
```

### Update case counts

In the `"sankey"` section, change `"confirmed_n"` if more PCR confirmations come in.

In `"situation_snapshot"`, update `"counts_as_of_7_may"` and its `_zh` twin.

### Rebuild and push

```bash
python3 scripts/build_tracker.py
git add .
git commit -m "Update: add May 10 Tenerife arrival"
git push
```

The site updates within seconds of the push.

---

## 15. Key concepts reference

### Python concepts used in this project

| Concept | What it does | Example |
|---|---|---|
| `f-string` | Embed variables in strings | `f"Hello {name}"` |
| `dict.get(key, default)` | Safe dictionary lookup | `snap.get("vessel", "—")` |
| `Path` | Cross-platform file paths | `ROOT / "data" / "file.json"` |
| `json.load(f)` | Parse JSON file → Python dict | `data = json.load(open("file.json"))` |
| `file.write_text(s)` | Write string to file | `Path("out.html").write_text(html)` |
| `for k, v in d.items()` | Loop over dict key+value pairs | `for lang, strings in STRINGS.items()` |
| List comprehension | Build list concisely | `[f"<li>{x}</li>" for x in items]` |

### HTML/CSS concepts

| Concept | What it does |
|---|---|
| `<meta http-equiv="refresh" content="3600"/>` | Browser auto-reloads page every hour |
| `lang="zh-Hans"` | Tells browsers/screen readers the page language |
| `aria-labelledby="id"` | Links a region to its heading for accessibility |
| `scope="col"` / `scope="row"` | Table header direction (accessibility) |
| CSS `var(--name)` | Use a CSS custom property (variable) |
| `@media (max-width: 640px)` | Apply styles only on narrow screens |
| `display: flex` | Arrange children horizontally |
| `display: grid` | Two-dimensional layout |

### Epidemiology formulas

| Formula | Meaning |
|---|---|
| `R₀ = 2.12` | On average, each case infects 2.12 others (before control) |
| `Td = T_gen × ln(2) / ln(R₀)` | Doubling time given generation interval `T_gen` |
| `CFR = deaths / cases × 100%` | Case fatality ratio |

---

## 16. Troubleshooting

### `json.decoder.JSONDecodeError`
Your JSON file has a syntax error. Common causes:
- **Trailing comma** on the last item: `["a", "b",]` ← remove the last comma
- **Unescaped double quote** inside a string: `"he said "hello""` ← use `"he said \"hello\""` or a different quote style
- **Missing comma** between two items

**Quick check:** paste your JSON into [jsonlint.com](https://jsonlint.com/) — it will point to the exact line.

### `SyntaxError` in Python
Python f-strings cannot contain `{` or `}` unless they are part of a variable. Double them to use literal braces in CSS inside an f-string:
```python
html = f"""
<style>
  .box {{ color: red; }}   ← {{ and }} = literal { and } in f-strings
</style>
"""
```

### Git push rejected (`fetch first`)
Someone else (or GitHub Actions) pushed to the repo while you were working. Fix:
```bash
git pull --no-rebase origin main   # get their changes
# resolve any conflicts, then:
git push
```

### GitHub Pages not updating
- Check that your file is called exactly `index.html` (lowercase)
- Check Settings → Pages → the branch is set to `main` and folder `/`
- Wait 2–3 minutes after pushing — Pages has a small delay

### The generated HTML looks broken in the browser
Open the browser's developer tools (right-click → Inspect → Console) and look for errors. Usually it's an unclosed HTML tag or a missing `"` in an attribute.

---

## Summary: the three-file workflow

Every time you want to update the site:

```
1. Edit data files          →  data/outbreaks.json
   (add facts, fix numbers)    data/cruise_outbreak_2026.json

2. Run the builder          →  python3 scripts/build_tracker.py
   (generates HTML)

3. Push to GitHub           →  git add .
   (publishes the site)        git commit -m "describe what changed"
                               git push
```

That's the whole loop. Master these three steps and you can build and maintain any data-driven static website.

---

*Built with Python 3 · Hosted on GitHub Pages · Data: WHO, ECDC, CDC, PAHO*
