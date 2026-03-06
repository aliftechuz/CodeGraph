"""Re-index all previously indexed repositories (incremental)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys

from code_graph.indexer import Indexer
from code_graph.neo4j_store import Neo4jStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("code_graph.reindex")

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "codegraph")


async def reindex_all():
    store = Neo4jStore(uri=NEO4J_URI, user=NEO4J_USER, password=NEO4J_PASSWORD)
    await store.connect()

    try:
        # Get all indexed repos and their paths from Neo4j
        repos = await store.query(
            "MATCH (r:Repository) RETURN r.name AS name, r.url AS path"
        )

        if not repos:
            log.info("No repositories indexed yet. Nothing to re-index.")
            return

        indexer = Indexer(store)
        for repo in repos:
            name = repo["name"]
            path = repo["path"]

            if not path or not os.path.isdir(path):
                log.warning("Skipping %s — path not found: %s", name, path)
                continue

            log.info("Re-indexing %s (%s)", name, path)
            stats = await indexer.index_repository(path, repo_name=name, incremental=True)
            log.info("  %s: %d indexed, %d skipped, %d errors",
                     name, stats["indexed"], stats["skipped"], stats["errors"])

        log.info("Re-index complete.")
    finally:
        await store.close()


if __name__ == "__main__":
    asyncio.run(reindex_all())
