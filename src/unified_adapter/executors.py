"""Execution layer for REST and MCP tool calls."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Optional

import httpx

from .logging import redact_payload
from .models import AdapterTool, McpOperation, RestOperation

logger = logging.getLogger(__name__)


class ExecutionError(Exception):
    pass


class CredentialInjector:
    def __init__(self, tool: AdapterTool) -> None:
        self.tool = tool

    def build_auth(
        self, credentials: Optional[Dict[str, Any]]
    ) -> tuple[Dict[str, str], Dict[str, str]]:
        headers: Dict[str, str] = {}
        query: Dict[str, str] = {}

        if not credentials:
            return headers, query

        adapter_meta = (self.tool.metadata or {}).get("adapter", {})
        auth = adapter_meta.get("auth") or {}
        auth_type = auth.get("type")

        if auth_type == "api_key":
            key_name = auth.get("name", "Authorization")
            location = auth.get("in", "header")
            template = auth.get("value_template")
            value = self._resolve_first_credential(credentials)
            if template:
                value = template.format(**credentials)
            if value is None:
                return headers, query
            if location == "query":
                query[key_name] = str(value)
            else:
                headers[key_name] = str(value)
        elif auth_type == "bearer":
            token = credentials.get("access_token") or self._resolve_first_credential(credentials)
            if token:
                headers["Authorization"] = f"Bearer {token}"

        return headers, query

    def _resolve_first_credential(self, credentials: Dict[str, Any]) -> Optional[str]:
        for _, value in credentials.items():
            if value:
                return str(value)
        return None


class RestExecutor:
    def __init__(self, max_retries: int = 2) -> None:
        self.max_retries = max_retries

    async def execute(
        self,
        tool: AdapterTool,
        operation: RestOperation,
        payload: Dict[str, Any],
        credentials: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        headers: Dict[str, str] = {}
        query: Dict[str, str] = {}

        injector = CredentialInjector(tool)
        auth_headers, auth_query = injector.build_auth(credentials)
        headers.update(auth_headers)
        query.update(auth_query)

        url, used_keys = self._build_url(operation.base_url, operation.path, payload)
        
        # Determine request body based on HTTP method
        method = operation.method.upper()
        body_data: Optional[str] = None
        form_data: Optional[Dict[str, str]] = None
        
        # For POST/PUT/PATCH: put remaining params in body (unless explicit 'body' key)
        if method in ("POST", "PUT", "PATCH"):
            explicit_body = payload.get("body")
            if explicit_body is not None:
                # Explicit body takes precedence
                headers["Content-Type"] = "application/json"
                body_data = json.dumps(explicit_body)
                # Any other params go to query
                query.update(self._extract_query_params(payload, used_keys | {"body"}))
            else:
                # Auto-detect: check tool metadata for content type hint
                adapter_meta = (tool.metadata or {}).get("adapter", {})
                content_type = adapter_meta.get("content_type", "application/x-www-form-urlencoded")
                
                # Extract params for body (exclude path-used keys and 'operation')
                body_params = self._extract_body_params(payload, used_keys | {"operation"})
                
                if body_params:
                    if content_type == "application/json":
                        headers["Content-Type"] = "application/json"
                        body_data = json.dumps(body_params)
                    else:
                        # Default: form-urlencoded (works for Slack and most APIs)
                        headers["Content-Type"] = "application/x-www-form-urlencoded"
                        form_data = body_params
        else:
            # GET/DELETE: use query params
            headers["Content-Type"] = "application/json"
            query.update(self._extract_query_params(payload, used_keys))

        attempt = 0
        while True:
            attempt += 1
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    if form_data:
                        response = await client.request(
                            method,
                            url,
                            headers=headers,
                            params=query,
                            data=form_data,
                        )
                    else:
                        response = await client.request(
                            method,
                            url,
                            headers=headers,
                            params=query,
                            content=body_data,
                        )
                response.raise_for_status()
                result = response.json() if response.content else {"status": "ok"}
                
                # Handle Slack-style responses where ok=false means error despite 200 OK
                if isinstance(result, dict) and result.get("ok") is False:
                    error_msg = result.get("error", "Unknown API error")
                    logger.warning("API returned ok=false: %s", error_msg)
                    # Still return result so caller can see the error details
                
                return result
            except Exception as exc:
                if attempt > self.max_retries:
                    raise ExecutionError(str(exc)) from exc
                backoff = min(2 ** attempt, 6)
                logger.warning(
                    "REST call failed (attempt %s/%s). Retrying in %ss. tool=%s payload=%s",
                    attempt,
                    self.max_retries,
                    backoff,
                    tool.tool_name,
                    redact_payload(payload),
                )
                await asyncio.sleep(backoff)

    def _build_url(self, base_url: str, path: str, payload: Dict[str, Any]) -> tuple[str, set[str]]:
        url = base_url.rstrip("/") + path
        used_keys: set[str] = set()
        for key, value in payload.items():
            token = f"{{{key}}}"
            if token in url:
                url = url.replace(token, str(value))
                used_keys.add(key)
        return url, used_keys

    def _extract_query_params(self, payload: Dict[str, Any], used_keys: set[str]) -> Dict[str, str]:
        query: Dict[str, str] = {}
        for key, value in payload.items():
            if key == "body" or key in used_keys:
                continue
            if isinstance(value, (str, int, float, bool)):
                query[key] = str(value)
        return query

    def _extract_body_params(self, payload: Dict[str, Any], exclude_keys: set[str]) -> Dict[str, str]:
        """Extract parameters for form body (excludes path params and special keys)."""
        body: Dict[str, str] = {}
        for key, value in payload.items():
            if key in exclude_keys:
                continue
            if isinstance(value, (str, int, float, bool)):
                body[key] = str(value)
            elif value is not None:
                # JSON-encode complex values
                body[key] = json.dumps(value)
        return body


class McpExecutor:
    def __init__(self, max_retries: int = 1) -> None:
        self.max_retries = max_retries

    async def execute(
        self,
        tool: AdapterTool,
        operation: McpOperation,
        payload: Dict[str, Any],
        credentials: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        url = self._normalize_mcp_url(operation.server_url)
        headers: Dict[str, str] = {"Content-Type": "application/json"}

        injector = CredentialInjector(tool)
        auth_headers, _ = injector.build_auth(credentials)
        headers.update(auth_headers)

        request_body = {
            "jsonrpc": "2.0",
            "id": "call-1",
            "method": "tools/call",
            "params": {
                "name": operation.method,
                "arguments": payload,
            },
        }

        attempt = 0
        while True:
            attempt += 1
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    response = await client.post(url, headers=headers, json=request_body)
                response.raise_for_status()
                response_data = response.json()
                return response_data.get("result", response_data)
            except Exception as exc:
                if attempt > self.max_retries:
                    raise ExecutionError(str(exc)) from exc
                backoff = min(2 ** attempt, 4)
                logger.warning(
                    "MCP call failed (attempt %s/%s). Retrying in %ss. tool=%s payload=%s",
                    attempt,
                    self.max_retries,
                    backoff,
                    tool.tool_name,
                    redact_payload(payload),
                )
                await asyncio.sleep(backoff)

    def _normalize_mcp_url(self, server_url: str) -> str:
        if server_url.endswith("/mcp"):
            return server_url
        return server_url.rstrip("/") + "/mcp"
