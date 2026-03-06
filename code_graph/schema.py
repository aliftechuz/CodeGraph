"""Node and Relationship dataclasses for the code knowledge graph."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CodeNode:
    """A node in the code knowledge graph.

    Labels: Repository, Service, File, Module, Class, Function,
    Variable, Endpoint, DatabaseTable, Event, ExternalAPI, BusinessRule
    """

    fqn: str  # fully qualified name — unique key
    name: str
    label: str  # Neo4j node label
    file_path: str = ""
    start_line: int = 0
    end_line: int = 0
    language: str = ""
    repo: str = ""
    properties: dict[str, str | int | bool | None] = field(default_factory=dict)

    def to_dict(self) -> dict:
        base = {
            "fqn": self.fqn,
            "name": self.name,
            "file_path": self.file_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "language": self.language,
            "repo": self.repo,
        }
        base.update(self.properties)
        return base


@dataclass
class CodeRelationship:
    """A directed relationship between two code nodes."""

    from_fqn: str
    to_fqn: str
    rel_type: str  # e.g. CALLS, CONTAINS, IMPORTS
    properties: dict[str, str | int | bool | None] = field(default_factory=dict)

    def to_dict(self) -> dict:
        base = {
            "from_fqn": self.from_fqn,
            "to_fqn": self.to_fqn,
        }
        base.update(self.properties)
        return base
