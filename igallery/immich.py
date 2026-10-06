import random

import httpx

from .config import Settings, valid_id

MAX_IMAGE_BYTES = 25 * 1024 * 1024


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

    async def list_ids(self) -> list[str]:
        album = self.settings.album_id
        method, path = ("GET", "/albums/" + album) if album else ("POST", "/search/random")
        kwargs = {} if album else {"json": {"size": self.settings.cache_count, "type": "IMAGE"}}
        try:
            async with self._request(method, path, **kwargs) as response:
                if response.status_code != 200:
                    raise SourceError("source_status")
                await response.aread()
                data = response.json()
                assets = data.get("assets") if album and isinstance(data, dict) else data
                if not isinstance(assets, list):
                    raise SourceError("source_schema")
                ids = list(dict.fromkeys(
                    a["id"] for a in assets if isinstance(a, dict)
                    and a.get("type") == "IMAGE" and valid_id(a.get("id"))
                ))
                if album:
                    random.shuffle(ids)
                return ids[:self.settings.cache_count]
        except (httpx.HTTPError, ValueError):
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
        except (httpx.HTTPError, ValueError):
            raise SourceError("source_request") from None
