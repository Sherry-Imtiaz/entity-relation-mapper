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
                    "Streamlit Flow visualisation is not available because streamlit-flow-component is not installed. "
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

            with st.expander("Graphviz ERD fallback"):
                dot = export_dot(display_state, only_active=only_active)
                st.graphviz_chart(dot, width="stretch")
                st.download_button(
                    "Download Graphviz DOT",
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
