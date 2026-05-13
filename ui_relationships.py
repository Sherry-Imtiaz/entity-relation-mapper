
from __future__ import annotations

import re
from typing import Dict, List, Tuple

import pandas as pd
import streamlit as st

from models import ErdState, Relationship
from state_manager import save_state
from validation import (
    get_context_tables,
    get_relationships_for_context,
    relationship_quality_summary,
    validate_relationships,
)
from ui_shared import *
from relationship_guidance import suggest_relationship_options


def _split_full_table(full_table: str) -> Tuple[str, str]:
    if "." in full_table:
        schema, table = full_table.split(".", 1)
        return schema, table
    return "", full_table


def _full_table(schema_name: str, table_name: str) -> str:
    schema = (schema_name or "").strip()
    table = (table_name or "").strip()
    return f"{schema}.{table}" if schema else table


def _relationship_full_tables(rel: Relationship) -> Tuple[str, str]:
    source = getattr(rel, "source_full_table", None) or _full_table(rel.source_schema, rel.source_table)
    target = getattr(rel, "target_full_table", None) or _full_table(rel.target_schema, rel.target_table)
    return source, target


def _relationship_id(
    source_schema: str,
    source_table: str,
    source_column: str,
    target_schema: str,
    target_table: str,
    target_column: str,
    relationship_type: str,
    condition_sql: str = "",
) -> str:
    raw = "|".join(
        [
            source_schema or "",
            source_table or "",
            source_column or "",
            target_schema or "",
            target_table or "",
            target_column or "",
            relationship_type or "",
            condition_sql or "",
        ]
    )
    return re.sub(r"[^A-Za-z0-9_]+", "_", raw).strip("_")[:220]


def _get_active_context_safe(state: ErdState):
    try:
        return get_active_context(state)
    except Exception:
        active_id = getattr(state, "active_context_id", "")
        if active_id and active_id in state.relationship_contexts:
            return state.relationship_contexts[active_id]
        return None


def _get_table_columns_safe(state: ErdState, full_table: str) -> List[str]:
    try:
        cols = get_table_columns(state, full_table)
        if cols:
            return cols
    except Exception:
        pass

    table = state.tables.get(full_table)
    if not table:
        return []
    return [c.column_name for c in sorted(table.columns, key=lambda c: c.ordinal_position)]


def _relationships_for_active_context(state: ErdState) -> Dict[str, Relationship]:
    active_ctx = _get_active_context_safe(state)
    if not active_ctx:
        return {}
    try:
        return get_relationships_for_context(state, active_ctx.id)
    except Exception:
        return {
            rid: rel
            for rid, rel in state.relationships.items()
            if getattr(rel, "context_id", "") == active_ctx.id
        }


def _relationships_dataframe(relationships: Dict[str, Relationship]) -> pd.DataFrame:
    rows = []
    for rel in relationships.values():
        source_full, target_full = _relationship_full_tables(rel)
        rows.append(
            {
                "id": rel.id,
                "context_id": getattr(rel, "context_id", ""),
                "source": f"{source_full}.{rel.source_column}",
                "target": f"{target_full}.{rel.target_column}",
                "type": getattr(rel, "relationship_type", ""),
                "cardinality": getattr(rel, "cardinality", ""),
                "join_type": getattr(rel, "join_type", ""),
                "confidence": getattr(rel, "confidence", None),
                "condition_sql": getattr(rel, "condition_sql", ""),
                "description": getattr(rel, "description", ""),
                "active": getattr(rel, "active", True),
            }
        )
    return pd.DataFrame(rows)


def _log_info(module: str, action: str, message: str, details=None) -> None:
    try:
        from logger import log_info

        log_info(module, action, message, details or "")
    except Exception:
        pass


def apply_pending_relationship_suggestions() -> None:
    pending_map = {
        "pending_manual_picklist_cardinality": "manual_picklist_cardinality",
        "pending_manual_picklist_join_type": "manual_picklist_join_type",
        "pending_manual_picklist_confidence": "manual_picklist_confidence",
    }

    for pending_key, widget_key in pending_map.items():
        if pending_key in st.session_state:
            st.session_state[widget_key] = st.session_state.pop(pending_key)


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


def render_relationship_suggestion_panel(suggestion: dict) -> None:
    st.markdown("#### Suggested relationship options")

    if suggestion.get("warning"):
        st.warning(suggestion["warning"])

    metric_col1, metric_col2, metric_col3 = st.columns(3)
    metric_col1.metric("Suggested cardinality", suggestion["cardinality"])
    metric_col2.metric("Suggested join", suggestion["join_type"])
    metric_col3.metric("Suggested confidence", f'{float(suggestion["confidence"]):.2f}')

    with st.expander("Why these options are suggested", expanded=False):
        st.write(suggestion["reason"])


def _apply_auto_suggestion_to_session(suggestion: dict) -> None:
    st.session_state["manual_picklist_join_type"] = suggestion["join_type"]
    st.session_state["manual_picklist_confidence"] = float(suggestion["confidence"])


def render_context_manual_relationship_picklist_form(state: ErdState) -> None:
    st.markdown("### Add relationship from active context")
    render_relationship_field_guide()
    apply_pending_relationship_suggestions()

    active_ctx = _get_active_context_safe(state)
    if not active_ctx:
        st.warning("Select or create a relationship context before adding relationships.")
        return

    scoped_tables = get_context_tables(state, active_ctx.id)
    if len(scoped_tables) < 2:
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
        source_columns = _get_table_columns_safe(state, source_full)
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
        target_columns = _get_table_columns_safe(state, target_full)
        target_col = st.selectbox(
            "Target column",
            target_columns,
            key="manual_picklist_target_column",
            help="The matching field in the target table. Often a primary key or unique ID.",
        )

    if not source_columns or not target_columns:
        st.warning("The selected tables must have columns before a relationship can be created.")
        return

    option_col1, option_col2 = st.columns(2)

    with option_col1:
        relationship_mode = st.selectbox(
            "Relationship mode",
            ["Standard relationship", "Conditional relationship"],
            key="manual_picklist_relationship_mode",
            help="Use Standard for direct joins. Use Conditional when an extra rule is required, such as src.Item_Type = 3.",
        )

    with option_col2:
        cardinality = st.selectbox(
            "Cardinality",
            ["many-to-one", "one-to-many", "one-to-one", "many-to-many"],
            key="manual_picklist_cardinality",
            help="Changing this field updates the suggested join/confidence. If auto-apply is enabled, those controls are updated automatically.",
        )

    suggestion = suggest_relationship_options(
        state,
        source_full,
        source_col,
        target_full,
        target_col,
        relationship_mode,
        selected_cardinality=cardinality,
    )

    auto_apply = st.checkbox(
        "Auto-apply suggested join and confidence",
        value=True,
        key="manual_picklist_auto_apply_suggestions",
        help="When enabled, the Join type and Confidence controls update from the selected cardinality and selected fields.",
    )

    if auto_apply:
        _apply_auto_suggestion_to_session(suggestion)

    join_col, confidence_col = st.columns(2)

    with join_col:
        join_type = st.selectbox(
            "Join type",
            ["LEFT JOIN", "INNER JOIN", "RIGHT JOIN", "FULL OUTER JOIN"],
            key="manual_picklist_join_type",
            help="LEFT JOIN keeps all source records. INNER JOIN only returns matching records.",
        )

    with confidence_col:
        if "manual_picklist_confidence" not in st.session_state:
            st.session_state["manual_picklist_confidence"] = float(suggestion["confidence"])

        confidence = st.slider(
            "Confidence",
            min_value=0.0,
            max_value=1.0,
            step=0.05,
            key="manual_picklist_confidence",
            help="Your confidence that this relationship is correct.",
        )

    render_relationship_suggestion_panel(suggestion)

    if not auto_apply:
        if st.button(
            "Apply suggested options",
            key="manual_picklist_apply_suggestion",
            help="Apply the suggested join type and confidence to the relationship form.",
        ):
            st.session_state["pending_manual_picklist_join_type"] = suggestion["join_type"]
            st.session_state["pending_manual_picklist_confidence"] = float(suggestion["confidence"])
            _log_info(
                "Relationships",
                "suggestion_applied",
                "Relationship suggestion applied",
                {
                    "source": f"{source_full}.{source_col}",
                    "target": f"{target_full}.{target_col}",
                    "suggestion": suggestion,
                },
            )
            st.success("Suggested options applied.")
            st.rerun()

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
        preview += f"\nCardinality: {cardinality}"
        preview += f"\nJoin type: {join_type}"
        if condition_sql.strip():
            preview += f"\nCondition: {condition_sql}"
        if extra_join_sql.strip():
            preview += f"\nExtra join: {extra_join_sql}"
        st.code(preview, language="text")

    if st.button("Add relationship from picklists", type="primary", key="manual_picklist_add_relationship"):
        if source_full == target_full and source_col == target_col:
            st.warning("Source and target are the same table/column. Confirm this is intentional before saving.")
            return

        source_schema, source_table = _split_full_table(source_full)
        target_schema, target_table = _split_full_table(target_full)
        relationship_type = "conditional" if condition_sql.strip() else "manual"

        rid = _relationship_id(
            source_schema,
            source_table,
            source_col,
            target_schema,
            target_table,
            target_col,
            relationship_type,
            condition_sql,
        )

        state.relationships[rid] = Relationship(
            id=rid,
            context_id=active_ctx.id,
            source_schema=source_schema,
            source_table=source_table,
            source_column=source_col,
            target_schema=target_schema,
            target_table=target_table,
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

        _log_info(
            "Relationships",
            "relationship_added",
            "Relationship added from picklist form",
            {
                "context": active_ctx.name,
                "source": f"{source_full}.{source_col}",
                "target": f"{target_full}.{target_col}",
                "relationship_type": relationship_type,
                "cardinality": cardinality,
                "join_type": join_type,
            },
        )

        st.success("Relationship added to the active context.")
        st.rerun()


def render_relationship_registry(state: ErdState) -> None:
    st.markdown("### Relationship registry")

    active_ctx = _get_active_context_safe(state)
    relationships = _relationships_for_active_context(state) if active_ctx else state.relationships

    if not relationships:
        st.info("No relationships have been created yet.")
        return

    df = _relationships_dataframe(relationships)
    st.dataframe(df, width="stretch", hide_index=True)

    with st.expander("Relationship validation", expanded=False):
        try:
            issues = validate_relationships(state)
            summary = relationship_quality_summary(state)
            if isinstance(summary, dict):
                cols = st.columns(min(4, max(1, len(summary))))
                for idx, (label, value) in enumerate(summary.items()):
                    cols[idx % len(cols)].metric(str(label), value)
            if issues:
                st.warning(f"{len(issues)} validation issue(s) found.")
                st.dataframe(pd.DataFrame(issues), width="stretch", hide_index=True)
            else:
                st.success("No validation issues found.")
        except Exception as exc:
            st.warning(f"Could not run relationship validation: {exc}")

    st.markdown("### Manage relationship")

    relationship_ids = sorted(relationships.keys())
    selected_id = st.selectbox(
        "Select relationship",
        relationship_ids,
        key="relationship_manage_selected_id",
        help="Select a relationship to review, activate/deactivate, or delete.",
    )

    rel = relationships[selected_id]
    source_full, target_full = _relationship_full_tables(rel)

    st.code(
        f"{source_full}.{rel.source_column} -> {target_full}.{rel.target_column}",
        language="text",
    )

    edit_col1, edit_col2, edit_col3 = st.columns(3)

    with edit_col1:
        new_active = st.checkbox(
            "Active",
            value=bool(getattr(rel, "active", True)),
            key=f"relationship_active_{selected_id}",
        )
    with edit_col2:
        new_confidence = st.slider(
            "Confidence",
            0.0,
            1.0,
            float(getattr(rel, "confidence", 1.0)),
            0.05,
            key=f"relationship_confidence_{selected_id}",
        )
    with edit_col3:
        join_options = ["LEFT JOIN", "INNER JOIN", "RIGHT JOIN", "FULL OUTER JOIN"]
        current_join = getattr(rel, "join_type", "LEFT JOIN")
        join_index = join_options.index(current_join) if current_join in join_options else 0
        new_join_type = st.selectbox(
            "Join type",
            join_options,
            index=join_index,
            key=f"relationship_join_type_{selected_id}",
        )

    new_description = st.text_area(
        "Description",
        value=getattr(rel, "description", ""),
        key=f"relationship_description_{selected_id}",
    )

    action_col1, action_col2 = st.columns(2)

    with action_col1:
        if st.button("Save relationship updates", key=f"save_relationship_{selected_id}"):
            rel.active = new_active
            rel.confidence = new_confidence
            rel.join_type = new_join_type
            rel.description = new_description
            state.relationships[selected_id] = rel
            save_state(state)
            st.success("Relationship updated.")
            st.rerun()

    with action_col2:
        if st.button("Delete relationship", type="secondary", key=f"delete_relationship_{selected_id}"):
            state.relationships.pop(selected_id, None)
            save_state(state)
            st.success("Relationship deleted.")
            st.rerun()


def render_relationships_tab(state: ErdState) -> None:
    st.info("Use this page to create, review, and maintain relationships for the active context.")

    render_context_manual_relationship_picklist_form(state)

    st.divider()

    render_relationship_registry(state)
