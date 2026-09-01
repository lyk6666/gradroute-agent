"""Local API entry point."""

from __future__ import annotations

import uvicorn

from graduation_exception_agent.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "graduation_exception_agent.api.app:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
