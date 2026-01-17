"""Admin API for managing adapter tools."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse

from .auth import AuthContext
from .tool_store import ToolRecord, ToolStore


logger = logging.getLogger(__name__)


class ToolCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    provider: str
    category: str
    adapter_type: str = Field(..., description="rest or mcp")
    enabled: bool = True
    mcp_server_url: Optional[str] = None
    openapi_url: Optional[str] = None
    base_url: Optional[str] = None
    operation_ids: List[str] = Field(default_factory=list)
    auth_config: Dict[str, Any] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    credential_mode: str = Field(default="hosted", description="hosted or byo")
    credential_id: Optional[int] = None
    credential_name: Optional[str] = None
    credential_environment: str = "production"
    org_id: Optional[str] = None


class ToolUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    provider: Optional[str] = None
    category: Optional[str] = None
    adapter_type: Optional[str] = None
    enabled: Optional[bool] = None
    mcp_server_url: Optional[str] = None
    openapi_url: Optional[str] = None
    base_url: Optional[str] = None
    operation_ids: Optional[List[str]] = None
    auth_config: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None
    credential_mode: Optional[str] = None
    credential_id: Optional[int] = None
    credential_name: Optional[str] = None
    credential_environment: Optional[str] = None
    org_id: Optional[str] = None


class ToolResponse(BaseModel):
    id: int
    name: str
    description: str
    provider: str
    category: str
    adapter_type: str
    enabled: bool
    mcp_server_url: Optional[str]
    openapi_url: Optional[str]
    base_url: Optional[str]
    operation_ids: List[str]
    auth_config: Dict[str, Any]
    tags: List[str]
    metadata: Dict[str, Any]
    credential_mode: str
    credential_id: Optional[int]
    credential_name: Optional[str]
    credential_environment: str
    org_id: Optional[str]
    created_at: str
    updated_at: str


def mount_admin_api(app, store: ToolStore) -> None:  # type: ignore[no-untyped-def]
    async def list_tools(request: Request) -> JSONResponse:
        _require_auth(request)
        tools = store.list_tools(enabled_only=False)
        payload = [_to_response(t).model_dump() for t in tools]
        return JSONResponse(payload)

    async def create_tool(request: Request) -> JSONResponse:
        auth = _require_auth(request)
        try:
            payload = await request.json()
            data = ToolCreate(**payload).model_dump()
        except ValidationError as exc:
            return JSONResponse({"error": "Invalid payload", "details": exc.errors()}, status_code=422)
        if not data.get("org_id") and auth.org_id:
            data["org_id"] = auth.org_id
        tool = store.create_tool(data)
        return JSONResponse(_to_response(tool).model_dump())

    async def get_tool(request: Request) -> JSONResponse:
        _require_auth(request)
        tool_id = int(request.path_params["tool_id"])
        tool = store.get_tool(tool_id)
        if not tool:
            return JSONResponse({"error": "Not found"}, status_code=404)
        return JSONResponse(_to_response(tool).model_dump())

    async def update_tool(request: Request) -> JSONResponse:
        auth = _require_auth(request)
        tool_id = int(request.path_params["tool_id"])
        try:
            payload = await request.json()
            data = ToolUpdate(**payload).model_dump(exclude_unset=True)
        except ValidationError as exc:
            return JSONResponse({"error": "Invalid payload", "details": exc.errors()}, status_code=422)
        if not data.get("org_id") and auth.org_id:
            data["org_id"] = auth.org_id
        try:
            tool = store.update_tool(tool_id, data)
        except ValueError:
            return JSONResponse({"error": "Not found"}, status_code=404)
        return JSONResponse(_to_response(tool).model_dump())

    async def delete_tool(request: Request) -> JSONResponse:
        _require_auth(request)
        tool_id = int(request.path_params["tool_id"])
        store.delete_tool(tool_id)
        return JSONResponse({"status": "deleted"})

    async def execute_tool(request: Request) -> JSONResponse:
        """Execute a tool by ID with provided payload and credentials."""
        auth = _require_auth(request)
        tool_id = int(request.path_params["tool_id"])
        
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        
        # Get the tool record
        tool_record = store.get_tool(tool_id)
        if not tool_record:
            # Try to find by name from payload (cross-system ID mismatch handling)
            tool_name = payload.get("tool_name") or payload.get("name")
            if tool_name:
                tool_record = store.get_tool_by_name(tool_name)
            if not tool_record:
                return JSONResponse({"error": f"Tool {tool_id} not found"}, status_code=404)
        
        if not tool_record.enabled:
            return JSONResponse({"error": f"Tool {tool_record.name} is disabled"}, status_code=400)
        
        # Extract execution parameters
        operation = payload.pop("operation", None) or payload.pop("method", "default")
        params = payload.pop("params", payload.pop("parameters", {}))
        credentials = payload.pop("credentials", None)
        meta = payload.pop("meta", None) or payload.pop("_meta", {})
        
        # Import here to avoid circular dependency
        from .tool_registry import ToolRegistry
        from .service import AdapterService
        from .openapi import OpenAPILoader
        from .automatos_client import AutomatosClient
        from .config import get_settings
        
        settings = get_settings()
        automatos_client = AutomatosClient(
            base_url=settings.automatos_api_base_url,
            api_key=settings.automatos_api_key,
        )
        openapi_loader = OpenAPILoader(cache_seconds=settings.adapter_openapi_cache_seconds)
        registry = ToolRegistry(settings, store, openapi_loader)
        service = AdapterService(settings, automatos_client, registry)
        
        try:
            # Load the tool from registry (includes operations from OpenAPI)
            tools = await registry.load_tools()
            # Tool names are formatted as mcp_{ToolName}_{OperationId}
            tool_prefix = f"mcp_{tool_record.name}_".lower()
            
            # Get all tools for this provider
            provider_tools = [t for t in tools if t.tool_name.lower().startswith(tool_prefix)]
            adapter_tool = None
            
            if operation and operation != "default":
                # Try exact operation match first
                target_name = f"mcp_{tool_record.name}_{operation}".lower()
                adapter_tool = next((t for t in provider_tools if t.tool_name.lower() == target_name), None)
                
                # Try fuzzy matching on operation keywords
                if not adapter_tool:
                    # Normalize operation: post_message -> ["post", "message"]
                    op_keywords = [k.lower() for k in operation.replace("_", " ").replace("-", " ").split()]
                    
                    # Score tools by how many keywords they match
                    scored_tools = []
                    for t in provider_tools:
                        tool_lower = t.tool_name.lower()
                        # Count matching keywords
                        matches = sum(1 for kw in op_keywords if kw in tool_lower)
                        if matches > 0:
                            scored_tools.append((t, matches))
                    
                    # Sort by match count (descending) and prefer shorter names (more specific)
                    scored_tools.sort(key=lambda x: (-x[1], len(x[0].tool_name)))
                    
                    if scored_tools:
                        adapter_tool = scored_tools[0][0]
                        logger.info(f"Fuzzy matched operation '{operation}' to tool '{adapter_tool.tool_name}'")
            
            # If still no match, use first tool from provider (but warn)
            if not adapter_tool and provider_tools:
                adapter_tool = provider_tools[0]
                logger.warning(f"No operation match for '{operation}', falling back to first tool: {adapter_tool.tool_name}")
            
            if not adapter_tool:
                available = [t.tool_name for t in tools if tool_record.name.lower() in t.tool_name.lower()]
                return JSONResponse({
                    "error": f"Tool {tool_record.name} could not be loaded from registry",
                    "details": f"Available matching tools: {available[:5]}"
                }, status_code=500)
            
            # Build execution payload
            execution_payload = {
                **params,
                "operation": operation
            }
            
            # Build meta with credentials if provided
            execution_meta = {**meta}
            if credentials:
                execution_meta["credentials"] = credentials
                execution_meta["credential_mode"] = "byo"
            elif meta.get("tenant_id"):
                execution_meta["credential_mode"] = "hosted"
            
            # Execute via AdapterService
            result = await service.execute_tool(adapter_tool, execution_payload, meta=execution_meta)
            
            return JSONResponse({
                "success": True,
                "tool": tool_record.name,
                "operation": operation,
                "result": result
            })
            
        except Exception as e:
            logger.exception(f"Tool execution failed: {tool_record.name}")
            return JSONResponse({
                "success": False,
                "error": str(e),
                "tool": tool_record.name
            }, status_code=500)

    async def execute_tool_by_name(request: Request) -> JSONResponse:
        """Execute a tool by name with provided payload and credentials."""
        auth = _require_auth(request)
        tool_name = request.path_params["tool_name"]
        
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        
        # Get the tool record by name
        tool_record = store.get_tool_by_name(tool_name)
        if not tool_record:
            return JSONResponse({"error": f"Tool '{tool_name}' not found"}, status_code=404)
        
        if not tool_record.enabled:
            return JSONResponse({"error": f"Tool {tool_record.name} is disabled"}, status_code=400)
        
        # Extract execution parameters
        operation = payload.pop("operation", None) or payload.pop("method", "default")
        params = payload.pop("params", payload.pop("parameters", {}))
        credentials = payload.pop("credentials", None)
        meta = payload.pop("meta", None) or payload.pop("_meta", {})
        
        from .tool_registry import ToolRegistry
        from .service import AdapterService
        from .openapi import OpenAPILoader
        from .automatos_client import AutomatosClient
        from .config import get_settings
        
        settings = get_settings()
        automatos_client = AutomatosClient(
            base_url=settings.automatos_api_base_url,
            api_key=settings.automatos_api_key,
        )
        openapi_loader = OpenAPILoader(cache_seconds=settings.adapter_openapi_cache_seconds)
        registry = ToolRegistry(settings, store, openapi_loader)
        service = AdapterService(settings, automatos_client, registry)
        
        try:
            tools = await registry.load_tools()
            # Tool names are formatted as mcp_{ToolName}_{OperationId}
            # Find tool matching: mcp_{tool_record.name}_{operation} or any mcp_{tool_record.name}_*
            tool_prefix = f"mcp_{tool_record.name}_".lower()
            
            # Get all tools for this provider
            provider_tools = [t for t in tools if t.tool_name.lower().startswith(tool_prefix)]
            adapter_tool = None
            
            if operation and operation != "default":
                # Try exact operation match first
                target_name = f"mcp_{tool_record.name}_{operation}".lower()
                adapter_tool = next((t for t in provider_tools if t.tool_name.lower() == target_name), None)
                
                # Try fuzzy matching on operation keywords
                if not adapter_tool:
                    # Normalize operation: post_message -> ["post", "message"]
                    op_keywords = [k.lower() for k in operation.replace("_", " ").replace("-", " ").split()]
                    
                    # Score tools by how many keywords they match
                    scored_tools = []
                    for t in provider_tools:
                        tool_lower = t.tool_name.lower()
                        # Count matching keywords
                        matches = sum(1 for kw in op_keywords if kw in tool_lower)
                        if matches > 0:
                            scored_tools.append((t, matches))
                    
                    # Sort by match count (descending) and prefer shorter names (more specific)
                    scored_tools.sort(key=lambda x: (-x[1], len(x[0].tool_name)))
                    
                    if scored_tools:
                        adapter_tool = scored_tools[0][0]
                        logger.info(f"Fuzzy matched operation '{operation}' to tool '{adapter_tool.tool_name}'")
            
            # If still no match, use first tool from provider (but warn)
            if not adapter_tool and provider_tools:
                adapter_tool = provider_tools[0]
                logger.warning(f"No operation match for '{operation}', falling back to first tool: {adapter_tool.tool_name}")
            
            if not adapter_tool:
                available = [t.tool_name for t in tools if tool_record.name.lower() in t.tool_name.lower()]
                return JSONResponse({
                    "error": f"Tool {tool_record.name} could not be loaded from registry",
                    "details": f"OpenAPI spec may be unavailable. Available matching tools: {available[:5]}"
                }, status_code=500)
            
            execution_payload = {**params, "operation": operation}
            execution_meta = {**meta}
            if credentials:
                execution_meta["credentials"] = credentials
                execution_meta["credential_mode"] = "byo"
            elif meta.get("tenant_id"):
                execution_meta["credential_mode"] = "hosted"
            
            result = await service.execute_tool(adapter_tool, execution_payload, meta=execution_meta)
            
            return JSONResponse({
                "success": True,
                "tool": tool_record.name,
                "operation": operation,
                "result": result
            })
            
        except Exception as e:
            logger.exception(f"Tool execution failed: {tool_record.name}")
            return JSONResponse({
                "success": False,
                "error": str(e),
                "tool": tool_record.name
            }, status_code=500)

    app.add_route("/admin/tools", list_tools, methods=["GET"])
    app.add_route("/admin/tools", create_tool, methods=["POST"])
    app.add_route("/admin/tools/{tool_id:int}", get_tool, methods=["GET"])
    app.add_route("/admin/tools/{tool_id:int}", update_tool, methods=["PUT"])
    app.add_route("/admin/tools/{tool_id:int}", delete_tool, methods=["DELETE"])
    app.add_route("/admin/tools/{tool_id:int}/execute", execute_tool, methods=["POST"])
    app.add_route("/admin/tools/name/{tool_name:str}/execute", execute_tool_by_name, methods=["POST"])


def _require_auth(request) -> AuthContext:  # type: ignore[no-untyped-def]
    auth = getattr(request.state, "auth", None)
    if not auth:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if isinstance(auth, dict):
        return AuthContext(subject="service", org_id=None, claims=auth)
    return auth


def _to_response(tool: ToolRecord) -> ToolResponse:
    return ToolResponse(
        id=tool.id,
        name=tool.name,
        description=tool.description,
        provider=tool.provider,
        category=tool.category,
        adapter_type=tool.adapter_type,
        enabled=tool.enabled,
        mcp_server_url=tool.mcp_server_url,
        openapi_url=tool.openapi_url,
        base_url=tool.base_url,
        operation_ids=tool.operation_ids,
        auth_config=tool.auth_config,
        tags=tool.tags,
        metadata=tool.metadata,
        credential_mode=tool.credential_mode,
        credential_id=tool.credential_id,
        credential_name=tool.credential_name,
        credential_environment=tool.credential_environment,
        org_id=tool.org_id,
        created_at=tool.created_at,
        updated_at=tool.updated_at,
    )
