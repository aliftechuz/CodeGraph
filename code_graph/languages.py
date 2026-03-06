"""Per-language tree-sitter node type mappings and file extension resolver."""

from __future__ import annotations

# ── File extension → language ────────────────────────────────────────────────
EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".swift": "swift",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".php": "php",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".dart": "dart",
    ".cs": "csharp",
}

# ── Tree-sitter node type mappings per language ──────────────────────────────
# Each language maps concept → list of tree-sitter node type strings.

LANGUAGE_MAPPINGS: dict[str, dict[str, list[str]]] = {
    "python": {
        "class": ["class_definition"],
        "function": ["function_definition"],
        "import": ["import_statement", "import_from_statement"],
        "call": ["call"],
        "decorator": ["decorator"],
        "variable": ["assignment", "augmented_assignment"],
        "string": ["string", "concatenated_string"],
    },
    "swift": {
        "class": ["class_declaration", "struct_declaration", "enum_declaration", "protocol_declaration", "actor_declaration"],
        "function": ["function_declaration", "init_declaration", "subscript_declaration"],
        "import": ["import_declaration"],
        "call": ["call_expression"],
        "decorator": ["attribute"],
        "variable": ["property_declaration", "let_declaration", "var_declaration"],
        "string": ["line_string_literal"],
    },
    "kotlin": {
        "class": ["class_declaration", "object_declaration", "interface_declaration"],
        "function": ["function_declaration"],
        "import": ["import_header"],
        "call": ["call_expression"],
        "decorator": ["annotation"],
        "variable": ["property_declaration"],
        "string": ["line_string_literal", "multi_line_string_literal"],
    },
    "php": {
        "class": ["class_declaration", "interface_declaration", "trait_declaration", "enum_declaration"],
        "function": ["function_definition", "method_declaration"],
        "import": ["namespace_use_declaration"],
        "call": ["function_call_expression", "member_call_expression"],
        "decorator": ["attribute_list"],
        "variable": ["property_declaration", "const_declaration"],
        "string": ["string", "encapsed_string"],
    },
    "javascript": {
        "class": ["class_declaration"],
        "function": ["function_declaration", "arrow_function", "method_definition", "function_expression"],
        "import": ["import_statement"],
        "call": ["call_expression"],
        "decorator": ["decorator"],
        "variable": ["variable_declaration", "lexical_declaration"],
        "string": ["string", "template_string"],
    },
    "typescript": {
        "class": ["class_declaration", "interface_declaration", "type_alias_declaration"],
        "function": ["function_declaration", "arrow_function", "method_definition", "function_expression"],
        "import": ["import_statement"],
        "call": ["call_expression"],
        "decorator": ["decorator"],
        "variable": ["variable_declaration", "lexical_declaration"],
        "string": ["string", "template_string"],
    },
    "go": {
        "class": ["type_declaration"],
        "function": ["function_declaration", "method_declaration"],
        "import": ["import_declaration"],
        "call": ["call_expression"],
        "decorator": [],  # Go has no decorators
        "variable": ["var_declaration", "const_declaration", "short_var_declaration"],
        "string": ["interpreted_string_literal", "raw_string_literal"],
    },
    "dart": {
        "class": ["class_definition", "enum_declaration", "mixin_declaration", "extension_declaration"],
        "function": ["function_signature", "method_signature", "function_body"],
        "import": ["import_or_export"],
        "call": ["call_expression"],
        "decorator": ["annotation"],
        "variable": ["initialized_variable_definition", "static_final_declaration"],
        "string": ["string_literal"],
    },
    "csharp": {
        "class": ["class_declaration", "struct_declaration", "interface_declaration", "enum_declaration", "record_declaration"],
        "function": ["method_declaration", "local_function_statement", "constructor_declaration"],
        "import": ["using_directive"],
        "call": ["invocation_expression"],
        "decorator": ["attribute"],
        "variable": ["field_declaration", "property_declaration"],
        "string": ["string_literal_expression", "interpolated_string_expression"],
    },
}

# ── Endpoint detection patterns ──────────────────────────────────────────────
# Decorator/annotation patterns that indicate HTTP endpoints.
ENDPOINT_PATTERNS: dict[str, list[str]] = {
    "python": [
        "app.route", "app.get", "app.post", "app.put", "app.delete", "app.patch",
        "router.get", "router.post", "router.put", "router.delete", "router.patch",
        "@api_view",
    ],
    "kotlin": [
        "@GetMapping", "@PostMapping", "@PutMapping", "@DeleteMapping", "@PatchMapping",
        "@RequestMapping",
    ],
    "swift": ["@GET", "@POST", "@PUT", "@DELETE"],
    "go": [
        "HandleFunc", "Handle", "r.Get", "r.Post", "r.Put", "r.Delete",
        "e.GET", "e.POST", "e.PUT", "e.DELETE",
    ],
    "typescript": [
        "@Get", "@Post", "@Put", "@Delete", "@Patch",
        "app.get", "app.post", "app.put", "app.delete",
        "router.get", "router.post", "router.put", "router.delete",
    ],
    "javascript": [
        "app.get", "app.post", "app.put", "app.delete",
        "router.get", "router.post", "router.put", "router.delete",
    ],
    "php": [
        "#[Route", "@Route",
    ],
    "dart": [],
    "csharp": [
        "[HttpGet", "[HttpPost", "[HttpPut", "[HttpDelete", "[HttpPatch",
        "[Route",
    ],
}

# ── DB model detection patterns ──────────────────────────────────────────────
DB_MODEL_PATTERNS: dict[str, list[str]] = {
    "python": ["models.Model", "Base", "db.Model", "DeclarativeBase", "SQLModel", "Document"],
    "kotlin": ["@Entity", "@Table", "@Document"],
    "swift": ["@Model", "NSManagedObject"],
    "go": ["gorm.Model", "bun.BaseModel"],
    "typescript": ["@Entity", "Schema", "model("],
    "javascript": ["Schema", "model(", "mongoose.model"],
    "php": ["Model", "Entity", "HasFactory"],
    "dart": ["@Entity", "@Table"],
    "csharp": ["DbContext", "[Table", "EntityTypeConfiguration"],
}

# ── Directories to skip during indexing ──────────────────────────────────────
SKIP_DIRS: set[str] = {
    ".git", "node_modules", "vendor", "build", "dist", "target",
    ".build", "__pycache__", ".tox", ".mypy_cache", ".pytest_cache",
    "Pods", ".gradle", "DerivedData", "bin", "obj", ".dart_tool",
    ".pub-cache", "packages", ".next", ".nuxt", "out", "coverage",
    ".venv", "venv", "env", ".env",
}
