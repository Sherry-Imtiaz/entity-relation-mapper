
from __future__ import annotations

from typing import Dict, Optional

import streamlit as st

from exports import export_dot, export_mermaid
from models import ErdState
from quality_checks import build_scoped_state_from_context


def _context_options(state: ErdState) -> Dict[str, Optional[str]]:
    options: Dict[str, Optional[str]] = {"Whole database": None}
    for context_id, context in sorted(getattr(state, "relationship_contexts", {}).items(), key=lambda item: getattr(item[1], "name", item[0]).lower()):
        name = getattr(context, "name", context_id)
        context_type = getattr(context, "context_type", "")
        label = f"{name} ({context_type})" if context_type else name
        if label in options:
            label = f"{label} [{context_id}]"
        options[label] = context_id
    return options


def render_erd_tab(state: ErdState) -> None:
    st.subheader("ERD View")
    if not getattr(state, "tables", {}):
        st.info("Load tables first.")
        return
    context_options = _context_options(state)
    selected_label = st.selectbox("Relationship Context", list(context_options.keys()), key="erd_context_select_v2213", help="Choose the relationship context to show in the ERD.")
    context_id = context_options[selected_label]
    only_active = st.checkbox("Only include active relationships", value=True, key="erd_only_active_v2213")
    connected_only = st.checkbox("Show only tables connected to the selected context relationships", value=True, key="erd_connected_only_v2213")
    display_state = build_scoped_state_from_context(state, context_id=context_id, active_only=only_active, connected_only=connected_only)
    st.info(f"Current ERD context: {selected_label}")
    st.caption(f"Tables shown: {len(getattr(display_state, 'tables', {}))} | Relationships shown: {len(getattr(display_state, 'relationships', {}))}")
    if not getattr(display_state, "tables", {}):
        st.warning("No tables are available for this ERD scope. Check the selected context or table import.")
        return
    dot = export_dot(display_state, only_active=False)
    st.graphviz_chart(dot, width="stretch")
    with st.expander("ERD source and download"):
        st.code(dot, language="dot")
        st.download_button("Download ERD source", data=dot, file_name="erd_graphviz.dot", mime="text/plain")
    with st.expander("Mermaid export text"):
        mermaid = export_mermaid(display_state, only_active=False)
        st.code(mermaid, language="mermaid")
        st.download_button("Download Mermaid ERD", data=mermaid, file_name="erd_mermaid.mmd", mime="text/plain")
