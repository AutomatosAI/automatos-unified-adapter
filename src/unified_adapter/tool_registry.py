 """Tool registry for the Unified Adapter."""
 
 from __future__ import annotations
 
import logging
import time
from typing import Any, Dict, List, Optional
 
 from pydantic import BaseModel, ConfigDict, create_model
 
 from .config import Settings
 from .models import AdapterTool, CredentialRef, McpOperation, RestOperation
 from .openapi import OpenAPILoader
from .tool_store import ToolRecord, ToolStore
 
 
 logger = logging.getLogger(__name__)
 
 
 class ToolRegistry:
     def __init__(
         self,
         settings: Settings,
        tool_store: ToolStore,
         openapi_loader: OpenAPILoader,
     ) -> None:
         self.settings = settings
        self.tool_store = tool_store
         self.openapi_loader = openapi_loader
         self._cache: List[AdapterTool] = []
         self._cache_timestamp: float = 0.0
 
     async def load_tools(self) -> List[AdapterTool]:
         if self._cache and time.time() - self._cache_timestamp < self.settings.adapter_tool_cache_seconds:
             return self._cache
 
        mcp_tools = self.tool_store.list_tools(enabled_only=True)
         tools: List[AdapterTool] = []
         allowlist = self.settings.tool_allowlist()
         op_allowlist = self.settings.operation_allowlist()
 
         for tool in mcp_tools:
            adapter_metadata = {
                "type": tool.adapter_type,
                "openapi_url": tool.openapi_url,
                "base_url": tool.base_url,
                "operation_ids": tool.operation_ids,
                "auth": tool.auth_config,
                "credential_mode": tool.credential_mode,
                "org_id": tool.org_id,
            }

            if tool.adapter_type == "rest":
                 rest_tools = await self._build_rest_tools(tool, adapter_metadata, op_allowlist)
                 tools.extend(rest_tools)
                 continue
 
            if tool.mcp_server_url and tool.mcp_server_url.startswith("http"):
                 mcp_tools = self._build_mcp_tools(tool, allowlist)
                 tools.extend(mcp_tools)
                 continue
 
            logger.info("Skipping non-executable tool: %s", tool.name)
 
         if allowlist:
             tools = [t for t in tools if t.tool_name in allowlist or t.provider in allowlist]
 
         self._cache = tools
         self._cache_timestamp = time.time()
         return tools
 
     async def _build_rest_tools(
         self,
        tool: ToolRecord,
         adapter_metadata: Dict[str, Any],
         op_allowlist: set[str],
     ) -> List[AdapterTool]:
         openapi_url = adapter_metadata.get("openapi_url")
         if not openapi_url:
            logger.warning("REST tool missing openapi_url: %s", tool.name)
             return []
 
         spec = await self.openapi_loader.load_spec(openapi_url)
         if not spec:
             return []
 
         operations = self.openapi_loader.extract_operations(spec)
         allowed_ops = set(adapter_metadata.get("operation_ids") or [])
         if op_allowlist:
             allowed_ops.update(op_allowlist)
 
         base_url = adapter_metadata.get("base_url") or self._extract_server_url(spec)
         if not base_url:
             logger.warning("OpenAPI spec missing server URL: %s", openapi_url)
             return []
 
         tools: List[AdapterTool] = []
         for op in operations:
             if allowed_ops and op.operation_id not in allowed_ops:
                 continue
            tool_name = self._format_tool_name(tool.name, op.operation_id)
             credential_ref = self._build_credential_ref(tool, adapter_metadata)
 
             rest_operation = RestOperation(
                 operation_id=op.operation_id,
                 method=op.method,
                 path=op.path,
                 base_url=base_url,
                 input_model=op.input_model,
                 description=op.description,
             )
 
             tools.append(
                 AdapterTool(
                     tool_name=tool_name,
                    description=op.description or tool.description or "",
                    provider=tool.provider or "unknown",
                    category=tool.category or "other",
                     adapter_type="rest",
                    credential_mode=tool.credential_mode,
                     credential_ref=credential_ref,
                     input_model=op.input_model,
                     rest_operation=rest_operation,
                    metadata=adapter_metadata,
                    tags=tool.tags or [],
                 )
             )
 
         return tools
 
    def _build_mcp_tools(self, tool: ToolRecord, allowlist: set[str]) -> List[AdapterTool]:
        methods = tool.operation_ids or []
        mcp_server_url = tool.mcp_server_url
         if not mcp_server_url:
             return []
 
         tools: List[AdapterTool] = []
        for method in methods or ["call"]:
            tool_name = self._format_tool_name(tool.name, method)
            if allowlist and tool_name not in allowlist and tool.name not in allowlist:
                 continue
 
             input_model = self._generic_input_model(tool_name)
             credential_ref = self._build_credential_ref(tool, {})
 
             tools.append(
                 AdapterTool(
                     tool_name=tool_name,
                    description=tool.description or "",
                    provider=tool.provider or "unknown",
                    category=tool.category or "other",
                     adapter_type="mcp",
                    credential_mode=tool.credential_mode,
                     credential_ref=credential_ref,
                     input_model=input_model,
                     mcp_operation=McpOperation(method=method, server_url=mcp_server_url),
                    metadata={"credential_mode": tool.credential_mode},
                    tags=tool.tags or [],
                 )
             )
 
         return tools
 
    def _build_credential_ref(
        self, tool: ToolRecord, adapter_metadata: Dict[str, Any]
    ) -> CredentialRef:
         return CredentialRef(
            credential_id=tool.credential_id,
            credential_name=tool.credential_name,
            credential_type=None,
            environment=tool.credential_environment,
         )
 
     def _generic_input_model(self, tool_name: str) -> type[BaseModel]:
         model_config = ConfigDict(extra="allow")
         return create_model(f"{self._sanitize_name(tool_name)}Input", __config__=model_config)
 
     def _format_tool_name(self, tool_name: Optional[str], method: str) -> str:
         base = self._sanitize_name(tool_name or "tool")
         suffix = self._sanitize_name(method)
         return f"mcp_{base}_{suffix}"
 
     def _sanitize_name(self, name: str) -> str:
         return "".join(ch.lower() if ch.isalnum() else "_" for ch in name)
 
     def _extract_server_url(self, spec: Dict[str, Any]) -> Optional[str]:
         servers = spec.get("servers") or []
         if not servers:
             return None
         server = servers[0]
         if isinstance(server, dict):
             return server.get("url")
         return None
