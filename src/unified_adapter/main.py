 """CLI entry point for the Unified Adapter."""
 
 from __future__ import annotations
 
 import asyncio
 
 from .config import get_settings
 from .logging import configure_logging
 from .server import build_server
 
 
 async def _run() -> None:
     settings = get_settings()
     configure_logging(settings.adapter_log_level)
 
     mcp = await build_server(settings)
     transport = settings.adapter_transport.lower()
 
     if transport in {"http", "streamable-http", "streamablehttp"}:
         await mcp.run_streamable_http_async(
             host=settings.adapter_host, port=settings.adapter_port
         )
     else:
         await mcp.run_stdio_async()
 
 
 def main() -> None:
     asyncio.run(_run())
 
 
 if __name__ == "__main__":
     main()
