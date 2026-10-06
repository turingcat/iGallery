import logging

import uvicorn

from .app import create_app
from .config import load_settings


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        app = create_app(load_settings())
    except (ValueError, OSError):
        raise SystemExit("Invalid configuration or inaccessible cache directory") from None
    uvicorn.run(app, host="127.0.0.1", port=8080, workers=1, access_log=False)


if __name__ == "__main__":
    main()
