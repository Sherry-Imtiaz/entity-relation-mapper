
from __future__ import annotations

import copy
from typing import Dict, List, Optional

import streamlit as st
import streamlit.components.v1 as components

from erd_rendering import build_interactive_svg_viewer, render_graphviz_bytes
from exports import export_dot, export_mermaid
from models import ErdState


def _multi_context_options(state: ErdState) -> Dict[str, str]:
    options: Dict[str, str] = {}
    for context_id, context in sorted(getattr(state, "relationship_contexts", {}).items(), key=lambda item: getattr(item[1], "name", item[0]).lower()):
        name = getattr(context, "name", context_id)
        context_type = getattr(context, "context_type", "")
        label = f"{name} ({context_type})" if context_type else name
        if label in options:
            label = f"{label} [{context_id}]"
        options[label] = context_id
    return options


def _full_table(schema_name: str, table_name: str) -> str:
    schema = (schema_name or "").strip()
    table = (table_name or "").strip()
    return f"{schema}.{table}" if schema else table


def _relationship_tables(rel) -> tuple[str, str]:
    source_full = getattr(rel, "source_full_table", None) or _full_table(getattr(rel, "source_schema", ""), getattr(rel, "source_table", ""))
    target_full = getattr(rel, "target_full_table", None) or _full_table(getattr(rel, "target_schema", ""), getattr(rel, "target_table", ""))
    return source_full, target_full


def _relationships_for_contexts(state: ErdState, context_ids: Optional[List[str]], active_only: bool) -> dict:
    rels = {}
    for rel_id, rel in getattr(state, "relationships", {}).items():
        if context_ids is not None and getattr(rel, "context_id", "") not in context_ids:
            continue
        if active_only and not bool(getattr(rel, "active", True)):
            continue
        rels[rel_id] = rel
    return rels


def _build_scoped_state(state: ErdState, context_ids: Optional[List[str]], active_only: bool, connected_only: bool) -> ErdState:
    scoped = copy.deepcopy(state)
    scoped.relationships = _relationships_for_contexts(state, context_ids, active_only=active_only)
    if connected_only:
        connected = set()
        for rel in scoped.relationships.values():
            source_full, target_full = _relationship_tables(rel)
            connected.add(source_full)
            connected.add(target_full)
        scoped.tables = {
            table_key: table
            for table_key, table in getattr(state, "tables", {}).items()
            if table_key in connected
            or getattr(table, "full_name", "") in connected
            or _full_table(getattr(table, "schema_name", ""), getattr(table, "table_name", "")) in connected
        }
    return scoped


def _dedupe_whole_database_if_available(display_state: ErdState, is_whole_database: bool, active_only: bool) -> ErdState:
    if not is_whole_database:
        return display_state
    try:
        from relationship_duplicates import deduplicated_relationships_for_whole_database
        scoped = copy.deepcopy(display_state)
        scoped.relationships = deduplicated_relationships_for_whole_database(display_state, active_only=active_only)
        return scoped
    except Exception:
        return display_state


def _selected_context_ids_from_ui(state: ErdState) -> tuple[Optional[List[str]], str, bool]:
    mode = st.radio(
        "ERD context selection mode",
        ["Whole database", "Selected relationship contexts"],
        horizontal=True,
        key="erd_context_mode_v2219",
    )
    if mode == "Whole database":
        return None, "Whole database", True
    context_options = _multi_context_options(state)
    if not context_options:
        st.warning("No relationship contexts are available.")
        return [], "No contexts selected", False
    selected_labels = st.multiselect(
        "Relationship contexts to include",
        list(context_options.keys()),
        default=list(context_options.keys())[:1],
        key="erd_context_multiselect_v2219",
        help="Select one or more relationship contexts to show in the ERD.",
    )
    context_ids = [context_options[label] for label in selected_labels if label in context_options]
    label = ", ".join(selected_labels) if selected_labels else "No contexts selected"
    return context_ids, label, False


def render_erd_tab(state: ErdState) -> None:
    st.subheader("ERD View")
    if not getattr(state, "tables", {}):
        st.info("Load tables first.")
        return

    context_ids, selected_label, is_whole_database = _selected_context_ids_from_ui(state)
    only_active = st.checkbox("Only include active relationships", value=True, key="erd_only_active_v2219")
    connected_only = st.checkbox("Show only tables connected to selected relationship contexts", value=True, key="erd_connected_only_v2219")
    display_mode = st.radio(
        "ERD display mode",
        ["Interactive viewer", "Static Streamlit Graphviz"],
        index=0,
        horizontal=True,
        key="erd_display_mode_v2219",
        help="Interactive viewer supports zoom, mouse-wheel zoom, pan, reset, and fit.",
    )

    display_state = _build_scoped_state(state, context_ids=context_ids, active_only=only_active, connected_only=connected_only)
    display_state = _dedupe_whole_database_if_available(display_state, is_whole_database, only_active)

    st.info(f"Current ERD scope: {selected_label}")
    st.caption(f"Tables shown: {len(getattr(display_state, 'tables', {}))} | Relationships shown: {len(getattr(display_state, 'relationships', {}))}")
    if not getattr(display_state, "tables", {}):
        st.warning("No tables are available for this ERD scope. Check the selected contexts or table import.")
        return

    dot = export_dot(display_state, only_active=False)
    mermaid = export_mermaid(display_state, only_active=False)
    svg_bytes, svg_error = render_graphviz_bytes(dot, "svg")

    if display_mode == "Interactive viewer" and svg_bytes:
        viewer_height = st.slider("Interactive viewer height", min_value=400, max_value=1200, value=760, step=40, key="erd_interactive_height_v2219")
        components.html(build_interactive_svg_viewer(svg_bytes, height=viewer_height), height=viewer_height, scrolling=False)
    elif display_mode == "Interactive viewer" and not svg_bytes:
        st.warning(svg_error or "Interactive SVG rendering is unavailable. Showing static Graphviz chart instead.")
        st.graphviz_chart(dot, width="stretch")
    else:
        st.graphviz_chart(dot, width="stretch")

    st.markdown("### Downloads")
    dot_col, svg_col, png_col, mermaid_col = st.columns(4)
    with dot_col:
        st.download_button("Download DOT", data=dot, file_name="erd_graphviz.dot", mime="text/plain")
    with svg_col:
        if svg_bytes:
            st.download_button("Download SVG", data=svg_bytes, file_name="erd_graphviz.svg", mime="image/svg+xml")
        else:
            st.button("Download SVG", disabled=True, help=svg_error or "SVG rendering unavailable.")
    png_bytes, png_error = render_graphviz_bytes(dot, "png")
    with png_col:
        if png_bytes:
            st.download_button("Download PNG", data=png_bytes, file_name="erd_graphviz.png", mime="image/png")
        else:
            st.button("Download PNG", disabled=True, help=png_error or "PNG rendering unavailable.")
    with mermaid_col:
        st.download_button("Download Mermaid", data=mermaid, file_name="erd_mermaid.mmd", mime="text/plain")

    if svg_error or png_error:
        with st.expander("Graphviz image rendering help", expanded=False):
            st.write("DOT and Mermaid downloads are always available. Interactive/SVG/PNG rendering requires the Graphviz renderer to be installed on the machine running Streamlit.")
            if svg_error:
                st.caption(f"SVG/Interactive: {svg_error}")
            if png_error and png_error != svg_error:
                st.caption(f"PNG: {png_error}")
    with st.expander("ERD source"):
        st.code(dot, language="dot")
    with st.expander("Mermaid export text"):
        st.code(mermaid, language="mermaid")
