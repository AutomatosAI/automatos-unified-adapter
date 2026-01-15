 # Research Summary: Unified Adapter Options
 
 This note captures the key findings used to inform the Unified Integrations Adapter design.
 
 ## Unified.to MCP
 
 - Unified offers a hosted MCP server with Streamable HTTP and SSE endpoints.
 - The MCP server surfaces tools based on Unified connections and permissions.
 - Each tool call counts against Unified API usage and is billed by plan.
 - Tool counts can exceed LLM limits, so explicit tool allowlists are required.
 
 Docs: `https://docs.unified.to/mcp` and `https://docs.unified.to/mcp/installation`.
 
 **Why not MVP:** Hosted pricing, vendor lock-in, and external dependency risk for a core gateway.
 
 ## Open Source MCP Servers
 
 - The official MCP servers repository provides reference servers.
 - Useful for testing, but not a unified, catalog-driven adapter.
 
 ## UTCP (Universal Tool Calling Protocol)
 
 - UTCP provides a direct-call alternative to MCP, avoiding wrapper tax.
 - UTCP → MCP bridge exists and could be evaluated long-term.
 
 Repo: `https://github.com/universal-tool-calling-protocol/utcp-mcp`
 
 **Why not MVP:** Requires protocol shift and ecosystem alignment with Context Forge.
 
 ## OpenAPI Registries
 
 - APIs.guru, Postman, and RapidAPI provide OpenAPI specs for REST passthrough.
 - These registries can bootstrap schemas, but specs still need validation.
 
 ## Chosen Direction
 
 Build an Automatos-hosted Unified Adapter that:
 - Uses Automatos as source of truth for tools and credentials.
 - Supports OpenAPI-backed REST passthrough.
 - Proxies upstream MCP servers when they exist.
 - Keeps Context Forge as the single external gateway.
