 """Core adapter service logic."""
 
 from __future__ import annotations
 
 import asyncio
 import logging
 from typing import Any, Dict, Optional
 
 from .automatos_client import AutomatosClient
 from .config import Settings
 from .executors import ExecutionError, McpExecutor, RestExecutor
 from .logging import redact_payload
 from .models import AdapterTool
 from .tool_registry import ToolRegistry
 
 
 logger = logging.getLogger(__name__)
 
 
 class AdapterService:
     def __init__(
         self,
         settings: Settings,
         automatos_client: AutomatosClient,
         tool_registry: ToolRegistry,
     ) -> None:
         self.settings = settings
         self.automatos_client = automatos_client
         self.tool_registry = tool_registry
         self.rest_executor = RestExecutor()
         self.mcp_executor = McpExecutor()
         self.semaphore = asyncio.Semaphore(settings.adapter_max_concurrency)
 
     async def execute_tool(self, tool: AdapterTool, payload: Dict[str, Any]) -> Dict[str, Any]:
         async with self.semaphore:
            logger.info("Executing tool=%s payload=%s", tool.tool_name, redact_payload(payload))
 
            payload_credentials = payload.pop("credentials", None)
            credentials = await self._resolve_credentials(tool, payload_credentials)
             try:
                 if tool.adapter_type == "rest" and tool.rest_operation:
                     result = await self.rest_executor.execute(
                         tool, tool.rest_operation, payload, credentials
                     )
                 elif tool.adapter_type == "mcp" and tool.mcp_operation:
                     result = await self.mcp_executor.execute(
                         tool, tool.mcp_operation, payload, credentials
                     )
                 else:
                     raise ExecutionError("Unsupported tool configuration")
 
                 return self._format_result(result)
             except ExecutionError as exc:
                 logger.error("Tool execution failed: %s", exc)
                 return self._format_error(str(exc))
 
    async def _resolve_credentials(
        self, tool: AdapterTool, payload_credentials: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        if tool.credential_mode == "byo":
            if not payload_credentials:
                raise ExecutionError("Missing credentials for BYO tool call")
            return payload_credentials

         ref = tool.credential_ref
         if ref.credential_id or ref.credential_name:
            resolved = await self.automatos_client.resolve_credential(
                 credential_id=ref.credential_id,
                 credential_name=ref.credential_name,
                 environment=ref.environment,
                 service_name=self.settings.service_name,
             )
            if not resolved:
                raise ExecutionError("Hosted credential not found")
            return resolved
 
         if ref.credential_type:
             type_id = await self.automatos_client.get_credential_type_id(ref.credential_type)
             if not type_id:
                 return None
             creds = await self.automatos_client.list_credentials(
                 credential_type_id=type_id, environment=ref.environment
             )
             if not creds:
                raise ExecutionError("Hosted credential not found")
             credential_name = creds[0].get("name")
            resolved = await self.automatos_client.resolve_credential(
                 credential_id=None,
                 credential_name=credential_name,
                 environment=ref.environment,
                 service_name=self.settings.service_name,
             )
            if not resolved:
                raise ExecutionError("Hosted credential not found")
            return resolved
 
        raise ExecutionError("Hosted credential reference missing")
 
     def _format_result(self, result: Any) -> Dict[str, Any]:
         return {"content": [{"type": "json", "json": result}]}
 
     def _format_error(self, message: str) -> Dict[str, Any]:
         return {"content": [{"type": "text", "text": message}], "is_error": True}
