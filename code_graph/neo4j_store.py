"""Async Neo4j client for the code knowledge graph."""

from __future__ import annotations

import logging
from typing import Any

from neo4j import AsyncGraphDatabase

from .schema import CodeNode, CodeRelationship

log = logging.getLogger("code_graph.neo4j")

# All valid node labels
NODE_LABELS = [
    "Repository", "Service", "File", "Module", "Class", "Function",
    "Variable", "Endpoint", "DatabaseTable", "Event", "ExternalAPI", "BusinessRule",
]


class Neo4jStore:
    """Async wrapper around the Neo4j Python driver."""

    def __init__(self, uri: str = "bolt://localhost:7687", user: str = "neo4j", password: str = "codegraph"):
        self._uri = uri
        self._user = user
        self._password = password
        self._driver = None

    async def connect(self):
        self._driver = AsyncGraphDatabase.driver(self._uri, auth=(self._user, self._password))
        await self._ensure_indexes()
        log.info("Connected to Neo4j at %s", self._uri)

    async def close(self):
        if self._driver:
            await self._driver.close()

    async def _ensure_indexes(self):
        """Create indexes for fast lookups."""
        async with self._driver.session() as session:
            for label in NODE_LABELS:
                await session.run(
                    f"CREATE INDEX IF NOT EXISTS FOR (n:{label}) ON (n.fqn)"
                )
                await session.run(
                    f"CREATE INDEX IF NOT EXISTS FOR (n:{label}) ON (n.name)"
                )
                await session.run(
                    f"CREATE INDEX IF NOT EXISTS FOR (n:{label}) ON (n.file_path)"
                )
            # Composite index for repo lookups
            for label in NODE_LABELS:
                await session.run(
                    f"CREATE INDEX IF NOT EXISTS FOR (n:{label}) ON (n.repo)"
                )

    async def upsert_nodes(self, nodes: list[CodeNode]):
        """Batch upsert nodes using UNWIND + MERGE."""
        if not nodes:
            return

        # Group by label for efficient MERGE
        by_label: dict[str, list[dict]] = {}
        for node in nodes:
            by_label.setdefault(node.label, []).append(node.to_dict())

        async with self._driver.session() as session:
            for label, items in by_label.items():
                query = f"""
                UNWIND $items AS item
                MERGE (n:{label} {{fqn: item.fqn}})
                SET n += item
                """
                await session.run(query, items=items)

        log.info("Upserted %d nodes across %d labels", len(nodes), len(by_label))

    async def upsert_relationships(self, rels: list[CodeRelationship]):
        """Batch upsert relationships using UNWIND + MERGE.

        Uses generic Node label for MERGE since we may not know the label
        of the target node.
        """
        if not rels:
            return

        # Group by rel_type
        by_type: dict[str, list[dict]] = {}
        for rel in rels:
            by_type.setdefault(rel.rel_type, []).append(rel.to_dict())

        async with self._driver.session() as session:
            for rel_type, items in by_type.items():
                # MERGE on fqn — target may not exist yet, create placeholder
                query = f"""
                UNWIND $items AS item
                MERGE (a {{fqn: item.from_fqn}})
                MERGE (b {{fqn: item.to_fqn}})
                MERGE (a)-[r:{rel_type}]->(b)
                SET r += item
                """
                await session.run(query, items=items)

        log.info("Upserted %d relationships across %d types", len(rels), len(by_type))

    async def clear_file(self, file_path: str, repo: str):
        """Delete all nodes (and their relationships) originating from a specific file."""
        async with self._driver.session() as session:
            await session.run(
                "MATCH (n {file_path: $file_path, repo: $repo}) DETACH DELETE n",
                file_path=file_path, repo=repo,
            )

    async def clear_repo(self, repo: str):
        """Delete all nodes for a repository."""
        async with self._driver.session() as session:
            await session.run(
                "MATCH (n {repo: $repo}) DETACH DELETE n",
                repo=repo,
            )
        log.info("Cleared all data for repo %s", repo)

    async def query(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict]:
        """Execute a Cypher query and return results as list of dicts."""
        async with self._driver.session() as session:
            result = await session.run(cypher, parameters=params or {})
            records = await result.data()
            return records

    async def get_stats(self) -> dict:
        """Return basic graph statistics."""
        stats: dict[str, Any] = {}
        async with self._driver.session() as session:
            # Node counts by label
            result = await session.run(
                "CALL db.labels() YIELD label "
                "CALL { WITH label "
                "  CALL db.stats.retrieve('GRAPH COUNTS') YIELD data "
                "  RETURN data } "
                "RETURN label"
            )
            # Simpler approach:
            for label in NODE_LABELS:
                result = await session.run(f"MATCH (n:{label}) RETURN count(n) AS cnt")
                record = await result.single()
                if record:
                    stats[label] = record["cnt"]

            # Total relationships
            result = await session.run("MATCH ()-[r]->() RETURN count(r) AS cnt")
            record = await result.single()
            if record:
                stats["total_relationships"] = record["cnt"]

        return stats

    async def find_callers(self, function_name: str) -> list[dict]:
        """Find all functions that call a given function."""
        records = await self.query(
            """
            MATCH (caller)-[r:CALLS]->(callee)
            WHERE r.callee_name CONTAINS $name OR callee.name = $name
            RETURN caller.fqn AS caller_fqn, caller.name AS caller_name,
                   caller.file_path AS file_path, caller.start_line AS line,
                   r.callee_name AS callee_name
            ORDER BY caller.file_path, caller.start_line
            """,
            {"name": function_name},
        )
        return records

    async def find_dependencies(self, service_name: str) -> list[dict]:
        """Find what a service depends on (imports, calls, external APIs)."""
        records = await self.query(
            """
            MATCH (f:File {repo: $name})-[r:IMPORTS]->(dep)
            RETURN DISTINCT dep.fqn AS dependency, r.raw AS import_statement
            ORDER BY dep.fqn
            LIMIT 200
            """,
            {"name": service_name},
        )
        return records

    async def trace_endpoint(self, path: str, method: str = "GET") -> list[dict]:
        """Trace an API endpoint through the call graph."""
        records = await self.query(
            """
            MATCH (ep:Endpoint)-[:HANDLED_BY]->(handler:Function)
            WHERE ep.path CONTAINS $path AND ($method = '' OR ep.http_method = $method)
            OPTIONAL MATCH (handler)-[:CALLS*1..5]->(callee)
            RETURN ep.name AS endpoint,
                   handler.fqn AS handler,
                   handler.file_path AS handler_file,
                   collect(DISTINCT callee.fqn) AS call_chain
            """,
            {"path": path, "method": method},
        )
        return records

    async def search_code(self, name: str) -> list[dict]:
        """Fuzzy search for any code entity by name."""
        records = await self.query(
            """
            MATCH (n)
            WHERE n.name CONTAINS $name
            RETURN n.fqn AS fqn, n.name AS name, labels(n) AS labels,
                   n.file_path AS file_path, n.start_line AS line,
                   n.language AS language, n.repo AS repo
            ORDER BY n.name
            LIMIT 50
            """,
            {"name": name},
        )
        return records

    async def list_services(self) -> list[dict]:
        """List all indexed repositories (treated as services)."""
        records = await self.query(
            """
            MATCH (f:File)
            WITH f.repo AS repo, f.language AS lang, count(f) AS file_count
            RETURN repo, collect(DISTINCT lang) AS languages, sum(file_count) AS total_files
            ORDER BY repo
            """
        )
        return records
