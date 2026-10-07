import os
import json
import subprocess
import socket
from pathlib import Path


def test_kiosk_waits_for_service_and_uses_local_url(tmp_path):
    bindir = tmp_path / 'bin'
    bindir.mkdir()
    log = tmp_path / 'calls'
    count = tmp_path / 'polls'
    preferences = tmp_path / '.config/igallery-chromium/Default/Preferences'
    preferences.parent.mkdir(parents=True)
    (preferences.parent.parent / 'SingletonLock').symlink_to(socket.gethostname() + '-99999999')
    preferences.write_text(json.dumps({'translate': {'enabled': True}, 'unrelated': {'keep': 42}}))
    (bindir / 'curl').write_text('#!/bin/sh\nif [ ! -f "$POLLS" ]; then touch "$POLLS"; exit 1; fi\nexit 0\n')
    (bindir / 'sleep').write_text('#!/bin/sh\necho sleep >> "$CALLS"\n')
    (bindir / 'chromium').write_text('#!/bin/sh\ncp "$HOME/.config/igallery-chromium/Default/Preferences" "$HOME/launch-preferences.json"\nprintf "%s\\n" "$@" >> "$CALLS"\nkill -TERM "$PPID"\n')
    for path in bindir.iterdir():
        path.chmod(0o755)
    env = {**os.environ, 'PATH': str(bindir) + ':/usr/bin:/bin', 'CALLS': str(log), 'POLLS': str(count), 'HOME': str(tmp_path)}
    result = subprocess.run(['bash', 'deploy/kiosk.sh'], env=env, timeout=5, capture_output=True)
    calls = log.read_text().splitlines()
    assert calls[0] == 'sleep'
    assert '--kiosk' in calls
    assert '--password-store=basic' in calls
    assert '--disable-features=Translate' in calls
    assert 'http://127.0.0.1:8080' in calls
    assert '--no-sandbox' not in calls
    assert result.returncode != 0
    assert json.loads((tmp_path / 'launch-preferences.json').read_text()) == {
        'translate': {'enabled': False}, 'unrelated': {'keep': 42},
    }
    assert json.loads(preferences.with_name('Preferences.igallery-backup').read_text())['translate']['enabled'] is True


def test_kiosk_selects_wayland_for_wayland_session(tmp_path):
    bindir = tmp_path / 'bin'
    bindir.mkdir()
    log = tmp_path / 'calls'
    (bindir / 'curl').write_text('#!/bin/sh\nexit 0\n')
    (bindir / 'chromium').write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$CALLS"\nkill -TERM "$PPID"\n')
    for path in bindir.iterdir():
        path.chmod(0o755)
    env = {**os.environ, 'PATH': str(bindir) + ':/usr/bin:/bin', 'CALLS': str(log), 'HOME': str(tmp_path), 'WAYLAND_DISPLAY': 'wayland-0'}
    subprocess.run(['bash', 'deploy/kiosk.sh'], env=env, timeout=5, capture_output=True)
    assert '--ozone-platform=wayland' in log.read_text().splitlines()
    preferences = tmp_path / '.config/igallery-chromium/Default/Preferences'
    assert json.loads(preferences.read_text())['translate']['enabled'] is False
