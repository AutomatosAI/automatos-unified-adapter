"""CLI entry point for the Unified Adapter."""

from __future__ import annotations

import asyncio

import uvicorn

from .config import get_settings
from .logging import configure_logging
from .server import build_server


async def _run() -> None:
    settings = get_settings()
    configure_logging(settings.adapter_log_level)

    mcp, app = await build_server(settings)
    transport = settings.adapter_transport.lower()

    if transport == "http":
        if not app:
            raise RuntimeError("HTTP app unavailable for transport=http")
        config = uvicorn.Config(app, host=settings.adapter_host, port=settings.adapter_port)
        server = uvicorn.Server(config)
        await server.serve()
        return
    if transport in {"streamable-http", "streamablehttp"}:
        if not app:
            raise RuntimeError("HTTP app unavailable for streamable transport")
        config = uvicorn.Config(app, host=settings.adapter_host, port=settings.adapter_port)
        server = uvicorn.Server(config)
        await server.serve()
        return
    await mcp.run_stdio_async()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
