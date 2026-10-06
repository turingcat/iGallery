import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

import httpx


def valid_id(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return str(UUID(value)) == value
    except ValueError:
        return False


@dataclass(frozen=True)
class Settings:
    immich_url: str
    api_key: str = field(repr=False)
    album_id: str | None = None
    cache_dir: Path = field(default_factory=lambda: Path.home() / ".cache/igallery")
    cache_count: int = 100
    interval_seconds: int = 30
    refresh_seconds: int = 600


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if env is None else env
    try:
        raw = env.get("IMMICH_URL", "").strip()
        if any(ord(c) < 32 or ord(c) == 127 for c in raw):
            raise ValueError()
        httpx.URL(raw)
        url = urlsplit(raw)
        if (url.scheme not in ("http", "https") or not url.hostname
                or url.username or url.password or url.query or url.fragment):
            raise ValueError()
        _ = url.port
        path = url.path.rstrip("/")
        if not path.endswith("/api"):
            path += "/api"
        base = urlunsplit((url.scheme, url.netloc, path, "", ""))
    except (ValueError, httpx.InvalidURL):
        raise ValueError("Invalid IMMICH_URL") from None
    key = env.get("IMMICH_API_KEY", "").strip()
    if not key or any(ord(c) < 32 or ord(c) > 126 for c in key):
        raise ValueError("Invalid IMMICH_API_KEY")
    album = env.get("IMMICH_ALBUM_ID") or None
    if album is not None and not valid_id(album):
        raise ValueError("Invalid IMMICH_ALBUM_ID")
    numbers = {}
    for name, default, maximum in (
        ("CACHE_COUNT", 100, 1000), ("INTERVAL_SECONDS", 30, None),
        ("REFRESH_SECONDS", 600, None),
    ):
        try:
            value = int(env.get("IGALLERY_" + name, str(default)))
            if value <= 0 or (maximum is not None and value > maximum):
                raise ValueError()
        except ValueError:
            raise ValueError("Invalid IGALLERY_" + name) from None
        numbers[name.lower()] = value
    return Settings(base, key, album,
                    Path(env.get("IGALLERY_CACHE_DIR", "~/.cache/igallery")).expanduser(),
                    **numbers)
