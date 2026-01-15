"""Admin API for managing adapter tools."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from starlette.exceptions import HTTPException

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
    credential_mode: str
    credential_id: Optional[int]
    credential_name: Optional[str]
    credential_environment: str
    org_id: Optional[str]
    created_at: str
    updated_at: str


def mount_admin_api(app, store: ToolStore) -> None:  # type: ignore[no-untyped-def]
    @app.get("/admin/tools", response_model=List[ToolResponse])
    async def list_tools(request):  # type: ignore[no-untyped-def]
        _require_auth(request)
        tools = store.list_tools(enabled_only=False)
        return [_to_response(t) for t in tools]

    @app.post("/admin/tools", response_model=ToolResponse)
    async def create_tool(request, payload: ToolCreate):  # type: ignore[no-untyped-def]
        auth = _require_auth(request)
        data = payload.model_dump()
        if not data.get("org_id") and auth.org_id:
            data["org_id"] = auth.org_id
        tool = store.create_tool(data)
        return _to_response(tool)

    @app.get("/admin/tools/{tool_id}", response_model=ToolResponse)
    async def get_tool(request, tool_id: int):  # type: ignore[no-untyped-def]
        _require_auth(request)
        tool = store.get_tool(tool_id)
        if not tool:
            from starlette.responses import JSONResponse

            return JSONResponse({"error": "Not found"}, status_code=404)
        return _to_response(tool)

    @app.put("/admin/tools/{tool_id}", response_model=ToolResponse)
    async def update_tool(request, tool_id: int, payload: ToolUpdate):  # type: ignore[no-untyped-def]
        auth = _require_auth(request)
        data = payload.model_dump(exclude_unset=True)
        if not data.get("org_id") and auth.org_id:
            data["org_id"] = auth.org_id
        try:
            tool = store.update_tool(tool_id, data)
        except ValueError:
            from starlette.responses import JSONResponse

            return JSONResponse({"error": "Not found"}, status_code=404)
        return _to_response(tool)

    @app.delete("/admin/tools/{tool_id}")
    async def delete_tool(request, tool_id: int):  # type: ignore[no-untyped-def]
        _require_auth(request)
        store.delete_tool(tool_id)
        return {"status": "deleted"}


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
        credential_mode=tool.credential_mode,
        credential_id=tool.credential_id,
        credential_name=tool.credential_name,
        credential_environment=tool.credential_environment,
        org_id=tool.org_id,
        created_at=tool.created_at,
        updated_at=tool.updated_at,
    )
