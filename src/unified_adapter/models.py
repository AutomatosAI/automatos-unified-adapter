"""Internal models for tool definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel


@dataclass(frozen=True)
class CredentialRef:
    credential_id: Optional[int] = None
    credential_name: Optional[str] = None
    credential_type: Optional[str] = None
    environment: str = "production"


@dataclass(frozen=True)
class RestOperation:
    operation_id: str
    method: str
    path: str
    base_url: str
    input_model: Type[BaseModel]
    description: str


@dataclass(frozen=True)
class McpOperation:
    method: str
    server_url: str


@dataclass(frozen=True)
class AdapterTool:
    tool_name: str
    description: str
    provider: str
    category: str
    adapter_type: str
    credential_mode: str
    credential_ref: CredentialRef
    input_model: Type[BaseModel]
    rest_operation: Optional[RestOperation] = None
    mcp_operation: Optional[McpOperation] = None
    metadata: Dict[str, Any] | None = None
    tags: List[str] | None = None
