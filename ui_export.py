from __future__ import annotations

import json

from datetime import UTC, datetime
from typing import Any, Dict, List, Optional, Tuple
import re

import pandas as pd
import streamlit as st

try:
    from streamlit_flow import streamlit_flow
except ImportError:
    streamlit_flow = None

from config import APP_CHANGELOG, APP_VERSION, APP_VERSION_NAME, STATE_FILE
from models import ColumnInfo, ErdState, Relationship, RelationshipContext, TableInfo
from state_manager import default_state, deserialize_state, load_state, merge_tables_keep_metadata, save_state, serialize_state
from importers import create_import_template_excel, create_simple_csv_template, import_schema_file, split_table_identifier
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
from ui_shared import *


def render_export_tab(state: ErdState) -> None:
    st.subheader("Export for ChatGPT / SQL generation")
    only_active = st.checkbox("Only export active relationships", value=True, key="export_only_active")
    active_ctx = get_active_context(state)

    export_scope_options = ["Whole database"]
    if active_ctx:
        export_scope_options.append("Active relationship context")
    export_scope = st.radio("Export scope", export_scope_options, index=1 if active_ctx else 0, horizontal=True)

    selected_context_id: Optional[str] = None
    selected_tables: List[str] = []

    if export_scope == "Active relationship context" and active_ctx:
        selected_context_id = active_ctx.id
        export_state = build_context_scoped_state(state, active_ctx.id)
        st.info(f"Exporting named relationship context: {active_ctx.name}")
        st.markdown("### Context export notes")
        st.write(f"**Type:** {active_ctx.context_type}")
        st.write(f"**Status:** {active_ctx.status}")
        if active_ctx.purpose:
            st.write(f"**Purpose:** {active_ctx.purpose}")
        if active_ctx.query_guidance:
            st.write(f"**Query Guidance:** {active_ctx.query_guidance}")
    else:
        export_state = state
        selected_tables = st.multiselect(
            "Limit export to selected tables, optional",
            sorted(state.tables.keys(), key=str.lower),
            default=[],
        )

    validation_df = validate_relationships(export_state)
    broken_count = 0 if validation_df.empty else int((validation_df["status"] == "Broken").sum())
    warning_count = 0 if validation_df.empty else int((validation_df["status"] == "Warning").sum())
    if broken_count:
        st.error(f"Export warning: {broken_count} broken relationship(s) detected in this export scope.")
    elif warning_count:
        st.warning(f"Export note: {warning_count} relationship warning(s) detected in this export scope.")
    else:
        st.success("No relationship validation issues detected in this export scope.")

    c1, c2, c3 = st.columns(3)
    with c1:
        if selected_context_id:
            md = export_markdown_with_context(state, selected_context_id, only_active=only_active)
        else:
            md = export_markdown(export_state, selected_tables=selected_tables or None, only_active=only_active)
        st.download_button(
            "Download ChatGPT Markdown",
            data=md,
            file_name=(f"chatgpt_erd_context_{selected_context_id}.md" if selected_context_id else "chatgpt_erd_context.md"),
            mime="text/markdown",
            width="stretch",
        )
    with c2:
        if selected_context_id:
            js = export_json_with_context(state, selected_context_id, only_active=only_active)
        else:
            js = export_json(export_state, only_active=only_active)
        st.download_button(
            "Download JSON",
            data=js,
            file_name=(f"chatgpt_erd_context_{selected_context_id}.json" if selected_context_id else "chatgpt_erd_context.json"),
            mime="application/json",
            width="stretch",
        )
    with c3:
        mermaid_export = export_mermaid(export_state, only_active=only_active)
        st.download_button(
            "Download Mermaid ERD",
            data=mermaid_export,
            file_name=(f"erd_mermaid_{selected_context_id}.mmd" if selected_context_id else "erd_mermaid.mmd"),
            mime="text/plain",
            width="stretch",
        )

    with st.expander("Relationship validation for export scope"):
        if validation_df.empty:
            st.info("No relationships in this export scope.")
        else:
            st.dataframe(validation_df.drop(columns=["id"]), width="stretch", hide_index=True)

    st.write("Preview:")
    st.code(md[:20000], language="markdown")
    if len(md) > 20000:
        st.warning("Preview truncated. Download the full Markdown export.")


# -----------------------------------------------------------------------------
# v2.2.6 Export quality checks override
# -----------------------------------------------------------------------------


def _safe_call_export(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except TypeError:
        try:
            return fn(*args)
        except TypeError:
            return fn(args[0])


def _get_active_context_for_export(state: ErdState):
    active_id = getattr(state, "active_context_id", "")
    if active_id and active_id in getattr(state, "relationship_contexts", {}):
        return state.relationship_contexts[active_id]
    return None


def _build_export_state_for_scope(state: ErdState, scope: str):
    active_ctx = _get_active_context_for_export(state)
    if scope == "Active relationship context" and active_ctx:
        try:
            return build_context_scoped_state(state, active_ctx.id), active_ctx.id, active_ctx.name
        except Exception:
            return state, active_ctx.id, active_ctx.name
    return state, None, "Whole database"


def _render_export_quality_panel(report: dict) -> None:
    st.markdown("### Export readiness")

    score = int(report.get("score", 0))
    status = report.get("status", "Unknown")

    metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
    metric_col1.metric("Readiness score", f"{score}%")
    metric_col2.metric("Status", status)
    metric_col3.metric("Tables", report.get("tables_included", 0))
    metric_col4.metric("Relationships", report.get("relationships_included", 0))

    detail_col1, detail_col2, detail_col3, detail_col4 = st.columns(4)
    detail_col1.metric("Columns", report.get("columns_included", 0))
    detail_col2.metric("Active relationships", report.get("active_relationships", 0))
    detail_col3.metric("Conditional relationships", report.get("conditional_relationships", 0))
    detail_col4.metric("Broken links", report.get("broken_relationship_count", 0))

    issue_col1, issue_col2, issue_col3 = st.columns(3)
    issue_col1.metric("Tables without relationships", report.get("tables_without_relationship_count", 0))
    issue_col2.metric("Missing descriptions", report.get("relationships_missing_descriptions_count", 0))
    issue_col3.metric(
        "Missing condition SQL",
        report.get("conditional_relationships_missing_condition_sql_count", 0),
    )

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


def _fallback_markdown_export(state: ErdState) -> str:
    lines = ["# Database Context Export", ""]
    lines.append("## Tables")
    for table in sorted(state.tables.values(), key=lambda t: t.full_name.lower()):
        lines.append(f"### {table.full_name}")
        for col in sorted(table.columns, key=lambda c: c.ordinal_position):
            pk = " PK" if getattr(col, "is_primary_key", False) else ""
            lines.append(f"- {col.column_name}: {col.data_type}{pk}")
        lines.append("")

    lines.append("## Relationships")
    for rel in state.relationships.values():
        source_full = getattr(rel, "source_full_table", None) or f"{rel.source_schema}.{rel.source_table}"
        target_full = getattr(rel, "target_full_table", None) or f"{rel.target_schema}.{rel.target_table}"
        lines.append(f"- {source_full}.{rel.source_column} -> {target_full}.{rel.target_column}")
        if getattr(rel, "condition_sql", ""):
            lines.append(f"  - Condition: {rel.condition_sql}")
        if getattr(rel, "description", ""):
            lines.append(f"  - Description: {rel.description}")
    return chr(10).join(lines)


def _fallback_json_export(state: ErdState) -> str:
    payload = {
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
                        "ordinal_position": col.ordinal_position,
                    }
                    for col in table.columns
                ],
            }
            for table in state.tables.values()
        ],
        "relationships": [
            {
                "id": rel.id,
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
                "description": rel.description,
                "active": rel.active,
            }
            for rel in state.relationships.values()
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def render_export_tab(state: ErdState) -> None:

    from quality_checks import build_export_quality_report, report_to_issue_rows

    st.subheader("Export for ChatGPT")
    st.caption("Export database and relationship context for SQL/query generation support.")

    active_ctx = _get_active_context_for_export(state)

    scope_options = ["Whole database"]
    if active_ctx:
        scope_options.append("Active relationship context")

    default_index = 1 if active_ctx else 0
    export_scope = st.radio(
        "Export scope",
        scope_options,
        index=default_index,
        horizontal=True,
        help="Choose whether to export the whole imported schema or only the active relationship context.",
        key="export_quality_scope",
    )

    export_state, context_id, scope_name = _build_export_state_for_scope(state, export_scope)

    if export_scope == "Active relationship context" and not active_ctx:
        st.warning("No active relationship context is selected. Exporting the whole database instead.")

    st.info(f"Current export scope: {scope_name}")

    report = build_export_quality_report(state, context_id=context_id)
    _render_export_quality_panel(report)

    try:
        from logger import log_info, log_warning

        if report.get("warnings"):
            log_warning(
                "Export",
                "quality_report_generated",
                "Export quality report generated with warnings",
                report,
            )
        else:
            log_info(
                "Export",
                "quality_report_generated",
                "Export quality report generated successfully",
                report,
            )
    except Exception:
        pass

    st.divider()

    export_format = st.selectbox(
        "Export format",
        ["Markdown", "JSON", "Mermaid"],
        help="Markdown is usually best for ChatGPT. JSON is best for structured processing. Mermaid is useful for ERD text.",
        key="export_quality_format",
    )

    include_only_active = st.checkbox(
        "Only include active relationships",
        value=True,
        help="Exclude inactive relationships from the export output where supported.",
        key="export_quality_only_active",
    )

    if export_format == "Markdown":
        try:
            if context_id:
                output = _safe_call_export(export_markdown_with_context, state, context_id, include_only_active)
            else:
                output = _safe_call_export(export_markdown, export_state, include_only_active)
        except Exception:
            output = _fallback_markdown_export(export_state)
        file_name = "entity_relation_mapper_export.md"
        mime = "text/markdown"
        language = "markdown"

    elif export_format == "JSON":
        try:
            if context_id:
                output = _safe_call_export(export_json_with_context, state, context_id, include_only_active)
            else:
                output = _safe_call_export(export_json, export_state, include_only_active)
            if not isinstance(output, str):
                output = json.dumps(output, indent=2, ensure_ascii=False)
        except Exception:
            output = _fallback_json_export(export_state)
        file_name = "entity_relation_mapper_export.json"
        mime = "application/json"
        language = "json"

    else:
        try:
            output = _safe_call_export(export_mermaid, export_state, include_only_active)
        except Exception:
            output = "erDiagram"
        file_name = "entity_relation_mapper_export.mmd"
        mime = "text/plain"
        language = "mermaid"

    with st.expander("Preview export output", expanded=True):
        st.code(output, language=language)

    st.download_button(
        f"Download {export_format} export",
        data=output,
        file_name=file_name,
        mime=mime,
    )

    try:
        from logger import log_info, log_warning

        details = {
            "format": export_format,
            "scope": scope_name,
            "score": report.get("score"),
            "status": report.get("status"),
            "warning_count": len(report.get("warnings", [])),
        }

        if report.get("warnings"):
            log_warning("Export", "export_generated_with_warnings", "Export generated with warnings", details)
        else:
            log_info("Export", "export_generated", "Export generated successfully", details)
    except Exception:
        pass
