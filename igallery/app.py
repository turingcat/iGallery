import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .cache import PhotoCache
from .config import Settings
from .immich import ImmichClient

WEB = Path(__file__).parent / "web"


def create_app(settings: Settings, source: ImmichClient | None = None) -> FastAPI:
    cache = PhotoCache(settings)

    async def refresh_loop(client):
        while True:
            await cache.refresh(client)
            await asyncio.sleep(settings.refresh_seconds)

    @asynccontextmanager
    async def lifespan(app):
        cache.load()
        # No httpx informational logs: upstream URLs may contain private context.
        logging.getLogger("httpx").setLevel(logging.WARNING)
        async with httpx.AsyncClient(trust_env=False) as http:
            task = asyncio.create_task(refresh_loop(source or ImmichClient(settings, http)))
            try:
                yield
            finally:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.cache = cache

    @app.get("/")
    def index():
        return FileResponse(WEB / "index.html", headers={"Cache-Control": "no-store"})

    @app.get("/api/photos")
    def photos():
        from fastapi.responses import JSONResponse
        return JSONResponse({
            "photos": [{"id": a, "url": "/api/photo/" + a} for a in cache.photo_ids()],
            "interval_seconds": settings.interval_seconds,
        }, headers={"Cache-Control": "no-store"})

    @app.get("/api/photo/{asset_id}")
    def photo(asset_id: str):
        path = cache.path_for(asset_id)
        if path is None:
            raise HTTPException(status_code=404, detail="Photo unavailable")
        # Open now so a later refresh/unlink cannot break a streaming response.
        from fastapi.responses import StreamingResponse
        try:
            stream = path.open("rb")
        except OSError:
            raise HTTPException(status_code=404, detail="Photo unavailable") from None

        def chunks():
            with stream:
                while chunk := stream.read(65536):
                    yield chunk
        return StreamingResponse(chunks(), media_type="image/jpeg",
                                 headers={"Cache-Control": "private, max-age=60"})

    @app.get("/health")
    def health():
        return {"status": "ok", "cache_count": len(cache.photo_ids()),
                "last_refresh_success": cache.last_refresh_success}

    app.mount("/static", StaticFiles(directory=WEB), name="static")
    return app
