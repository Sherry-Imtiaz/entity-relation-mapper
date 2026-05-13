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


def render_erd_tab(state: ErdState) -> None:
        st.subheader("ERD View")
        only_active = st.checkbox("Only active relationships", value=True, key="erd_only_active")
        active_ctx = get_active_context(state)
        erd_scope_options = ["Whole database", "Active relationship context"]
        erd_scope = st.radio("ERD scope", erd_scope_options, index=1 if active_ctx else 0, horizontal=True)

        if not state.tables:
            st.info("Load tables first.")
        else:
            display_state = state
            if erd_scope == "Active relationship context":
                if active_ctx:
                    display_state = build_context_scoped_state(state, active_ctx.id)
                    st.info(f"Showing ERD for context: {active_ctx.name}")
                else:
                    st.warning("No active context selected. Showing whole database instead.")

            if streamlit_flow is None:
                st.error(
                    "ERD visualisation is not available because streamlit-flow-component is not installed. "
                    "Install it with: pip install streamlit-flow-component"
                )
            else:
                flow_key = f"erd_flow_state_{erd_scope}_{state.active_context_id or 'all'}"
                col_reset, col_help = st.columns([1, 3])
                with col_reset:
                    reset_erd_flow = st.button("Reset ERD layout", key="reset_erd_flow")
                with col_help:
                    st.caption("Drag tables to rearrange. Use the built-in controls to zoom, fit, and navigate the ERD.")

                if reset_erd_flow or flow_key not in st.session_state:
                    st.session_state[flow_key] = build_streamlit_flow_state_from_erd_state(display_state)

                if st.session_state.get(flow_key) is None:
                    st.warning("Could not build Streamlit Flow ERD state.")
                else:
                    st.session_state[flow_key] = streamlit_flow(
                        f"erd_streamlit_flow_{erd_scope}_{state.active_context_id or 'all'}",
                        st.session_state[flow_key],
                        height=750,
                        fit_view=True,
                        show_controls=True,
                        show_minimap=True,
                    )

            with st.expander("ERD diagram"):
                dot = export_dot(display_state, only_active=only_active)
                st.graphviz_chart(dot, width="stretch")
                st.download_button(
                    "Download ERD source",
                    data=dot,
                    file_name="erd_graphviz.dot",
                    mime="text/plain",
                )

            with st.expander("Mermaid ERD text"):
                mermaid = export_mermaid(display_state, only_active=only_active)
                st.code(mermaid, language="mermaid")
                st.download_button(
                    "Download Mermaid ERD",
                    data=mermaid,
                    file_name="erd_mermaid.mmd",
                    mime="text/plain",
                )

    # ---------------------------------------------------------------------
    # Export tab
    # ---------------------------------------------------------------------


# -----------------------------------------------------------------------------
# v2.1.7 ERD visual simplification override
# -----------------------------------------------------------------------------

def render_erd_tab(state: ErdState) -> None:
    st.subheader("ERD View")

    only_active = st.checkbox("Only active relationships", value=True, key="erd_only_active")
    active_ctx = get_active_context(state)

    erd_scope_options = ["Whole database", "Active relationship context"]
    erd_scope = st.radio(
        "ERD scope",
        erd_scope_options,
        index=1 if active_ctx else 0,
        horizontal=True,
    )

    if not state.tables:
        st.info("Load tables first.")
        return

    display_state = state
    if erd_scope == "Active relationship context":
        if active_ctx:
            display_state = build_context_scoped_state(state, active_ctx.id)
            st.info(f"Showing ERD for context: {active_ctx.name}")
        else:
            st.warning("No active context selected. Showing whole database instead.")

    st.caption(
        "ERD diagram view. Each table shows a compact schema preview with a maximum of 10 prioritised fields."
    )

    dot = export_dot(display_state, only_active=only_active)
    st.graphviz_chart(dot, width="stretch")

    with st.expander("ERD source and download"):
        st.code(dot, language="dot")
        st.download_button(
            "Download ERD source",
            data=dot,
            file_name="erd_graphviz.dot",
            mime="text/plain",
        )

    with st.expander("Mermaid export text"):
        mermaid = export_mermaid(display_state, only_active=only_active)
        st.code(mermaid, language="mermaid")
        st.download_button(
            "Download Mermaid ERD",
            data=mermaid,
            file_name="erd_mermaid.mmd",
            mime="text/plain",
        )


# -----------------------------------------------------------------------------
# v2.2.11 Relationship selection ERD override
# -----------------------------------------------------------------------------


def _v2211_get_active_context_for_erd(state):
    active_id = getattr(state, "active_context_id", "")
    if active_id and active_id in getattr(state, "relationship_contexts", {}):
        return state.relationship_contexts[active_id]
    return None


def _v2211_build_context_state_for_erd(state, context_id):
    try:
        return build_context_scoped_state(state, context_id)
    except Exception:
        import copy

        scoped = copy.deepcopy(state)
        scoped.relationships = {
            rid: rel
            for rid, rel in getattr(state, "relationships", {}).items()
            if getattr(rel, "context_id", "") == context_id
        }
        return scoped


def render_erd_tab(state: ErdState) -> None:
    st.subheader("ERD View")

    active_ctx = _v2211_get_active_context_for_erd(state)

    erd_scope_options = ["Whole database"]
    if active_ctx:
        erd_scope_options.append("Active relationship context")

    erd_scope = st.radio(
        "ERD scope",
        erd_scope_options,
        index=1 if active_ctx else 0,
        horizontal=True,
        key="erd_v2211_scope",
    )

    if not state.tables:
        st.info("Load tables first.")
        return

    context_id = active_ctx.id if erd_scope == "Active relationship context" and active_ctx else None
    scope_name = active_ctx.name if context_id else "Whole database"

    st.info(f"Showing ERD scope: {scope_name}")

    selected_relationship_ids, _available_rels = selected_relationships_multiselect(
        state,
        context_id=context_id,
        key_prefix="erd_relationships_v2211",
        active_only_default=True,
    )

    show_connected_only = st.checkbox(
        "Show only tables connected to selected relationships",
        value=True,
        key="erd_v2211_connected_tables_only",
        help="When enabled, the ERD only shows tables used by the selected relationships.",
    )

    base_state = _v2211_build_context_state_for_erd(state, context_id) if context_id else state
    display_state = build_selected_relationship_state(
        base_state,
        selected_relationship_ids,
        include_connected_tables_only=show_connected_only,
    )

    st.caption(
        "ERD diagram view. Use relationship selection to focus the diagram on specific links."
    )

    dot = export_dot(display_state, only_active=True)
    st.graphviz_chart(dot, width="stretch")

    with st.expander("ERD source and download"):
        st.code(dot, language="dot")
        st.download_button(
            "Download ERD source",
            data=dot,
            file_name="erd_graphviz.dot",
            mime="text/plain",
        )

    with st.expander("Mermaid export text"):
        mermaid = export_mermaid(display_state, only_active=True)
        st.code(mermaid, language="mermaid")
        st.download_button(
            "Download Mermaid ERD",
            data=mermaid,
            file_name="erd_mermaid.mmd",
            mime="text/plain",
        )


# -----------------------------------------------------------------------------
# v2.2.12 Context-based ERD override
# -----------------------------------------------------------------------------


def _v2212_erd_full_table(schema_name, table_name):
    schema = (schema_name or "").strip()
    table = (table_name or "").strip()
    return f"{schema}.{table}" if schema else table


def _v2212_erd_relationship_tables(rel):
    source_full = getattr(rel, "source_full_table", None) or _v2212_erd_full_table(
        getattr(rel, "source_schema", ""),
        getattr(rel, "source_table", ""),
    )
    target_full = getattr(rel, "target_full_table", None) or _v2212_erd_full_table(
        getattr(rel, "target_schema", ""),
        getattr(rel, "target_table", ""),
    )
    return source_full, target_full


def _v2212_erd_context_options(state):
    options = {"Whole database": None}
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


def _v2212_erd_relationships_for_context(state, context_id=None, active_only=True):
    rels = {}
    for rel_id, rel in getattr(state, "relationships", {}).items():
        if context_id and getattr(rel, "context_id", "") != context_id:
            continue
        if active_only and not bool(getattr(rel, "active", True)):
            continue
        rels[rel_id] = rel
    return rels


def _v2212_erd_build_scoped_state(state, context_id=None, active_only=True, connected_only=True):
    import copy

    scoped = copy.deepcopy(state)
    rels = _v2212_erd_relationships_for_context(state, context_id=context_id, active_only=active_only)
    scoped.relationships = rels

    if connected_only:
        connected = set()
        for rel in rels.values():
            source_full, target_full = _v2212_erd_relationship_tables(rel)
            connected.add(source_full)
            connected.add(target_full)
        scoped.tables = {
            key: table for key, table in getattr(state, "tables", {}).items() if key in connected
        }
    elif context_id:
        # If context tables are not explicitly assigned, still infer from relationships.
        connected = set()
        for rel in rels.values():
            source_full, target_full = _v2212_erd_relationship_tables(rel)
            connected.add(source_full)
            connected.add(target_full)
        scoped.tables = {
            key: table for key, table in getattr(state, "tables", {}).items() if key in connected
        }

    return scoped


def render_erd_tab(state) -> None:
    st.subheader("ERD View")

    if not getattr(state, "tables", {}):
        st.info("Load tables first.")
        return

    context_options = _v2212_erd_context_options(state)
    selected_label = st.selectbox(
        "Relationship Context",
        list(context_options.keys()),
        key="erd_v2212_context",
        help="Choose the relationship context to show in the ERD.",
    )
    context_id = context_options[selected_label]

    only_active = st.checkbox(
        "Only include active relationships",
        value=True,
        key="erd_v2212_only_active",
    )

    connected_only = st.checkbox(
        "Show only tables connected to the selected context relationships",
        value=True,
        key="erd_v2212_connected_only",
    )

    display_state = _v2212_erd_build_scoped_state(
        state,
        context_id=context_id,
        active_only=only_active,
        connected_only=connected_only,
    )

    st.info(f"Current ERD context: {selected_label}")
    st.caption(
        f"Tables shown: {len(getattr(display_state, 'tables', {}))} | "
        f"Relationships shown: {len(getattr(display_state, 'relationships', {}))}"
    )

    dot = export_dot(display_state, only_active=False)
    st.graphviz_chart(dot, width="stretch")

    with st.expander("ERD source and download"):
        st.code(dot, language="dot")
        st.download_button(
            "Download ERD source",
            data=dot,
            file_name="erd_graphviz.dot",
            mime="text/plain",
        )

    with st.expander("Mermaid export text"):
        mermaid = export_mermaid(display_state, only_active=False)
        st.code(mermaid, language="mermaid")
        st.download_button(
            "Download Mermaid ERD",
            data=mermaid,
            file_name="erd_mermaid.mmd",
            mime="text/plain",
        )
