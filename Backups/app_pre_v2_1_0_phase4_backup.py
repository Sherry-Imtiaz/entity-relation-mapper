"""
Entity Relation Mapper / ERD Exporter
-------------------------------------

Purpose:
- Load database schema from CSV or Excel instead of needing a live database connection.
- Optional: still connect directly to a database using SQLAlchemy if required.
- Load tables, columns, table notes, and optional relationships from files.
- Suggest likely relationships based on naming patterns such as Customer_Id, Associate_Id, Item_Id, etc.
- Allow manual relationships and conditional relationships.
- Save/load ERD state locally.
- Export a ChatGPT-friendly relationship map for query generation.

Install:
    pip install streamlit pandas sqlalchemy pyodbc openpyxl streamlit-flow-component

Run:
    streamlit run entity_relation_mapper_app.py

Recommended CSV / Excel import format:

    schema_name, table_name, column_name, data_type, nullable, is_primary_key, ordinal_position, row_count, module, purpose, notes, comment
    PropertyWise, Properties, Property_Id, int, no, yes, 1, 10000, Property, Property master, Main property table, Primary key
    PropertyWise, Properties, Assessment_No, varchar(50), yes, no, 2, 10000, Property, Property master, Main property table,

Also supported:
- A file with one row per table and a `columns` field containing comma-separated column names.
- Excel files with sheets named `Tables`, `Columns`, and optionally `Relationships`.
- Relationship import using columns such as:
    source_table, source_column, target_table, target_column, relationship_type, cardinality, join_type, condition_sql, extra_join_sql, description

Notes:
- This stores local state in ./erd_mapper_state.json
- It does not modify your source database.
"""

from __future__ import annotations

import io
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

try:
    from streamlit_flow import streamlit_flow
except ImportError:
    streamlit_flow = None
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError


from config import APP_CHANGELOG, APP_VERSION, APP_VERSION_NAME, STATE_FILE
from models import ColumnInfo, ErdState, Relationship, RelationshipContext, TableInfo

# -----------------------------------------------------------------------------
# State helpers
# -----------------------------------------------------------------------------


def table_key(schema_name: str, table_name: str) -> str:
    return f"{schema_name}.{table_name}" if schema_name else table_name


def make_context_id(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_]+", "_", name.strip().lower()).strip("_")
    return slug or f"relationship_context_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"


def unique_context_id(existing_contexts: Dict[str, RelationshipContext], name: str) -> str:
    base = make_context_id(name)
    candidate = base
    counter = 2
    while candidate in existing_contexts:
        candidate = f"{base}_{counter}"
        counter += 1
    return candidate


def rel_id(
    source_schema: str,
    source_table: str,
    source_column: str,
    target_schema: str,
    target_table: str,
    target_column: str,
    relationship_type: str,
    condition_sql: str = "",
) -> str:
    raw = "|".join([
        source_schema or "",
        source_table,
        source_column,
        target_schema or "",
        target_table,
        target_column,
        relationship_type,
        condition_sql or "",
    ])
    return re.sub(r"[^A-Za-z0-9_]+", "_", raw).strip("_")[:220]


from state_manager import default_state, deserialize_state, load_state, merge_tables_keep_metadata, save_state, serialize_state

from importers import (
    create_import_template_excel,
    create_simple_csv_template,
    import_schema_file,
    split_table_identifier,
)
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

from ui_contexts import render_contexts_tab
from ui_tables import render_tables_tab
from ui_relationships import render_relationships_tab
from ui_inference import render_inference_tab
from ui_erd import render_erd_tab
from ui_export import render_export_tab


# -----------------------------------------------------------------------------
# CSV / Excel import helpers
# -----------------------------------------------------------------------------





















# -----------------------------------------------------------------------------
# Optional DB introspection
# -----------------------------------------------------------------------------


@st.cache_resource(show_spinner=False)
def get_engine(connection_string: str) -> Engine:
    return create_engine(connection_string, pool_pre_ping=True, future=True)


def test_connection(engine: Engine) -> Tuple[bool, str]:
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            _ = result.scalar()
        return True, "Connection successful."
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def normalize_type(col: Dict[str, Any]) -> str:
    raw_type = str(col.get("type", ""))
    return raw_type.replace("COLLATE", "").strip()


def get_database_name(engine: Engine) -> str:
    try:
        with engine.connect() as conn:
            dialect_name = engine.dialect.name.lower()
            if "mssql" in dialect_name:
                return str(conn.execute(text("SELECT DB_NAME()" )).scalar() or "")
            if "postgresql" in dialect_name:
                return str(conn.execute(text("SELECT current_database()" )).scalar() or "")
            if "mysql" in dialect_name:
                return str(conn.execute(text("SELECT DATABASE()" )).scalar() or "")
    except Exception:
        pass
    return ""


def get_row_counts(engine: Engine, tables: Dict[str, TableInfo]) -> Dict[str, Optional[int]]:
    counts: Dict[str, Optional[int]] = {k: None for k in tables}
    dialect_name = engine.dialect.name.lower()

    if "mssql" in dialect_name:
        sql = """
        SELECT
            s.name AS schema_name,
            t.name AS table_name,
            SUM(p.rows) AS row_count
        FROM sys.tables t
        INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
        INNER JOIN sys.partitions p ON t.object_id = p.object_id
        WHERE p.index_id IN (0, 1)
        GROUP BY s.name, t.name
        """
        try:
            with engine.connect() as conn:
                df = pd.read_sql(text(sql), conn)
            for _, row in df.iterrows():
                k = table_key(str(row["schema_name"]), str(row["table_name"]))
                if k in counts:
                    counts[k] = int(row["row_count"])
            return counts
        except Exception:
            return counts

    return counts


def introspect_tables(engine: Engine, include_schemas: Optional[List[str]] = None) -> Dict[str, TableInfo]:
    inspector = inspect(engine)
    tables: Dict[str, TableInfo] = {}
    schemas = include_schemas or inspector.get_schema_names()

    ignored_schemas = {"INFORMATION_SCHEMA", "sys", "db_owner", "db_datareader", "db_datawriter"}

    for schema in schemas:
        if schema in ignored_schemas:
            continue
        try:
            table_names = inspector.get_table_names(schema=schema)
        except SQLAlchemyError:
            continue

        for tname in table_names:
            try:
                columns_raw = inspector.get_columns(tname, schema=schema)
                pk_raw = inspector.get_pk_constraint(tname, schema=schema) or {}
                pk_columns = set(pk_raw.get("constrained_columns") or [])
            except SQLAlchemyError:
                continue

            cols = []
            for idx, col in enumerate(columns_raw, start=1):
                cname = str(col.get("name", ""))
                cols.append(
                    ColumnInfo(
                        schema_name=schema or "",
                        table_name=tname,
                        column_name=cname,
                        data_type=normalize_type(col),
                        nullable=bool(col.get("nullable", True)),
                        ordinal_position=idx,
                        is_primary_key=cname in pk_columns,
                    )
                )

            info = TableInfo(schema_name=schema or "", table_name=tname, columns=cols)
            tables[info.full_name] = info

    counts = get_row_counts(engine, tables)
    for k, count in counts.items():
        tables[k].row_count = count

    return tables


def detect_explicit_foreign_keys(engine: Engine, tables: Dict[str, TableInfo]) -> Dict[str, Relationship]:
    inspector = inspect(engine)
    relationships: Dict[str, Relationship] = {}

    for t in tables.values():
        try:
            fks = inspector.get_foreign_keys(t.table_name, schema=t.schema_name or None)
        except SQLAlchemyError:
            continue

        for fk in fks:
            constrained = fk.get("constrained_columns") or []
            referred = fk.get("referred_columns") or []
            referred_schema = fk.get("referred_schema") or t.schema_name
            referred_table = fk.get("referred_table") or ""

            for source_col, target_col in zip(constrained, referred):
                rid = rel_id(
                    t.schema_name,
                    t.table_name,
                    source_col,
                    referred_schema,
                    referred_table,
                    target_col,
                    "explicit_fk",
                )
                relationships[rid] = Relationship(
                    id=rid,
                    source_schema=t.schema_name,
                    source_table=t.table_name,
                    source_column=source_col,
                    target_schema=referred_schema or "",
                    target_table=referred_table,
                    target_column=target_col,
                    relationship_type="explicit_fk",
                    cardinality="many-to-one",
                    join_type="LEFT JOIN",
                    confidence=1.0,
                    description=f"Detected database foreign key: {fk.get('name', '')}",
                )

    return relationships


# -----------------------------------------------------------------------------
# Inference logic
# -----------------------------------------------------------------------------







# -----------------------------------------------------------------------------
# Export helpers
# -----------------------------------------------------------------------------








# -----------------------------------------------------------------------------
# UI helpers
# -----------------------------------------------------------------------------


def ensure_state() -> ErdState:
    if "erd_state" not in st.session_state:
        st.session_state.erd_state = load_state()
    return st.session_state.erd_state


def set_state(state: ErdState) -> None:
    st.session_state.erd_state = state


def relationships_df(state: ErdState) -> pd.DataFrame:
    rows = []
    for r in state.relationships.values():
        rows.append({
            "active": r.active,
            "context": context_display_name(state, r.context_id),
            "type": r.relationship_type,
            "confidence": r.confidence,
            "source_table": r.source_full_table,
            "source_column": r.source_column,
            "target_table": r.target_full_table,
            "target_column": r.target_column,
            "cardinality": r.cardinality,
            "condition_sql": r.condition_sql,
            "extra_join_sql": r.extra_join_sql,
            "description": r.description,
            "id": r.id,
        })
    return pd.DataFrame(rows)


def columns_df(table: TableInfo) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "column": c.column_name,
            "type": c.data_type,
            "nullable": c.nullable,
            "primary_key": c.is_primary_key,
            "comment": c.comment,
        }
        for c in sorted(table.columns, key=lambda x: x.ordinal_position)
    ])


def split_full_table(full_table: str) -> Tuple[str, str]:
    return split_table_identifier(full_table)


def get_table_columns(state: ErdState, full_table: str) -> List[str]:
    t = state.tables.get(full_table)
    if not t:
        return []
    return [c.column_name for c in sorted(t.columns, key=lambda x: x.ordinal_position)]


def get_schema_options(state: ErdState) -> List[str]:
    schemas = sorted({t.schema_name or "(no schema)" for t in state.tables.values()}, key=str.lower)
    return ["All schemas"] + schemas


def filter_table_options(state: ErdState, schema_filter: str = "All schemas", search_text: str = "") -> List[str]:
    search = (search_text or "").strip().lower()
    options: List[str] = []
    for full_name, table in state.tables.items():
        schema_name = table.schema_name or "(no schema)"
        if schema_filter and schema_filter != "All schemas" and schema_name != schema_filter:
            continue
        if search and search not in full_name.lower() and search not in table.table_name.lower():
            continue
        options.append(full_name)
    return sorted(options, key=str.lower)


def render_table_filter_controls(state: ErdState, key_prefix: str) -> Tuple[str, str, List[str]]:
    c1, c2 = st.columns([1, 2])
    with c1:
        schema_filter = st.selectbox("Schema filter", get_schema_options(state), key=f"{key_prefix}_schema_filter")
    with c2:
        search_text = st.text_input("Search table name", key=f"{key_prefix}_table_search")
    options = filter_table_options(state, schema_filter=schema_filter, search_text=search_text)
    return schema_filter, search_text, options


def get_active_context(state: ErdState) -> Optional[RelationshipContext]:
    if state.active_context_id:
        return state.relationship_contexts.get(state.active_context_id)
    return None






def build_context_scoped_state(state: ErdState, context_id: str) -> ErdState:
    ctx = state.relationship_contexts.get(context_id)
    if not ctx:
        return state

    scoped_tables = get_context_tables(state, context_id)
    scoped_relationships = get_relationships_for_context(state, context_id)

    # Include tables referenced by context relationships, even if not explicitly assigned yet.
    for rel in scoped_relationships.values():
        if rel.source_full_table in state.tables:
            scoped_tables[rel.source_full_table] = state.tables[rel.source_full_table]
        if rel.target_full_table in state.tables:
            scoped_tables[rel.target_full_table] = state.tables[rel.target_full_table]

    return ErdState(
        connection_label=state.connection_label,
        database_name=f"{state.database_name} / {ctx.name}",
        loaded_at=state.loaded_at,
        tables=scoped_tables,
        relationships=scoped_relationships,
        relationship_contexts={context_id: ctx},
        active_context_id=context_id,
    )



def relationship_context_warning(state: ErdState) -> None:
    ctx = get_active_context(state)
    if not ctx:
        st.warning("Create or select a relationship context before adding context-scoped relationships.")
    elif not get_context_table_set(state, ctx.id):
        st.warning("The active relationship context has no assigned tables. Add tables in the Relationship Contexts tab first.")













# -----------------------------------------------------------------------------
# Main Streamlit app
# -----------------------------------------------------------------------------


def main() -> None:
    st.set_page_config(page_title="Entity Relation Mapper", layout="wide")
    state = ensure_state()

    st.title("Entity Relation Mapper")
    st.caption(f"Version: {APP_VERSION} — {APP_VERSION_NAME}")
    st.caption("Import tables/columns from CSV or Excel, map relationships, add conditional joins, and export a ChatGPT-ready ERD map.")

    with st.sidebar:
        st.header("Load Schema")
        st.markdown(f"**Version:** {APP_VERSION}")
        with st.expander("Version changelog"):
            for item in APP_CHANGELOG:
                st.markdown(f"**{item['version']} — {item['title']}**")
                for change in item["changes"]:
                    st.markdown(f"- {change}")
        load_method = st.radio(
            "Load method",
            ["Import CSV / Excel", "Connect to database"],
            index=0,
            help="CSV / Excel import is recommended when you already exported table and column metadata.",
        )

        connection_label = st.text_input("Source label", value=state.connection_label or "Imported schema")

        if load_method == "Import CSV / Excel":
            st.write("Upload a CSV or Excel file containing your tables and columns.")
            uploaded_schema = st.file_uploader(
                "Schema file",
                type=["csv", "xlsx", "xlsm", "xls"],
                help="Use a Columns sheet with one row per column, or a simple CSV with table_name and column_name.",
            )

            replace_existing = st.checkbox(
                "Replace existing tables on import",
                value=True,
                help="If unticked, imported tables will be merged with the current state.",
            )
            replace_relationships = st.checkbox(
                "Replace imported/inferred relationships on import",
                value=False,
                help="Manual and conditional relationships are preserved unless this is ticked and the imported file contains replacements.",
            )

            if uploaded_schema is not None:
                with st.expander("Import preview and validation", expanded=False):
                    try:
                        uploaded_schema.seek(0)
                        preview_tables, preview_relationships, preview_message = import_schema_file(uploaded_schema)
                        uploaded_schema.seek(0)
                        preview = validate_import_preview(preview_tables, preview_relationships)
                        st.write(preview_message)
                        p1, p2, p3, p4 = st.columns(4)
                        p1.metric("Tables", preview["tables"])
                        p2.metric("Columns", preview["columns"])
                        p3.metric("Relationships", preview["relationships"])
                        p4.metric("Conditional", preview["conditional_relationships"])
                        if preview["errors"]:
                            st.error("Import errors detected:")
                            for item in preview["errors"]:
                                st.write(f"- {item}")
                        if preview["warnings"]:
                            st.warning("Import warnings detected:")
                            for item in preview["warnings"]:
                                st.write(f"- {item}")
                        if not preview["errors"] and not preview["warnings"]:
                            st.success("No import validation issues detected.")
                    except Exception as exc:  # noqa: BLE001
                        st.warning(f"Preview could not be generated: {exc}")
                        try:
                            uploaded_schema.seek(0)
                        except Exception:
                            pass

            if st.button("Load file", type="primary", width="stretch"):
                if uploaded_schema is None:
                    st.error("Upload a CSV or Excel schema file first.")
                else:
                    try:
                        uploaded_schema.seek(0)
                        incoming_tables, imported_relationships, import_message = import_schema_file(uploaded_schema)
                        if not incoming_tables:
                            st.error("No tables were found in the file. Check that it includes table_name and column_name or columns.")
                        else:
                            state.connection_label = connection_label
                            state.database_name = connection_label
                            state.loaded_at = datetime.now(UTC).isoformat()

                            if replace_existing:
                                state.tables = incoming_tables
                            else:
                                state.tables = merge_tables_keep_metadata(state.tables, incoming_tables)

                            if imported_relationships:
                                if replace_relationships:
                                    existing_manual = {
                                        k: r for k, r in state.relationships.items()
                                        if r.relationship_type in {"manual", "conditional"}
                                    }
                                    state.relationships = {**existing_manual, **imported_relationships}
                                else:
                                    state.relationships.update(imported_relationships)

                            save_state(state)
                            st.success(import_message)
                            st.rerun()
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"Could not import schema file: {exc}")

            st.divider()
            st.download_button(
                "Download Excel template",
                data=create_import_template_excel(),
                file_name="erd_import_template.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width="stretch",
            )
            st.download_button(
                "Download simple CSV template",
                data=create_simple_csv_template(),
                file_name="erd_import_template.csv",
                mime="text/csv",
                width="stretch",
            )

        else:
            connection_string = st.text_area(
                "SQLAlchemy connection string",
                height=120,
                placeholder="mssql+pyodbc://USER:PASSWORD@SERVER/DATABASE?driver=ODBC+Driver+17+for+SQL+Server&TrustServerCertificate=yes",
            )
            include_schema_text = st.text_input(
                "Schemas to include, comma-separated",
                value="dbo,PropertyWise",
                help="Leave blank to scan all visible schemas. For WCC-style DBs, use dbo,PropertyWise where applicable.",
            )

            col_a, col_b = st.columns(2)
            with col_a:
                test_clicked = st.button("Test", width="stretch")
            with col_b:
                load_clicked = st.button("Load DB", type="primary", width="stretch")

            if test_clicked or load_clicked:
                if not connection_string.strip():
                    st.error("Enter a SQLAlchemy connection string first.")
                else:
                    engine = get_engine(connection_string.strip())
                    ok, msg = test_connection(engine)
                    if ok:
                        st.success(msg)
                    else:
                        st.error(msg)

                    if ok and load_clicked:
                        schemas = [s.strip() for s in include_schema_text.split(",") if s.strip()] or None
                        with st.spinner("Loading schema, columns, row counts and foreign keys..."):
                            incoming_tables = introspect_tables(engine, schemas)
                            explicit = detect_explicit_foreign_keys(engine, incoming_tables)
                            database_name = get_database_name(engine)

                        state.connection_label = connection_label
                        state.database_name = database_name or connection_label
                        state.loaded_at = datetime.now(UTC).isoformat()
                        state.tables = merge_tables_keep_metadata(state.tables, incoming_tables)

                        existing_non_auto = {
                            k: r for k, r in state.relationships.items()
                            if r.relationship_type not in {"explicit_fk", "inferred"}
                        }
                        state.relationships = {**explicit, **existing_non_auto}
                        save_state(state)
                        st.success(f"Loaded {len(state.tables)} tables and {len(explicit)} explicit foreign-key relationships.")
                        st.rerun()

        st.divider()
        if st.button("Save state", width="stretch"):
            save_state(state)
            st.success(f"Saved to {STATE_FILE}")

        uploaded_state = st.file_uploader("Import saved ERD state JSON", type=["json"], key="state_import")
        if uploaded_state is not None:
            try:
                imported = deserialize_state(json.loads(uploaded_state.read().decode("utf-8")))
                set_state(imported)
                save_state(imported)
                st.success("Imported and saved state.")
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(f"Could not import state: {exc}")

        if STATE_FILE.exists():
            st.download_button(
                "Download saved state",
                data=STATE_FILE.read_text(encoding="utf-8"),
                file_name="erd_mapper_state.json",
                mime="application/json",
                width="stretch",
            )

    metric_cols = st.columns(5)
    metric_cols[0].metric("Contexts", len(state.relationship_contexts))
    metric_cols[1].metric("Tables", len(state.tables))
    metric_cols[2].metric("Relationships", len(state.relationships))
    metric_cols[3].metric("Active", sum(1 for r in state.relationships.values() if r.active))
    metric_cols[4].metric("Conditional", sum(1 for r in state.relationships.values() if r.relationship_type == "conditional"))

    tab_contexts, tab_tables, tab_relationships, tab_infer, tab_erd, tab_export = st.tabs([
        "Relationship Contexts",
        "Tables",
        "Relationships",
        "Infer Links",
        "ERD View",
        "Export for ChatGPT",
    ])

    # ---------------------------------------------------------------------
    # Relationship Contexts tab
    # ---------------------------------------------------------------------
    with tab_contexts:
        render_contexts_tab(state)

    with tab_tables:
        render_tables_tab(state)

    with tab_relationships:
        render_relationships_tab(state)

    with tab_infer:
        render_inference_tab(state)

    with tab_erd:
        render_erd_tab(state)

    with tab_export:
        render_export_tab(state)

if __name__ == "__main__":
    main()
