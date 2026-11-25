#!/usr/bin/env bash
# Generate load so the scaling reflex has something to react to. Uses 'hey' if installed, curl otherwise.
set -euo pipefail
URL="${1:?usage: load.sh <https://app-url> [seconds] [concurrency]}"
SECONDS_TO_RUN="${2:-300}"
CONCURRENCY="${3:-200}"
if command -v hey >/dev/null; then
  hey -z "${SECONDS_TO_RUN}s" -c "$CONCURRENCY" "$URL"
else
  end=$((SECONDS + SECONDS_TO_RUN))
  while (( SECONDS < end )); do
    seq "$CONCURRENCY" | xargs -P "$CONCURRENCY" -I{} curl -s -o /dev/null "$URL"
  done
fi
