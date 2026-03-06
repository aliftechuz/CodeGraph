# CodeGraph

AST-based code knowledge graph. Parses source code across 10 languages, builds a Neo4j graph of classes, functions, endpoints, DB models, imports, and call chains — then exposes it all via MCP for Claude.

## Why

Documentation gets outdated. Code doesn't. CodeGraph lets you query business logic directly from source code.

## What it extracts

**12 node types**: Repository, Service, File, Module, Class, Function, Variable, Endpoint, DatabaseTable, Event, ExternalAPI, BusinessRule

**15 relationship types**: CONTAINS_FILE, DEFINES, CONTAINS, HAS_METHOD, HAS_FIELD, EXTENDS, IMPLEMENTS, CALLS, CALLS_EXTERNAL, EXPOSES, HANDLED_BY, READS_FROM, WRITES_TO, PUBLISHES, SUBSCRIBES_TO, IMPORTS

## Supported languages

Swift, Kotlin, PHP, Python, JavaScript, TypeScript, Go, Dart, C#

## Setup

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Docker

### Install

```bash
git clone https://github.com/mustafo/CodeGraph.git
cd CodeGraph
uv sync
```

### Start Neo4j

```bash
docker compose up -d
```

Neo4j Browser: http://localhost:7474 (neo4j / codegraph)

## Usage

### Index repositories

```bash
# Single repo
uv run main.py index /path/to/your-repo

# With a custom name
uv run main.py index /path/to/your-repo --name my-service

# Multiple repos
uv run main.py index \
  /path/to/repo-one --name backend \
  /path/to/repo-two --name mobile
```

Indexing is incremental by default — only changed files get re-parsed.

### Re-index all

```bash
uv run reindex.py
```

Re-indexes every previously indexed repo (incremental).

### MCP server (Claude Desktop)

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "code-graph": {
      "command": "uv",
      "args": ["--directory", "/path/to/CodeGraph", "run", "main.py"]
    }
  }
}
```

### MCP server (Claude Code)

```bash
claude mcp add --transport stdio -s user code-graph -- uv --directory /path/to/CodeGraph run main.py
```

### Available MCP tools

| Tool | Description |
|---|---|
| `index_repository` | Index a local git repo into the graph |
| `query_code` | Execute raw Cypher against the graph |
| `find_callers` | Find all functions that call a given function |
| `find_dependencies` | Find what a service depends on |
| `trace_endpoint` | Trace an API endpoint through the call graph |
| `list_services` | List all indexed repositories |
| `search_code` | Fuzzy search for any code entity by name |
| `graph_stats` | Node and relationship counts |

## Architecture

```
Claude Desktop / Claude Code
        │
    MCP (stdio)
        │
   main.py (FastMCP)
        │
   code_graph/
   ├── parser.py      ← tree-sitter AST parsing
   ├── languages.py   ← per-language node type mappings
   ├── schema.py      ← CodeNode / CodeRelationship
   ├── neo4j_store.py ← async Neo4j client
   └── indexer.py     ← repo walker + orchestrator
        │
   Neo4j (Docker)
```

## Example queries via Claude

- "What services are indexed?"
- "Who calls `processPayment`?"
- "Trace POST /api/checkout through the call graph"
- "What classes extend BaseRepository?"
- "Show me all REST endpoints in the payments service"
