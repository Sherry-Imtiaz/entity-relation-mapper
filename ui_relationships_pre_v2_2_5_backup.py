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
from relationship_guidance import suggest_relationship_options


def render_relationships_tab(state: ErdState) -> None:
        st.subheader("Relationship registry")
        render_context_manual_relationship_picklist_form(state)
        st.divider()
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
            render_relationship_suggestion_panel(
        state,
        source_full,
        source_col,
        target_full,
        target_col,
        relationship_mode,
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
            "Use this page to create, review, and maintain relationships for the active context. "
            ""
        )

    # ---------------------------------------------------------------------
    # Inference tab
    # ---------------------------------------------------------------------


def render_relationship_field_guide() -> None:
    with st.expander("Relationship field guide", expanded=False):
        st.markdown(
            """
| Field | Meaning |
|---|---|
| Source table | The table where the relationship starts. Usually the child/detail table or the table containing the foreign key. |
| Source column | The source field used in the join. Often an ID or foreign-key-like field. |
| Target table | The table being joined to. Usually the parent, master, or reference table. |
| Target column | The matching field in the target table. Often a primary key or unique ID. |
| Relationship mode | Standard relationships join directly. Conditional relationships need an additional rule such as `src.Item_Type = 3`. |
| Cardinality | Describes how records relate between the two tables, such as many source records to one target record. |
| Join type | Defines the SQL join style. `LEFT JOIN` keeps all source records. `INNER JOIN` only keeps matching records. |
| Confidence | Your confidence that this relationship is correct. |
| Condition SQL | A rule that must be true for the relationship to apply. Useful for discriminator fields like `Item_Type`. |
| Extra Join SQL | Optional extra filter used in the join, such as active/current records only. |
| Description | Business meaning of the relationship. This improves ChatGPT-generated SQL and future review. |
"""
        )


def apply_pending_relationship_suggestions() -> None:
    pending_map = {
        "pending_manual_picklist_cardinality": "manual_picklist_cardinality",
        "pending_manual_picklist_join_type": "manual_picklist_join_type",
        "pending_manual_picklist_confidence": "manual_picklist_confidence",
    }

    for pending_key, widget_key in pending_map.items():
        if pending_key in st.session_state:
            st.session_state[widget_key] = st.session_state.pop(pending_key)


def render_relationship_suggestion_panel(
    state: ErdState,
    source_full: str,
    source_col: str,
    target_full: str,
    target_col: str,
    relationship_mode: str,
) -> None:
    suggestion = suggest_relationship_options(
        state,
        source_full,
        source_col,
        target_full,
        target_col,
        relationship_mode,
    )

    st.markdown("#### Suggested relationship options")

    if suggestion.get("warning"):
        st.warning(suggestion["warning"])

    metric_col1, metric_col2, metric_col3 = st.columns(3)
    metric_col1.metric("Suggested cardinality", suggestion["cardinality"])
    metric_col2.metric("Suggested join", suggestion["join_type"])
    metric_col3.metric("Suggested confidence", f'{float(suggestion["confidence"]):.2f}')

    with st.expander("Why these options are suggested", expanded=False):
        st.write(suggestion["reason"])

    if st.button(
        "Apply suggested options",
        key="manual_picklist_apply_suggestion",
        help="Apply the suggested cardinality, join type, and confidence to the relationship form.",
    ):
        st.session_state["pending_manual_picklist_cardinality"] = suggestion["cardinality"]
        st.session_state["pending_manual_picklist_join_type"] = suggestion["join_type"]
        st.session_state["pending_manual_picklist_confidence"] = float(suggestion["confidence"])

        try:
            from logger import log_info

            log_info(
                "Relationships",
                "suggestion_applied",
                "Relationship suggestion applied",
                {
                    "source": f"{source_full}.{source_col}",
                    "target": f"{target_full}.{target_col}",
                    "suggestion": suggestion,
                },
            )
        except Exception:
            pass

        st.success("Suggested options applied.")
        st.rerun()


def render_context_manual_relationship_picklist_form(state: ErdState) -> None:
    st.markdown("### Add relationship from active context")
    apply_pending_relationship_suggestions()

    active_ctx = get_active_context(state)
    if not active_ctx:
        relationship_context_warning(state)
        return

    scoped_tables = get_context_tables(state, active_ctx.id)
    if len(scoped_tables) < 2:
        relationship_context_warning(state)
        st.info("Add at least two tables to the active relationship context before creating relationships.")
        return

    st.info(f"Relationship creation scope: {active_ctx.name} - {len(scoped_tables)} assigned tables")

    table_options = sorted(scoped_tables.keys(), key=str.lower)
    schema_options = ["All schemas"] + sorted(
        {scoped_tables[t].schema_name or "(no schema)" for t in table_options},
        key=str.lower,
    )

    col_source, col_target = st.columns(2)

    with col_source:
        st.markdown("**Source**")
        source_schema_filter = st.selectbox(
            "Source schema filter",
            schema_options,
            key="manual_picklist_source_schema_filter",
        )
        source_search = st.text_input(
            "Search source table",
            placeholder="Type to filter source tables",
            key="manual_picklist_source_search",
        )

        source_options = table_options
        if source_schema_filter != "All schemas":
            source_options = [
                t for t in source_options
                if (scoped_tables[t].schema_name or "(no schema)") == source_schema_filter
            ]
        if source_search.strip():
            source_options = [
                t for t in source_options
                if source_search.strip().lower() in t.lower()
            ]
        if not source_options:
            source_options = table_options

        source_full = st.selectbox(
            "Source table",
            source_options,
            key="manual_picklist_source_table",
            help="The table where the relationship starts. Usually the child/detail table or the table containing the foreign key.",
        )
        source_columns = get_table_columns(state, source_full)
        source_col = st.selectbox(
            "Source column",
            source_columns,
            key="manual_picklist_source_column",
            help="The source field used in the join. Often an ID or foreign-key-like field.",
        )

    with col_target:
        st.markdown("**Target**")
        target_schema_filter = st.selectbox(
            "Target schema filter",
            schema_options,
            key="manual_picklist_target_schema_filter",
        )
        target_search = st.text_input(
            "Search target table",
            placeholder="Type to filter target tables",
            key="manual_picklist_target_search",
        )

        target_options = table_options
        if target_schema_filter != "All schemas":
            target_options = [
                t for t in target_options
                if (scoped_tables[t].schema_name or "(no schema)") == target_schema_filter
            ]
        if target_search.strip():
            target_options = [
                t for t in target_options
                if target_search.strip().lower() in t.lower()
            ]
        if not target_options:
            target_options = table_options

        target_full = st.selectbox(
            "Target table",
            target_options,
            key="manual_picklist_target_table",
            help="The table being joined to. Usually the parent, master, or reference table.",
        )
        target_columns = get_table_columns(state, target_full)
        target_col = st.selectbox(
            "Target column",
            target_columns,
            key="manual_picklist_target_column",
            help="The matching field in the target table. Often a primary key or unique ID.",
        )

    options_col1, options_col2, options_col3 = st.columns(3)

    with options_col1:
        relationship_mode = st.selectbox(
            "Relationship mode",
            ["Standard relationship", "Conditional relationship"],
            key="manual_picklist_relationship_mode",
            help="Use Standard for direct joins. Use Conditional when an extra rule is required, such as src.Item_Type = 3.",
        )
    with options_col2:
        cardinality = st.selectbox(
            "Cardinality",
            ["many-to-one", "one-to-many", "one-to-one", "many-to-many"],
            key="manual_picklist_cardinality",
            help="Describes how records relate between source and target tables. Many-to-one is common for detail-to-master joins.",
        )
    with options_col3:
        join_type = st.selectbox(
            "Join type",
            ["LEFT JOIN", "INNER JOIN", "RIGHT JOIN", "FULL OUTER JOIN"],
            key="manual_picklist_join_type",
            help="LEFT JOIN keeps all source records. INNER JOIN only returns matching records.",
        )

    confidence = st.slider(
        "Confidence",
        min_value=0.0,
        max_value=1.0,
        value=st.session_state.get("manual_picklist_confidence", 1.0),
        step=0.05,
        key="manual_picklist_confidence",
    )

    render_relationship_suggestion_panel(
        state,
        source_full,
        source_col,
        target_full,
        target_col,
        relationship_mode,
    )

    condition_sql = ""
    if relationship_mode == "Conditional relationship":
        condition_sql = st.text_input(
            "Condition SQL",
            placeholder="Example: src.Item_Type = 3",
            key="manual_picklist_condition_sql",
            help="Extra rule required for this relationship to be valid. Use this for discriminator fields such as Item_Type.",
        )

    extra_join_sql = st.text_input(
        "Extra Join SQL, optional",
        placeholder="Example: src.ValidTo IS NULL",
        key="manual_picklist_extra_join_sql",
        help="Optional extra SQL filter for the join, such as active/current records only.",
    )

    description = st.text_area(
        "Description / business meaning",
        placeholder="Explain what this relationship means in business/database terms.",
        key="manual_picklist_description",
        help="Describe the business meaning of the relationship. This improves future SQL generation and review.",
    )

    with st.expander("Relationship preview", expanded=False):
        preview = f"{source_full}.{source_col} -> {target_full}.{target_col}"
        if condition_sql.strip():
            preview += f"\\nCondition: {condition_sql}"
        if extra_join_sql.strip():
            preview += f"\\nExtra join: {extra_join_sql}"
        st.code(preview, language="text")

    if st.button("Add relationship from picklists", type="primary", key="manual_picklist_add_relationship"):
        if source_full == target_full and source_col == target_col:
            st.warning("Source and target are the same table/column. Confirm this is intentional before saving.")
            return

        ss, stbl = split_full_table(source_full)
        ts, ttbl = split_full_table(target_full)
        relationship_type = "conditional" if condition_sql.strip() else "manual"

        rid = rel_id(
            ss,
            stbl,
            source_col,
            ts,
            ttbl,
            target_col,
            relationship_type,
            condition_sql,
        )

        state.relationships[rid] = Relationship(
            id=rid,
            context_id=active_ctx.id,
            source_schema=ss,
            source_table=stbl,
            source_column=source_col,
            target_schema=ts,
            target_table=ttbl,
            target_column=target_col,
            relationship_type=relationship_type,
            cardinality=cardinality,
            join_type=join_type,
            confidence=confidence,
            condition_sql=condition_sql,
            extra_join_sql=extra_join_sql,
            description=description,
        )

        save_state(state)

        try:
            from logger import log_info

            log_info(
                "Relationships",
                "relationship_added",
                "Relationship added from picklist form",
                {
                    "context": active_ctx.name,
                    "source": f"{source_full}.{source_col}",
                    "target": f"{target_full}.{target_col}",
                    "relationship_type": relationship_type,
                },
            )
        except Exception:
            pass

        st.success("Relationship added to the active context.")
        st.rerun()
