import asyncio
import io
import json
import time
from PIL import Image
from fastapi.testclient import TestClient
from igallery.app import create_app
from igallery.cache import PhotoCache
from igallery.config import load_settings

ID = '00000000-0000-0000-0000-000000000001'

class Source:
    async def list_photos(self):
        await asyncio.sleep(60)
        return []


def settings(tmp_path):
    return load_settings({'IMMICH_URL': 'http://nas.example', 'IMMICH_API_KEY': 'unit-test-secret', 'IGALLERY_CACHE_DIR': str(tmp_path)})


def test_cached_photo_available_during_blocked_refresh(tmp_path):
    cfg = settings(tmp_path)
    buf = io.BytesIO()
    Image.new('RGB', (10, 10)).save(buf, 'JPEG')
    (tmp_path / (ID + '.jpg')).write_bytes(buf.getvalue())
    (tmp_path / 'manifest.json').write_text('{"version":1,"ids":["' + ID + '"]}')
    with TestClient(create_app(cfg, Source())) as client:
        data = client.get('/api/photos').json()
        assert data == {'photos': [{'id': ID, 'url': '/api/photo/' + ID}], 'interval_seconds': 30}
        assert client.get('/api/photo/' + ID).headers['content-type'] == 'image/jpeg'
        assert client.get('/api/photo/00000000-0000-0000-0000-000000000002').status_code == 404
        assert client.get('/api/photo/..%2F..%2Fetc%2Fpasswd').status_code == 404
        for endpoint in ('/', '/api/photos', '/health'):
            text = client.get(endpoint).text
            assert 'unit-test-secret' not in text
            assert 'nas.example' not in text
        (tmp_path / (ID + '.jpg')).unlink()
        assert client.get('/api/photo/' + ID).status_code == 404


def test_empty_startup_and_failure_health(tmp_path):
    class Empty:
        async def list_photos(self):
            return []
    with TestClient(create_app(settings(tmp_path), Empty())) as client:
        for _ in range(50):
            health = client.get('/health').json()
            if health['last_refresh_success'] is False:
                break
            time.sleep(.01)
        assert health == {'status': 'ok', 'cache_count': 0, 'last_refresh_success': False}
        assert client.get('/').status_code == 200
        assert client.get('/api/photos').json()['photos'] == []
        assert client.post('/api/refresh').status_code == 404


def test_ambient_proxy_does_not_break_local_frame(tmp_path, monkeypatch):
    monkeypatch.setenv('ALL_PROXY', 'socks5://127.0.0.1:1')
    with TestClient(create_app(settings(tmp_path), Source())) as client:
        assert client.get('/health').status_code == 200

def test_player_scripts_are_not_cached_across_upgrades(tmp_path):
    with TestClient(create_app(settings(tmp_path), Source())) as client:
        for path in ('/static/player.js', '/static/slideshow.js', '/static/style.css'):
            response = client.get(path)
            assert response.status_code == 200
            assert response.headers.get('cache-control') == 'no-store'

def test_api_exposes_cached_date_without_private_metadata(tmp_path):
    buf = io.BytesIO()
    Image.new('RGB', (10, 10)).save(buf, 'JPEG')
    (tmp_path / (ID + '.jpg')).write_bytes(buf.getvalue())
    (tmp_path / 'manifest.json').write_text(json.dumps({
        'version': 1, 'ids': [ID], 'dates': {ID: '2020-01-02'},
    }))
    with TestClient(create_app(settings(tmp_path), Source())) as client:
        assert client.get('/api/photos').json()['photos'] == [
            {'id': ID, 'url': '/api/photo/' + ID, 'taken_date': '2020-01-02'},
        ]
