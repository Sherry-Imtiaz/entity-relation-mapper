
from __future__ import annotations
from typing import Dict, List, Tuple
import pandas as pd
import streamlit as st
from models import ErdState, Relationship
from relationship_duplicates import create_or_get_shared_context, duplicate_context_names, find_duplicate_relationships, relationship_id_for_context, relationship_signature_from_values
from relationship_guidance import suggest_relationship_options
from state_manager import save_state
from ui_shared import *
from validation import get_context_tables, get_relationships_for_context, relationship_quality_summary, validate_relationships

def _split_full_table(full_table: str) -> Tuple[str, str]:
    return tuple(full_table.split(".", 1)) if "." in full_table else ("", full_table)

def _full_table(schema_name: str, table_name: str) -> str:
    return f"{schema_name}.{table_name}" if schema_name else table_name

def _relationship_full_tables(rel: Relationship) -> Tuple[str, str]:
    return (getattr(rel, "source_full_table", None) or _full_table(rel.source_schema, rel.source_table), getattr(rel, "target_full_table", None) or _full_table(rel.target_schema, rel.target_table))

def _get_active_context_safe(state: ErdState):
    try:
        return get_active_context(state)
    except Exception:
        return state.relationship_contexts.get(getattr(state, "active_context_id", ""))

def _get_table_columns_safe(state: ErdState, full_table: str) -> List[str]:
    try:
        cols = get_table_columns(state, full_table)
        if cols:
            return cols
    except Exception:
        pass
    table = state.tables.get(full_table)
    return [c.column_name for c in sorted(table.columns, key=lambda c: c.ordinal_position)] if table else []

def _relationships_for_active_context(state: ErdState) -> Dict[str, Relationship]:
    active_ctx = _get_active_context_safe(state)
    if not active_ctx:
        return {}
    try:
        return get_relationships_for_context(state, active_ctx.id)
    except Exception:
        return {rid: rel for rid, rel in state.relationships.items() if getattr(rel, "context_id", "") == active_ctx.id}

def _relationships_dataframe(relationships: Dict[str, Relationship]) -> pd.DataFrame:
    rows = []
    for rel in relationships.values():
        source_full, target_full = _relationship_full_tables(rel)
        rows.append({"id": rel.id, "context_id": getattr(rel, "context_id", ""), "source": f"{source_full}.{rel.source_column}", "target": f"{target_full}.{rel.target_column}", "type": getattr(rel, "relationship_type", ""), "cardinality": getattr(rel, "cardinality", ""), "join_type": getattr(rel, "join_type", ""), "confidence": getattr(rel, "confidence", None), "condition_sql": getattr(rel, "condition_sql", ""), "description": getattr(rel, "description", ""), "active": getattr(rel, "active", True)})
    return pd.DataFrame(rows)

def _log_info(module: str, action: str, message: str, details=None) -> None:
    try:
        from logger import log_info
        log_info(module, action, message, details or "")
    except Exception:
        pass

def _apply_pending_suggestions() -> None:
    for pending_key, widget_key in {"pending_manual_picklist_join_type": "manual_picklist_join_type", "pending_manual_picklist_confidence": "manual_picklist_confidence"}.items():
        if pending_key in st.session_state:
            st.session_state[widget_key] = st.session_state.pop(pending_key)

def _render_field_guide() -> None:
    with st.expander("Relationship field guide", expanded=False):
        st.markdown("| Field | Meaning |\\n|---|---|\\n| Source / Target | Select the two table columns to connect. |\\n| Duplicate handling | Controls what happens when the same connection already exists in another context. |")

def _render_suggestion_panel(suggestion: dict) -> None:
    st.markdown("#### Suggested relationship options")
    if suggestion.get("warning"):
        st.warning(suggestion["warning"])
    c1, c2, c3 = st.columns(3)
    c1.metric("Suggested cardinality", suggestion["cardinality"])
    c2.metric("Suggested join", suggestion["join_type"])
    c3.metric("Suggested confidence", f'{float(suggestion["confidence"]):.2f}')
    with st.expander("Why these options are suggested", expanded=False):
        st.write(suggestion["reason"])

def render_context_manual_relationship_picklist_form(state: ErdState) -> None:
    st.markdown("### Add relationship from active context")
    _render_field_guide()
    _apply_pending_suggestions()
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
    schema_options = ["All schemas"] + sorted({scoped_tables[t].schema_name or "(no schema)" for t in table_options}, key=str.lower)
    col_source, col_target = st.columns(2)
    with col_source:
        st.markdown("**Source**")
        source_schema_filter = st.selectbox("Source schema filter", schema_options, key="manual_picklist_source_schema_filter")
        source_search = st.text_input("Search source table", placeholder="Type to filter source tables", key="manual_picklist_source_search")
        source_options = table_options
        if source_schema_filter != "All schemas":
            source_options = [t for t in source_options if (scoped_tables[t].schema_name or "(no schema)") == source_schema_filter]
        if source_search.strip():
            source_options = [t for t in source_options if source_search.strip().lower() in t.lower()]
        if not source_options:
            source_options = table_options
        source_full = st.selectbox("Source table", source_options, key="manual_picklist_source_table")
        source_columns = _get_table_columns_safe(state, source_full)
        source_col = st.selectbox("Source column", source_columns, key="manual_picklist_source_column")
    with col_target:
        st.markdown("**Target**")
        target_schema_filter = st.selectbox("Target schema filter", schema_options, key="manual_picklist_target_schema_filter")
        target_search = st.text_input("Search target table", placeholder="Type to filter target tables", key="manual_picklist_target_search")
        target_options = table_options
        if target_schema_filter != "All schemas":
            target_options = [t for t in target_options if (scoped_tables[t].schema_name or "(no schema)") == target_schema_filter]
        if target_search.strip():
            target_options = [t for t in target_options if target_search.strip().lower() in t.lower()]
        if not target_options:
            target_options = table_options
        target_full = st.selectbox("Target table", target_options, key="manual_picklist_target_table")
        target_columns = _get_table_columns_safe(state, target_full)
        target_col = st.selectbox("Target column", target_columns, key="manual_picklist_target_column")
    if not source_columns or not target_columns:
        st.warning("The selected tables must have columns before a relationship can be created.")
        return
    option_col1, option_col2 = st.columns(2)
    with option_col1:
        relationship_mode = st.selectbox("Relationship mode", ["Standard relationship", "Conditional relationship"], key="manual_picklist_relationship_mode")
    with option_col2:
        cardinality = st.selectbox("Cardinality", ["many-to-one", "one-to-many", "one-to-one", "many-to-many"], key="manual_picklist_cardinality")
    suggestion = suggest_relationship_options(state, source_full, source_col, target_full, target_col, relationship_mode, selected_cardinality=cardinality)
    auto_apply = st.checkbox("Auto-apply suggested join and confidence", value=True, key="manual_picklist_auto_apply_suggestions")
    if auto_apply:
        st.session_state["manual_picklist_join_type"] = suggestion["join_type"]
        st.session_state["manual_picklist_confidence"] = float(suggestion["confidence"])
    join_col, confidence_col = st.columns(2)
    with join_col:
        join_type = st.selectbox("Join type", ["LEFT JOIN", "INNER JOIN", "RIGHT JOIN", "FULL OUTER JOIN"], key="manual_picklist_join_type")
    with confidence_col:
        if "manual_picklist_confidence" not in st.session_state:
            st.session_state["manual_picklist_confidence"] = float(suggestion["confidence"])
        confidence = st.slider("Confidence", 0.0, 1.0, step=0.05, key="manual_picklist_confidence")
    _render_suggestion_panel(suggestion)
    if not auto_apply and st.button("Apply suggested options", key="manual_picklist_apply_suggestion"):
        st.session_state["pending_manual_picklist_join_type"] = suggestion["join_type"]
        st.session_state["pending_manual_picklist_confidence"] = float(suggestion["confidence"])
        st.success("Suggested options applied.")
        st.rerun()
    condition_sql = ""
    if relationship_mode == "Conditional relationship":
        condition_sql = st.text_input("Condition SQL", placeholder="Example: src.Item_Type = 3", key="manual_picklist_condition_sql")
    extra_join_sql = st.text_input("Extra Join SQL, optional", placeholder="Example: src.ValidTo IS NULL", key="manual_picklist_extra_join_sql")
    description = st.text_area("Description / business meaning", placeholder="Explain what this relationship means.", key="manual_picklist_description")
    source_schema, source_table = _split_full_table(source_full)
    target_schema, target_table = _split_full_table(target_full)
    relationship_type = "conditional" if condition_sql.strip() else "manual"
    signature = relationship_signature_from_values(source_schema, source_table, source_col, target_schema, target_table, target_col, relationship_type, condition_sql, extra_join_sql)
    duplicates = find_duplicate_relationships(state, signature)
    duplicate_action = "No duplicate"
    if duplicates:
        st.warning("This connection already exists in another relationship context: " + ", ".join(duplicate_context_names(state, duplicates)))
        duplicate_action = st.selectbox("Duplicate handling", ["Do not add duplicate", "Add to this context anyway", "Extract/use Shared Relationships context"], key="manual_picklist_duplicate_action")
    with st.expander("Relationship preview", expanded=False):
        preview = f"{source_full}.{source_col} -> {target_full}.{target_col}\\nContext: {active_ctx.name}\\nCardinality: {cardinality}\\nJoin type: {join_type}"
        if condition_sql.strip():
            preview += f"\\nCondition: {condition_sql}"
        if extra_join_sql.strip():
            preview += f"\\nExtra join: {extra_join_sql}"
        st.code(preview, language="text")
    if st.button("Add relationship from picklists", type="primary", key="manual_picklist_add_relationship"):
        if source_full == target_full and source_col == target_col:
            st.warning("Source and target are the same table/column. Confirm this is intentional before saving.")
            return
        target_context_id, target_context_name = active_ctx.id, active_ctx.name
        if duplicates and duplicate_action == "Do not add duplicate":
            st.warning("Relationship was not added because the same connection already exists in another context.")
            return
        if duplicates and duplicate_action == "Extract/use Shared Relationships context":
            table_keys = [key for key in [source_full, target_full] if key in state.tables]
            shared_ctx = create_or_get_shared_context(state, table_keys=table_keys)
            target_context_id, target_context_name = shared_ctx.id, shared_ctx.name
        rid = relationship_id_for_context(target_context_id, source_schema, source_table, source_col, target_schema, target_table, target_col, relationship_type, condition_sql, extra_join_sql)
        if rid in state.relationships:
            st.warning("This exact relationship already exists in the selected target context.")
            return
        state.relationships[rid] = Relationship(id=rid, context_id=target_context_id, source_schema=source_schema, source_table=source_table, source_column=source_col, target_schema=target_schema, target_table=target_table, target_column=target_col, relationship_type=relationship_type, cardinality=cardinality, join_type=join_type, confidence=confidence, condition_sql=condition_sql, extra_join_sql=extra_join_sql, description=description)
        save_state(state)
        _log_info("Relationships", "relationship_added", "Relationship added from picklist form", {"context": target_context_name, "duplicate_action": duplicate_action})
        st.success(f"Relationship added to {target_context_name}.")
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

            if isinstance(issues, pd.DataFrame):
                if len(issues) > 0:
                    st.warning(f"{len(issues)} validation issue(s) found.")
                    st.dataframe(issues, width="stretch", hide_index=True)
                else:
                    st.success("No validation issues found.")
            elif issues:
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
        help="Select a relationship to review, edit, or delete.",
    )

    rel = relationships[selected_id]
    source_full, target_full = _relationship_full_tables(rel)

    st.code(
        f"{source_full}.{rel.source_column} -> {target_full}.{rel.target_column}",
        language="text",
    )

    source_schema = getattr(rel, "source_schema", "")
    source_table = getattr(rel, "source_table", "")
    target_schema = getattr(rel, "target_schema", "")
    target_table = getattr(rel, "target_table", "")

    current_type = (getattr(rel, "relationship_type", "") or "manual").lower()
    current_mode = "Conditional relationship" if current_type == "conditional" or (getattr(rel, "condition_sql", "") or "").strip() else "Standard relationship"

    mode_col, cardinality_col = st.columns(2)

    with mode_col:
        new_mode = st.selectbox(
            "Relationship mode",
            ["Standard relationship", "Conditional relationship"],
            index=1 if current_mode == "Conditional relationship" else 0,
            key=f"manage_relationship_mode_{selected_id}",
            help="Use Conditional relationship when this link requires an extra SQL condition such as Item_Type = 1039.",
        )

    with cardinality_col:
        cardinality_options = ["many-to-one", "one-to-many", "one-to-one", "many-to-many"]
        current_cardinality = getattr(rel, "cardinality", "many-to-one")
        cardinality_index = cardinality_options.index(current_cardinality) if current_cardinality in cardinality_options else 0
        new_cardinality = st.selectbox(
            "Cardinality",
            cardinality_options,
            index=cardinality_index,
            key=f"manage_relationship_cardinality_{selected_id}",
            help="Describes how records relate between source and target tables.",
        )

    settings_col1, settings_col2, settings_col3 = st.columns(3)

    with settings_col1:
        new_active = st.checkbox(
            "Active",
            value=bool(getattr(rel, "active", True)),
            key=f"relationship_active_{selected_id}",
            help="Inactive relationships are excluded from active-only exports and ERD views.",
        )

    with settings_col2:
        join_options = ["LEFT JOIN", "INNER JOIN", "RIGHT JOIN", "FULL OUTER JOIN"]
        current_join = getattr(rel, "join_type", "LEFT JOIN")
        join_index = join_options.index(current_join) if current_join in join_options else 0
        new_join_type = st.selectbox(
            "Join type",
            join_options,
            index=join_index,
            key=f"relationship_join_type_{selected_id}",
            help="LEFT JOIN keeps all source records. INNER JOIN keeps matched records only.",
        )

    with settings_col3:
        new_confidence = st.slider(
            "Confidence",
            min_value=0.0,
            max_value=1.0,
            value=float(getattr(rel, "confidence", 1.0)),
            step=0.05,
            key=f"relationship_confidence_{selected_id}",
            help="Your confidence that this relationship is correct.",
        )

    if new_mode == "Conditional relationship":
        new_condition_sql = st.text_input(
            "Condition SQL",
            value=getattr(rel, "condition_sql", "") or "",
            key=f"relationship_condition_sql_{selected_id}",
            placeholder="Example: PropertyWise.Associations_Role_Based.Item_Type = 1039",
            help="Condition required for this relationship to be valid.",
        )
    else:
        new_condition_sql = ""
        if (getattr(rel, "condition_sql", "") or "").strip():
            st.info("Changing this relationship to Standard will clear the existing Condition SQL when saved.")

    new_extra_join_sql = st.text_input(
        "Extra Join SQL, optional",
        value=getattr(rel, "extra_join_sql", "") or "",
        key=f"relationship_extra_join_sql_{selected_id}",
        placeholder="Example: src.ValidTo IS NULL",
        help="Optional extra filter for the join, such as current/active records only.",
    )

    new_description = st.text_area(
        "Description / business meaning",
        value=getattr(rel, "description", "") or "",
        key=f"relationship_description_{selected_id}",
        help="Business meaning of this relationship.",
    )

    new_relationship_type = "conditional" if new_mode == "Conditional relationship" else "manual"

    try:
        from relationship_duplicates import (
            duplicate_context_names,
            find_duplicate_relationships,
            relationship_id_for_context,
            relationship_signature_from_values,
        )

        new_signature = relationship_signature_from_values(
            source_schema,
            source_table,
            getattr(rel, "source_column", ""),
            target_schema,
            target_table,
            getattr(rel, "target_column", ""),
            new_relationship_type,
            new_condition_sql,
            new_extra_join_sql,
        )
        duplicate_matches = find_duplicate_relationships(
            state,
            new_signature,
            exclude_relationship_id=selected_id,
        )
    except Exception:
        duplicate_matches = []

    duplicate_update_action = "Save update"

    if duplicate_matches:
        duplicate_contexts = duplicate_context_names(state, duplicate_matches)
        st.warning(
            "This updated relationship matches an existing connection in: "
            + ", ".join(duplicate_contexts)
        )
        duplicate_update_action = st.selectbox(
            "Duplicate update handling",
            ["Cancel update", "Save anyway"],
            key=f"relationship_duplicate_update_action_{selected_id}",
            help="Choose whether to cancel the update or save even though it duplicates another connection.",
        )

    with st.expander("Updated relationship preview", expanded=False):
        preview = f"{source_full}.{rel.source_column} -> {target_full}.{rel.target_column}"
        preview += f"
Mode: {new_mode}"
        preview += f"
Cardinality: {new_cardinality}"
        preview += f"
Join type: {new_join_type}"
        preview += f"
Active: {new_active}"
        if new_condition_sql.strip():
            preview += f"
Condition: {new_condition_sql}"
        if new_extra_join_sql.strip():
            preview += f"
Extra join: {new_extra_join_sql}"
        st.code(preview, language="text")

    action_col1, action_col2 = st.columns(2)

    with action_col1:
        if st.button("Save relationship updates", type="primary", key=f"save_relationship_{selected_id}"):
            if duplicate_matches and duplicate_update_action == "Cancel update":
                st.warning("Update cancelled because the edited relationship duplicates another connection.")
                return

            if new_relationship_type == "conditional" and not new_condition_sql.strip():
                st.warning("Conditional relationships require Condition SQL before saving.")
                return

            try:
                from relationship_duplicates import relationship_id_for_context

                new_id = relationship_id_for_context(
                    getattr(rel, "context_id", ""),
                    source_schema,
                    source_table,
                    getattr(rel, "source_column", ""),
                    target_schema,
                    target_table,
                    getattr(rel, "target_column", ""),
                    new_relationship_type,
                    new_condition_sql,
                    new_extra_join_sql,
                )
            except Exception:
                new_id = selected_id

            if new_id != selected_id and new_id in state.relationships:
                st.warning("A relationship with the updated ID already exists. Review duplicate handling before saving.")
                return

            rel.id = new_id
            rel.relationship_type = new_relationship_type
            rel.cardinality = new_cardinality
            rel.join_type = new_join_type
            rel.confidence = new_confidence
            rel.active = new_active
            rel.condition_sql = new_condition_sql
            rel.extra_join_sql = new_extra_join_sql
            rel.description = new_description

            if new_id != selected_id:
                state.relationships.pop(selected_id, None)

            state.relationships[new_id] = rel
            save_state(state)

            _log_info(
                "Relationships",
                "relationship_updated",
                "Relationship updated from manage relationship form",
                {
                    "old_id": selected_id,
                    "new_id": new_id,
                    "relationship_type": new_relationship_type,
                    "condition_changed": new_id != selected_id,
                },
            )

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
