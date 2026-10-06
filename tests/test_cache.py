import io
import json
from dataclasses import replace
from PIL import Image
import pytest
from igallery.config import load_settings
from igallery.immich import SourceError
from igallery.cache import PhotoCache

IDS = [f'00000000-0000-0000-0000-{n:012d}' for n in range(1, 5)]

def jpeg():
    buf = io.BytesIO()
    Image.new('RGB', (32, 24), 'red').save(buf, 'JPEG')
    return buf.getvalue()

class Source:
    def __init__(self, ids, bad=(), fail=False):
        self.ids, self.bad, self.fail = ids, bad, fail
        self.downloads = []
    async def list_ids(self):
        if self.fail:
            raise SourceError('source_request')
        return self.ids
    async def download(self, asset_id):
        self.downloads.append(asset_id)
        return b'bad' if asset_id in self.bad else jpeg()

@pytest.fixture
def settings(tmp_path):
    return load_settings({'IMMICH_URL': 'http://nas.example', 'IMMICH_API_KEY': 'unit-test-secret', 'IGALLERY_CACHE_DIR': str(tmp_path), 'IGALLERY_CACHE_COUNT': '2'})

async def test_persist_and_reuse(settings):
    cache = PhotoCache(settings)
    src = Source([IDS[0], IDS[0], IDS[1], '../bad'])
    assert await cache.refresh(src)
    assert cache.photo_ids() == IDS[:2]
    restored = PhotoCache(settings)
    restored.load()
    assert restored.photo_ids() == IDS[:2]
    src.downloads.clear()
    assert await restored.refresh(src)
    assert src.downloads == []
    with Image.open(restored.path_for(IDS[0])) as image:
        assert image.size == (32, 24)
    assert restored.path_for('../bad') is None

@pytest.mark.parametrize('source', [Source([], fail=True), Source([]), Source([IDS[2]], bad=[IDS[2]])])
async def test_failure_preserves_old(settings, source):
    cache = PhotoCache(settings)
    await cache.refresh(Source(IDS[:2]))
    assert not await cache.refresh(source)
    assert cache.photo_ids() == IDS[:2]
    restored = PhotoCache(settings)
    restored.load()
    assert restored.photo_ids() == IDS[:2]

async def test_partial_success_and_cleanup(settings):
    cache = PhotoCache(settings)
    await cache.refresh(Source(IDS[:2]))
    assert await cache.refresh(Source(IDS[2:], bad=[IDS[3]]))
    assert cache.photo_ids() == [IDS[2], IDS[0]]
    assert not (settings.cache_dir / (IDS[1] + '.jpg')).exists()
    assert len(list(settings.cache_dir.glob('*.jpg'))) == 2

async def test_atomic_manifest_failure(settings, monkeypatch):
    cache = PhotoCache(settings)
    await cache.refresh(Source(IDS[:2]))
    import os
    original = os.replace
    def fail_manifest(src, dst):
        if str(dst).endswith('manifest.json'):
            raise OSError('disk full')
        original(src, dst)
    monkeypatch.setattr(os, 'replace', fail_manifest)
    assert not await cache.refresh(Source(IDS[2:]))
    assert cache.photo_ids() == IDS[:2]
    restored = PhotoCache(settings)
    restored.load()
    assert restored.photo_ids() == IDS[:2]

async def test_corrupt_manifest_missing_file_and_symlink(settings, tmp_path):
    cache = PhotoCache(settings)
    (tmp_path / 'manifest.json').write_text('bad')
    cache.load()
    assert cache.photo_ids() == []
    await cache.refresh(Source(IDS[:2]))
    (tmp_path / (IDS[0] + '.jpg')).unlink()
    outside = tmp_path.parent / 'outside.jpg'
    outside.write_bytes(jpeg())
    (tmp_path / (IDS[0] + '.jpg')).symlink_to(outside)
    restored = PhotoCache(settings)
    restored.load()
    assert restored.photo_ids() == [IDS[1]]
    assert restored.path_for(IDS[0]) is None
    assert outside.exists()

async def test_corrupted_referenced_image_is_downloaded_again(settings):
    cache = PhotoCache(settings)
    await cache.refresh(Source(IDS[:2]))
    (settings.cache_dir / (IDS[0] + '.jpg')).write_bytes(b'corrupted')
    restored = PhotoCache(settings)
    restored.load()
    assert restored.photo_ids() == [IDS[1]]
    source = Source(IDS[:2])
    assert await restored.refresh(source)
    assert IDS[0] in source.downloads
    with Image.open(restored.path_for(IDS[0])) as image:
        assert image.format == 'JPEG'
