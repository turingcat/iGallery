import random
from datetime import date, datetime

import httpx

from .config import Settings, valid_id

MAX_IMAGE_BYTES = 25 * 1024 * 1024
PUBLIC_VISIBILITIES = {'timeline', 'archive', 'hidden'}


def valid_location(value) -> str | None:
    if not isinstance(value, str):
        return None
    value = ' '.join(value.split())
    return value[:300] or None


def taken_location(asset) -> str | None:
    exif = asset.get('exifInfo')
    if not isinstance(exif, dict):
        return None
    parts = list(dict.fromkeys(part for key in ('country', 'state', 'city')
                              if (part := valid_location(exif.get(key)))))
    return valid_location(' / '.join(parts))


def valid_date(value) -> str | None:
    if not isinstance(value, str) or len(value) != 10:
        return None
    try:
        return value if date.fromisoformat(value).isoformat() == value else None
    except ValueError:
        return None


def taken_date(asset) -> str | None:
    exif = asset.get('exifInfo')
    original = exif.get('dateTimeOriginal') if isinstance(exif, dict) else None
    for value in (asset.get('localDateTime'), original):
        if isinstance(value, str):
            try:
                datetime.fromisoformat(value)
            except ValueError:
                continue
            day = valid_date(value[:10])
            if day:
                return day
    return None


class SourceError(Exception):
    """Sanitized source failure, safe to report without credentials."""


class ImmichClient:
    def __init__(self, settings: Settings, http: httpx.AsyncClient):
        self.settings = settings
        self.http = http

    def _request(self, method, path, **kwargs):
        return self.http.stream(
            method, self.settings.immich_url + path,
            headers={"x-api-key": self.settings.api_key}, timeout=15,
            follow_redirects=False, **kwargs,
        )

    async def list_photos(self) -> list[dict]:
        album = self.settings.album_id
        method, path = ("GET", "/albums/" + album) if album else ("POST", "/search/random")
        kwargs = {} if album else {"json": {"size": self.settings.cache_count, "withExif": True, "filter": {
            "type": {"eq": "IMAGE"}, "visibility": {"notIn": ["locked"]},
        }}}
        try:
            async with self._request(method, path, **kwargs) as response:
                if response.status_code != 200:
                    raise SourceError("source_status")
                await response.aread()
                data = response.json()
                assets = data.get("assets") if album and isinstance(data, dict) else data
                if not isinstance(assets, list):
                    raise SourceError("source_schema")
                photos = {}
                for asset in assets:
                    if (isinstance(asset, dict) and asset.get("type") == "IMAGE"
                            and isinstance(asset.get('visibility'), str)
                            and asset['visibility'] in PUBLIC_VISIBILITIES and valid_id(asset.get("id"))):
                        photos.setdefault(asset['id'], {'id': asset['id'], 'taken_date': taken_date(asset),
                                                       'location': taken_location(asset)})
                photos = list(photos.values())
                if album:
                    random.shuffle(photos)
                return photos[:self.settings.cache_count]
        except (httpx.HTTPError, httpx.InvalidURL, ValueError):
            raise SourceError("source_request") from None

    async def download(self, asset_id: str) -> bytes:
        if not valid_id(asset_id):
            raise SourceError("invalid_asset")
        try:
            async with self._request("GET", f"/assets/{asset_id}/thumbnail", params={"size": "preview"}) as response:
                if response.status_code != 200:
                    raise SourceError("source_status")
                if not response.headers.get("content-type", "").lower().startswith("image/"):
                    raise SourceError("source_content")
                if int(response.headers.get("content-length", "0")) > MAX_IMAGE_BYTES:
                    raise SourceError("source_size")
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_IMAGE_BYTES:
                        raise SourceError("source_size")
                return bytes(body)
        except (httpx.HTTPError, httpx.InvalidURL, ValueError):
            raise SourceError("source_request") from None
