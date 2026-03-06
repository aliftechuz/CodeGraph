"""Tree-sitter AST parser — extracts CodeNodes and CodeRelationships from source files."""

from __future__ import annotations

import hashlib
from pathlib import Path

import tree_sitter_language_pack as tslp

from .languages import (
    DB_MODEL_PATTERNS,
    ENDPOINT_PATTERNS,
    EXTENSION_TO_LANGUAGE,
    LANGUAGE_MAPPINGS,
)
from .schema import CodeNode, CodeRelationship


def detect_language(file_path: str) -> str | None:
    """Return the tree-sitter language key for a file, or None."""
    ext = Path(file_path).suffix.lower()
    return EXTENSION_TO_LANGUAGE.get(ext)


def content_hash(source: bytes) -> str:
    return hashlib.sha256(source).hexdigest()


def _node_text(node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _find_name(node, source: bytes) -> str:
    """Extract the name identifier from a tree-sitter node."""
    # Try common child field names
    for field_name in ("name", "declarator", "pattern"):
        child = node.child_by_field_name(field_name)
        if child:
            if child.type == "identifier" or child.type == "type_identifier":
                return _node_text(child, source)
            # Nested — e.g. typed_pattern → identifier
            inner = child.child_by_field_name("name")
            if inner:
                return _node_text(inner, source)
            # Fallback: first identifier child
            for sub in child.children:
                if sub.type in ("identifier", "type_identifier"):
                    return _node_text(sub, source)
            return _node_text(child, source)

    # Fallback: first identifier child of node itself
    for child in node.children:
        if child.type in ("identifier", "type_identifier", "simple_identifier"):
            return _node_text(child, source)

    # Go: type_declaration wraps type_spec which has the name
    for child in node.children:
        if child.type == "type_spec":
            inner_name = child.child_by_field_name("name")
            if inner_name:
                return _node_text(inner_name, source)
            for sub in child.children:
                if sub.type in ("identifier", "type_identifier"):
                    return _node_text(sub, source)

    return ""


def _find_params(node, source: bytes) -> str:
    """Extract parameter list text from a function node."""
    for child in node.children:
        if child.type in ("parameters", "parameter_list", "formal_parameters", "formal_parameter_list"):
            return _node_text(child, source)
    params_field = node.child_by_field_name("parameters")
    if params_field:
        return _node_text(params_field, source)
    return ""


def _is_async(node, source: bytes) -> bool:
    """Check if a function is async."""
    text = _node_text(node, source)
    return "async " in text[:50]


def _find_decorators(node, source: bytes, lang: str) -> list[str]:
    """Collect decorator/annotation text for a node."""
    decorators: list[str] = []
    mapping = LANGUAGE_MAPPINGS.get(lang, {})
    dec_types = mapping.get("decorator", [])
    if not dec_types:
        return decorators
    # Walk siblings before this node
    parent = node.parent
    if not parent:
        return decorators
    found_self = False
    for child in reversed(parent.children):
        if child.id == node.id:
            found_self = True
            continue
        if found_self and child.type in dec_types:
            decorators.append(_node_text(child, source))
        elif found_self and child.type not in dec_types:
            break
    return decorators


def _build_fqn(repo: str, file_path: str, *parts: str) -> str:
    """Build a fully qualified name."""
    segments = [repo, file_path] + [p for p in parts if p]
    return "::".join(segments)


def _extract_call_name(node, source: bytes) -> str:
    """Extract the callee name from a call expression node."""
    fn = node.child_by_field_name("function") or node.child_by_field_name("name")
    if fn:
        # a.b.c() → take last identifier
        text = _node_text(fn, source)
        # strip generics and whitespace
        text = text.split("<")[0].strip()
        return text
    # Fallback: first child
    if node.children:
        return _node_text(node.children[0], source)
    return ""


def _extract_import_path(node, source: bytes) -> str:
    """Extract the imported module/path from an import node."""
    return _node_text(node, source).strip()


def _detect_endpoint(decorators: list[str], lang: str) -> tuple[str, str] | None:
    """If decorators indicate an HTTP endpoint, return (method, path)."""
    patterns = ENDPOINT_PATTERNS.get(lang, [])
    for dec in decorators:
        for pat in patterns:
            if pat in dec:
                method = "GET"
                for m in ("get", "post", "put", "delete", "patch"):
                    if m.lower() in dec.lower():
                        method = m.upper()
                        break
                # Try to extract path from decorator string
                path = ""
                for ch in ('"', "'", "`"):
                    if ch in dec:
                        parts = dec.split(ch)
                        if len(parts) >= 2:
                            path = parts[1]
                            break
                return method, path
    return None


def _detect_db_model(node, source: bytes, lang: str, decorators: list[str]) -> bool:
    """Detect if a class is a DB model."""
    patterns = DB_MODEL_PATTERNS.get(lang, [])
    text = _node_text(node, source)
    for pat in patterns:
        if pat in text:
            return True
    for dec in decorators:
        for pat in patterns:
            if pat in dec:
                return True
    return False


class FileParseResult:
    """Result of parsing a single file."""

    def __init__(self, file_path: str, language: str, repo: str, hash: str):
        self.file_path = file_path
        self.language = language
        self.repo = repo
        self.hash = hash
        self.nodes: list[CodeNode] = []
        self.relationships: list[CodeRelationship] = []


def parse_file(file_path: str, repo: str, source: bytes | None = None) -> FileParseResult | None:
    """Parse a source file and extract code graph nodes and relationships.

    Returns None if the file language is unsupported.
    """
    lang = detect_language(file_path)
    if lang is None:
        return None

    if source is None:
        source = Path(file_path).read_bytes()

    hash_val = content_hash(source)
    result = FileParseResult(file_path, lang, repo, hash_val)
    mapping = LANGUAGE_MAPPINGS.get(lang)
    if not mapping:
        return result

    # Get the tree-sitter parser for this language
    parser = tslp.get_parser(lang)
    tree = parser.parse(source)
    root = tree.root_node

    # Create File node
    file_fqn = _build_fqn(repo, file_path)
    result.nodes.append(CodeNode(
        fqn=file_fqn,
        name=Path(file_path).name,
        label="File",
        file_path=file_path,
        start_line=1,
        end_line=source.count(b"\n") + 1,
        language=lang,
        repo=repo,
        properties={"content_hash": hash_val},
    ))

    # Stack to track parent context for FQN building
    # Each entry: (tree-sitter node id, fqn_prefix)
    class_stack: list[tuple[int, str]] = []

    def _current_prefix() -> str:
        return class_stack[-1][1] if class_stack else file_fqn

    def _walk(node):
        ntype = node.type

        # ── Classes / Structs / Interfaces ───────────────────────────────
        if ntype in mapping.get("class", []):
            name = _find_name(node, source)
            if not name:
                name = f"<anon_{node.start_point[0]}>"
            fqn = _build_fqn(_current_prefix(), name)
            decorators = _find_decorators(node, source, lang)
            is_db = _detect_db_model(node, source, lang, decorators)

            label = "Class"
            kind = ntype.replace("_declaration", "").replace("_definition", "")

            code_node = CodeNode(
                fqn=fqn, name=name, label=label,
                file_path=file_path,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                language=lang, repo=repo,
                properties={
                    "kind": kind,
                    "visibility": _extract_visibility(node, source),
                    "docstring": _extract_docstring(node, source, lang),
                },
            )
            result.nodes.append(code_node)

            # Relationship: file DEFINES class
            result.relationships.append(CodeRelationship(
                from_fqn=file_fqn, to_fqn=fqn, rel_type="DEFINES",
            ))

            # If DB model, also create a DatabaseTable node
            if is_db:
                table_fqn = f"table::{repo}::{name.lower()}"
                result.nodes.append(CodeNode(
                    fqn=table_fqn, name=name, label="DatabaseTable",
                    file_path=file_path,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    language=lang, repo=repo,
                ))
                result.relationships.append(CodeRelationship(
                    from_fqn=fqn, to_fqn=table_fqn, rel_type="WRITES_TO",
                ))

            # Extract superclass / implements
            _extract_inheritance(node, source, lang, fqn, result)

            class_stack.append((node.id, fqn))
            for child in node.children:
                _walk(child)
            class_stack.pop()
            return

        # ── Functions / Methods ──────────────────────────────────────────
        if ntype in mapping.get("function", []):
            name = _find_name(node, source)
            if not name:
                name = f"<anon_{node.start_point[0]}>"
            fqn = _build_fqn(_current_prefix(), name)
            decorators = _find_decorators(node, source, lang)
            params = _find_params(node, source)
            is_method = bool(class_stack)

            code_node = CodeNode(
                fqn=fqn, name=name, label="Function",
                file_path=file_path,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                language=lang, repo=repo,
                properties={
                    "kind": "method" if is_method else "function",
                    "is_async": _is_async(node, source),
                    "params": params,
                    "signature": f"{name}({params})",
                    "visibility": _extract_visibility(node, source),
                    "docstring": _extract_docstring(node, source, lang),
                },
            )
            result.nodes.append(code_node)

            # Relationship
            rel_type = "HAS_METHOD" if is_method else "DEFINES"
            result.relationships.append(CodeRelationship(
                from_fqn=_current_prefix(), to_fqn=fqn, rel_type=rel_type,
            ))

            # Endpoint detection
            endpoint = _detect_endpoint(decorators, lang)
            if endpoint:
                method, path = endpoint
                ep_fqn = f"endpoint::{repo}::{method}::{path}"
                result.nodes.append(CodeNode(
                    fqn=ep_fqn, name=f"{method} {path}", label="Endpoint",
                    file_path=file_path,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    language=lang, repo=repo,
                    properties={"http_method": method, "path": path, "protocol": "REST"},
                ))
                result.relationships.append(CodeRelationship(
                    from_fqn=ep_fqn, to_fqn=fqn, rel_type="HANDLED_BY",
                ))

            # Walk body for calls
            for child in node.children:
                _walk(child)
            return

        # ── Imports ──────────────────────────────────────────────────────
        if ntype in mapping.get("import", []):
            import_text = _extract_import_path(node, source)
            import_fqn = f"import::{repo}::{import_text[:200]}"
            result.relationships.append(CodeRelationship(
                from_fqn=file_fqn, to_fqn=import_fqn,
                rel_type="IMPORTS",
                properties={"raw": import_text[:200]},
            ))
            return  # No need to recurse into import

        # ── Calls ────────────────────────────────────────────────────────
        if ntype in mapping.get("call", []):
            callee = _extract_call_name(node, source)
            if callee:
                # Find the enclosing function
                caller_fqn = _current_prefix()
                # Try to find nearest function ancestor
                parent = node.parent
                while parent:
                    if parent.type in mapping.get("function", []):
                        pname = _find_name(parent, source)
                        if pname:
                            # Rebuild FQN for the function
                            # Walk up to find class context
                            caller_fqn = _find_ancestor_fqn(parent, source, mapping, repo, file_fqn)
                        break
                    parent = parent.parent

                result.relationships.append(CodeRelationship(
                    from_fqn=caller_fqn,
                    to_fqn=f"call::{callee}",
                    rel_type="CALLS",
                    properties={
                        "line": node.start_point[0] + 1,
                        "callee_name": callee,
                    },
                ))

        # ── Recurse ──────────────────────────────────────────────────────
        for child in node.children:
            _walk(child)

    _walk(root)
    return result


def _find_ancestor_fqn(func_node, source: bytes, mapping: dict, repo: str, file_fqn: str) -> str:
    """Find the FQN of a function node by walking up to find its class context."""
    func_name = _find_name(func_node, source)
    parent = func_node.parent
    while parent:
        if parent.type in mapping.get("class", []):
            class_name = _find_name(parent, source)
            if class_name:
                class_fqn = _build_fqn(file_fqn, class_name)
                return _build_fqn(class_fqn, func_name)
        parent = parent.parent
    return _build_fqn(file_fqn, func_name)


def _extract_visibility(node, source: bytes) -> str:
    """Extract visibility modifier (public, private, etc.)."""
    text = _node_text(node, source)[:100]
    for vis in ("public", "private", "protected", "internal", "fileprivate", "open"):
        if vis in text.split()[:3]:
            return vis
    return ""


def _extract_docstring(node, source: bytes, lang: str) -> str:
    """Extract docstring/comment from the node or preceding sibling."""
    # Check preceding sibling for comment
    prev = node.prev_named_sibling
    if prev and prev.type in ("comment", "block_comment", "line_comment", "doc_comment"):
        doc = _node_text(prev, source).strip()
        return doc[:500]

    # For Python, check first child string
    if lang == "python":
        body = node.child_by_field_name("body")
        if body and body.children:
            first = body.children[0]
            if first.type == "expression_statement" and first.children:
                expr = first.children[0]
                if expr.type == "string":
                    return _node_text(expr, source).strip("\"' \n")[:500]
    return ""


def _extract_inheritance(node, source: bytes, lang: str, class_fqn: str, result: FileParseResult):
    """Extract extends/implements relationships from a class node."""
    # Look for superclass/argument_list/type_parameters etc
    for child in node.children:
        if child.type in (
            "superclass", "superclasses", "class_heritage",
            "superclass_clause", "type_list", "argument_list",
            "super_class_clause", "interfaces", "base_list",
        ):
            text = _node_text(child, source)
            # Extract type names — split on comma
            for part in text.replace("(", "").replace(")", "").split(","):
                parent_name = part.strip().split("<")[0].split(".")[-1].strip(": ")
                if parent_name and parent_name not in ("", "(", ")", "{"):
                    result.relationships.append(CodeRelationship(
                        from_fqn=class_fqn,
                        to_fqn=f"type::{parent_name}",
                        rel_type="EXTENDS",
                    ))
