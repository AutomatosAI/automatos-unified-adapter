"""Core adapter service logic (PRD-35 Enhanced)."""

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
    """
    Core adapter service for tool execution.
    
    PRD-35 Enhancement:
    - Supports credential_mode in MCP request meta
    - "byo" mode: credentials from request payload
    - "hosted" mode: callback to Automatos /api/tools/credentials/resolve
    """
    
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

    async def execute_tool(
        self,
        tool: AdapterTool,
        payload: Dict[str, Any],
        meta: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute a tool with credential resolution.
        
        Args:
            tool: The tool definition
            payload: Tool execution parameters
            meta: Request metadata containing credential_mode, tenant_id, etc.
        
        Returns:
            MCP-formatted result
        """
        async with self.semaphore:
            logger.info("Executing tool=%s payload=%s", tool.tool_name, redact_payload(payload))
            
            # Extract execution context from meta (PRD-35)
            meta = meta or {}
            
            # Check for credentials in both meta and payload
            byo_credentials = meta.get("credentials")
            payload_credentials = payload.pop("credentials", None)
            
            # IMPORTANT: Also check for 'token' in payload (Slack and other APIs use this)
            # If token is present, it's BYO mode
            if not payload_credentials and "token" in payload:
                payload_credentials = {"token": payload["token"]}
            
            # Merge credentials (payload takes precedence)
            final_credentials = payload_credentials or byo_credentials
            
            # Auto-detect credential mode:
            # If credentials are provided in request, it's BYO mode (no tenant_id needed)
            # Otherwise, use meta.credential_mode or tool default
            if final_credentials:
                credential_mode = "byo"
                logger.info("Auto-detected BYO mode (credentials in request)")
            else:
                credential_mode = meta.get("credential_mode", tool.credential_mode)
            
            tenant_id = meta.get("tenant_id")
            
            # Resolve credentials based on mode
            credentials = await self._resolve_credentials_v2(
                tool=tool,
                credential_mode=credential_mode,
                tenant_id=tenant_id,
                byo_credentials=final_credentials
            )
            
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

    async def _resolve_credentials_v2(
        self,
        tool: AdapterTool,
        credential_mode: str,
        tenant_id: Optional[str],
        byo_credentials: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        PRD-35: Resolve credentials based on mode.
        
        Args:
            tool: The tool definition
            credential_mode: "byo" or "hosted"
            tenant_id: Tenant UUID (required for hosted mode)
            byo_credentials: Credentials from request (for BYO mode)
        
        Returns:
            Resolved credential data
        """
        # BYO Mode: Use credentials from request
        if credential_mode == "byo":
            if not byo_credentials:
                raise ExecutionError("Missing credentials for BYO tool call")
            logger.info("Using BYO credentials for tool=%s", tool.tool_name)
            return byo_credentials
        
        # Hosted Mode: Callback to Automatos
        if credential_mode == "hosted":
            # Extract tool name from adapter tool (remove mcp_ prefix and method)
            tool_name = self._extract_tool_name(tool.tool_name)
            
            logger.info(
                "Resolving hosted credentials: tenant=%s tool=%s",
                tenant_id, tool_name
            )
            
            resolved = await self.automatos_client.resolve_tool_credential(
                tenant_id=tenant_id,
                tool_name=tool_name,
                service_name=self.settings.service_name
            )
            
            if not resolved:
                raise ExecutionError(
                    f"Hosted credential not found for tool '{tool_name}' in tenant"
                )
            
            return resolved
        
        # Legacy mode: Use tool's credential_ref
        return await self._resolve_credentials_legacy(tool, byo_credentials)
    
    async def _resolve_credentials_legacy(
        self,
        tool: AdapterTool,
        payload_credentials: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Legacy credential resolution using tool.credential_ref."""
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
    
    def _extract_tool_name(self, tool_name: str) -> str:
        """
        Extract the base tool name from a full tool name.
        
        E.g., "mcp_github_repos_list" -> "github"
        """
        if tool_name.startswith("mcp_"):
            parts = tool_name[4:].split("_", 1)  # Remove "mcp_" and split
            return parts[0] if parts else tool_name
        return tool_name

    def _format_result(self, result: Any) -> Dict[str, Any]:
        return {"content": [{"type": "json", "json": result}]}

    def _format_error(self, message: str) -> Dict[str, Any]:
        return {"content": [{"type": "text", "text": message}], "is_error": True}
