#!/bin/bash
set -eu
browser=$(command -v chromium || command -v chromium-browser || true)
if [ -z "$browser" ]; then
    echo "Chromium is not installed" >&2
    exit 1
fi
while true; do
    until curl --noproxy '*' -fsS --max-time 3 http://127.0.0.1:8080/health >/dev/null 2>&1; do
        sleep 2
    done
    "$browser" --kiosk --noerrdialogs --disable-infobars --no-first-run \
        --disable-session-crashed-bubble \
        --user-data-dir="$HOME/.config/igallery-chromium" \
        http://127.0.0.1:8080 || true
    sleep 5
done
