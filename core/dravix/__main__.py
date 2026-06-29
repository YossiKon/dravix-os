"""Entry point: ``python -m dravix`` (and the ``dravix`` console script)."""
from __future__ import annotations

import uvicorn

from .config import get_settings
from .logging import setup_logging


def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    uvicorn.run(
        "dravix.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
