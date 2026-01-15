"""Postgres-backed tool metadata store for the adapter."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg


logger = logging.getLogger(__name__)


@dataclass
class ToolRecord:
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


class ToolStore:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self._init_db()

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self.database_url)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS adapter_tools (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    provider TEXT NOT NULL,
                    category TEXT NOT NULL,
                    adapter_type TEXT NOT NULL,
                    enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    mcp_server_url TEXT,
                    openapi_url TEXT,
                    base_url TEXT,
                    operation_ids JSONB,
                    auth_config JSONB,
                    tags JSONB,
                    credential_mode TEXT NOT NULL DEFAULT 'hosted',
                    credential_id INTEGER,
                    credential_name TEXT,
                    credential_environment TEXT NOT NULL DEFAULT 'production',
                    org_id TEXT,
                    created_at TIMESTAMPTZ NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL
                )
                """
            )

    def list_tools(self, enabled_only: bool = True) -> List[ToolRecord]:
        with self._connect() as conn:
            query = "SELECT * FROM adapter_tools"
            params: List[Any] = []
            if enabled_only:
                query += " WHERE enabled = TRUE"
            rows = conn.execute(query, params).fetchall()
        return [self._to_record(row) for row in rows]

    def get_tool(self, tool_id: int) -> Optional[ToolRecord]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM adapter_tools WHERE id = %s", (tool_id,)
            ).fetchone()
        return self._to_record(row) if row else None

    def create_tool(self, payload: Dict[str, Any]) -> ToolRecord:
        now = datetime.utcnow()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO adapter_tools (
                    name, description, provider, category, adapter_type, enabled,
                    mcp_server_url, openapi_url, base_url, operation_ids, auth_config,
                    tags, credential_mode, credential_id, credential_name,
                    credential_environment, org_id, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    payload["name"],
                    payload.get("description", ""),
                    payload["provider"],
                    payload["category"],
                    payload["adapter_type"],
                    payload.get("enabled", True),
                    payload.get("mcp_server_url"),
                    payload.get("openapi_url"),
                    payload.get("base_url"),
                    payload.get("operation_ids", []),
                    payload.get("auth_config", {}),
                    payload.get("tags", []),
                    payload.get("credential_mode", "hosted"),
                    payload.get("credential_id"),
                    payload.get("credential_name"),
                    payload.get("credential_environment", "production"),
                    payload.get("org_id"),
                    now,
                    now,
                ),
            )
            tool_id = cursor.fetchone()[0]
        tool = self.get_tool(int(tool_id))
        if not tool:
            raise ValueError("Failed to create tool")
        return tool

    def update_tool(self, tool_id: int, payload: Dict[str, Any]) -> ToolRecord:
        existing = self.get_tool(tool_id)
        if not existing:
            raise ValueError("Tool not found")

        updated = {
            "name": payload.get("name", existing.name),
            "description": payload.get("description", existing.description),
            "provider": payload.get("provider", existing.provider),
            "category": payload.get("category", existing.category),
            "adapter_type": payload.get("adapter_type", existing.adapter_type),
            "enabled": payload.get("enabled", existing.enabled),
            "mcp_server_url": payload.get("mcp_server_url", existing.mcp_server_url),
            "openapi_url": payload.get("openapi_url", existing.openapi_url),
            "base_url": payload.get("base_url", existing.base_url),
            "operation_ids": payload.get("operation_ids", existing.operation_ids),
            "auth_config": payload.get("auth_config", existing.auth_config),
            "tags": payload.get("tags", existing.tags),
            "credential_mode": payload.get("credential_mode", existing.credential_mode),
            "credential_id": payload.get("credential_id", existing.credential_id),
            "credential_name": payload.get("credential_name", existing.credential_name),
            "credential_environment": payload.get(
                "credential_environment", existing.credential_environment
            ),
            "org_id": payload.get("org_id", existing.org_id),
        }

        now = datetime.utcnow()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE adapter_tools SET
                    name = %s, description = %s, provider = %s, category = %s,
                    adapter_type = %s, enabled = %s, mcp_server_url = %s, openapi_url = %s,
                    base_url = %s, operation_ids = %s, auth_config = %s, tags = %s,
                    credential_mode = %s, credential_id = %s, credential_name = %s,
                    credential_environment = %s, org_id = %s, updated_at = %s
                WHERE id = %s
                """,
                (
                    updated["name"],
                    updated["description"],
                    updated["provider"],
                    updated["category"],
                    updated["adapter_type"],
                    updated["enabled"],
                    updated["mcp_server_url"],
                    updated["openapi_url"],
                    updated["base_url"],
                    updated["operation_ids"],
                    updated["auth_config"],
                    updated["tags"],
                    updated["credential_mode"],
                    updated["credential_id"],
                    updated["credential_name"],
                    updated["credential_environment"],
                    updated["org_id"],
                    now,
                    tool_id,
                ),
            )
        return self.get_tool(tool_id)  # type: ignore[return-value]

    def delete_tool(self, tool_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM adapter_tools WHERE id = %s", (tool_id,))

    def _to_record(self, row) -> ToolRecord:
        return ToolRecord(
            id=int(row[0]),
            name=row[1],
            description=row[2] or "",
            provider=row[3],
            category=row[4],
            adapter_type=row[5],
            enabled=bool(row[6]),
            mcp_server_url=row[7],
            openapi_url=row[8],
            base_url=row[9],
            operation_ids=row[10] or [],
            auth_config=row[11] or {},
            tags=row[12] or [],
            credential_mode=row[13] or "hosted",
            credential_id=row[14],
            credential_name=row[15],
            credential_environment=row[16] or "production",
            org_id=row[17],
            created_at=str(row[18]),
            updated_at=str(row[19]),
        )
