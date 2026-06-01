"""FastMCP server for grounded-rag-assistant (Project 2).

Phase 0: placeholder server. It constructs a named FastMCP server and runs it
over stdio so that an MCP client (Claude Code, Cursor, or the LangGraph agent)
can connect and see the server come up. No tools are registered yet — the
retrieval/generation tools land in Phase 1.

Run it with::

    make mcp-server          # docker compose run --no-deps -i api python -m app.mcp.server

The server blocks on stdio and exits cleanly on Ctrl-C / EOF.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

# Single shared server instance. Phase 1 registers tools against this object.
mcp = FastMCP("grounded-rag")


def main() -> None:
    """Run the FastMCP server on the stdio transport."""
    # stdio is the default transport; explicit for clarity. Phase 1 adds the
    # streamable-HTTP transport behind MCP_TRANSPORT=http.
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
