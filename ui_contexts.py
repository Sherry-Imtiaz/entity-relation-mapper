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


def render_contexts_tab(state: ErdState) -> None:
        st.subheader("Named Relationship Contexts")
        st.write(
            "Create named relationship contexts such as Module Relations, Payment Relations, Customer Relations, "
            "or Property Ownership Relations. Phase 1 lets you create contexts and assign tables to them."
        )

        with st.expander("Create new relationship context", expanded=not bool(state.relationship_contexts)):
            new_name = st.text_input("Context name", placeholder="Example: Property Ownership Relations", key="new_context_name")
            new_type = st.selectbox(
                "Context type",
                [
                    "Module Relation",
                    "Payment Relation",
                    "Customer Relation",
                    "Property Relation",
                    "Animal Relation",
                    "Regulatory Relation",
                    "Reporting Relation",
                    "Other",
                ],
                key="new_context_type",
            )
            custom_new_type = ""
            if new_type == "Other":
                custom_new_type = st.text_input(
                    "Custom context type",
                    placeholder="Example: Rates Relation, Debtor Relation, Asset Relation",
                    key="new_context_custom_type",
                )
            new_purpose = st.text_area("Purpose", placeholder="What does this relationship context explain?", key="new_context_purpose")
            if st.button("Create relationship context", type="primary"):
                if not new_name.strip():
                    st.error("Enter a context name first.")
                else:
                    cid = unique_context_id(state.relationship_contexts, new_name)
                    state.relationship_contexts[cid] = RelationshipContext(
                        id=cid,
                        name=new_name.strip(),
                        context_type=(custom_new_type.strip() if new_type == "Other" and custom_new_type.strip() else new_type),
                        purpose=new_purpose.strip(),
                    )
                    state.active_context_id = cid
                    save_state(state)
                    st.success(f"Created relationship context: {new_name.strip()}")
                    st.rerun()

        if not state.relationship_contexts:
            st.info("No relationship contexts have been created yet.")
        else:
            context_ids = list(state.relationship_contexts.keys())
            active_index = context_ids.index(state.active_context_id) if state.active_context_id in context_ids else 0
            context_choice = st.selectbox(
                "Active relationship context",
                context_ids,
                index=active_index,
                format_func=lambda cid: f"{state.relationship_contexts[cid].name} ({state.relationship_contexts[cid].context_type})",
            )
            state.active_context_id = context_choice
            ctx = state.relationship_contexts[context_choice]

            st.divider()
            st.markdown("### Context details")
            d1, d2, d3 = st.columns([2, 1, 1])
            existing_context_type_before_select = ctx.context_type
            with d1:
                ctx.name = st.text_input("Relationship context name", value=ctx.name, key=f"ctx_name_{ctx.id}")
            with d2:
                ctx.context_type = st.selectbox(
                    "Relationship type",
                    [
                        "Module Relation",
                        "Payment Relation",
                        "Customer Relation",
                        "Property Relation",
                        "Animal Relation",
                        "Regulatory Relation",
                        "Reporting Relation",
                        "Other",
                    ],
                    index=[
                        "Module Relation",
                        "Payment Relation",
                        "Customer Relation",
                        "Property Relation",
                        "Animal Relation",
                        "Regulatory Relation",
                        "Reporting Relation",
                        "Other",
                    ].index(ctx.context_type) if ctx.context_type in [
                        "Module Relation",
                        "Payment Relation",
                        "Customer Relation",
                        "Property Relation",
                        "Animal Relation",
                        "Regulatory Relation",
                        "Reporting Relation",
                        "Other",
                    ] else 0,
                    key=f"ctx_type_{ctx.id}",
                )
            with d3:
                ctx.status = st.selectbox(
                    "Status",
                    ["Draft", "Reviewed", "Approved", "Deprecated"],
                    index=["Draft", "Reviewed", "Approved", "Deprecated"].index(ctx.status) if ctx.status in ["Draft", "Reviewed", "Approved", "Deprecated"] else 0,
                    key=f"ctx_status_{ctx.id}",
                )

            custom_existing_type = st.text_input(
                "Custom relationship type / label override",
                value="" if existing_context_type_before_select in [
                    "Module Relation",
                    "Payment Relation",
                    "Customer Relation",
                    "Property Relation",
                    "Animal Relation",
                    "Regulatory Relation",
                    "Reporting Relation",
                    "Other",
                ] else existing_context_type_before_select,
                placeholder="Optional. Example: Debtor Payment Relation",
                key=f"ctx_custom_type_{ctx.id}",
            )
            if custom_existing_type.strip():
                ctx.context_type = custom_existing_type.strip()

            ctx.owner_reviewer = st.text_input("Owner / reviewer", value=ctx.owner_reviewer, key=f"ctx_owner_{ctx.id}")
            ctx.purpose = st.text_area("Purpose", value=ctx.purpose, key=f"ctx_purpose_{ctx.id}")
            ctx.business_context = st.text_area("Business context", value=ctx.business_context, key=f"ctx_business_{ctx.id}")
            ctx.primary_join_path = st.text_area("Primary join path", value=ctx.primary_join_path, key=f"ctx_join_path_{ctx.id}")
            ctx.conditional_logic_notes = st.text_area("Conditional logic notes", value=ctx.conditional_logic_notes, key=f"ctx_condition_notes_{ctx.id}")
            ctx.query_guidance = st.text_area("Query / export guidance", value=ctx.query_guidance, key=f"ctx_query_guidance_{ctx.id}")
            ctx.comments = st.text_area("Comments", value=ctx.comments, key=f"ctx_comments_{ctx.id}")

            st.divider()
            st.markdown("### Tables assigned to this context")
            assigned_tables = [t for t in ctx.included_tables if t in state.tables]
            missing_tables = [t for t in ctx.included_tables if t not in state.tables]
            ctx.included_tables = assigned_tables + missing_tables

            if assigned_tables:
                st.dataframe(
                    pd.DataFrame({"included_table": assigned_tables}),
                    width="stretch",
                    hide_index=True,
                )
            else:
                st.info("No tables have been assigned to this relationship context yet.")

            if missing_tables:
                st.warning("Some assigned tables are no longer available in the imported schema:")
                st.write(missing_tables)

            remove_tables = st.multiselect(
                "Remove assigned tables",
                assigned_tables,
                key=f"ctx_remove_tables_{ctx.id}",
            )
            if st.button("Remove selected tables", key=f"ctx_remove_btn_{ctx.id}"):
                ctx.included_tables = [t for t in ctx.included_tables if t not in remove_tables]
                ctx.updated_at = datetime.now(UTC).isoformat()
                save_state(state)
                st.success("Removed selected tables from the context.")
                st.rerun()

            st.markdown("### Add tables to this context")
            if not state.tables:
                st.info("Import schema tables before assigning tables to a relationship context.")
            else:
                _, _, table_options = render_table_filter_controls(state, key_prefix=f"ctx_add_{ctx.id}")
                candidate_options = [t for t in table_options if t not in ctx.included_tables]
                add_tables = st.multiselect(
                    "Filtered tables available to add",
                    candidate_options,
                    key=f"ctx_add_tables_{ctx.id}",
                )
                if st.button("Add selected tables to context", key=f"ctx_add_btn_{ctx.id}"):
                    ctx.included_tables = sorted(set(ctx.included_tables + add_tables), key=str.lower)
                    ctx.updated_at = datetime.now(UTC).isoformat()
                    save_state(state)
                    st.success("Added selected tables to the context.")
                    st.rerun()

            b1, b2 = st.columns([1, 1])
            if b1.button("Save context details", type="primary", key=f"ctx_save_{ctx.id}"):
                ctx.updated_at = datetime.now(UTC).isoformat()
                save_state(state)
                st.success("Saved relationship context.")
            if b2.button("Delete active context", key=f"ctx_delete_{ctx.id}"):
                del state.relationship_contexts[ctx.id]
                state.active_context_id = next(iter(state.relationship_contexts.keys()), "")
                save_state(state)
                st.success("Deleted relationship context.")
                st.rerun()

            with st.expander("Phase 1 note"):
                st.write(
                    "This phase creates the context model and table assignment workflow. "
                    "Manual, inferred, conditional relationships, ERD view, and exports will be scoped to the selected context in the next phases."
                )

    # ---------------------------------------------------------------------
    # Tables tab
    # ---------------------------------------------------------------------
