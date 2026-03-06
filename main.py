"""Code Knowledge Graph — MCP server for Claude Desktop."""

from __future__ import annotations

import json
import logging
import os

from mcp.server.fastmcp import FastMCP

from code_graph.indexer import Indexer
from code_graph.neo4j_store import Neo4jStore

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")
log = logging.getLogger("code_graph")

# ── Configuration ────────────────────────────────────────────────────────────
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "codegraph")

# ── Shared state ─────────────────────────────────────────────────────────────
store = Neo4jStore(uri=NEO4J_URI, user=NEO4J_USER, password=NEO4J_PASSWORD)
indexer = Indexer(store)

# ── MCP Server ───────────────────────────────────────────────────────────────
mcp = FastMCP(
    "code-graph",
    instructions="Code Knowledge Graph — query business logic directly from source code across Swift, Kotlin, PHP, Python, JS, TS, Go, Dart, C#.",
)


async def _ensure_connected():
    if store._driver is None:
        await store.connect()


# ── Tools ────────────────────────────────────────────────────────────────────


@mcp.tool()
async def index_repository(
    path: str,
    name: str | None = None,
    incremental: bool = True,
) -> str:
    """Index a local git repository into the code knowledge graph.

    Parses source files (Swift, Kotlin, PHP, Python, JS, TS, Go, Dart, C#)
    and extracts classes, functions, endpoints, DB models, imports, and call graphs.

    Args:
        path: Absolute path to the repository root directory.
        name: Optional human-readable name. Defaults to directory name.
        incremental: Skip unchanged files (default True).
    """
    await _ensure_connected()
    if not os.path.isdir(path):
        return f"Error: directory not found: {path}"
    stats = await indexer.index_repository(path, repo_name=name, incremental=incremental)
    return json.dumps(stats, indent=2)


@mcp.tool()
async def query_code(cypher: str) -> str:
    """Execute a Cypher query against the code knowledge graph.

    The graph contains nodes: Repository, Service, File, Module, Class, Function,
    Variable, Endpoint, DatabaseTable, Event, ExternalAPI, BusinessRule.

    Relationships: CONTAINS_FILE, DEFINES, CONTAINS, HAS_METHOD, HAS_FIELD,
    EXTENDS, IMPLEMENTS, CALLS, CALLS_EXTERNAL, EXPOSES, HANDLED_BY,
    READS_FROM, WRITES_TO, PUBLISHES, SUBSCRIBES_TO, IMPORTS.

    All nodes have: fqn, name, file_path, start_line, end_line, language, repo.

    Example queries:
    - "MATCH (c:Class) WHERE c.repo = 'myapp' RETURN c.name, c.file_path LIMIT 20"
    - "MATCH (f:Function)-[:CALLS]->(g:Function) RETURN f.name, g.name LIMIT 20"
    - "MATCH (ep:Endpoint) RETURN ep.name, ep.path, ep.http_method"

    Args:
        cypher: A Cypher query string.
    """
    await _ensure_connected()
    records = await store.query(cypher)
    return json.dumps(records, indent=2, default=str)


@mcp.tool()
async def find_callers(function_name: str) -> str:
    """Find all functions that call a given function.

    Args:
        function_name: Name of the function to search for (partial match supported).
    """
    await _ensure_connected()
    records = await store.find_callers(function_name)
    if not records:
        return f"No callers found for '{function_name}'"
    return json.dumps(records, indent=2, default=str)


@mcp.tool()
async def find_dependencies(service_name: str) -> str:
    """Find what a service/repository depends on (imports and external calls).

    Args:
        service_name: Repository name as indexed.
    """
    await _ensure_connected()
    records = await store.find_dependencies(service_name)
    if not records:
        return f"No dependencies found for '{service_name}'"
    return json.dumps(records, indent=2, default=str)


@mcp.tool()
async def trace_endpoint(path: str, method: str = "") -> str:
    """Trace an API endpoint through the call graph.

    Shows the handler function and what it calls (up to 5 levels deep).

    Args:
        path: API path or partial path (e.g. "/api/users", "/checkout").
        method: HTTP method filter (GET, POST, etc.). Empty matches all.
    """
    await _ensure_connected()
    records = await store.trace_endpoint(path, method)
    if not records:
        return f"No endpoint found matching '{method} {path}'"
    return json.dumps(records, indent=2, default=str)


@mcp.tool()
async def list_services() -> str:
    """List all indexed repositories/services with their languages and file counts."""
    await _ensure_connected()
    records = await store.list_services()
    if not records:
        return "No services indexed yet. Use index_repository to add one."
    return json.dumps(records, indent=2, default=str)


@mcp.tool()
async def search_code(name: str) -> str:
    """Fuzzy search for any code entity (class, function, endpoint, etc.) by name.

    Args:
        name: Search term (partial match on entity names).
    """
    await _ensure_connected()
    records = await store.search_code(name)
    if not records:
        return f"No entities found matching '{name}'"
    return json.dumps(records, indent=2, default=str)


@mcp.tool()
async def graph_stats() -> str:
    """Return basic statistics about the code knowledge graph (node counts, relationships)."""
    await _ensure_connected()
    stats = await store.get_stats()
    return json.dumps(stats, indent=2)


async def cli_index(paths: list[str], names: list[str | None]):
    """CLI entry point for indexing repositories."""
    await store.connect()
    try:
        for path, name in zip(paths, names):
            print(f"\n{'='*60}")
            print(f"Indexing: {path}" + (f" (as {name})" if name else ""))
            print(f"{'='*60}")
            stats = await indexer.index_repository(path, repo_name=name, incremental=True)
            print(json.dumps(stats, indent=2))
        print(f"\nDone. Graph stats:")
        print(json.dumps(await store.get_stats(), indent=2))
    finally:
        await store.close()


if __name__ == "__main__":
    import sys
    import asyncio

    # CLI: python main.py index /path/to/repo [--name alias] [/path/to/repo2 ...]
    if len(sys.argv) > 1 and sys.argv[1] == "index":
        args = sys.argv[2:]
        paths: list[str] = []
        names: list[str | None] = []
        i = 0
        while i < len(args):
            if args[i] == "--name" and i + 1 < len(args):
                if names:
                    names[-1] = args[i + 1]
                i += 2
            else:
                paths.append(args[i])
                names.append(None)
                i += 1

        if not paths:
            print("Usage: python main.py index /path/to/repo [--name alias] [/path/to/repo2 ...]")
            sys.exit(1)

        asyncio.run(cli_index(paths, names))
    else:
        mcp.run()
