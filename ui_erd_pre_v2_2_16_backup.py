
from __future__ import annotations

from typing import Dict, Optional

import streamlit as st

from erd_rendering import render_graphviz_bytes
from exports import export_dot, export_mermaid
from models import ErdState
from quality_checks import build_scoped_state_from_context


def _context_options(state: ErdState) -> Dict[str, Optional[str]]:
    options: Dict[str, Optional[str]] = {"Whole database": None}

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


def _maybe_deduplicate_whole_database(state: ErdState, context_id: Optional[str], active_only: bool) -> ErdState:
    if context_id is not None:
        return state

    try:
        import copy
        from relationship_duplicates import deduplicated_relationships_for_whole_database

        scoped = copy.deepcopy(state)
        scoped.relationships = deduplicated_relationships_for_whole_database(state, active_only=active_only)
        return scoped
    except Exception:
        return state


def render_erd_tab(state: ErdState) -> None:
    st.subheader("ERD View")

    if not getattr(state, "tables", {}):
        st.info("Load tables first.")
        return

    context_options = _context_options(state)
    selected_label = st.selectbox(
        "Relationship Context",
        list(context_options.keys()),
        key="erd_context_select_v2215",
        help="Choose the relationship context to show in the ERD.",
    )
    context_id = context_options[selected_label]

    only_active = st.checkbox(
        "Only include active relationships",
        value=True,
        key="erd_only_active_v2215",
    )

    connected_only = st.checkbox(
        "Show only tables connected to the selected context relationships",
        value=True,
        key="erd_connected_only_v2215",
    )

    display_state = build_scoped_state_from_context(
        state,
        context_id=context_id,
        active_only=only_active,
        connected_only=connected_only,
    )
    display_state = _maybe_deduplicate_whole_database(display_state, context_id, only_active)

    st.info(f"Current ERD context: {selected_label}")
    st.caption(
        f"Tables shown: {len(getattr(display_state, 'tables', {}))} | "
        f"Relationships shown: {len(getattr(display_state, 'relationships', {}))}"
    )

    if not getattr(display_state, "tables", {}):
        st.warning("No tables are available for this ERD scope. Check the selected context or table import.")
        return

    dot = export_dot(display_state, only_active=False)
    mermaid = export_mermaid(display_state, only_active=False)

    st.graphviz_chart(dot, width="stretch")

    st.markdown("### Downloads")

    dot_col, svg_col, png_col, mermaid_col = st.columns(4)

    with dot_col:
        st.download_button(
            "Download DOT",
            data=dot,
            file_name="erd_graphviz.dot",
            mime="text/plain",
        )

    svg_bytes, svg_error = render_graphviz_bytes(dot, "svg")
    with svg_col:
        if svg_bytes:
            st.download_button(
                "Download SVG",
                data=svg_bytes,
                file_name="erd_graphviz.svg",
                mime="image/svg+xml",
            )
        else:
            st.button("Download SVG", disabled=True, help=svg_error or "SVG rendering unavailable.")

    png_bytes, png_error = render_graphviz_bytes(dot, "png")
    with png_col:
        if png_bytes:
            st.download_button(
                "Download PNG",
                data=png_bytes,
                file_name="erd_graphviz.png",
                mime="image/png",
            )
        else:
            st.button("Download PNG", disabled=True, help=png_error or "PNG rendering unavailable.")

    with mermaid_col:
        st.download_button(
            "Download Mermaid",
            data=mermaid,
            file_name="erd_mermaid.mmd",
            mime="text/plain",
        )

    if svg_error or png_error:
        with st.expander("Graphviz image rendering help", expanded=False):
            st.write(
                "DOT and Mermaid downloads are always available. SVG/PNG downloads require the "
                "Graphviz renderer to be installed on the machine running Streamlit."
            )
            if svg_error:
                st.caption(f"SVG: {svg_error}")
            if png_error and png_error != svg_error:
                st.caption(f"PNG: {png_error}")

    with st.expander("ERD source"):
        st.code(dot, language="dot")

    with st.expander("Mermaid export text"):
        st.code(mermaid, language="mermaid")
