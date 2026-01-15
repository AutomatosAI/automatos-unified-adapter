"""MCP server setup for the Unified Adapter."""

import logging
from typing import Any, Awaitable, Callable, Dict, Optional

from fastmcp import FastMCP

from .admin_api import mount_admin_api
from .automatos_client import AutomatosClient
from .auth import ClerkJwtVerifier
from .config import Settings
from .openapi import OpenAPILoader
from .service import AdapterService
from .tool_registry import ToolRegistry
from .tool_store import ToolStore

logger = logging.getLogger(__name__)


async def build_server(settings: Settings) -> FastMCP:
    automatos_client = AutomatosClient(
        base_url=settings.automatos_api_base_url,
        api_key=settings.automatos_api_key,
        timeout_seconds=settings.automatos_api_timeout_seconds,
        verify_ssl=settings.automatos_api_verify_ssl,
    )
    tool_store = ToolStore(settings.adapter_database_url)
    openapi_loader = OpenAPILoader(cache_seconds=settings.adapter_openapi_cache_seconds)
    registry = ToolRegistry(settings, tool_store, openapi_loader)
    service = AdapterService(settings, automatos_client, registry)

    mcp = FastMCP(settings.service_name, instructions=_instructions())
    _attach_auth(mcp, settings)
    _attach_healthcheck(mcp)
    mount_admin_api(mcp.app, tool_store)  # type: ignore[arg-type]

    tools = await registry.load_tools()
    for tool in tools:
        handler = _tool_handler(service, tool)
        mcp.tool(name=tool.tool_name)(handler)
        logger.info("Registered tool: %s", tool.tool_name)

    return mcp


def _tool_handler(
    service: AdapterService, tool: Any
) -> Callable[[Any], Awaitable[Dict[str, Any]]]:
    async def handler(payload: tool.input_model) -> Dict[str, Any]:
        return await service.execute_tool(tool, payload.model_dump())

    handler.__name__ = tool.tool_name
    return handler


def _attach_auth(mcp: FastMCP, settings: Settings) -> None:
    app = getattr(mcp, "app", None)
    if not app:
        logger.warning("FastMCP app not available; auth middleware disabled")
        return

    clerk_verifier: Optional[ClerkJwtVerifier] = None
    if settings.clerk_jwks_url:
        clerk_verifier = ClerkJwtVerifier(
            jwks_url=settings.clerk_jwks_url,
            issuer=settings.clerk_issuer,
            audience=settings.clerk_audience,
        )

    @app.middleware("http")
    async def auth_middleware(request, call_next):  # type: ignore[no-untyped-def]
        if request.url.path.endswith("/health"):
            return await call_next(request)

        auth_header = request.headers.get("authorization", "")
        token = auth_header.replace("Bearer", "").strip()

        if settings.adapter_auth_token and token == settings.adapter_auth_token:
            request.state.auth = {"type": "service"}
            return await call_next(request)

        if clerk_verifier and token:
            try:
                auth_ctx = await clerk_verifier.verify(token)
                request.state.auth = auth_ctx
                return await call_next(request)
            except Exception as exc:
                logger.warning("JWT validation failed: %s", exc)

        from starlette.responses import JSONResponse

        return JSONResponse({"error": "Unauthorized"}, status_code=401)


def _attach_healthcheck(mcp: FastMCP) -> None:
    app = getattr(mcp, "app", None)
    if not app:
        return

    @app.get("/health")
    async def healthcheck():  # type: ignore[no-untyped-def]
        return {"status": "ok"}


def _instructions() -> str:
    return (
        "Unified Integrations Adapter for Automatos. "
        "This server aggregates tools from Automatos and proxies to REST or MCP upstreams."
    )
