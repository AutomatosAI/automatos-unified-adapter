"""Migrate Automatos MCP seed tools into the adapter tool store."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List

from unified_adapter.tool_store import ToolStore


def _load_seed(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _build_payload(item: Dict[str, Any], default_credential_mode: str) -> Dict[str, Any]:
    metadata = dict(item.get("metadata") or {})
    metadata["source"] = "automatos_seed"
    if item.get("capabilities") is not None:
        metadata["capabilities"] = item.get("capabilities")
    if item.get("credentials_schema") is not None:
        metadata["credentials_schema"] = item.get("credentials_schema")
    if item.get("logo"):
        metadata["logo"] = item.get("logo")

    adapter_type = "mcp" if item.get("mcp_server_url") else "rest"

    return {
        "name": item.get("name", "").strip(),
        "description": item.get("description", "") or "",
        "provider": item.get("provider", "unknown"),
        "category": item.get("category", "other"),
        "adapter_type": adapter_type,
        "enabled": item.get("status") == "active",
        "mcp_server_url": item.get("mcp_server_url"),
        "openapi_url": metadata.get("openapi_url"),
        "base_url": metadata.get("base_url"),
        "operation_ids": metadata.get("operation_ids") or [],
        "auth_config": metadata.get("auth_config") or {},
        "tags": item.get("tags") or [],
        "metadata": metadata,
        "credential_mode": default_credential_mode,
        "credential_environment": "production",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate tool metadata into adapter store")
    parser.add_argument(
        "--seed",
        default=os.getenv("AUTOMATOS_MCP_SEED_PATH", ""),
        help="Path to mcp_tools_seed.json",
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("ADAPTER_DATABASE_URL", ""),
        help="Adapter Postgres database URL",
    )
    parser.add_argument(
        "--default-credential-mode",
        default=os.getenv("DEFAULT_CREDENTIAL_MODE", "hosted"),
        choices=["hosted", "byo"],
        help="Default credential mode for imported tools",
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Start index within the seed list (default: 0)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of tools to import (0 = all)",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        default=True,
        help="Skip tools already present (by name).",
    )

    args = parser.parse_args()
    if not args.seed:
        raise SystemExit("Seed path missing. Set --seed or AUTOMATOS_MCP_SEED_PATH.")
    if not args.database_url:
        raise SystemExit("Database URL missing. Set --database-url or ADAPTER_DATABASE_URL.")

    seed_path = Path(args.seed).expanduser().resolve()
    if not seed_path.exists():
        raise SystemExit(f"Seed file not found: {seed_path}")

    store = ToolStore(args.database_url)
    tools = _load_seed(seed_path)
    if args.offset:
        tools = tools[args.offset :]
    if args.limit:
        tools = tools[: args.limit]

    existing_names = {
        tool.name for tool in store.list_tools(enabled_only=False)
    }

    created = 0
    skipped = 0
    for index, item in enumerate(tools, start=1):
        name = (item.get("name") or "").strip()
        if not name:
            continue
        if args.skip_existing and name in existing_names:
            skipped += 1
            continue
        payload = _build_payload(item, args.default_credential_mode)
        store.create_tool(payload)
        created += 1
        existing_names.add(name)
        if index % 50 == 0:
            print(f"Processed {index}/{len(tools)}...")

    print(f"Imported tools: {created} created, {skipped} skipped")


if __name__ == "__main__":
    main()
