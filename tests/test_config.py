import pytest
from igallery.config import load_settings

BASE = {"IMMICH_URL": "https://nas.example/api/", "IMMICH_API_KEY": "unit-test-secret"}

def test_defaults_hide_key():
    cfg = load_settings(BASE)
    assert cfg.immich_url == "https://nas.example/api"
    assert (cfg.cache_count, cfg.interval_seconds, cfg.refresh_seconds) == (100, 30, 600)
    assert "unit-test-secret" not in repr(cfg)

@pytest.mark.parametrize("url,want", [("http://nas.example:2283/", "http://nas.example:2283/api"), ("https://nas.example/photos/", "https://nas.example/photos/api")])
def test_url_normalization(url, want):
    assert load_settings({**BASE, "IMMICH_URL": url}).immich_url == want

@pytest.mark.parametrize("key,value", [("IMMICH_API_KEY", ""), ("IMMICH_URL", "file:///private"), ("IMMICH_URL", "http://user:pass@nas.example"), ("IMMICH_URL", "http://nas.example?key=unit-test-secret"), ("IMMICH_URL", "http://nas.example:abc"), ("IGALLERY_CACHE_COUNT", "0"), ("IGALLERY_CACHE_COUNT", "1001"), ("IGALLERY_INTERVAL_SECONDS", "-1"), ("IGALLERY_REFRESH_SECONDS", "no"), ("IMMICH_ALBUM_ID", "../bad")])
def test_bad_configuration_is_safe(key, value):
    with pytest.raises(ValueError) as error:
        load_settings({**BASE, key: value})
    assert "unit-test-secret" not in str(error.value)

def test_album_and_cache_path(tmp_path):
    cfg = load_settings({**BASE, "IMMICH_ALBUM_ID": "00000000-0000-0000-0000-000000000001", "IGALLERY_CACHE_DIR": str(tmp_path)})
    assert cfg.album_id == "00000000-0000-0000-0000-000000000001"
    assert cfg.cache_dir == tmp_path
