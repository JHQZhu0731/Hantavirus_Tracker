#!/usr/bin/env bash
# Daily regeneration of index.html. Example crontab (6 AM local):
# 0 6 * * * /path/to/Hantavirus\ Tracker/refresh_daily.sh >> /path/to/hantavirus-build.log 2>&1
set -euo pipefail
cd "$(dirname "$0")"
exec python3 scripts/build_tracker.py
