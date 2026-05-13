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
    pip install streamlit pandas sqlalchemy pyodbc openpyxl

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
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError


STATE_FILE = Path("erd_mapper_state.json")
APP_VERSION = "v1.1.3"
APP_VERSION_NAME = "Export String Literal Syntax Patch"
APP_CHANGELOG = [
    {
        "version": "v1.1.3 Patch",
        "title": "Export Helper String Literal Fix",
        "changes": [
            "Fixed an unterminated string literal caused by newline join syntax in the context export helper.",
            "Replaced vulnerable newline string concatenation with chr(10)-based joins.",
            "Preserved the v1.1.2 Streamlit and UTC deprecation fixes."
        ],
    },
    {
        "version": "v1.1.2 Patch",
        "title": "Streamlit and UTC Deprecation Fixes",
        "changes": [
            "Replaced deprecated Streamlit width="stretch" parameters with width='stretch'.",
            "Replaced deprecated Streamlit width="content" pattern support with width='content' where applicable.",
            "Replaced datetime.now(UTC) with timezone-aware datetime.now(UTC).",
            "Reduced command-line deprecation warnings when running the app on current Streamlit and Python versions.",
        ],
    },
    {
        "version": "v1.1.1 Patch",
        "title": "Phase 3 Syntax Fix",
        "changes": [
            "Fixed a syntax issue where a return statement could be interpreted outside a helper function after Phase 3 edits.",
            "Re-stabilised the context export and validation helper section.",
            "Maintained all previous v1.1.0 Phase 1, Phase 2, and Phase 3 changelog entries in code.",
        ],
    },
    {
        "version": "v1.1.0 Phase 3",
        "title": "Context Export, Validation, and Relationship Quality",
        "changes": [
            "Added context-scoped Markdown, JSON, and Mermaid exports.",
            "Added relationship validation and broken relationship detection.",
            "Added relationship quality dashboard metrics.",
            "Added import validation preview foundation for schema files.",
            "Added improved conditional relationship review/edit workflow.",
            "Added clearer custom naming and rename support for relationship contexts.",
        ],
    },
    {
        "version": "v1.1.0 Phase 2",
        "title": "Context-Scoped Relationships and ERD",
        "changes": [
            "Scoped manual relationships to the active named relationship context.",
            "Scoped inferred relationship suggestions to tables assigned to the active named relationship context.",
            "Scoped conditional relationships to the active named relationship context.",
            "Updated relationship registry display to show context names.",
            "Updated ERD view to optionally display only the active named relationship context.",
            "Maintained changelog history directly in the application code.",
        ],
    },
    {
        "version": "v1.1.0 Phase 1",
        "title": "Named Relationship Context Foundation",
        "changes": [
            "Added visible app versioning.",
            "Added named relationship context data model.",
            "Added relationship context management screen.",
            "Added schema-filtered and searchable table assignment for contexts.",
        ],
    },
    {
        "version": "v1.0.0",
        "title": "Baseline CSV/Excel ERD Mapper",
        "changes": [
            "Added CSV and Excel schema import.",
            "Added table and column viewer.",
            "Added manual, inferred, and conditional relationships.",
            "Added ERD view and ChatGPT-friendly Markdown/JSON export.",
        ],
    },
]


# -----------------------------------------------------------------------------
# Data models
# -----------------------------------------------------------------------------


@dataclass
class ColumnInfo:
    schema_name: str
    table_name: str
    column_name: str
    data_type: str = ""
    nullable: bool = True
    ordinal_position: int = 0
    is_primary_key: bool = False
    comment: str = ""

    @property
    def full_table(self) -> str:
        return f"{self.schema_name}.{self.table_name}" if self.schema_name else self.table_name


@dataclass
class TableInfo:
    schema_name: str
    table_name: str
    row_count: Optional[int] = None
    purpose: str = ""
    module: str = ""
    notes: str = ""
    columns: List[ColumnInfo] = field(default_factory=list)

    @property
    def full_name(self) -> str:
        return f"{self.schema_name}.{self.table_name}" if self.schema_name else self.table_name


@dataclass
class Relationship:
    id: str
    source_schema: str
    source_table: str
    source_column: str
    target_schema: str
    target_table: str
    target_column: str
    context_id: str = ""
    relationship_type: str = "manual"  # explicit_fk, inferred, manual, conditional, imported
    cardinality: str = "many-to-one"   # one-to-one, one-to-many, many-to-one, many-to-many
    join_type: str = "LEFT JOIN"
    active: bool = True
    confidence: float = 1.0
    condition_sql: str = ""            # e.g. src.Item_Type = 3
    extra_join_sql: str = ""           # e.g. src.ValidTo IS NULL
    description: str = ""
    source_alias: str = "src"
    target_alias: str = "tgt"
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def source_full_table(self) -> str:
        return f"{self.source_schema}.{self.source_table}" if self.source_schema else self.source_table

    @property
    def target_full_table(self) -> str:
        return f"{self.target_schema}.{self.target_table}" if self.target_schema else self.target_table

    def join_clause(self, left_alias: str = "src", right_alias: str = "tgt") -> str:
        base = (
            f"{self.join_type} {self.target_full_table} {right_alias} "
            f"ON {left_alias}.{self.source_column} = {right_alias}.{self.target_column}"
        )
        conditions = []
        if self.condition_sql.strip():
            conditions.append(self.condition_sql.strip())
        if self.extra_join_sql.strip():
            conditions.append(self.extra_join_sql.strip())
        if conditions:
            base += " AND " + " AND ".join(conditions)
        return base


@dataclass
class RelationshipContext:
    id: str
    name: str
    context_type: str = "Module Relation"
    purpose: str = ""
    business_context: str = ""
    included_tables: List[str] = field(default_factory=list)
    primary_join_path: str = ""
    conditional_logic_notes: str = ""
    query_guidance: str = ""
    comments: str = ""
    owner_reviewer: str = ""
    status: str = "Draft"
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class ErdState:
    connection_label: str = ""
    database_name: str = ""
    loaded_at: str = ""
    tables: Dict[str, TableInfo] = field(default_factory=dict)
    relationships: Dict[str, Relationship] = field(default_factory=dict)
    relationship_contexts: Dict[str, RelationshipContext] = field(default_factory=dict)
    active_context_id: str = ""


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


def default_state() -> ErdState:
    return ErdState()


def serialize_state(state: ErdState) -> Dict[str, Any]:
    return {
        "connection_label": state.connection_label,
        "database_name": state.database_name,
        "loaded_at": state.loaded_at,
        "tables": {k: asdict(v) for k, v in state.tables.items()},
        "relationships": {k: asdict(v) for k, v in state.relationships.items()},
        "relationship_contexts": {k: asdict(v) for k, v in state.relationship_contexts.items()},
        "active_context_id": state.active_context_id,
    }


def deserialize_state(payload: Dict[str, Any]) -> ErdState:
    tables: Dict[str, TableInfo] = {}
    for k, t in payload.get("tables", {}).items():
        cols = [ColumnInfo(**c) for c in t.get("columns", [])]
        t_clean = {kk: vv for kk, vv in t.items() if kk != "columns"}
        tables[k] = TableInfo(**t_clean, columns=cols)

    relationships: Dict[str, Relationship] = {}
    for k, r in payload.get("relationships", {}).items():
        r_clean = dict(r)
        r_clean.setdefault("context_id", "")
        relationships[k] = Relationship(**r_clean)

    relationship_contexts: Dict[str, RelationshipContext] = {}
    for k, c in payload.get("relationship_contexts", {}).items():
        c_clean = dict(c)
        c_clean.setdefault("id", k)
        relationship_contexts[k] = RelationshipContext(**c_clean)

    active_context_id = payload.get("active_context_id", "")
    if active_context_id not in relationship_contexts:
        active_context_id = next(iter(relationship_contexts.keys()), "")

    return ErdState(
        connection_label=payload.get("connection_label", ""),
        database_name=payload.get("database_name", ""),
        loaded_at=payload.get("loaded_at", ""),
        tables=tables,
        relationships=relationships,
        relationship_contexts=relationship_contexts,
        active_context_id=active_context_id,
    )


def save_state(state: ErdState, path: Path = STATE_FILE) -> None:
    path.write_text(json.dumps(serialize_state(state), indent=2), encoding="utf-8")


def load_state(path: Path = STATE_FILE) -> ErdState:
    if not path.exists():
        return default_state()
    return deserialize_state(json.loads(path.read_text(encoding="utf-8")))


def merge_tables_keep_metadata(existing: Dict[str, TableInfo], incoming: Dict[str, TableInfo]) -> Dict[str, TableInfo]:
    """Refresh columns/row counts while preserving user-entered purpose/module/notes/comments."""
    merged = dict(incoming)
    for k, old in existing.items():
        if k in merged:
            if old.purpose and not merged[k].purpose:
                merged[k].purpose = old.purpose
            if old.module and not merged[k].module:
                merged[k].module = old.module
            if old.notes and not merged[k].notes:
                merged[k].notes = old.notes
            old_comments = {c.column_name: c.comment for c in old.columns if c.comment}
            for col in merged[k].columns:
                if not col.comment:
                    col.comment = old_comments.get(col.column_name, "")
    return merged


# -----------------------------------------------------------------------------
# CSV / Excel import helpers
# -----------------------------------------------------------------------------


HEADER_ALIASES = {
    "schema_name": {
        "schema", "schema_name", "table_schema", "database_schema", "owner", "schema name",
    },
    "table_name": {
        "table", "table_name", "tablename", "table name", "object", "object_name", "object name",
        "entity", "entity_name", "entity name",
    },
    "full_table": {
        "full_table", "full table", "fully_qualified_table", "fully qualified table",
        "table_full_name", "table full name", "qualified_table", "qualified table",
    },
    "column_name": {
        "column", "column_name", "column name", "field", "field_name", "field name", "attribute",
        "attribute_name", "attribute name", "name",
    },
    "columns": {
        "columns", "column_list", "column list", "fields", "field_list", "field list",
    },
    "data_type": {
        "type", "data_type", "data type", "datatype", "column_type", "column type", "field_type", "field type",
    },
    "nullable": {
        "nullable", "is_nullable", "is nullable", "allow_null", "allow null", "allows_null", "allows null",
        "null", "nulls", "required",
    },
    "is_primary_key": {
        "is_primary_key", "is primary key", "primary_key", "primary key", "pk", "is_pk", "is pk",
    },
    "ordinal_position": {
        "ordinal_position", "ordinal position", "ordinal", "position", "column_order", "column order", "order",
    },
    "row_count": {
        "row_count", "row count", "rows", "record_count", "record count", "records",
    },
    "module": {"module", "area", "system", "business_area", "business area"},
    "purpose": {"purpose", "description", "table_description", "table description", "business_meaning", "business meaning"},
    "notes": {"notes", "table_notes", "table notes", "remarks"},
    "comment": {"comment", "column_comment", "column comment", "column_description", "column description"},
    "source_table": {"source_table", "source table", "from_table", "from table", "left_table", "left table"},
    "source_column": {"source_column", "source column", "from_column", "from column", "left_column", "left column"},
    "target_table": {"target_table", "target table", "to_table", "to table", "right_table", "right table"},
    "target_column": {"target_column", "target column", "to_column", "to column", "right_column", "right column"},
    "relationship_type": {"relationship_type", "relationship type", "type", "rel_type", "rel type"},
    "cardinality": {"cardinality", "relationship_cardinality", "relationship cardinality"},
    "join_type": {"join_type", "join type", "join"},
    "active": {"active", "enabled", "is_active", "is active"},
    "confidence": {"confidence", "score"},
    "condition_sql": {"condition_sql", "condition sql", "condition", "discriminator_condition", "discriminator condition"},
    "extra_join_sql": {"extra_join_sql", "extra join sql", "extra_join", "extra join", "additional_join", "additional join"},
}


def clean_header(value: Any) -> str:
    text_value = str(value or "").strip().lower()
    text_value = re.sub(r"[\s\-\/]+", "_", text_value)
    text_value = re.sub(r"[^a-z0-9_]+", "", text_value)
    text_value = re.sub(r"_+", "_", text_value).strip("_")
    return text_value


def canonical_header(value: Any) -> str:
    raw = str(value or "").strip().lower()
    raw_clean = clean_header(raw)
    for canonical, aliases in HEADER_ALIASES.items():
        alias_clean = {clean_header(a) for a in aliases}
        if raw_clean in alias_clean:
            return canonical
    return raw_clean


def normalize_dataframe_headers(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [canonical_header(c) for c in df.columns]
    return df


def value_is_blank(value: Any) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except Exception:
        pass
    return str(value).strip() == ""


def safe_str(value: Any) -> str:
    if value_is_blank(value):
        return ""
    return str(value).strip()


def parse_bool(value: Any, default: bool = False) -> bool:
    if value_is_blank(value):
        return default
    text_value = str(value).strip().lower()
    if text_value in {"1", "true", "yes", "y", "pk", "primary", "primary key", "active"}:
        return True
    if text_value in {"0", "false", "no", "n", "not null", "required", "inactive"}:
        return False
    return default


def parse_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    if value_is_blank(value):
        return default
    try:
        return int(float(str(value).replace(",", "")))
    except Exception:
        return default


def parse_float(value: Any, default: float = 1.0) -> float:
    if value_is_blank(value):
        return default
    try:
        return float(value)
    except Exception:
        return default


def split_table_identifier(value: Any, fallback_schema: str = "") -> Tuple[str, str]:
    text_value = safe_str(value)
    if not text_value:
        return fallback_schema, ""

    # Handles db.schema.table by taking the last two parts as schema.table.
    parts = [p.strip(" []`\"'") for p in text_value.split(".") if p.strip()]
    if len(parts) >= 2:
        return parts[-2], parts[-1]
    return fallback_schema, parts[0] if parts else ""


def get_row_value(row: pd.Series, key: str, default: Any = "") -> Any:
    if key in row.index:
        return row.get(key, default)
    return default


def build_tables_from_column_rows(columns_df: pd.DataFrame, tables_df: Optional[pd.DataFrame] = None) -> Dict[str, TableInfo]:
    columns_df = normalize_dataframe_headers(columns_df).dropna(how="all")
    if tables_df is not None:
        tables_df = normalize_dataframe_headers(tables_df).dropna(how="all")

    tables: Dict[str, TableInfo] = {}
    table_meta: Dict[str, Dict[str, Any]] = {}

    if tables_df is not None and not tables_df.empty:
        for _, row in tables_df.iterrows():
            schema = safe_str(get_row_value(row, "schema_name"))
            table = safe_str(get_row_value(row, "table_name"))
            full_table = safe_str(get_row_value(row, "full_table"))
            if full_table and not table:
                schema, table = split_table_identifier(full_table, schema)
            elif "." in table and not schema:
                schema, table = split_table_identifier(table)
            if not table:
                continue
            key = table_key(schema, table)
            table_meta[key] = {
                "row_count": parse_int(get_row_value(row, "row_count"), None),
                "module": safe_str(get_row_value(row, "module")),
                "purpose": safe_str(get_row_value(row, "purpose")),
                "notes": safe_str(get_row_value(row, "notes")),
            }

    for _, row in columns_df.iterrows():
        schema = safe_str(get_row_value(row, "schema_name"))
        table = safe_str(get_row_value(row, "table_name"))
        full_table = safe_str(get_row_value(row, "full_table"))
        column = safe_str(get_row_value(row, "column_name"))

        if full_table and not table:
            schema, table = split_table_identifier(full_table, schema)
        elif "." in table and not schema:
            schema, table = split_table_identifier(table)

        if not table or not column:
            continue

        key = table_key(schema, table)
        if key not in tables:
            meta = table_meta.get(key, {})
            tables[key] = TableInfo(
                schema_name=schema,
                table_name=table,
                row_count=parse_int(get_row_value(row, "row_count"), meta.get("row_count")),
                module=safe_str(get_row_value(row, "module")) or meta.get("module", ""),
                purpose=safe_str(get_row_value(row, "purpose")) or meta.get("purpose", ""),
                notes=safe_str(get_row_value(row, "notes")) or meta.get("notes", ""),
                columns=[],
            )

        ordinal = parse_int(get_row_value(row, "ordinal_position"), len(tables[key].columns) + 1) or len(tables[key].columns) + 1
        nullable_default = True
        required_value = get_row_value(row, "nullable", "")
        nullable = parse_bool(required_value, nullable_default)
        if safe_str(required_value).lower() in {"required", "not null", "no"}:
            nullable = False

        tables[key].columns.append(
            ColumnInfo(
                schema_name=schema,
                table_name=table,
                column_name=column,
                data_type=safe_str(get_row_value(row, "data_type")),
                nullable=nullable,
                ordinal_position=ordinal,
                is_primary_key=parse_bool(get_row_value(row, "is_primary_key"), False),
                comment=safe_str(get_row_value(row, "comment")),
            )
        )

    # Sort columns and remove duplicates while preserving first occurrence.
    for t in tables.values():
        seen = set()
        unique_cols = []
        for c in sorted(t.columns, key=lambda x: x.ordinal_position):
            if c.column_name.lower() in seen:
                continue
            seen.add(c.column_name.lower())
            unique_cols.append(c)
        t.columns = unique_cols

    return tables


def build_tables_from_table_rows(tables_df: pd.DataFrame) -> Dict[str, TableInfo]:
    tables_df = normalize_dataframe_headers(tables_df).dropna(how="all")
    tables: Dict[str, TableInfo] = {}

    for _, row in tables_df.iterrows():
        schema = safe_str(get_row_value(row, "schema_name"))
        table = safe_str(get_row_value(row, "table_name"))
        full_table = safe_str(get_row_value(row, "full_table"))
        if full_table and not table:
            schema, table = split_table_identifier(full_table, schema)
        elif "." in table and not schema:
            schema, table = split_table_identifier(table)

        if not table:
            continue

        raw_columns = safe_str(get_row_value(row, "columns"))
        column_names = [c.strip() for c in re.split(r"[,;\n\r\t|]+", raw_columns) if c.strip()]
        key = table_key(schema, table)
        tables[key] = TableInfo(
            schema_name=schema,
            table_name=table,
            row_count=parse_int(get_row_value(row, "row_count"), None),
            module=safe_str(get_row_value(row, "module")),
            purpose=safe_str(get_row_value(row, "purpose")),
            notes=safe_str(get_row_value(row, "notes")),
            columns=[
                ColumnInfo(
                    schema_name=schema,
                    table_name=table,
                    column_name=col_name,
                    ordinal_position=i,
                    is_primary_key=col_name.lower() in {"id", f"{table.lower()}_id", f"{singularize(table)}_id"},
                )
                for i, col_name in enumerate(column_names, start=1)
            ],
        )

    return tables


def build_relationships_from_rows(relationships_df: pd.DataFrame) -> Dict[str, Relationship]:
    relationships_df = normalize_dataframe_headers(relationships_df).dropna(how="all")
    relationships: Dict[str, Relationship] = {}

    for _, row in relationships_df.iterrows():
        source_schema, source_table = split_table_identifier(get_row_value(row, "source_table"))
        target_schema, target_table = split_table_identifier(get_row_value(row, "target_table"))
        source_column = safe_str(get_row_value(row, "source_column"))
        target_column = safe_str(get_row_value(row, "target_column"))

        if not source_table or not target_table or not source_column or not target_column:
            continue

        relationship_type = safe_str(get_row_value(row, "relationship_type")) or "imported"
        condition_sql = safe_str(get_row_value(row, "condition_sql"))
        rid = rel_id(
            source_schema,
            source_table,
            source_column,
            target_schema,
            target_table,
            target_column,
            relationship_type,
            condition_sql,
        )
        relationships[rid] = Relationship(
            id=rid,
            source_schema=source_schema,
            source_table=source_table,
            source_column=source_column,
            target_schema=target_schema,
            target_table=target_table,
            target_column=target_column,
            relationship_type=relationship_type,
            cardinality=safe_str(get_row_value(row, "cardinality")) or "many-to-one",
            join_type=safe_str(get_row_value(row, "join_type")) or "LEFT JOIN",
            active=parse_bool(get_row_value(row, "active"), True),
            confidence=parse_float(get_row_value(row, "confidence"), 1.0),
            condition_sql=condition_sql,
            extra_join_sql=safe_str(get_row_value(row, "extra_join_sql")),
            description=safe_str(get_row_value(row, "description")) or safe_str(get_row_value(row, "purpose")),
        )

    return relationships


def read_uploaded_tabular_file(uploaded_file: Any) -> Tuple[Dict[str, pd.DataFrame], str]:
    file_name = uploaded_file.name.lower()
    if file_name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
        return {"Columns": df}, "csv"

    if file_name.endswith((".xlsx", ".xlsm", ".xls")):
        xls = pd.ExcelFile(uploaded_file)
        sheets = {sheet_name: pd.read_excel(xls, sheet_name=sheet_name) for sheet_name in xls.sheet_names}
        return sheets, "excel"

    raise ValueError("Unsupported file type. Please upload a CSV or Excel file.")


def find_sheet(sheets: Dict[str, pd.DataFrame], possible_names: List[str]) -> Optional[pd.DataFrame]:
    normalized_lookup = {clean_header(name): df for name, df in sheets.items()}
    for name in possible_names:
        key = clean_header(name)
        if key in normalized_lookup:
            return normalized_lookup[key]
    return None


def import_schema_file(uploaded_file: Any) -> Tuple[Dict[str, TableInfo], Dict[str, Relationship], str]:
    sheets, file_type = read_uploaded_tabular_file(uploaded_file)

    tables_sheet = find_sheet(sheets, ["Tables", "Table", "Entities", "Entity"])
    columns_sheet = find_sheet(sheets, ["Columns", "Column", "Fields", "Schema"])
    relationships_sheet = find_sheet(sheets, ["Relationships", "Relationship", "Relations", "Joins", "Links"])

    if columns_sheet is None:
        # CSV or simple Excel: use first sheet.
        first_sheet_name = next(iter(sheets.keys()))
        first_df = sheets[first_sheet_name]
        normalized_first = normalize_dataframe_headers(first_df)
        if "column_name" in normalized_first.columns:
            columns_sheet = first_df
        elif "columns" in normalized_first.columns:
            tables = build_tables_from_table_rows(first_df)
            relationships = build_relationships_from_rows(relationships_sheet) if relationships_sheet is not None else {}
            return tables, relationships, f"Imported from {file_type} using one-row-per-table format."
        else:
            raise ValueError(
                "Could not find a column list. Use either one row per column with `table_name` and `column_name`, "
                "or one row per table with `table_name` and `columns`."
            )

    columns_normalized = normalize_dataframe_headers(columns_sheet)
    if "column_name" in columns_normalized.columns:
        tables = build_tables_from_column_rows(columns_sheet, tables_sheet)
    elif "columns" in columns_normalized.columns:
        tables = build_tables_from_table_rows(columns_sheet)
    else:
        raise ValueError("The import file must include either `column_name` or `columns`.")

    relationships = build_relationships_from_rows(relationships_sheet) if relationships_sheet is not None else {}
    return tables, relationships, f"Imported {len(tables)} tables and {len(relationships)} relationships from {file_type}."


def create_import_template_excel() -> bytes:
    tables_df = pd.DataFrame([
        {
            "schema_name": "PropertyWise",
            "table_name": "Properties",
            "row_count": 10000,
            "module": "Property",
            "purpose": "Property master table",
            "notes": "Main table for property records",
        },
        {
            "schema_name": "PropertyWise",
            "table_name": "Associations_Role_Based",
            "row_count": 50000,
            "module": "Associations",
            "purpose": "Links associates to modules/items",
            "notes": "Uses Item_Type to determine target module",
        },
    ])
    columns_df = pd.DataFrame([
        {
            "schema_name": "PropertyWise",
            "table_name": "Properties",
            "column_name": "Property_Id",
            "data_type": "int",
            "nullable": "no",
            "is_primary_key": "yes",
            "ordinal_position": 1,
            "comment": "Primary property identifier",
        },
        {
            "schema_name": "PropertyWise",
            "table_name": "Properties",
            "column_name": "Assessment_No",
            "data_type": "varchar(50)",
            "nullable": "yes",
            "is_primary_key": "no",
            "ordinal_position": 2,
            "comment": "Assessment number",
        },
        {
            "schema_name": "PropertyWise",
            "table_name": "Associations_Role_Based",
            "column_name": "Item_Id",
            "data_type": "int",
            "nullable": "no",
            "is_primary_key": "no",
            "ordinal_position": 1,
            "comment": "Linked item id. Meaning depends on Item_Type.",
        },
        {
            "schema_name": "PropertyWise",
            "table_name": "Associations_Role_Based",
            "column_name": "Item_Type",
            "data_type": "int",
            "nullable": "no",
            "is_primary_key": "no",
            "ordinal_position": 2,
            "comment": "Discriminator. 3=Property, 1039=Reg App, 1200=Animal, 1080=Reg Entity.",
        },
        {
            "schema_name": "PropertyWise",
            "table_name": "Associations_Role_Based",
            "column_name": "Associate_Id",
            "data_type": "int",
            "nullable": "no",
            "is_primary_key": "no",
            "ordinal_position": 3,
            "comment": "Linked associate/person/company id",
        },
    ])
    relationships_df = pd.DataFrame([
        {
            "source_table": "PropertyWise.Associations_Role_Based",
            "source_column": "Item_Id",
            "target_table": "PropertyWise.Properties",
            "target_column": "Property_Id",
            "relationship_type": "conditional",
            "cardinality": "many-to-one",
            "join_type": "LEFT JOIN",
            "condition_sql": "src.Item_Type = 3",
            "extra_join_sql": "",
            "description": "Item_Type 3 means the association item links to a property record.",
            "active": "yes",
            "confidence": 1.0,
        }
    ])

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        tables_df.to_excel(writer, sheet_name="Tables", index=False)
        columns_df.to_excel(writer, sheet_name="Columns", index=False)
        relationships_df.to_excel(writer, sheet_name="Relationships", index=False)
    output.seek(0)
    return output.read()


def create_simple_csv_template() -> str:
    df = pd.DataFrame([
        {
            "schema_name": "PropertyWise",
            "table_name": "Properties",
            "column_name": "Property_Id",
            "data_type": "int",
            "nullable": "no",
            "is_primary_key": "yes",
            "ordinal_position": 1,
            "row_count": 10000,
            "module": "Property",
            "purpose": "Property master table",
            "notes": "Main table for property records",
            "comment": "Primary property identifier",
        },
        {
            "schema_name": "PropertyWise",
            "table_name": "Properties",
            "column_name": "Assessment_No",
            "data_type": "varchar(50)",
            "nullable": "yes",
            "is_primary_key": "no",
            "ordinal_position": 2,
            "row_count": 10000,
            "module": "Property",
            "purpose": "Property master table",
            "notes": "Main table for property records",
            "comment": "Assessment number",
        },
    ])
    return df.to_csv(index=False)


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


def clean_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def singularize(name: str) -> str:
    n = name.lower()
    if n.endswith("ies"):
        return n[:-3] + "y"
    if n.endswith("ses"):
        return n[:-2]
    if n.endswith("s") and not n.endswith("ss"):
        return n[:-1]
    return n


def likely_id_columns(table: TableInfo) -> List[str]:
    result = []
    for c in table.columns:
        cname = c.column_name.lower()
        if c.is_primary_key:
            result.append(c.column_name)
        elif cname in {"id", f"{table.table_name.lower()}_id", f"{singularize(table.table_name)}_id"}:
            result.append(c.column_name)
        elif cname.endswith("_id") or cname.endswith("id"):
            result.append(c.column_name)
    return list(dict.fromkeys(result))


def score_relationship(source_col: str, target_table: TableInfo, target_col: str) -> float:
    sc = clean_name(source_col)
    tt = clean_name(target_table.table_name)
    tt_singular = clean_name(singularize(target_table.table_name))
    tc = clean_name(target_col)

    score = 0.0

    if sc == tc and (sc.endswith("id") or sc.endswith("no") or sc.endswith("number")):
        score += 0.45

    if sc in {f"{tt}id", f"{tt_singular}id", f"{tt}no", f"{tt_singular}no"}:
        score += 0.45

    if tc in {"id", f"{tt}id", f"{tt_singular}id", f"{tt}no", f"{tt_singular}no"}:
        score += 0.25

    common_link_cols = {
        "associateid",
        "associationid",
        "rolebasedassociationid",
        "itemid",
        "itemtype",
        "propertyid",
        "propertynumber",
        "animalid",
        "customerid",
        "contactid",
        "addressid",
        "regappid",
        "regentityid",
    }
    if sc == tc and sc in common_link_cols:
        score += 0.25

    return min(score, 0.99)


def infer_relationships(tables: Dict[str, TableInfo], min_confidence: float = 0.60) -> Dict[str, Relationship]:
    relationships: Dict[str, Relationship] = {}
    table_values = list(tables.values())

    target_candidates: List[Tuple[TableInfo, ColumnInfo]] = []
    for target in table_values:
        id_cols = set(likely_id_columns(target))
        for col in target.columns:
            if col.column_name in id_cols:
                target_candidates.append((target, col))

    for source in table_values:
        for scol in source.columns:
            sc_lower = scol.column_name.lower()
            if not (
                sc_lower.endswith("id")
                or sc_lower.endswith("_id")
                or sc_lower.endswith("no")
                or sc_lower.endswith("number")
            ):
                continue

            for target, tcol in target_candidates:
                if source.full_name == target.full_name:
                    continue
                score = score_relationship(scol.column_name, target, tcol.column_name)
                if score < min_confidence:
                    continue

                rid = rel_id(
                    source.schema_name,
                    source.table_name,
                    scol.column_name,
                    target.schema_name,
                    target.table_name,
                    tcol.column_name,
                    "inferred",
                )
                relationships[rid] = Relationship(
                    id=rid,
                    source_schema=source.schema_name,
                    source_table=source.table_name,
                    source_column=scol.column_name,
                    target_schema=target.schema_name,
                    target_table=target.table_name,
                    target_column=tcol.column_name,
                    relationship_type="inferred",
                    cardinality="many-to-one",
                    join_type="LEFT JOIN",
                    confidence=round(score, 2),
                    description="Inferred by column/table naming pattern. Please verify before using in production queries.",
                )

    return relationships


# -----------------------------------------------------------------------------
# Export helpers
# -----------------------------------------------------------------------------


def table_to_export_dict(t: TableInfo) -> Dict[str, Any]:
    return {
        "table": t.full_name,
        "schema": t.schema_name,
        "name": t.table_name,
        "module": t.module,
        "purpose": t.purpose,
        "row_count": t.row_count,
        "notes": t.notes,
        "columns": [
            {
                "name": c.column_name,
                "type": c.data_type,
                "nullable": c.nullable,
                "primary_key": c.is_primary_key,
                "comment": c.comment,
            }
            for c in sorted(t.columns, key=lambda x: x.ordinal_position)
        ],
    }


def relationship_to_export_dict(r: Relationship) -> Dict[str, Any]:
    return {
        "id": r.id,
        "context_id": r.context_id,
        "active": r.active,
        "type": r.relationship_type,
        "confidence": r.confidence,
        "cardinality": r.cardinality,
        "source": {
            "table": r.source_full_table,
            "column": r.source_column,
        },
        "target": {
            "table": r.target_full_table,
            "column": r.target_column,
        },
        "join_type": r.join_type,
        "join_rule": f"{r.source_full_table}.{r.source_column} = {r.target_full_table}.{r.target_column}",
        "condition_sql": r.condition_sql,
        "extra_join_sql": r.extra_join_sql,
        "example_join_clause": r.join_clause("src", "tgt"),
        "description": r.description,
    }


def export_json(state: ErdState, only_active: bool = True) -> str:
    rels = list(state.relationships.values())
    if only_active:
        rels = [r for r in rels if r.active]

    payload = {
        "exported_at": datetime.now(UTC).isoformat(),
        "app_version": APP_VERSION,
        "app_version_name": APP_VERSION_NAME,
        "export_version": "1.1",
        "database_name": state.database_name,
        "loaded_at": state.loaded_at,
        "instructions_for_chatgpt": (
            "Use this schema map to write SQL queries. Prefer active relationships. "
            "Respect conditional relationships, especially where a source table uses Item_Type, Module, Status, Date ranges, "
            "or other discriminator columns to determine which target table applies. "
            "When uncertain, ask for confirmation or produce a SELECT preview before INSERT/UPDATE/DELETE."
        ),
        "relationship_contexts": {k: asdict(v) for k, v in state.relationship_contexts.items()},
        "active_context_id": state.active_context_id,
        "tables": [table_to_export_dict(t) for t in state.tables.values()],
        "relationships": [relationship_to_export_dict(r) for r in rels],
    }
    return json.dumps(payload, indent=2)


def export_markdown(state: ErdState, selected_tables: Optional[List[str]] = None, only_active: bool = True) -> str:
    tables = state.tables
    if selected_tables:
        tables = {k: v for k, v in tables.items() if k in selected_tables}

    rels = list(state.relationships.values())
    if only_active:
        rels = [r for r in rels if r.active]
    if selected_tables:
        selected = set(selected_tables)
        rels = [r for r in rels if r.source_full_table in selected or r.target_full_table in selected]

    lines: List[str] = []
    lines.append("# Database Entity Relationship Map")
    lines.append("")
    lines.append(f"App Version: `{APP_VERSION}`")
    lines.append(f"Database / Source: `{state.database_name or 'Unknown'}`")
    lines.append(f"Loaded at: `{state.loaded_at or 'Unknown'}`")
    if state.active_context_id and state.active_context_id in state.relationship_contexts:
        ctx = state.relationship_contexts[state.active_context_id]
        lines.append(f"Relationship Context: `{ctx.name}`")
        lines.append(f"Context Type: `{ctx.context_type}`")
        lines.append(f"Context Status: `{ctx.status}`")
    lines.append("")
    lines.append("## How to use this map for SQL generation")
    lines.append("- Use the `Relationships` section as the approved join map.")
    lines.append("- Use `conditional` relationships only when their condition is satisfied.")
    lines.append("- If a relationship is `inferred`, treat it as lower confidence unless verified.")
    lines.append("- For data-changing SQL, produce a SELECT preview first.")
    lines.append("")

    lines.append("## Tables")
    for t in sorted(tables.values(), key=lambda x: x.full_name.lower()):
        lines.append(f"\n### `{t.full_name}`")
        if t.module:
            lines.append(f"Module: {t.module}")
        if t.purpose:
            lines.append(f"Purpose: {t.purpose}")
        if t.row_count is not None:
            lines.append(f"Approx row count: {t.row_count}")
        if t.notes:
            lines.append(f"Notes: {t.notes}")
        lines.append("")
        lines.append("| Column | Type | Nullable | PK | Comment |")
        lines.append("|---|---:|:---:|:---:|---|")
        for c in sorted(t.columns, key=lambda x: x.ordinal_position):
            lines.append(
                f"| `{c.column_name}` | `{c.data_type}` | {'Yes' if c.nullable else 'No'} | "
                f"{'Yes' if c.is_primary_key else ''} | {c.comment or ''} |"
            )

    lines.append("\n## Relationships")
    if not rels:
        lines.append("No relationships recorded.")
    else:
        lines.append("| Type | Confidence | Source | Target | Rule / Condition | Notes |")
        lines.append("|---|---:|---|---|---|---|")
        for r in sorted(rels, key=lambda x: (x.source_full_table.lower(), x.target_full_table.lower())):
            rule = f"`{r.source_full_table}.{r.source_column}` = `{r.target_full_table}.{r.target_column}`"
            if r.condition_sql:
                rule += f"<br>Condition: `{r.condition_sql}`"
            if r.extra_join_sql:
                rule += f"<br>Extra join: `{r.extra_join_sql}`"
            lines.append(
                f"| {r.relationship_type} | {r.confidence:.2f} | "
                f"`{r.source_full_table}` | `{r.target_full_table}` | {rule} | {r.description or ''} |"
            )

    lines.append("\n## Query-generation rules for ChatGPT")
    lines.append("When generating SQL from this ERD, follow these rules:")
    lines.append("1. Start from the table that contains the main requested entity or transaction.")
    lines.append("2. Join only through relationships listed above unless the user authorises a new inferred join.")
    lines.append("3. For conditional relationships, include the condition in the ON clause or WHERE clause as appropriate.")
    lines.append("4. For optional relationships, use LEFT JOIN unless the user requests only matched records.")
    lines.append("5. For INSERT/UPDATE/DELETE operations, first generate a SELECT query for review.")

    return "\n".join(lines)


def export_mermaid(state: ErdState, only_active: bool = True) -> str:
    lines = ["erDiagram"]

    for t in sorted(state.tables.values(), key=lambda x: x.full_name.lower()):
        safe_table = re.sub(r"[^A-Za-z0-9_]", "_", t.full_name)
        lines.append(f"  {safe_table} {{")
        for c in sorted(t.columns, key=lambda x: x.ordinal_position):
            dtype = re.sub(r"[^A-Za-z0-9_]", "_", c.data_type or "unknown")[:40]
            cname = re.sub(r"[^A-Za-z0-9_]", "_", c.column_name)
            pk = " PK" if c.is_primary_key else ""
            lines.append(f"    {dtype} {cname}{pk}")
        lines.append("  }")

    rels = [r for r in state.relationships.values() if (r.active or not only_active)]
    for r in rels:
        src = re.sub(r"[^A-Za-z0-9_]", "_", r.source_full_table)
        tgt = re.sub(r"[^A-Za-z0-9_]", "_", r.target_full_table)
        label_parts = [r.source_column, r.target_column]
        if r.relationship_type == "conditional" and r.condition_sql:
            label_parts.append("conditional")
        label = " / ".join(label_parts).replace('"', "'")

        if r.cardinality == "one-to-many":
            connector = "||--o{"
        elif r.cardinality == "many-to-one":
            connector = "}o--||"
        elif r.cardinality == "one-to-one":
            connector = "||--||"
        else:
            connector = "}o--o{"
        lines.append(f"  {src} {connector} {tgt} : \"{label}\"")

    return "\n".join(lines)


def export_dot(state: ErdState, only_active: bool = True) -> str:
    lines = ["digraph ERD {", "  graph [rankdir=LR];", "  node [shape=record, fontsize=10];"]

    for t in sorted(state.tables.values(), key=lambda x: x.full_name.lower()):
        node_id = re.sub(r"[^A-Za-z0-9_]", "_", t.full_name)
        cols = []
        for c in sorted(t.columns, key=lambda x: x.ordinal_position)[:30]:
            pk = "*" if c.is_primary_key else ""
            cols.append(f"{pk}{c.column_name}")
        label = "{" + t.full_name + "|" + "\\l".join(cols) + "\\l}"
        lines.append(f'  {node_id} [label="{label}"];')

    rels = [r for r in state.relationships.values() if (r.active or not only_active)]
    for r in rels:
        src = re.sub(r"[^A-Za-z0-9_]", "_", r.source_full_table)
        tgt = re.sub(r"[^A-Za-z0-9_]", "_", r.target_full_table)
        label = f"{r.source_column} → {r.target_column}"
        if r.relationship_type == "conditional":
            label += " [conditional]"
        lines.append(f'  {src} -> {tgt} [label="{label}"];')

    lines.append("}")
    return "\n".join(lines)


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


def context_display_name(state: ErdState, context_id: str) -> str:
    if not context_id:
        return "Global / Unassigned"
    ctx = state.relationship_contexts.get(context_id)
    if not ctx:
        return "Missing context"
    return ctx.name


def get_context_table_set(state: ErdState, context_id: str) -> set[str]:
    ctx = state.relationship_contexts.get(context_id)
    if not ctx:
        return set(state.tables.keys())
    return {t for t in ctx.included_tables if t in state.tables}


def get_context_tables(state: ErdState, context_id: str) -> Dict[str, TableInfo]:
    table_set = get_context_table_set(state, context_id)
    if not table_set:
        return {}
    return {k: v for k, v in state.tables.items() if k in table_set}


def get_relationships_for_context(state: ErdState, context_id: str, include_global: bool = False) -> Dict[str, Relationship]:
    return {
        rid: rel
        for rid, rel in state.relationships.items()
        if rel.context_id == context_id or (include_global and not rel.context_id)
    }


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


VALID_RELATIONSHIP_TYPES = {"explicit_fk", "imported", "manual", "inferred", "conditional"}
VALID_JOIN_TYPES = {"LEFT JOIN", "INNER JOIN", "RIGHT JOIN", "FULL OUTER JOIN"}
VALID_CARDINALITIES = {"one-to-one", "one-to-many", "many-to-one", "many-to-many"}


def relationship_context_warning(state: ErdState) -> None:
    ctx = get_active_context(state)
    if not ctx:
        st.warning("Create or select a relationship context before adding context-scoped relationships.")
    elif not get_context_table_set(state, ctx.id):
        st.warning("The active relationship context has no assigned tables. Add tables in the Relationship Contexts tab first.")


def validate_relationships(state: ErdState, context_id: Optional[str] = None) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    rels = state.relationships
    if context_id is not None:
        rels = get_relationships_for_context(state, context_id)

    for rel in rels.values():
        errors: List[str] = []
        warnings: List[str] = []

        source_table = state.tables.get(rel.source_full_table)
        target_table = state.tables.get(rel.target_full_table)

        if not source_table:
            errors.append("Source table missing")
        elif rel.source_column not in {c.column_name for c in source_table.columns}:
            errors.append("Source column missing")

        if not target_table:
            errors.append("Target table missing")
        elif rel.target_column not in {c.column_name for c in target_table.columns}:
            errors.append("Target column missing")

        if rel.relationship_type not in VALID_RELATIONSHIP_TYPES:
            warnings.append("Invalid or non-standard relationship type")

        if rel.join_type not in VALID_JOIN_TYPES:
            warnings.append("Invalid or non-standard join type")

        if rel.cardinality not in VALID_CARDINALITIES:
            warnings.append("Invalid or non-standard cardinality")

        if rel.relationship_type == "conditional" and not rel.condition_sql.strip():
            errors.append("Conditional relationship missing condition_sql")

        if rel.context_id and rel.context_id not in state.relationship_contexts:
            warnings.append("Relationship references missing context")

        if not rel.context_id:
            warnings.append("Relationship is global/unassigned")

        status = "Valid"
        if errors:
            status = "Broken"
        elif warnings:
            status = "Warning"

        rows.append(
            {
                "status": status,
                "context": context_display_name(state, rel.context_id),
                "type": rel.relationship_type,
                "active": rel.active,
                "source_table": rel.source_full_table,
                "source_column": rel.source_column,
                "target_table": rel.target_full_table,
                "target_column": rel.target_column,
                "condition_sql": rel.condition_sql,
                "errors": "; ".join(errors),
                "warnings": "; ".join(warnings),
                "id": rel.id,
            }
        )

    return pd.DataFrame(rows)


def relationship_quality_summary(state: ErdState, context_id: Optional[str] = None) -> Dict[str, int]:
    validation = validate_relationships(state, context_id=context_id)
    if validation.empty:
        return {
            "total": 0,
            "active": 0,
            "manual": 0,
            "imported": 0,
            "inferred": 0,
            "conditional": 0,
            "valid": 0,
            "warnings": 0,
            "broken": 0,
        }

    return {
        "total": int(len(validation)),
        "active": int(validation["active"].sum()),
        "manual": int((validation["type"] == "manual").sum()),
        "imported": int((validation["type"] == "imported").sum()),
        "inferred": int((validation["type"] == "inferred").sum()),
        "conditional": int((validation["type"] == "conditional").sum()),
        "valid": int((validation["status"] == "Valid").sum()),
        "warnings": int((validation["status"] == "Warning").sum()),
        "broken": int((validation["status"] == "Broken").sum()),
    }


def validate_import_preview(tables: Dict[str, TableInfo], relationships: Dict[str, Relationship]) -> Dict[str, Any]:
    warnings: List[str] = []
    errors: List[str] = []
    table_column_pairs = set()
    duplicate_columns = 0
    total_columns = 0

    for table in tables.values():
        if not table.table_name:
            errors.append("A table row is missing table_name")
        for col in table.columns:
            total_columns += 1
            if not col.column_name:
                errors.append(f"{table.full_name} has a missing column_name")
            pair = (table.full_name.lower(), col.column_name.lower())
            if pair in table_column_pairs:
                duplicate_columns += 1
            table_column_pairs.add(pair)

    if duplicate_columns:
        warnings.append(f"Duplicate table/column rows detected: {duplicate_columns}")

    temp_state = ErdState(tables=tables, relationships=relationships)
    rel_validation = validate_relationships(temp_state)
    broken_relationships = 0 if rel_validation.empty else int((rel_validation["status"] == "Broken").sum())
    warning_relationships = 0 if rel_validation.empty else int((rel_validation["status"] == "Warning").sum())

    if broken_relationships:
        errors.append(f"Broken imported relationships: {broken_relationships}")
    if warning_relationships:
        warnings.append(f"Imported relationships with warnings: {warning_relationships}")

    return {
        "tables": len(tables),
        "columns": total_columns,
        "relationships": len(relationships),
        "conditional_relationships": sum(1 for r in relationships.values() if r.relationship_type == "conditional"),
        "warnings": warnings,
        "errors": errors,
        "relationship_validation": rel_validation,
    }


def export_markdown_with_context(state: ErdState, context_id: Optional[str], only_active: bool = True) -> str:
    if not context_id:
        return export_markdown(state, only_active=only_active)

    ctx = state.relationship_contexts.get(context_id)
    scoped_state = build_context_scoped_state(state, context_id)
    if not ctx:
        return export_markdown(scoped_state, only_active=only_active)

    line_break = chr(10)
    header = [
        "# Named Relationship Context Export",
        "",
        f"App Version: `{APP_VERSION}`",
        f"Export Scope: `{ctx.name}`",
        f"Relationship Type: `{ctx.context_type}`",
        f"Status: `{ctx.status}`",
        f"Owner / Reviewer: `{ctx.owner_reviewer or ''}`",
        "",
        "## Context Notes",
        f"Purpose: {ctx.purpose or ''}",
        f"Business Context: {ctx.business_context or ''}",
        f"Primary Join Path: {ctx.primary_join_path or ''}",
        f"Conditional Logic Notes: {ctx.conditional_logic_notes or ''}",
        f"Query Guidance: {ctx.query_guidance or ''}",
        f"Comments: {ctx.comments or ''}",
        "",
    ]
    return line_break.join(header) + line_break + export_markdown(scoped_state, only_active=only_active)


def export_json_with_context(state: ErdState, context_id: Optional[str], only_active: bool = True) -> str:
    if not context_id:
        return export_json(state, only_active=only_active)

    scoped_state = build_context_scoped_state(state, context_id)
    return export_json(scoped_state, only_active=only_active)


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

    tab_contexts, tab_tables, tab_relationships, tab_infer, tab_conditional, tab_erd, tab_export = st.tabs([
        "Relationship Contexts",
        "Tables",
        "Relationships",
        "Infer Links",
        "Conditional Links",
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

            with st.expander("Deactivate / delete a relationship"):
                rel_options = [
                    f"{r.relationship_type}: {r.source_full_table}.{r.source_column} -> {r.target_full_table}.{r.target_column} [{r.id}]"
                    for r in state.relationships.values()
                ]
                choice = st.selectbox("Relationship", rel_options)
                chosen_id = choice.split("[")[-1].rstrip("]") if choice else ""
                col1, col2, col3 = st.columns(3)
                if col1.button("Toggle active") and chosen_id in state.relationships:
                    state.relationships[chosen_id].active = not state.relationships[chosen_id].active
                    save_state(state)
                    st.rerun()
                if col2.button("Delete") and chosen_id in state.relationships:
                    del state.relationships[chosen_id]
                    save_state(state)
                    st.rerun()
                if col3.button("Save registry"):
                    save_state(state)
                    st.success("Saved.")

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

            description = st.text_area("Description / business meaning", key="manual_description")
            extra_join_sql = st.text_input("Extra join condition, optional", placeholder="e.g. src.ValidTo IS NULL")

            if st.button("Add manual relationship", type="primary"):
                ss, stbl = split_full_table(source_full)
                ts, ttbl = split_full_table(target_full)
                rid = rel_id(ss, stbl, source_col, ts, ttbl, target_col, "manual", extra_join_sql)
                state.relationships[rid] = Relationship(
                    id=rid,
                    context_id=active_ctx.id,
                    source_schema=ss,
                    source_table=stbl,
                    source_column=source_col,
                    target_schema=ts,
                    target_table=ttbl,
                    target_column=target_col,
                    relationship_type="manual",
                    cardinality=cardinality,
                    join_type=join_type,
                    confidence=confidence,
                    extra_join_sql=extra_join_sql,
                    description=description,
                )
                save_state(state)
                st.success("Manual relationship added.")
                st.rerun()
        else:
            relationship_context_warning(state)
            st.info("Assign at least two tables to the active relationship context before adding manual relationships.")

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
    # Conditional relationships tab
    # ---------------------------------------------------------------------
    with tab_conditional:
        st.subheader("Conditional relationships")
        active_ctx = get_active_context(state)
        scoped_tables = get_context_tables(state, active_ctx.id) if active_ctx else {}
        if active_ctx:
            st.info(f"Conditional relationship scope: {active_ctx.name} — {len(scoped_tables)} assigned tables")
        else:
            st.warning("Create or select a relationship context before adding conditional relationships.")
        st.write(
            "Use this when a table links to different target tables depending on a discriminator field, "
            "such as `Item_Type = 3` meaning Property, `Item_Type = 1200` meaning Animal, etc."
        )

        if active_ctx:
            context_conditionals = [
                rel for rel in state.relationships.values()
                if rel.context_id == active_ctx.id and rel.relationship_type == "conditional"
            ]
            with st.expander("Review / edit existing conditional relationships", expanded=bool(context_conditionals)):
                if not context_conditionals:
                    st.info("No conditional relationships have been added to this context yet.")
                else:
                    cond_options = {
                        f"{rel.source_full_table}.{rel.source_column} -> {rel.target_full_table}.{rel.target_column} [{rel.id}]": rel.id
                        for rel in context_conditionals
                    }
                    selected_cond_label = st.selectbox("Conditional relationship", list(cond_options.keys()), key="edit_conditional_select")
                    selected_cond_id = cond_options[selected_cond_label]
                    rel = state.relationships[selected_cond_id]
                    rel.active = st.checkbox("Active", value=rel.active, key=f"edit_cond_active_{rel.id}")
                    rel.condition_sql = st.text_input("Condition SQL", value=rel.condition_sql, key=f"edit_cond_sql_{rel.id}")
                    rel.extra_join_sql = st.text_input("Extra join SQL", value=rel.extra_join_sql, key=f"edit_cond_extra_{rel.id}")
                    rel.description = st.text_area("Description / business meaning", value=rel.description, key=f"edit_cond_desc_{rel.id}")
                    csave, cdelete = st.columns(2)
                    if csave.button("Save conditional relationship", key=f"save_cond_{rel.id}"):
                        save_state(state)
                        st.success("Saved conditional relationship.")
                    if cdelete.button("Delete conditional relationship", key=f"delete_cond_{rel.id}"):
                        del state.relationships[selected_cond_id]
                        save_state(state)
                        st.success("Deleted conditional relationship.")
                        st.rerun()

        if active_ctx and len(scoped_tables) >= 2:
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Source/link table filter**")
                _, _, cond_source_options = render_table_filter_controls(state, key_prefix="cond_source")
                cond_source_options = [t for t in cond_source_options if t in scoped_tables] or sorted(scoped_tables.keys(), key=str.lower)
                source_full = st.selectbox("Source/link table", cond_source_options, key="cond_source_table")
                source_col = st.selectbox("Source item/key column", get_table_columns(state, source_full), key="cond_source_col")
                discriminator_col = st.selectbox(
                    "Discriminator column",
                    [""] + get_table_columns(state, source_full),
                    key="cond_discriminator_col",
                )
                discriminator_value = st.text_input("Discriminator value", placeholder="e.g. 3, 1039, 1200")
            with c2:
                st.markdown("**Target table filter**")
                _, _, cond_target_options = render_table_filter_controls(state, key_prefix="cond_target")
                cond_target_options = [t for t in cond_target_options if t in scoped_tables] or sorted(scoped_tables.keys(), key=str.lower)
                target_full = st.selectbox("Target table", cond_target_options, key="cond_target_table")
                target_col = st.selectbox("Target key column", get_table_columns(state, target_full), key="cond_target_col")
                join_type = st.selectbox("Join type", ["LEFT JOIN", "INNER JOIN"], key="cond_join_type")
                cardinality = st.selectbox("Cardinality", ["many-to-one", "one-to-many", "one-to-one", "many-to-many"], key="cond_cardinality")

            condition_sql = st.text_input(
                "Condition SQL",
                value=(f"src.{discriminator_col} = {discriminator_value}" if discriminator_col and discriminator_value else ""),
                help="Use aliases src and tgt. Example: src.Item_Type = 3",
            )
            extra_join_sql = st.text_input(
                "Extra join SQL, optional",
                key="cond_extra",
                placeholder="e.g. src.ValidTo IS NULL OR src.ValidTo >= GETDATE()",
            )
            description = st.text_area(
                "Business meaning",
                placeholder="Example: Item_Type = 3 means this association row links to PropertyWise.Properties.",
                key="cond_desc",
            )

            if st.button("Add conditional relationship", type="primary"):
                ss, stbl = split_full_table(source_full)
                ts, ttbl = split_full_table(target_full)
                rid = rel_id(ss, stbl, source_col, ts, ttbl, target_col, "conditional", condition_sql)
                state.relationships[rid] = Relationship(
                    id=rid,
                    context_id=active_ctx.id,
                    source_schema=ss,
                    source_table=stbl,
                    source_column=source_col,
                    target_schema=ts,
                    target_table=ttbl,
                    target_column=target_col,
                    relationship_type="conditional",
                    cardinality=cardinality,
                    join_type=join_type,
                    confidence=1.0,
                    condition_sql=condition_sql,
                    extra_join_sql=extra_join_sql,
                    description=description,
                )
                save_state(state)
                st.success("Conditional relationship added.")
                st.rerun()

        with st.expander("Example conditional relationships for CouncilWise / PropertyWise style data"):
            st.code(
                """Associations_Role_Based.Item_Id -> Properties.Property_Id
Condition: src.Item_Type = 3
Meaning: Item_Type 3 represents Property relationships.

Associations_Role_Based.Item_Id -> RegApps.RegApp_Id
Condition: src.Item_Type = 1039
Meaning: Item_Type 1039 represents Regulatory Applications.

Associations_Role_Based.Item_Id -> Animals.Animal_Id
Condition: src.Item_Type = 1200
Meaning: Item_Type 1200 represents Animal records.

Associations_Role_Based.Item_Id -> RegEntities.RegEntity_Id
Condition: src.Item_Type = 1080
Meaning: Item_Type 1080 represents Regulatory Entities.
""",
                language="text",
            )

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

            dot = export_dot(display_state, only_active=only_active)
            st.graphviz_chart(dot, width="stretch")
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
