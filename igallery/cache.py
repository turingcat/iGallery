import asyncio
import io
import json
import logging
import os
import tempfile
import warnings
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from .config import Settings, valid_id
from .immich import ImmichClient, SourceError, valid_date

logger = logging.getLogger(__name__)


def atomic_write(path: Path, content: bytes):
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".pending-")
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(content)
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def normalized_image(data: bytes) -> bytes:
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            photo = ImageOps.exif_transpose(image).convert("RGB")
            photo.thumbnail((1920, 1920))
            result = io.BytesIO()
            photo.save(result, "JPEG", quality=85)
            return result.getvalue()


class PhotoCache:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.directory = settings.cache_dir
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._ids: list[str] = []
        self._dates: dict[str, str] = {}
        self.last_refresh_success: bool | None = None

    def _path(self, asset_id):
        return self.directory / (asset_id + ".jpg")

    def _exists(self, asset_id):
        path = self._path(asset_id)
        if path.is_symlink() or not path.is_file():
            return False
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(path) as image:
                    image.verify()
                    return image.format == "JPEG"
        except (OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            return False

    def load(self) -> None:
        try:
            manifest = json.loads((self.directory / "manifest.json").read_text())
            if not isinstance(manifest, dict) or manifest.get("version") != 1:
                return
            ids = manifest.get("ids")
            if not isinstance(ids, list):
                return
            self._ids = list(dict.fromkeys(
                asset_id for asset_id in ids if valid_id(asset_id) and self._exists(asset_id)
            ))[:self.settings.cache_count]
            dates = manifest.get('dates', {})
            self._dates = {a: day for a in self._ids if (day := valid_date(dates.get(a)))} if isinstance(dates, dict) else {}
        except (OSError, ValueError):
            logger.warning("cache_manifest_unavailable")

    def photo_ids(self) -> list[str]:
        return self._ids.copy()

    def taken_date_for(self, asset_id: str) -> str | None:
        return self._dates.get(asset_id)

    def path_for(self, asset_id: str) -> Path | None:
        if asset_id not in self._ids or not valid_id(asset_id) or not self._exists(asset_id):
            return None
        return self._path(asset_id)

    async def refresh(self, source: ImmichClient) -> bool:
        self.last_refresh_success = False
        try:
            candidates = await source.list_photos()
            ready = []
            dates = self._dates.copy()
            for photo in candidates:
                asset_id = photo['id']
                if not valid_id(asset_id) or asset_id in ready:
                    continue
                if len(ready) >= self.settings.cache_count:
                    break
                try:
                    if not self._exists(asset_id):
                        data = await source.download(asset_id)
                        image = await asyncio.to_thread(normalized_image, data)
                        await asyncio.to_thread(atomic_write, self._path(asset_id), image)
                    ready.append(asset_id)
                    day = valid_date(photo.get('taken_date'))
                    if day:
                        dates[asset_id] = day
                    else:
                        dates.pop(asset_id, None)
                except (SourceError, OSError, ValueError, UnidentifiedImageError,
                        Image.DecompressionBombError, Image.DecompressionBombWarning):
                    logger.warning("cache_photo_failed")
            if not ready:
                return False
            ids = list(dict.fromkeys(ready + [a for a in self._ids if self._exists(a)]))[:self.settings.cache_count]
            dates = {a: dates[a] for a in ids if a in dates}
            manifest = json.dumps({"version": 1, "ids": ids, "dates": dates}).encode()
            await asyncio.to_thread(atomic_write, self.directory / "manifest.json", manifest)
            self._ids = ids
            self._dates = dates
            self.last_refresh_success = True
            for path in self.directory.glob("*.jpg"):
                if valid_id(path.stem) and path.stem not in ids:
                    path.unlink(missing_ok=True)
            return True
        except (SourceError, OSError):
            logger.warning("cache_refresh_failed")
            return False
