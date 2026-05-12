from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from config import APP_VERSION, APP_VERSION_NAME
from models import ErdState, Relationship, TableInfo
from validation import get_context_tables, get_relationships_for_context


def build_context_scoped_state(state: ErdState, context_id: str) -> ErdState:
    ctx = state.relationship_contexts.get(context_id)
    if not ctx:
        return state

    scoped_tables = get_context_tables(state, context_id)
    scoped_relationships = get_relationships_for_context(state, context_id)

    for rel in scoped_relationships.values():
        if rel.source_full_table in state.tables:
            scoped_tables[rel.source_full_table] = state.tables[rel.source_full_table]
        if rel.target_full_table in state.tables:
            scoped_tables[rel.target_full_table] = state.tables[rel.target_full_table]

    return ErdState(
        connection_label=state.connection_label,
        database_name=f"{state.database_name} / {ctx.name}",
        loaded_at=state.loaded_at,
        tables=scoped_tables,
        relationships=scoped_relationships,
        relationship_contexts={context_id: ctx},
        active_context_id=context_id,
    )

def table_to_export_dict(t: TableInfo) -> Dict[str, Any]:
    return {
        "table": t.full_name,
        "schema": t.schema_name,
        "name": t.table_name,
        "module": t.module,
        "purpose": t.purpose,
        "row_count": t.row_count,
        "notes": t.notes,
        "columns": [
            {
                "name": c.column_name,
                "type": c.data_type,
                "nullable": c.nullable,
                "primary_key": c.is_primary_key,
                "comment": c.comment,
            }
            for c in sorted(t.columns, key=lambda x: x.ordinal_position)
        ],
    }


def relationship_to_export_dict(r: Relationship) -> Dict[str, Any]:
    return {
        "id": r.id,
        "context_id": r.context_id,
        "active": r.active,
        "type": r.relationship_type,
        "confidence": r.confidence,
        "cardinality": r.cardinality,
        "source": {
            "table": r.source_full_table,
            "column": r.source_column,
        },
        "target": {
            "table": r.target_full_table,
            "column": r.target_column,
        },
        "join_type": r.join_type,
        "join_rule": f"{r.source_full_table}.{r.source_column} = {r.target_full_table}.{r.target_column}",
        "condition_sql": r.condition_sql,
        "extra_join_sql": r.extra_join_sql,
        "example_join_clause": r.join_clause("src", "tgt"),
        "description": r.description,
    }


def export_json(state: ErdState, only_active: bool = True) -> str:
    rels = list(state.relationships.values())
    if only_active:
        rels = [r for r in rels if r.active]

    payload = {
        "exported_at": datetime.now(UTC).isoformat(),
        "app_version": APP_VERSION,
        "app_version_name": APP_VERSION_NAME,
        "export_version": "1.1",
        "database_name": state.database_name,
        "loaded_at": state.loaded_at,
        "instructions_for_chatgpt": (
            "Use this schema map to write SQL queries. Prefer active relationships. "
            "Respect conditional relationships, especially where a source table uses Item_Type, Module, Status, Date ranges, "
            "or other discriminator columns to determine which target table applies. "
            "When uncertain, ask for confirmation or produce a SELECT preview before INSERT/UPDATE/DELETE."
        ),
        "relationship_contexts": {k: asdict(v) for k, v in state.relationship_contexts.items()},
        "active_context_id": state.active_context_id,
        "tables": [table_to_export_dict(t) for t in state.tables.values()],
        "relationships": [relationship_to_export_dict(r) for r in rels],
    }
    return json.dumps(payload, indent=2)


def export_markdown(state: ErdState, selected_tables: Optional[List[str]] = None, only_active: bool = True) -> str:
    tables = state.tables
    if selected_tables:
        tables = {k: v for k, v in tables.items() if k in selected_tables}

    rels = list(state.relationships.values())
    if only_active:
        rels = [r for r in rels if r.active]
    if selected_tables:
        selected = set(selected_tables)
        rels = [r for r in rels if r.source_full_table in selected or r.target_full_table in selected]

    lines: List[str] = []
    lines.append("# Database Entity Relationship Map")
    lines.append("")
    lines.append(f"App Version: `{APP_VERSION}`")
    lines.append(f"Database / Source: `{state.database_name or 'Unknown'}`")
    lines.append(f"Loaded at: `{state.loaded_at or 'Unknown'}`")
    if state.active_context_id and state.active_context_id in state.relationship_contexts:
        ctx = state.relationship_contexts[state.active_context_id]
        lines.append(f"Relationship Context: `{ctx.name}`")
        lines.append(f"Context Type: `{ctx.context_type}`")
        lines.append(f"Context Status: `{ctx.status}`")
    lines.append("")
    lines.append("## How to use this map for SQL generation")
    lines.append("- Use the `Relationships` section as the approved join map.")
    lines.append("- Use `conditional` relationships only when their condition is satisfied.")
    lines.append("- If a relationship is `inferred`, treat it as lower confidence unless verified.")
    lines.append("- For data-changing SQL, produce a SELECT preview first.")
    lines.append("")

    lines.append("## Tables")
    for t in sorted(tables.values(), key=lambda x: x.full_name.lower()):
        lines.append(f"\n### `{t.full_name}`")
        if t.module:
            lines.append(f"Module: {t.module}")
        if t.purpose:
            lines.append(f"Purpose: {t.purpose}")
        if t.row_count is not None:
            lines.append(f"Approx row count: {t.row_count}")
        if t.notes:
            lines.append(f"Notes: {t.notes}")
        lines.append("")
        lines.append("| Column | Type | Nullable | PK | Comment |")
        lines.append("|---|---:|:---:|:---:|---|")
        for c in sorted(t.columns, key=lambda x: x.ordinal_position):
            lines.append(
                f"| `{c.column_name}` | `{c.data_type}` | {'Yes' if c.nullable else 'No'} | "
                f"{'Yes' if c.is_primary_key else ''} | {c.comment or ''} |"
            )

    lines.append("\n## Relationships")
    if not rels:
        lines.append("No relationships recorded.")
    else:
        lines.append("| Type | Confidence | Source | Target | Rule / Condition | Notes |")
        lines.append("|---|---:|---|---|---|---|")
        for r in sorted(rels, key=lambda x: (x.source_full_table.lower(), x.target_full_table.lower())):
            rule = f"`{r.source_full_table}.{r.source_column}` = `{r.target_full_table}.{r.target_column}`"
            if r.condition_sql:
                rule += f"<br>Condition: `{r.condition_sql}`"
            if r.extra_join_sql:
                rule += f"<br>Extra join: `{r.extra_join_sql}`"
            lines.append(
                f"| {r.relationship_type} | {r.confidence:.2f} | "
                f"`{r.source_full_table}` | `{r.target_full_table}` | {rule} | {r.description or ''} |"
            )

    lines.append("\n## Query-generation rules for ChatGPT")
    lines.append("When generating SQL from this ERD, follow these rules:")
    lines.append("1. Start from the table that contains the main requested entity or transaction.")
    lines.append("2. Join only through relationships listed above unless the user authorises a new inferred join.")
    lines.append("3. For conditional relationships, include the condition in the ON clause or WHERE clause as appropriate.")
    lines.append("4. For optional relationships, use LEFT JOIN unless the user requests only matched records.")
    lines.append("5. For INSERT/UPDATE/DELETE operations, first generate a SELECT query for review.")

    return "\n".join(lines)


def export_mermaid(state: ErdState, only_active: bool = True) -> str:
    lines = ["erDiagram"]

    for t in sorted(state.tables.values(), key=lambda x: x.full_name.lower()):
        safe_table = re.sub(r"[^A-Za-z0-9_]", "_", t.full_name)
        lines.append(f"  {safe_table} {{")
        for c in sorted(t.columns, key=lambda x: x.ordinal_position):
            dtype = re.sub(r"[^A-Za-z0-9_]", "_", c.data_type or "unknown")[:40]
            cname = re.sub(r"[^A-Za-z0-9_]", "_", c.column_name)
            pk = " PK" if c.is_primary_key else ""
            lines.append(f"    {dtype} {cname}{pk}")
        lines.append("  }")

    rels = [r for r in state.relationships.values() if (r.active or not only_active)]
    for r in rels:
        src = re.sub(r"[^A-Za-z0-9_]", "_", r.source_full_table)
        tgt = re.sub(r"[^A-Za-z0-9_]", "_", r.target_full_table)
        label_parts = [r.source_column, r.target_column]
        if r.relationship_type == "conditional" and r.condition_sql:
            label_parts.append("conditional")
        label = " / ".join(label_parts).replace('"', "'")

        if r.cardinality == "one-to-many":
            connector = "||--o{"
        elif r.cardinality == "many-to-one":
            connector = "}o--||"
        elif r.cardinality == "one-to-one":
            connector = "||--||"
        else:
            connector = "}o--o{"
        lines.append(f"  {src} {connector} {tgt} : \"{label}\"")

    return "\n".join(lines)


def export_dot(state: ErdState, only_active: bool = True) -> str:
    lines = ["digraph ERD {", "  graph [rankdir=LR];", "  node [shape=record, fontsize=10];"]

    for t in sorted(state.tables.values(), key=lambda x: x.full_name.lower()):
        node_id = re.sub(r"[^A-Za-z0-9_]", "_", t.full_name)
        cols = []
        for c in sorted(t.columns, key=lambda x: x.ordinal_position)[:30]:
            pk = "*" if c.is_primary_key else ""
            cols.append(f"{pk}{c.column_name}")
        label = "{" + t.full_name + "|" + "\\l".join(cols) + "\\l}"
        lines.append(f'  {node_id} [label="{label}"];')

    rels = [r for r in state.relationships.values() if (r.active or not only_active)]
    for r in rels:
        src = re.sub(r"[^A-Za-z0-9_]", "_", r.source_full_table)
        tgt = re.sub(r"[^A-Za-z0-9_]", "_", r.target_full_table)
        label = f"{r.source_column} → {r.target_column}"
        if r.condition_sql:
            label += " [conditional]"
        lines.append(f'  {src} -> {tgt} [label="{label}"];')

    lines.append("}")
    return chr(10).join(lines)


def export_markdown_with_context(state: ErdState, context_id: Optional[str], only_active: bool = True) -> str:
    if not context_id:
        return export_markdown(state, only_active=only_active)

    ctx = state.relationship_contexts.get(context_id)
    scoped_state = build_context_scoped_state(state, context_id)
    if not ctx:
        return export_markdown(scoped_state, only_active=only_active)

    line_break = chr(10)
    header = [
        "# Named Relationship Context Export",
        "",
        f"App Version: `{APP_VERSION}`",
        f"Export Scope: `{ctx.name}`",
        f"Relationship Type: `{ctx.context_type}`",
        f"Status: `{ctx.status}`",
        f"Owner / Reviewer: `{ctx.owner_reviewer or ''}`",
        "",
        "## Context Notes",
        f"Purpose: {ctx.purpose or ''}",
        f"Business Context: {ctx.business_context or ''}",
        f"Primary Join Path: {ctx.primary_join_path or ''}",
        f"Conditional Logic Notes: {ctx.conditional_logic_notes or ''}",
        f"Query Guidance: {ctx.query_guidance or ''}",
        f"Comments: {ctx.comments or ''}",
        "",
    ]
    return line_break.join(header) + line_break + export_markdown(scoped_state, only_active=only_active)


def export_json_with_context(state: ErdState, context_id: Optional[str], only_active: bool = True) -> str:
    if not context_id:
        return export_json(state, only_active=only_active)

    scoped_state = build_context_scoped_state(state, context_id)
    return export_json(scoped_state, only_active=only_active)

