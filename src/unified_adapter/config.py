"""Configuration for the Unified Integrations Adapter."""

from __future__ import annotations

from functools import lru_cache
from typing import Optional, Set

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)

    service_name: str = Field(default="automatos-unified-adapter")

    automatos_api_base_url: str = Field(default="http://localhost:8000")
    automatos_api_key: str = Field(default="")
    automatos_api_timeout_seconds: float = Field(default=20)
    automatos_api_verify_ssl: bool = Field(default=True)

    adapter_transport: str = Field(default="streamable-http")
    adapter_host: str = Field(default="0.0.0.0")
    adapter_port: int = Field(default=8000)
    adapter_auth_token: Optional[str] = Field(default=None)
    adapter_database_url: str = Field(
        default="postgresql://user:password@host:5432/context_forge"
    )

    adapter_max_concurrency: int = Field(default=20)
    adapter_tool_cache_seconds: int = Field(default=300)
    adapter_openapi_cache_seconds: int = Field(default=3600)

    adapter_tool_allowlist: Optional[str] = Field(default=None)
    adapter_operation_allowlist: Optional[str] = Field(default=None)

    adapter_log_level: str = Field(default="INFO")

    clerk_jwks_url: Optional[str] = Field(default=None)
    clerk_issuer: Optional[str] = Field(default=None)
    clerk_audience: Optional[str] = Field(default=None)

    def tool_allowlist(self) -> Set[str]:
        if not self.adapter_tool_allowlist:
            return set()
        return {item.strip() for item in self.adapter_tool_allowlist.split(",") if item.strip()}

    def operation_allowlist(self) -> Set[str]:
        if not self.adapter_operation_allowlist:
            return set()
        return {
            item.strip()
            for item in self.adapter_operation_allowlist.split(",")
            if item.strip()
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
