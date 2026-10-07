#!/bin/bash
set -eu
browser=$(command -v chromium || command -v chromium-browser || true)
if [ -z "$browser" ]; then
    echo "Chromium is not installed" >&2
    exit 1
fi
platform=--ozone-platform=x11
if [ -n "${WAYLAND_DISPLAY:-}" ]; then
    platform=--ozone-platform=wayland
fi
while true; do
    until curl --noproxy '*' -fsS --max-time 3 http://127.0.0.1:8080/health >/dev/null 2>&1; do
        sleep 2
    done
    # Set the profile preference too: some Chromium builds ignore the feature flag.
    python3 - <<'PY'
import json
import os
import shutil
import socket
import tempfile
from pathlib import Path

profile = Path.home() / '.config/igallery-chromium'
lock = profile / 'SingletonLock'
if lock.is_symlink():
    host, _, pid = os.readlink(lock).rpartition('-')
    if host != socket.gethostname() or not pid.isdigit() or Path('/proc', pid).exists():
        raise SystemExit('Close the igallery Chromium session before starting kiosk')
preferences = profile / 'Default/Preferences'
preferences.parent.mkdir(parents=True, exist_ok=True)
data = json.loads(preferences.read_text()) if preferences.exists() else {}
if preferences.exists():
    backup = preferences.with_name('Preferences.igallery-backup')
    if not backup.exists():
        shutil.copy2(preferences, backup)
translate = data.setdefault('translate', {})
translate['enabled'] = False
fd, name = tempfile.mkstemp(dir=preferences.parent, prefix='.preferences-')
try:
    with os.fdopen(fd, 'w') as out:
        json.dump(data, out)
    os.replace(name, preferences)
finally:
    Path(name).unlink(missing_ok=True)
PY
    "$browser" "$platform" --kiosk --noerrdialogs --disable-infobars --no-first-run \
        --disable-session-crashed-bubble \
        --disable-features=Translate \
        --password-store=basic \
        --user-data-dir="$HOME/.config/igallery-chromium" \
        http://127.0.0.1:8080 || true
    sleep 5
done
