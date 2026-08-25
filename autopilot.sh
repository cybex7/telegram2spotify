#!/usr/bin/env bash
# Runs the rest of the pipeline unattended: match -> push -> export, sleeping
# exactly as long as Spotify's own Retry-After says on a search-quota ban,
# repeating until every track is resolved. No AI in this loop -- it is the
# same match/push/export/sleep cycle that was run by hand across three
# multi-hour rate-limit windows; this is that loop, checked in as a script.
#
# Usage:
#   ./autopilot.sh "Playlist name" <playlist-id> [--include-review]
#
# Safe to Ctrl-C and re-run any time: all progress lives in state.sqlite.
# Run it with nohup, or as a cron/systemd job, to survive a closed terminal:
#   nohup ./autopilot.sh "Music On" abc123 --include-review > /dev/null 2>&1 &
set -euo pipefail
cd "$(dirname "$0")"

if [ "$#" -lt 2 ]; then
  echo "usage: ./autopilot.sh \"Playlist name\" <playlist-id> [--include-review]" >&2
  exit 1
fi
NAME="$1"; PLID="$2"; shift 2

LOG="autopilot.log"
: > "$LOG"

while true; do
  echo "$(date '+%F %T') starting run_match.py" | tee -a "$LOG"
  set +e
  out=$(python3 -u run_match.py 2>&1)
  rc=$?
  set -e
  echo "$out" >> "$LOG"

  python3 -u run_push.py "$NAME" "$PLID" "$@" >> "$LOG" 2>&1
  python3 -u run_export.py >> "$LOG" 2>&1

  remaining=$(python3 -c "
import sqlite3
c = sqlite3.connect('state.sqlite')
print(c.execute(\"SELECT COUNT(*) FROM tracks WHERE status='ingested'\").fetchone()[0])
")
  echo "$(date '+%F %T') cycle done: remaining=$remaining exit=$rc" | tee -a "$LOG"

  if [ "$remaining" = "0" ]; then
    echo "$(date '+%F %T') ALL TRACKS PROCESSED -- autopilot finished" | tee -a "$LOG"
    break
  fi

  if [ "$rc" = "2" ]; then
    wait_s=$(echo "$out" | grep -oP "wait \K[0-9]+" | head -1)
    [ -z "$wait_s" ] && wait_s=3600
    sleep_s=$((wait_s + 90))
    resume_at=$(date -d "+${sleep_s} seconds" '+%F %T')
    echo "$(date '+%F %T') rate-limited, sleeping ${sleep_s}s (resuming ~$resume_at)" | tee -a "$LOG"
    sleep "$sleep_s"
  else
    echo "$(date '+%F %T') match exited $rc without a rate-limit signal but $remaining remain -- stopping, needs a look" | tee -a "$LOG"
    exit 1
  fi
done
