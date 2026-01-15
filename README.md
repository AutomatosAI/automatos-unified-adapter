 # Automatos Unified Integrations Adapter
 
Standalone MCP server that exposes a single MCP endpoint for Context Forge discovery. It supports
REST passthrough (OpenAPI-backed) and proxying to upstream MCP servers while keeping tool metadata
in the adapter store (Automatos UI can act as a client).
 
 ## Why This Service Exists
 
 Automatos uses Context Forge as the single MCP gateway (`mcp.automatos.app`), but Context Forge only
 discovers tools from live MCP servers. The Unified Adapter bridges Automatos' tool catalog to a
 single MCP server so Context Forge can discover and invoke many integrations without running one
 MCP server per tool.
 
 Reference PRDs:
 - `docs/PRD-34-UNIFIED-INTEGRATIONS-ADAPTER.md`
 - `automatos-ai/docs/PRDS/33-MCP-GATEWAY-INTEGRATION.md`
 
 Research notes:
 - `docs/RESEARCH.md`
 - `docs/ARCHITECTURE.md`
 
 ## Architecture (High Level)
 
- Unified Adapter stores tool definitions and exposes them as MCP tools.
- Automatos UI can manage tools/credentials as a client.
 - Context Forge registers one gateway pointing to this adapter.
 - LLM tool calls flow: Automatos → Context Forge → Unified Adapter → SaaS API.
 
 ## Enterprise-Grade Design Notes
 
- Tool discovery caching with TTL.
- Credential resolution via Automatos `/api/credentials/resolve` (hosted mode).
 - Request concurrency limits and retry/backoff for upstream calls.
 - Optional allowlists for tools/operations to keep tool counts under model limits.
 - OpenAPI cache + operation filtering to avoid exposing thousands of endpoints.
 
 ## Quick Start
 
### 1) Configure Environment

Copy `env.example` and set values:
 
 ```
 AUTOMATOS_API_BASE_URL=https://api.automatos.app
 AUTOMATOS_API_KEY=your_internal_service_key
 ADAPTER_DATABASE_URL=postgresql://user:password@host:5432/context_forge
 ADAPTER_TRANSPORT=streamable-http
 ADAPTER_HOST=0.0.0.0
 ADAPTER_PORT=8000
 ADAPTER_AUTH_TOKEN=optional_shared_bearer_token
 CLERK_JWKS_URL=
 CLERK_ISSUER=
 CLERK_AUDIENCE=
 ```
 
 ### 2) Run Locally
 
 ```
 python -m venv .venv
 source .venv/bin/activate
 pip install -e ".[dev]"
 automatos-unified-adapter
 ```
 
 MCP endpoint (streamable HTTP): `http://localhost:8000/mcp`
 
 ### 3) Register with Context Forge
 
 ```
 curl -X POST https://mcp.automatos.app/gateways \
   -H "Authorization: Bearer $MCPGATEWAY_BEARER_TOKEN" \
   -H "Content-Type: application/json" \
   -d '{"name":"automatos-unified-adapter","url":"http://adapter:8000/mcp","transport":"streamablehttp"}'
 ```
 
## Tool Mapping Strategy

The adapter stores tool metadata and exposes MCP tools directly:

- MCP proxy tools: store `mcp_server_url` (HTTP/HTTPS only).
- REST passthrough tools: configure `openapi_url` + `operation_ids` + `auth` in the adapter.
 
 ```json
 {
   "adapter": {
     "type": "rest",
     "openapi_url": "https://api.example.com/openapi.json",
     "operation_ids": ["listUsers", "createUser"],
     "auth": {
       "type": "api_key",
       "in": "header",
       "name": "Authorization",
       "value_template": "Bearer {api_key}"
     }
   }
 }
 ```
 
Tools are exposed using the naming convention `mcp_<tool>_<method>` for compatibility with the
Automatos tool registry.

## Admin API (MVP)

Basic tool registry endpoints (protected by Clerk JWT or service token):

- `GET /admin/tools`
- `POST /admin/tools`
- `GET /admin/tools/{tool_id}`
- `PUT /admin/tools/{tool_id}`
- `DELETE /admin/tools/{tool_id}`
 
 ## Operational Notes
 
 - The adapter does **not** log credential values.
 - Use `ADAPTER_TOOL_ALLOWLIST` to keep tool counts low for LLM limits.
 - OpenAPI operations are cached to avoid frequent spec downloads.
- Tool discovery is loaded at startup; restart the service to pick up new tools.
 
 ## Repository Layout
 
 ```
 automatos-unified-adapter/
   src/unified_adapter/   # server + tool registry
   docs/                  # reference PRD
 ```
 
