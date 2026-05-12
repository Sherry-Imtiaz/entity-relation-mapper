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


def render_inference_tab(state: ErdState) -> None:
        st.subheader("Infer likely relationships")
        active_ctx = get_active_context(state)
        scoped_tables = get_context_tables(state, active_ctx.id) if active_ctx else {}
        if active_ctx:
            st.info(f"Inference scope: {active_ctx.name} — {len(scoped_tables)} assigned tables")
        else:
            st.warning("Create or select a relationship context before running scoped inference.")
        st.write(
            "This scans column names such as `Associate_Id`, `Property_Id`, `Item_Id`, `Customer_Id`, "
            "and tries to match them against likely ID columns in other tables. Review before accepting."
        )
        min_conf = st.slider("Minimum confidence", 0.40, 0.95, 0.65, 0.05)
        if st.button("Run inference"):
            if not active_ctx or not scoped_tables:
                relationship_context_warning(state)
            else:
                with st.spinner("Inferring likely relationships inside the active context..."):
                    inferred = infer_relationships(scoped_tables, min_confidence=min_conf)
                    for rel in inferred.values():
                        rel.context_id = active_ctx.id
                st.session_state.inferred_relationships = inferred
                st.success(f"Found {len(inferred)} possible relationships inside {active_ctx.name}.")

        inferred_relationships: Dict[str, Relationship] = st.session_state.get("inferred_relationships", {})
        if inferred_relationships:
            flat_rows = []
            for r in inferred_relationships.values():
                flat_rows.append({
                    "accept": False,
                    "confidence": r.confidence,
                    "source_table": r.source_full_table,
                    "source_column": r.source_column,
                    "target_table": r.target_full_table,
                    "target_column": r.target_column,
                    "description": r.description,
                    "id": r.id,
                })
            edited = st.data_editor(
                pd.DataFrame(flat_rows),
                width="stretch",
                hide_index=True,
                column_config={"id": None},
            )
            if st.button("Accept selected inferred relationships", type="primary"):
                accepted_ids = edited.loc[edited["accept"] == True, "id"].tolist()  # noqa: E712
                for rid in accepted_ids:
                    inferred_relationships[rid].context_id = active_ctx.id if active_ctx else ""
                    state.relationships[rid] = inferred_relationships[rid]
                save_state(state)
                st.success(f"Accepted {len(accepted_ids)} inferred relationships.")
                st.rerun()

    # ---------------------------------------------------------------------
    # ERD View tab
    # ---------------------------------------------------------------------
