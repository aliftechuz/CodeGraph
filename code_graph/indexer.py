"""Orchestrator: walk repo → parse → store in Neo4j."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path

from .languages import EXTENSION_TO_LANGUAGE, SKIP_DIRS
from .neo4j_store import Neo4jStore
from .parser import FileParseResult, content_hash, parse_file, detect_language
from .schema import CodeNode, CodeRelationship

log = logging.getLogger("code_graph.indexer")


class Indexer:
    """Walk a repository, parse source files, and store the graph in Neo4j."""

    def __init__(self, store: Neo4jStore, max_concurrency: int = 8):
        self._store = store
        self._sem = asyncio.Semaphore(max_concurrency)

    async def index_repository(
        self,
        repo_path: str,
        repo_name: str | None = None,
        incremental: bool = True,
    ) -> dict:
        """Index all source files in a repository.

        Args:
            repo_path: Absolute path to the repository root.
            repo_name: Human-readable repo name. Defaults to directory name.
            incremental: If True, skip files whose content hash hasn't changed.

        Returns:
            Summary dict with counts.
        """
        repo_root = Path(repo_path).resolve()
        if not repo_root.is_dir():
            raise ValueError(f"Not a directory: {repo_root}")

        repo = repo_name or repo_root.name
        t0 = time.monotonic()

        # Collect existing content hashes for incremental mode
        existing_hashes: dict[str, str] = {}
        if incremental:
            try:
                records = await self._store.query(
                    "MATCH (f:File {repo: $repo}) RETURN f.file_path AS path, f.content_hash AS hash",
                    {"repo": repo},
                )
                existing_hashes = {r["path"]: r["hash"] for r in records if r.get("hash")}
            except Exception:
                log.warning("Could not fetch existing hashes — doing full index")

        # Walk the repo
        source_files = list(self._collect_files(repo_root))
        log.info("Found %d source files in %s", len(source_files), repo)

        # Create Repository node
        repo_node = CodeNode(
            fqn=f"repo::{repo}",
            name=repo,
            label="Repository",
            repo=repo,
            properties={"url": str(repo_root)},
        )
        await self._store.upsert_nodes([repo_node])

        # Parse and store
        stats = {"total_files": len(source_files), "indexed": 0, "skipped": 0, "errors": 0}
        tasks = []
        for fpath in source_files:
            rel_path = str(fpath.relative_to(repo_root))
            tasks.append(self._index_file(fpath, rel_path, repo, existing_hashes, stats))

        await asyncio.gather(*tasks)

        elapsed = time.monotonic() - t0
        stats["elapsed_seconds"] = round(elapsed, 2)
        log.info(
            "Indexed %s: %d files in %.1fs (%d skipped, %d errors)",
            repo, stats["indexed"], elapsed, stats["skipped"], stats["errors"],
        )
        return stats

    async def _index_file(
        self,
        fpath: Path,
        rel_path: str,
        repo: str,
        existing_hashes: dict[str, str],
        stats: dict,
    ):
        async with self._sem:
            try:
                lang = detect_language(str(fpath))
                if lang is None:
                    stats["skipped"] += 1
                    return

                source = fpath.read_bytes()

                # Incremental check
                h = content_hash(source)
                if existing_hashes.get(rel_path) == h:
                    stats["skipped"] += 1
                    return

                result = parse_file(str(fpath), repo, source)
                if result is None:
                    stats["skipped"] += 1
                    return

                # Fix file_path to be relative
                for node in result.nodes:
                    if node.file_path == str(fpath):
                        node.file_path = rel_path
                for rel in result.relationships:
                    if str(fpath) in rel.from_fqn:
                        rel.from_fqn = rel.from_fqn.replace(str(fpath), rel_path)
                    if str(fpath) in rel.to_fqn:
                        rel.to_fqn = rel.to_fqn.replace(str(fpath), rel_path)

                # Clear old data for this file, then upsert new
                await self._store.clear_file(rel_path, repo)
                await self._store.upsert_nodes(result.nodes)
                await self._store.upsert_relationships(result.relationships)

                # Link file to repo
                file_fqn = f"{repo}::{rel_path}"
                await self._store.upsert_relationships([
                    CodeRelationship(
                        from_fqn=f"repo::{repo}",
                        to_fqn=file_fqn,
                        rel_type="CONTAINS_FILE",
                    )
                ])

                stats["indexed"] += 1
            except Exception as exc:
                log.error("Error indexing %s: %s", rel_path, exc)
                stats["errors"] += 1

    def _collect_files(self, root: Path):
        """Yield all source files under root, skipping ignored directories."""
        for dirpath, dirnames, filenames in os.walk(root):
            # Prune skipped directories in-place
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]

            for fname in filenames:
                ext = Path(fname).suffix.lower()
                if ext in EXTENSION_TO_LANGUAGE:
                    yield Path(dirpath) / fname
