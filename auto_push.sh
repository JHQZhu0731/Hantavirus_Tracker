#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# auto_push.sh  —  Rebuild index.html and push to GitHub
#
# Usage (manual):
#   ./auto_push.sh
#
# Usage (hourly cron — add with `crontab -e`):
#   0 * * * * /path/to/Hantavirus\ Tracker/auto_push.sh >> ~/hantavirus-auto.log 2>&1
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting hourly rebuild..."

# 1. Rebuild the HTML
python3 scripts/build_tracker.py

# 2. Stage generated files (data edits commit separately)
git add index.html zh/index.html

# 3. Commit only if there are staged changes
if git diff --cached --quiet; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] No changes — nothing to push."
else
  git commit -m "Auto-update $(date '+%Y-%m-%d %H:%M UTC')"
  git push
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Pushed to GitHub."
fi
