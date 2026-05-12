from __future__ import annotations

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
