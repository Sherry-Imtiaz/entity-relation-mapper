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


def render_tables_tab(state: ErdState) -> None:
        st.subheader("Tables and columns")
        if not state.tables:
            st.info("Import a CSV/Excel schema file or load a database to begin.")
            st.markdown(
                """
                **Minimum CSV columns required:**
                - `table_name`
                - `column_name`

                **Recommended columns:**
                - `schema_name`
                - `table_name`
                - `column_name`
                - `data_type`
                - `nullable`
                - `is_primary_key`
                - `ordinal_position`
                - `row_count`
                - `module`
                - `purpose`
                - `notes`
                - `comment`
                """
            )
        else:
            table_names = sorted(state.tables.keys(), key=str.lower)
            selected_table = st.selectbox("Select table", table_names)
            t = state.tables[selected_table]

            c1, c2, c3 = st.columns([1, 1, 1])
            with c1:
                t.module = st.text_input("Module", value=t.module, key=f"module_{selected_table}")
            with c2:
                t.purpose = st.text_input("Purpose", value=t.purpose, key=f"purpose_{selected_table}")
            with c3:
                st.text_input("Approx row count", value="" if t.row_count is None else str(t.row_count), disabled=True)

            t.notes = st.text_area("Table notes", value=t.notes, key=f"notes_{selected_table}")

            st.dataframe(columns_df(t), width="stretch", hide_index=True)

            with st.expander("Edit column comments"):
                for col in sorted(t.columns, key=lambda x: x.ordinal_position):
                    col.comment = st.text_input(
                        f"{col.column_name}",
                        value=col.comment,
                        key=f"comment_{selected_table}_{col.column_name}",
                    )

            if st.button("Save table notes/comments"):
                save_state(state)
                st.success("Saved table metadata.")

    # ---------------------------------------------------------------------
    # Relationships tab
    # ---------------------------------------------------------------------
