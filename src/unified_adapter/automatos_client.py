"""Automatos API client for tools and credentials."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class AutomatosClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout_seconds: float = 20,
        verify_ssl: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.verify_ssl = verify_ssl

    def _headers(self) -> Dict[str, str]:
        return {"X-API-Key": self.api_key}

    async def list_mcp_tools(self, status: Optional[str] = "active") -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"limit": 10000}
        if status:
            params["status"] = status

        url = f"{self.base_url}/api/mcp-tools"
        async with httpx.AsyncClient(timeout=self.timeout_seconds, verify=self.verify_ssl) as client:
            response = await client.get(url, headers=self._headers(), params=params)
            response.raise_for_status()
            payload = response.json()

        if isinstance(payload, dict) and "data" in payload:
            return payload["data"]
        if isinstance(payload, list):
            return payload
        logger.warning("Unexpected MCP tools response shape: %s", type(payload))
        return []

    async def resolve_credential(
        self,
        credential_id: Optional[int],
        credential_name: Optional[str],
        environment: str,
        service_name: str,
    ) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}/api/credentials/resolve"
        payload: Dict[str, Any] = {
            "credential_id": credential_id,
            "credential_name": credential_name,
            "environment": environment,
            "service_name": service_name,
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds, verify=self.verify_ssl) as client:
            response = await client.post(url, headers=self._headers(), json=payload)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            data = response.json()

        return data.get("data") if isinstance(data, dict) else None

    async def get_credential_type_id(self, type_name: str) -> Optional[int]:
        url = f"{self.base_url}/api/credentials/types/by-name/{type_name}"
        async with httpx.AsyncClient(timeout=self.timeout_seconds, verify=self.verify_ssl) as client:
            response = await client.get(url, headers=self._headers())
            if response.status_code == 404:
                return None
            response.raise_for_status()
            payload = response.json()
        if isinstance(payload, dict):
            return payload.get("id")
        return None

    async def list_credentials(
        self,
        credential_type_id: Optional[int],
        environment: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/api/credentials"
        params: Dict[str, Any] = {"limit": 100}
        if credential_type_id:
            params["credential_type_id"] = credential_type_id
        if environment:
            params["environment"] = environment

        async with httpx.AsyncClient(timeout=self.timeout_seconds, verify=self.verify_ssl) as client:
            response = await client.get(url, headers=self._headers(), params=params)
            response.raise_for_status()
            payload = response.json()
        if isinstance(payload, dict):
            return payload.get("items", [])
        return []
