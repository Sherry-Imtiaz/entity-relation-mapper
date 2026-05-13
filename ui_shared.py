from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Dict, List, Optional, Tuple
import re

import pandas as pd
import streamlit as st

from models import ColumnInfo, ErdState, Relationship, RelationshipContext, TableInfo
from validation import context_display_name, get_context_table_set, get_context_tables, get_relationships_for_context


def table_key(schema_name: str, table_name: str) -> str:
    return f"{schema_name}.{table_name}" if schema_name else table_name


def make_context_id(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_]+", "_", name.strip().lower()).strip("_")
    return slug or f"relationship_context_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"


def unique_context_id(existing_contexts: Dict[str, RelationshipContext], name: str) -> str:
    base = make_context_id(name)
    candidate = base
    counter = 2
    while candidate in existing_contexts:
        candidate = f"{base}_{counter}"
        counter += 1
    return candidate


def rel_id(
    source_schema: str,
    source_table: str,
    source_column: str,
    target_schema: str,
    target_table: str,
    target_column: str,
    relationship_type: str,
    condition_sql: str = "",
) -> str:
    raw = "|".join([
        source_schema or "",
        source_table,
        source_column,
        target_schema or "",
        target_table,
        target_column,
        relationship_type,
        condition_sql or "",
    ])
    return re.sub(r"[^A-Za-z0-9_]+", "_", raw).strip("_")[:220]


from state_manager import default_state, deserialize_state, load_state, merge_tables_keep_metadata, save_state, serialize_state

from importers import (
    create_import_template_excel,
    create_simple_csv_template,
    import_schema_file,
    split_table_identifier,
)
from validation import (
    context_display_name,
    get_context_table_set,
    get_context_tables,
    get_relationships_for_context,
    relationship_quality_summary,
    validate_import_preview,
    validate_relationships,
)
from inference import infer_relationships
from exports import (
    build_context_scoped_state,
    export_dot,
    export_json,
    export_json_with_context,
    export_markdown,
    export_markdown_with_context,
    export_mermaid,
)
from visualisation import build_streamlit_flow_state_from_erd_state


def split_full_table(full_table: str) -> Tuple[str, str]:
    return split_table_identifier(full_table)


def relationships_df(state: ErdState) -> pd.DataFrame:
    rows = []
    for r in state.relationships.values():
        rows.append({
            "active": r.active,
            "context": context_display_name(state, r.context_id),
            "type": r.relationship_type,
            "confidence": r.confidence,
            "source_table": r.source_full_table,
            "source_column": r.source_column,
            "target_table": r.target_full_table,
            "target_column": r.target_column,
            "cardinality": r.cardinality,
            "condition_sql": r.condition_sql,
            "extra_join_sql": r.extra_join_sql,
            "description": r.description,
            "id": r.id,
        })
    return pd.DataFrame(rows)


def get_table_columns(state: ErdState, full_table: str) -> List[str]:
    t = state.tables.get(full_table)
    if not t:
        return []
    return [c.column_name for c in sorted(t.columns, key=lambda x: x.ordinal_position)]


def get_schema_options(state: ErdState) -> List[str]:
    schemas = sorted({t.schema_name or "(no schema)" for t in state.tables.values()}, key=str.lower)
    return ["All schemas"] + schemas


def filter_table_options(state: ErdState, schema_filter: str = "All schemas", search_text: str = "") -> List[str]:
    search = (search_text or "").strip().lower()
    options: List[str] = []
    for full_name, table in state.tables.items():
        schema_name = table.schema_name or "(no schema)"
        if schema_filter and schema_filter != "All schemas" and schema_name != schema_filter:
            continue
        if search and search not in full_name.lower() and search not in table.table_name.lower():
            continue
        options.append(full_name)
    return sorted(options, key=str.lower)


def render_table_filter_controls(state: ErdState, key_prefix: str) -> Tuple[str, str, List[str]]:
    c1, c2 = st.columns([1, 2])
    with c1:
        schema_filter = st.selectbox("Schema filter", get_schema_options(state), key=f"{key_prefix}_schema_filter")
    with c2:
        search_text = st.text_input("Search table name", key=f"{key_prefix}_table_search")
    options = filter_table_options(state, schema_filter=schema_filter, search_text=search_text)
    return schema_filter, search_text, options


def get_active_context(state: ErdState) -> Optional[RelationshipContext]:
    if state.active_context_id:
        return state.relationship_contexts.get(state.active_context_id)
    return None


def relationship_context_warning(state: ErdState) -> None:
    ctx = get_active_context(state)
    if not ctx:
        st.warning("Create or select a relationship context before adding context-scoped relationships.")
    elif not get_context_table_set(state, ctx.id):
        st.warning("The active relationship context has no assigned tables. Add tables in the Relationship Contexts tab first.")


def tables_df(state: ErdState) -> pd.DataFrame:
    rows = []
    for table in sorted(state.tables.values(), key=lambda t: t.full_name.lower()):
        rows.append(
            {
                "schema_name": getattr(table, "schema_name", ""),
                "table_name": getattr(table, "table_name", ""),
                "full_name": getattr(table, "full_name", ""),
                "columns": len(getattr(table, "columns", []) or []),
                "row_count": getattr(table, "row_count", None),
                "module": getattr(table, "module", ""),
                "purpose": getattr(table, "purpose", ""),
                "notes": getattr(table, "notes", ""),
            }
        )
    return pd.DataFrame(rows)


def columns_df(table: TableInfo) -> pd.DataFrame:
    rows = []
    for column in sorted(getattr(table, "columns", []) or [], key=lambda c: getattr(c, "ordinal_position", 0)):
        rows.append(
            {
                "ordinal_position": getattr(column, "ordinal_position", None),
                "column_name": getattr(column, "column_name", ""),
                "data_type": getattr(column, "data_type", ""),
                "nullable": getattr(column, "nullable", ""),
                "is_primary_key": getattr(column, "is_primary_key", False),
                "comment": getattr(column, "comment", ""),
            }
        )
    return pd.DataFrame(rows)

