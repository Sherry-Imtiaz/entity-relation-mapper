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
        st.subheader("Named Relationship Contexts")
        st.write(
            "Create named relationship contexts such as Module Relations, Payment Relations, Customer Relations, "
            "or Property Ownership Relations. Phase 1 lets you create contexts and assign tables to them."
        )

        with st.expander("Create new relationship context", expanded=not bool(state.relationship_contexts)):
            new_name = st.text_input("Context name", placeholder="Example: Property Ownership Relations", key="new_context_name")
            new_type = st.selectbox(
                "Context type",
                [
                    "Module Relation",
                    "Payment Relation",
                    "Customer Relation",
                    "Property Relation",
                    "Animal Relation",
                    "Regulatory Relation",
                    "Reporting Relation",
                    "Other",
                ],
                key="new_context_type",
            )
            custom_new_type = ""
            if new_type == "Other":
                custom_new_type = st.text_input(
                    "Custom context type",
                    placeholder="Example: Rates Relation, Debtor Relation, Asset Relation",
                    key="new_context_custom_type",
                )
            new_purpose = st.text_area("Purpose", placeholder="What does this relationship context explain?", key="new_context_purpose")
            if st.button("Create relationship context", type="primary"):
                if not new_name.strip():
                    st.error("Enter a context name first.")
                else:
                    cid = unique_context_id(state.relationship_contexts, new_name)
                    state.relationship_contexts[cid] = RelationshipContext(
                        id=cid,
                        name=new_name.strip(),
                        context_type=(custom_new_type.strip() if new_type == "Other" and custom_new_type.strip() else new_type),
                        purpose=new_purpose.strip(),
                    )
                    state.active_context_id = cid
                    save_state(state)
                    st.success(f"Created relationship context: {new_name.strip()}")
                    st.rerun()

        if not state.relationship_contexts:
            st.info("No relationship contexts have been created yet.")
        else:
            context_ids = list(state.relationship_contexts.keys())
            active_index = context_ids.index(state.active_context_id) if state.active_context_id in context_ids else 0
            context_choice = st.selectbox(
                "Active relationship context",
                context_ids,
                index=active_index,
                format_func=lambda cid: f"{state.relationship_contexts[cid].name} ({state.relationship_contexts[cid].context_type})",
            )
            state.active_context_id = context_choice
            ctx = state.relationship_contexts[context_choice]

            st.divider()
            st.markdown("### Context details")
            d1, d2, d3 = st.columns([2, 1, 1])
            existing_context_type_before_select = ctx.context_type
            with d1:
                ctx.name = st.text_input("Relationship context name", value=ctx.name, key=f"ctx_name_{ctx.id}")
            with d2:
                ctx.context_type = st.selectbox(
                    "Relationship type",
                    [
                        "Module Relation",
                        "Payment Relation",
                        "Customer Relation",
                        "Property Relation",
                        "Animal Relation",
                        "Regulatory Relation",
                        "Reporting Relation",
                        "Other",
                    ],
                    index=[
                        "Module Relation",
                        "Payment Relation",
                        "Customer Relation",
                        "Property Relation",
                        "Animal Relation",
                        "Regulatory Relation",
                        "Reporting Relation",
                        "Other",
                    ].index(ctx.context_type) if ctx.context_type in [
                        "Module Relation",
                        "Payment Relation",
                        "Customer Relation",
                        "Property Relation",
                        "Animal Relation",
                        "Regulatory Relation",
                        "Reporting Relation",
                        "Other",
                    ] else 0,
                    key=f"ctx_type_{ctx.id}",
                )
            with d3:
                ctx.status = st.selectbox(
                    "Status",
                    ["Draft", "Reviewed", "Approved", "Deprecated"],
                    index=["Draft", "Reviewed", "Approved", "Deprecated"].index(ctx.status) if ctx.status in ["Draft", "Reviewed", "Approved", "Deprecated"] else 0,
                    key=f"ctx_status_{ctx.id}",
                )

            custom_existing_type = st.text_input(
                "Custom relationship type / label override",
                value="" if existing_context_type_before_select in [
                    "Module Relation",
                    "Payment Relation",
                    "Customer Relation",
                    "Property Relation",
                    "Animal Relation",
                    "Regulatory Relation",
                    "Reporting Relation",
                    "Other",
                ] else existing_context_type_before_select,
                placeholder="Optional. Example: Debtor Payment Relation",
                key=f"ctx_custom_type_{ctx.id}",
            )
            if custom_existing_type.strip():
                ctx.context_type = custom_existing_type.strip()

            ctx.owner_reviewer = st.text_input("Owner / reviewer", value=ctx.owner_reviewer, key=f"ctx_owner_{ctx.id}")
            ctx.purpose = st.text_area("Purpose", value=ctx.purpose, key=f"ctx_purpose_{ctx.id}")
            ctx.business_context = st.text_area("Business context", value=ctx.business_context, key=f"ctx_business_{ctx.id}")
            ctx.primary_join_path = st.text_area("Primary join path", value=ctx.primary_join_path, key=f"ctx_join_path_{ctx.id}")
            ctx.conditional_logic_notes = st.text_area("Conditional logic notes", value=ctx.conditional_logic_notes, key=f"ctx_condition_notes_{ctx.id}")
            ctx.query_guidance = st.text_area("Query / export guidance", value=ctx.query_guidance, key=f"ctx_query_guidance_{ctx.id}")
            ctx.comments = st.text_area("Comments", value=ctx.comments, key=f"ctx_comments_{ctx.id}")

            st.divider()
            st.markdown("### Tables assigned to this context")
            assigned_tables = [t for t in ctx.included_tables if t in state.tables]
            missing_tables = [t for t in ctx.included_tables if t not in state.tables]
            ctx.included_tables = assigned_tables + missing_tables

            if assigned_tables:
                st.dataframe(
                    pd.DataFrame({"included_table": assigned_tables}),
                    width="stretch",
                    hide_index=True,
                )
            else:
                st.info("No tables have been assigned to this relationship context yet.")

            if missing_tables:
                st.warning("Some assigned tables are no longer available in the imported schema:")
                st.write(missing_tables)

            remove_tables = st.multiselect(
                "Remove assigned tables",
                assigned_tables,
                key=f"ctx_remove_tables_{ctx.id}",
            )
            if st.button("Remove selected tables", key=f"ctx_remove_btn_{ctx.id}"):
                ctx.included_tables = [t for t in ctx.included_tables if t not in remove_tables]
                ctx.updated_at = datetime.now(UTC).isoformat()
                save_state(state)
                st.success("Removed selected tables from the context.")
                st.rerun()

            st.markdown("### Add tables to this context")
            if not state.tables:
                st.info("Import schema tables before assigning tables to a relationship context.")
            else:
                _, _, table_options = render_table_filter_controls(state, key_prefix=f"ctx_add_{ctx.id}")
                candidate_options = [t for t in table_options if t not in ctx.included_tables]
                add_tables = st.multiselect(
                    "Filtered tables available to add",
                    candidate_options,
                    key=f"ctx_add_tables_{ctx.id}",
                )
                if st.button("Add selected tables to context", key=f"ctx_add_btn_{ctx.id}"):
                    ctx.included_tables = sorted(set(ctx.included_tables + add_tables), key=str.lower)
                    ctx.updated_at = datetime.now(UTC).isoformat()
                    save_state(state)
                    st.success("Added selected tables to the context.")
                    st.rerun()

            b1, b2 = st.columns([1, 1])
            if b1.button("Save context details", type="primary", key=f"ctx_save_{ctx.id}"):
                ctx.updated_at = datetime.now(UTC).isoformat()
                save_state(state)
                st.success("Saved relationship context.")
            if b2.button("Delete active context", key=f"ctx_delete_{ctx.id}"):
                del state.relationship_contexts[ctx.id]
                state.active_context_id = next(iter(state.relationship_contexts.keys()), "")
                save_state(state)
                st.success("Deleted relationship context.")
                st.rerun()

            with st.expander("Phase 1 note"):
                st.write(
                    "This phase creates the context model and table assignment workflow. "
                    "Manual, inferred, conditional relationships, ERD view, and exports will be scoped to the selected context in the next phases."
                )

    # ---------------------------------------------------------------------
    # Tables tab
    # ---------------------------------------------------------------------
    with tab_tables:
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
    with tab_relationships:
        st.subheader("Relationship registry")
        active_ctx = get_active_context(state)
        if active_ctx:
            st.info(f"Active context: {active_ctx.name} ({active_ctx.context_type})")
        else:
            st.info("No active relationship context selected. Existing relationships are shown as global/unassigned.")

        registry_scope = st.radio(
            "Relationship registry scope",
            ["Active context only", "All relationships"],
            horizontal=True,
            key="relationship_registry_scope",
        )
        df = relationships_df(state)
        if not df.empty and registry_scope == "Active context only":
            df = df[df["context"] == context_display_name(state, state.active_context_id)]

        dashboard_context_id = state.active_context_id if registry_scope == "Active context only" else None
        quality = relationship_quality_summary(state, context_id=dashboard_context_id)
        st.markdown("### Relationship quality dashboard")
        q1, q2, q3, q4, q5, q6 = st.columns(6)
        q1.metric("Total", quality["total"])
        q2.metric("Active", quality["active"])
        q3.metric("Manual", quality["manual"])
        q4.metric("Inferred", quality["inferred"])
        q5.metric("Conditional", quality["conditional"])
        q6.metric("Broken", quality["broken"])

        with st.expander("Relationship validation details"):
            validation_df = validate_relationships(state, context_id=dashboard_context_id)
            if validation_df.empty:
                st.info("No relationships to validate.")
            else:
                st.dataframe(validation_df.drop(columns=["id"]), width="stretch", hide_index=True)

        if df.empty:
            st.info("No relationships yet. Import a Relationships sheet, infer links, or add manual relationships.")
        else:
            type_filter = st.multiselect(
                "Filter by type",
                sorted(df["type"].dropna().unique().tolist()),
                default=sorted(df["type"].dropna().unique().tolist()),
            )
            filtered = df[df["type"].isin(type_filter)] if type_filter else df
            st.dataframe(filtered.drop(columns=["id"]), width="stretch", hide_index=True)

            with st.expander("Edit / delete a relationship"):
                rel_options = [
                    f"{r.relationship_type}: {r.source_full_table}.{r.source_column} -> {r.target_full_table}.{r.target_column} [{r.id}]"
                    for r in state.relationships.values()
                    if registry_scope == "All relationships" or context_display_name(state, r.context_id) == context_display_name(state, state.active_context_id)
                ]
                if not rel_options:
                    st.info("No relationships available for editing in this scope.")
                else:
                    choice = st.selectbox("Relationship", rel_options)
                    chosen_id = choice.split("[")[-1].rstrip("]") if choice else ""
                    if chosen_id in state.relationships:
                        rel = state.relationships[chosen_id]
                        rel.active = st.checkbox("Active", value=rel.active, key=f"rel_edit_active_{rel.id}")
                        rel.relationship_type = st.selectbox(
                            "Relationship type",
                            ["manual", "conditional", "inferred", "imported", "explicit_fk"],
                            index=["manual", "conditional", "inferred", "imported", "explicit_fk"].index(rel.relationship_type) if rel.relationship_type in ["manual", "conditional", "inferred", "imported", "explicit_fk"] else 0,
                            key=f"rel_edit_type_{rel.id}",
                        )
                        rel.join_type = st.selectbox(
                            "Join type",
                            ["LEFT JOIN", "INNER JOIN", "RIGHT JOIN", "FULL OUTER JOIN"],
                            index=["LEFT JOIN", "INNER JOIN", "RIGHT JOIN", "FULL OUTER JOIN"].index(rel.join_type) if rel.join_type in ["LEFT JOIN", "INNER JOIN", "RIGHT JOIN", "FULL OUTER JOIN"] else 0,
                            key=f"rel_edit_join_{rel.id}",
                        )
                        rel.cardinality = st.selectbox(
                            "Cardinality",
                            ["many-to-one", "one-to-many", "one-to-one", "many-to-many"],
                            index=["many-to-one", "one-to-many", "one-to-one", "many-to-many"].index(rel.cardinality) if rel.cardinality in ["many-to-one", "one-to-many", "one-to-one", "many-to-many"] else 0,
                            key=f"rel_edit_cardinality_{rel.id}",
                        )
                        rel.condition_sql = st.text_input("Condition SQL, optional", value=rel.condition_sql, key=f"rel_edit_condition_{rel.id}")
                        rel.extra_join_sql = st.text_input("Extra join SQL, optional", value=rel.extra_join_sql, key=f"rel_edit_extra_{rel.id}")
                        rel.description = st.text_area("Description / business meaning", value=rel.description, key=f"rel_edit_description_{rel.id}")
                        col1, col2 = st.columns(2)
                        if col1.button("Save relationship", key=f"rel_save_{rel.id}"):
                            save_state(state)
                            st.success("Saved relationship.")
                        if col2.button("Delete relationship", key=f"rel_delete_{rel.id}"):
                            del state.relationships[chosen_id]
                            save_state(state)
                            st.success("Deleted relationship.")
                            st.rerun()

        st.divider()
        st.subheader("Add manual relationship")
        active_ctx = get_active_context(state)
        scoped_tables = get_context_tables(state, active_ctx.id) if active_ctx else {}
        if active_ctx and len(scoped_tables) >= 2:
            st.caption("Manual relationships added here will be stored against the active relationship context.")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Source table filter**")
                _, _, source_table_options = render_table_filter_controls(state, key_prefix="manual_source")
                source_table_options = [t for t in source_table_options if t in scoped_tables] or sorted(scoped_tables.keys(), key=str.lower)
                source_full = st.selectbox("Source table", source_table_options, key="manual_source_table")
                source_col = st.selectbox("Source column", get_table_columns(state, source_full), key="manual_source_col")
            with c2:
                st.markdown("**Target table filter**")
                _, _, target_table_options = render_table_filter_controls(state, key_prefix="manual_target")
                target_table_options = [t for t in target_table_options if t in scoped_tables] or sorted(scoped_tables.keys(), key=str.lower)
                target_full = st.selectbox("Target table", target_table_options, key="manual_target_table")
                target_col = st.selectbox("Target column", get_table_columns(state, target_full), key="manual_target_col")

            c3, c4, c5 = st.columns(3)
            with c3:
                cardinality = st.selectbox("Cardinality", ["many-to-one", "one-to-many", "one-to-one", "many-to-many"])
            with c4:
                join_type = st.selectbox("Join type", ["LEFT JOIN", "INNER JOIN", "RIGHT JOIN", "FULL OUTER JOIN"])
            with c5:
                confidence = st.slider("Confidence", 0.0, 1.0, 0.90, 0.05)

            relationship_mode = st.radio(
                "Relationship mode",
                ["Standard relationship", "Conditional relationship"],
                horizontal=True,
                key="manual_relationship_mode",
            )
            condition_sql = ""
            if relationship_mode == "Conditional relationship":
                condition_sql = st.text_input(
                    "Condition SQL",
                    placeholder="Example: src.Item_Type = 3",
                    key="manual_condition_sql",
                )
            extra_join_sql = st.text_input(
                "Extra join SQL, optional",
                placeholder="Example: src.ValidTo IS NULL",
                key="manual_extra_join_sql",
            )
            description = st.text_area("Description / business meaning", key="manual_description")

            if st.button("Add relationship", type="primary"):
                ss, stbl = split_full_table(source_full)
                ts, ttbl = split_full_table(target_full)
                new_relationship_type = "conditional" if relationship_mode == "Conditional relationship" else "manual"
                rid = rel_id(ss, stbl, source_col, ts, ttbl, target_col, new_relationship_type, condition_sql)
                state.relationships[rid] = Relationship(
                    id=rid,
                    context_id=active_ctx.id,
                    source_schema=ss,
                    source_table=stbl,
                    source_column=source_col,
                    target_schema=ts,
                    target_table=ttbl,
                    target_column=target_col,
                    relationship_type=new_relationship_type,
                    cardinality=cardinality,
                    join_type=join_type,
                    confidence=confidence,
                    condition_sql=condition_sql,
                    extra_join_sql=extra_join_sql,
                    description=description,
                )
                save_state(state)
                st.success("Relationship added.")
                st.rerun()
        else:
            relationship_context_warning(state)
            st.info("Assign at least two tables to the active relationship context before adding manual relationships.")

        st.divider()
        st.info(
            "Visual relationship creation has been removed from this tab. "
            "Use the form above to create/edit relationships, and use the ERD View tab for interactive Streamlit Flow visualisation."
        )

    # ---------------------------------------------------------------------
    # Inference tab
    # ---------------------------------------------------------------------
    with tab_infer:
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
    with tab_erd:
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
    with tab_export:
        st.subheader("Export for ChatGPT / SQL generation")
        only_active = st.checkbox("Only export active relationships", value=True, key="export_only_active")
        active_ctx = get_active_context(state)

        export_scope_options = ["Whole database"]
        if active_ctx:
            export_scope_options.append("Active relationship context")
        export_scope = st.radio("Export scope", export_scope_options, index=1 if active_ctx else 0, horizontal=True)

        selected_context_id: Optional[str] = None
        selected_tables: List[str] = []

        if export_scope == "Active relationship context" and active_ctx:
            selected_context_id = active_ctx.id
            export_state = build_context_scoped_state(state, active_ctx.id)
            st.info(f"Exporting named relationship context: {active_ctx.name}")
            st.markdown("### Context export notes")
            st.write(f"**Type:** {active_ctx.context_type}")
            st.write(f"**Status:** {active_ctx.status}")
            if active_ctx.purpose:
                st.write(f"**Purpose:** {active_ctx.purpose}")
            if active_ctx.query_guidance:
                st.write(f"**Query Guidance:** {active_ctx.query_guidance}")
        else:
            export_state = state
            selected_tables = st.multiselect(
                "Limit export to selected tables, optional",
                sorted(state.tables.keys(), key=str.lower),
                default=[],
            )

        validation_df = validate_relationships(export_state)
        broken_count = 0 if validation_df.empty else int((validation_df["status"] == "Broken").sum())
        warning_count = 0 if validation_df.empty else int((validation_df["status"] == "Warning").sum())
        if broken_count:
            st.error(f"Export warning: {broken_count} broken relationship(s) detected in this export scope.")
        elif warning_count:
            st.warning(f"Export note: {warning_count} relationship warning(s) detected in this export scope.")
        else:
            st.success("No relationship validation issues detected in this export scope.")

        c1, c2, c3 = st.columns(3)
        with c1:
            if selected_context_id:
                md = export_markdown_with_context(state, selected_context_id, only_active=only_active)
            else:
                md = export_markdown(export_state, selected_tables=selected_tables or None, only_active=only_active)
            st.download_button(
                "Download ChatGPT Markdown",
                data=md,
                file_name=(f"chatgpt_erd_context_{selected_context_id}.md" if selected_context_id else "chatgpt_erd_context.md"),
                mime="text/markdown",
                width="stretch",
            )
        with c2:
            if selected_context_id:
                js = export_json_with_context(state, selected_context_id, only_active=only_active)
            else:
                js = export_json(export_state, only_active=only_active)
            st.download_button(
                "Download JSON",
                data=js,
                file_name=(f"chatgpt_erd_context_{selected_context_id}.json" if selected_context_id else "chatgpt_erd_context.json"),
                mime="application/json",
                width="stretch",
            )
        with c3:
            mermaid_export = export_mermaid(export_state, only_active=only_active)
            st.download_button(
                "Download Mermaid ERD",
                data=mermaid_export,
                file_name=(f"erd_mermaid_{selected_context_id}.mmd" if selected_context_id else "erd_mermaid.mmd"),
                mime="text/plain",
                width="stretch",
            )

        with st.expander("Relationship validation for export scope"):
            if validation_df.empty:
                st.info("No relationships in this export scope.")
            else:
                st.dataframe(validation_df.drop(columns=["id"]), width="stretch", hide_index=True)

        st.write("Preview:")
        st.code(md[:20000], language="markdown")
        if len(md) > 20000:
            st.warning("Preview truncated. Download the full Markdown export.")

if __name__ == "__main__":
    main()
