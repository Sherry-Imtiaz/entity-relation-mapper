from __future__ import annotations

import io
import re
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from models import ColumnInfo, Relationship, TableInfo


def singularize(name: str) -> str:
    n = name.lower()
    if n.endswith("ies"):
        return n[:-3] + "y"
    if n.endswith("ses"):
        return n[:-2]
    if n.endswith("s") and not n.endswith("ss"):
        return n[:-1]
    return n


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

