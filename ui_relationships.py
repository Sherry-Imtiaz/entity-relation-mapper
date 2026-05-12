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


def render_relationships_tab(state: ErdState) -> None:
        st.subheader("Relationship registry")
        active_ctx = get_active_context(state)
        if active_ctx:
            st.info(f"Active context: {active_ctx.name} ({active_ctx.context_type})")
        else:
            st.info("No active relationship context selected. Existing relationships are shown as global/unassigned.")

        registry_scope = st.radio(
            "Relationship registry scope",
            ["Active context only", "All relationships"],
            horizontal=True,
            key="relationship_registry_scope",
        )
        df = relationships_df(state)
        if not df.empty and registry_scope == "Active context only":
            df = df[df["context"] == context_display_name(state, state.active_context_id)]

        dashboard_context_id = state.active_context_id if registry_scope == "Active context only" else None
        quality = relationship_quality_summary(state, context_id=dashboard_context_id)
        st.markdown("### Relationship quality dashboard")
        q1, q2, q3, q4, q5, q6 = st.columns(6)
        q1.metric("Total", quality["total"])
        q2.metric("Active", quality["active"])
        q3.metric("Manual", quality["manual"])
        q4.metric("Inferred", quality["inferred"])
        q5.metric("Conditional", quality["conditional"])
        q6.metric("Broken", quality["broken"])

        with st.expander("Relationship validation details"):
            validation_df = validate_relationships(state, context_id=dashboard_context_id)
            if validation_df.empty:
                st.info("No relationships to validate.")
            else:
                st.dataframe(validation_df.drop(columns=["id"]), width="stretch", hide_index=True)

        if df.empty:
            st.info("No relationships yet. Import a Relationships sheet, infer links, or add manual relationships.")
        else:
            type_filter = st.multiselect(
                "Filter by type",
                sorted(df["type"].dropna().unique().tolist()),
                default=sorted(df["type"].dropna().unique().tolist()),
            )
            filtered = df[df["type"].isin(type_filter)] if type_filter else df
            st.dataframe(filtered.drop(columns=["id"]), width="stretch", hide_index=True)

            with st.expander("Edit / delete a relationship"):
                rel_options = [
                    f"{r.relationship_type}: {r.source_full_table}.{r.source_column} -> {r.target_full_table}.{r.target_column} [{r.id}]"
                    for r in state.relationships.values()
                    if registry_scope == "All relationships" or context_display_name(state, r.context_id) == context_display_name(state, state.active_context_id)
                ]
                if not rel_options:
                    st.info("No relationships available for editing in this scope.")
                else:
                    choice = st.selectbox("Relationship", rel_options)
                    chosen_id = choice.split("[")[-1].rstrip("]") if choice else ""
                    if chosen_id in state.relationships:
                        rel = state.relationships[chosen_id]
                        rel.active = st.checkbox("Active", value=rel.active, key=f"rel_edit_active_{rel.id}")
                        rel.relationship_type = st.selectbox(
                            "Relationship type",
                            ["manual", "conditional", "inferred", "imported", "explicit_fk"],
                            index=["manual", "conditional", "inferred", "imported", "explicit_fk"].index(rel.relationship_type) if rel.relationship_type in ["manual", "conditional", "inferred", "imported", "explicit_fk"] else 0,
                            key=f"rel_edit_type_{rel.id}",
                        )
                        rel.join_type = st.selectbox(
                            "Join type",
                            ["LEFT JOIN", "INNER JOIN", "RIGHT JOIN", "FULL OUTER JOIN"],
                            index=["LEFT JOIN", "INNER JOIN", "RIGHT JOIN", "FULL OUTER JOIN"].index(rel.join_type) if rel.join_type in ["LEFT JOIN", "INNER JOIN", "RIGHT JOIN", "FULL OUTER JOIN"] else 0,
                            key=f"rel_edit_join_{rel.id}",
                        )
                        rel.cardinality = st.selectbox(
                            "Cardinality",
                            ["many-to-one", "one-to-many", "one-to-one", "many-to-many"],
                            index=["many-to-one", "one-to-many", "one-to-one", "many-to-many"].index(rel.cardinality) if rel.cardinality in ["many-to-one", "one-to-many", "one-to-one", "many-to-many"] else 0,
                            key=f"rel_edit_cardinality_{rel.id}",
                        )
                        rel.condition_sql = st.text_input("Condition SQL, optional", value=rel.condition_sql, key=f"rel_edit_condition_{rel.id}")
                        rel.extra_join_sql = st.text_input("Extra join SQL, optional", value=rel.extra_join_sql, key=f"rel_edit_extra_{rel.id}")
                        rel.description = st.text_area("Description / business meaning", value=rel.description, key=f"rel_edit_description_{rel.id}")
                        col1, col2 = st.columns(2)
                        if col1.button("Save relationship", key=f"rel_save_{rel.id}"):
                            save_state(state)
                            st.success("Saved relationship.")
                        if col2.button("Delete relationship", key=f"rel_delete_{rel.id}"):
                            del state.relationships[chosen_id]
                            save_state(state)
                            st.success("Deleted relationship.")
                            st.rerun()

        st.divider()
        st.subheader("Add manual relationship")
        active_ctx = get_active_context(state)
        scoped_tables = get_context_tables(state, active_ctx.id) if active_ctx else {}
        if active_ctx and len(scoped_tables) >= 2:
            st.caption("Manual relationships added here will be stored against the active relationship context.")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Source table filter**")
                _, _, source_table_options = render_table_filter_controls(state, key_prefix="manual_source")
                source_table_options = [t for t in source_table_options if t in scoped_tables] or sorted(scoped_tables.keys(), key=str.lower)
                source_full = st.selectbox("Source table", source_table_options, key="manual_source_table")
                source_col = st.selectbox("Source column", get_table_columns(state, source_full), key="manual_source_col")
            with c2:
                st.markdown("**Target table filter**")
                _, _, target_table_options = render_table_filter_controls(state, key_prefix="manual_target")
                target_table_options = [t for t in target_table_options if t in scoped_tables] or sorted(scoped_tables.keys(), key=str.lower)
                target_full = st.selectbox("Target table", target_table_options, key="manual_target_table")
                target_col = st.selectbox("Target column", get_table_columns(state, target_full), key="manual_target_col")

            c3, c4, c5 = st.columns(3)
            with c3:
                cardinality = st.selectbox("Cardinality", ["many-to-one", "one-to-many", "one-to-one", "many-to-many"])
            with c4:
                join_type = st.selectbox("Join type", ["LEFT JOIN", "INNER JOIN", "RIGHT JOIN", "FULL OUTER JOIN"])
            with c5:
                confidence = st.slider("Confidence", 0.0, 1.0, 0.90, 0.05)

            relationship_mode = st.radio(
                "Relationship mode",
                ["Standard relationship", "Conditional relationship"],
                horizontal=True,
                key="manual_relationship_mode",
            )
            condition_sql = ""
            if relationship_mode == "Conditional relationship":
                condition_sql = st.text_input(
                    "Condition SQL",
                    placeholder="Example: src.Item_Type = 3",
                    key="manual_condition_sql",
                )
            extra_join_sql = st.text_input(
                "Extra join SQL, optional",
                placeholder="Example: src.ValidTo IS NULL",
                key="manual_extra_join_sql",
            )
            description = st.text_area("Description / business meaning", key="manual_description")

            if st.button("Add relationship", type="primary"):
                ss, stbl = split_full_table(source_full)
                ts, ttbl = split_full_table(target_full)
                new_relationship_type = "conditional" if relationship_mode == "Conditional relationship" else "manual"
                rid = rel_id(ss, stbl, source_col, ts, ttbl, target_col, new_relationship_type, condition_sql)
                state.relationships[rid] = Relationship(
                    id=rid,
                    context_id=active_ctx.id,
                    source_schema=ss,
                    source_table=stbl,
                    source_column=source_col,
                    target_schema=ts,
                    target_table=ttbl,
                    target_column=target_col,
                    relationship_type=new_relationship_type,
                    cardinality=cardinality,
                    join_type=join_type,
                    confidence=confidence,
                    condition_sql=condition_sql,
                    extra_join_sql=extra_join_sql,
                    description=description,
                )
                save_state(state)
                st.success("Relationship added.")
                st.rerun()
        else:
            relationship_context_warning(state)
            st.info("Assign at least two tables to the active relationship context before adding manual relationships.")

        st.divider()
        st.info(
            "Visual relationship creation has been removed from this tab. "
            "Use the form above to create/edit relationships, and use the ERD View tab for interactive Streamlit Flow visualisation."
        )

    # ---------------------------------------------------------------------
    # Inference tab
    # ---------------------------------------------------------------------
