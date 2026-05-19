
from __future__ import annotations

import hashlib
import json
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

from exports import export_mermaid
from models import ErdState
from quality_checks import (
    build_export_quality_report,
    build_scoped_state_from_context,
    report_to_issue_rows,
    relationship_tables,
)


def _context_options(state: ErdState) -> Dict[str, str]:
    options: Dict[str, str] = {}
    for context_id, context in sorted(
        getattr(state, "relationship_contexts", {}).items(),
        key=lambda item: getattr(item[1], "name", item[0]).lower(),
    ):
        name = getattr(context, "name", context_id)
        context_type = getattr(context, "context_type", "")
        label = f"{name} ({context_type})" if context_type else name
        if label in options:
            label = f"{label} [{context_id}]"
        options[label] = context_id
    return options


def _selected_context_scope(state: ErdState, key_prefix: str) -> Tuple[str, Optional[List[str]], str]:
    mode = st.radio(
        "Context selection mode",
        ["Whole database", "Selected relationship contexts"],
        horizontal=True,
        key=f"{key_prefix}_context_mode",
        help="Use Whole database for all relationships, or choose specific relationship contexts to include.",
    )

    if mode == "Whole database":
        return mode, None, "Whole database"

    context_options = _context_options(state)
    if not context_options:
        st.warning("No relationship contexts are available yet.")
        return mode, [], "Selected contexts"

    labels = list(context_options.keys())
    default_labels = labels[:1]
    selected_labels = st.multiselect(
        "Relationship contexts to include",
        labels,
        default=default_labels,
        key=f"{key_prefix}_selected_contexts",
        help="Select one or more relationship contexts to include in this export.",
    )
    context_ids = [context_options[label] for label in selected_labels]
    scope_label = ", ".join(selected_labels) if selected_labels else "Selected contexts"
    return mode, context_ids, scope_label


def _context_name(state: ErdState, context_id: str) -> str:
    context = getattr(state, "relationship_contexts", {}).get(context_id)
    return getattr(context, "name", context_id) if context else context_id


def _export_markdown(state: ErdState, source_state: ErdState, scope_label: str, only_active: bool = True) -> str:
    lines = [f"# Entity Relation Mapper Export — {scope_label}", ""]

    lines.append("## Tables")
    if not state.tables:
        lines.append("_No tables included._")
    else:
        for table in sorted(state.tables.values(), key=lambda t: t.full_name.lower()):
            lines.append(f"### {table.full_name}")
            for col in sorted(getattr(table, "columns", []) or [], key=lambda c: c.ordinal_position):
                pk = " PK" if getattr(col, "is_primary_key", False) else ""
                nullable = f", nullable={getattr(col, 'nullable', '')}" if getattr(col, "nullable", "") else ""
                lines.append(f"- {col.column_name}: {col.data_type}{pk}{nullable}")
            lines.append("")

    lines.append("## Relationships")
    rels = [rel for rel in state.relationships.values() if bool(getattr(rel, "active", True)) or not only_active]
    if not rels:
        lines.append("_No relationships included._")
    else:
        for rel in rels:
            source_full, target_full = relationship_tables(rel)
            context_name = _context_name(source_state, getattr(rel, "context_id", ""))
            lines.append(f"- {source_full}.{rel.source_column} -> {target_full}.{rel.target_column}")
            lines.append(f"  - Context: {context_name}")
            lines.append(f"  - Type: {getattr(rel, 'relationship_type', '')}")
            lines.append(f"  - Cardinality: {getattr(rel, 'cardinality', '')}")
            lines.append(f"  - Join: {getattr(rel, 'join_type', '')}")
            if getattr(rel, "condition_sql", ""):
                lines.append(f"  - Condition: {rel.condition_sql}")
            if getattr(rel, "extra_join_sql", ""):
                lines.append(f"  - Extra join: {rel.extra_join_sql}")
            if getattr(rel, "description", ""):
                lines.append(f"  - Description: {rel.description}")
    return "\n".join(lines)


def _export_json(state: ErdState, source_state: ErdState, scope_label: str, only_active: bool = True) -> str:
    payload = {
        "scope": scope_label,
        "tables": [
            {
                "schema_name": table.schema_name,
                "table_name": table.table_name,
                "full_name": table.full_name,
                "columns": [
                    {
                        "column_name": col.column_name,
                        "data_type": col.data_type,
                        "is_primary_key": col.is_primary_key,
                        "nullable": getattr(col, "nullable", ""),
                        "ordinal_position": col.ordinal_position,
                    }
                    for col in getattr(table, "columns", []) or []
                ],
            }
            for table in state.tables.values()
        ],
        "relationships": [
            {
                "id": rel.id,
                "context_id": getattr(rel, "context_id", ""),
                "context_name": _context_name(source_state, getattr(rel, "context_id", "")),
                "source_schema": rel.source_schema,
                "source_table": rel.source_table,
                "source_column": rel.source_column,
                "target_schema": rel.target_schema,
                "target_table": rel.target_table,
                "target_column": rel.target_column,
                "relationship_type": rel.relationship_type,
                "cardinality": rel.cardinality,
                "join_type": rel.join_type,
                "condition_sql": rel.condition_sql,
                "extra_join_sql": getattr(rel, "extra_join_sql", ""),
                "description": rel.description,
                "active": rel.active,
            }
            for rel in state.relationships.values()
            if bool(getattr(rel, "active", True)) or not only_active
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _render_export_quality_panel(report: dict) -> None:
    st.markdown("### Export readiness")
    metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
    metric_col1.metric("Readiness score", f"{int(report.get('score', 0))}%")
    metric_col2.metric("Status", report.get("status", "Unknown"))
    metric_col3.metric("Tables", report.get("tables_included", 0))
    metric_col4.metric("Relationships", report.get("relationships_included", 0))

    detail_col1, detail_col2, detail_col3, detail_col4 = st.columns(4)
    detail_col1.metric("Columns", report.get("columns_included", 0))
    detail_col2.metric("Active relationships", report.get("active_relationships", 0))
    detail_col3.metric("Conditional relationships", report.get("conditional_relationships", 0))
    detail_col4.metric("Broken links", report.get("broken_relationship_count", 0))

    warnings = report.get("warnings", [])
    if warnings:
        st.warning("This export may be incomplete. Review the issues below before using the output for SQL generation.")
        for warning in warnings:
            st.caption(f"- {warning}")
    else:
        st.success("Export readiness checks look good.")

    rows = report_to_issue_rows(report)
    if rows:
        with st.expander("Review export quality issues", expanded=False):
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


def _log_export_once(report: dict, export_format: str, scope_label: str) -> None:
    payload = {
        "format": export_format,
        "scope": scope_label,
        "score": report.get("score"),
        "warning_count": len(report.get("warnings", [])),
        "relationships_included": report.get("relationships_included"),
        "tables_included": report.get("tables_included"),
    }
    signature = hashlib.md5(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    if st.session_state.get("last_multi_context_export_log_signature") == signature:
        return
    st.session_state["last_multi_context_export_log_signature"] = signature

    try:
        from logger import log_info, log_warning
        details = {
            "format": export_format,
            "scope": scope_label,
            "score": report.get("score"),
            "status": report.get("status"),
            "warning_count": len(report.get("warnings", [])),
            "relationships_included": report.get("relationships_included"),
            "tables_included": report.get("tables_included"),
        }
        if report.get("warnings"):
            log_warning("Export", "export_generated_with_warnings", "Export generated with warnings", details)
        else:
            log_info("Export", "export_generated", "Export generated successfully", details)
    except Exception:
        pass


def render_export_tab(state: ErdState) -> None:
    st.subheader("Export for ChatGPT")
    st.caption("Export the whole database or selected relationship contexts for SQL/query generation support.")

    _mode, context_ids, scope_label = _selected_context_scope(state, "export_v2216")

    only_active = st.checkbox(
        "Only include active relationships",
        value=True,
        key="export_only_active_v2216",
        help="Exclude inactive relationships from the export and quality report.",
    )
    connected_only = st.checkbox(
        "Only include tables connected to the selected relationships",
        value=True,
        key="export_connected_only_v2216",
        help="When enabled, tables are inferred from relationship endpoints.",
    )

    scoped_state = build_scoped_state_from_context(
        state,
        context_ids=context_ids,
        active_only=only_active,
        connected_only=connected_only,
    )

    report = build_export_quality_report(
        state,
        context_ids=context_ids,
        selected_relationship_ids=list(scoped_state.relationships.keys()),
        infer_tables_from_relationships=True,
        active_only=only_active,
    )

    st.info(f"Current export scope: {scope_label}")
    st.caption(f"Tables included: {len(scoped_state.tables)} | Relationships included: {len(scoped_state.relationships)}")
    _render_export_quality_panel(report)
    st.divider()

    export_format = st.selectbox(
        "Export format",
        ["Markdown", "JSON", "Mermaid"],
        key="export_format_v2216",
    )

    if export_format == "Markdown":
        output = _export_markdown(scoped_state, state, scope_label, only_active=only_active)
        file_name = "entity_relation_mapper_export.md"
        mime = "text/markdown"
        language = "markdown"
    elif export_format == "JSON":
        output = _export_json(scoped_state, state, scope_label, only_active=only_active)
        file_name = "entity_relation_mapper_export.json"
        mime = "application/json"
        language = "json"
    else:
        try:
            output = export_mermaid(scoped_state, only_active=only_active)
        except Exception:
            output = "erDiagram"
        file_name = "entity_relation_mapper_export.mmd"
        mime = "text/plain"
        language = "mermaid"

    _log_export_once(report, export_format, scope_label)

    with st.expander("Preview export output", expanded=True):
        st.code(output, language=language)

    st.download_button(
        f"Download {export_format} export",
        data=output,
        file_name=file_name,
        mime=mime,
    )
