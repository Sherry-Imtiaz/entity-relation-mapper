"""
Entity Relation Mapper / ERD Exporter
-------------------------------------

Purpose:
- Connect to a database and load all tables + columns.
- Detect existing foreign keys where available.
- Suggest likely relationships based on naming patterns such as Customer_Id, Associate_Id, Item_Id, etc.
- Allow manual relationships and conditional relationships.
- Save/load ERD state locally.
- Export a ChatGPT-friendly relationship map for query generation.

Install:
    pip install streamlit pandas sqlalchemy pyodbc

Run:
    streamlit run entity_relation_mapper_app.py

Example SQL Server connection string:
    mssql+pyodbc://USER:PASSWORD@SERVER/DATABASE?driver=ODBC+Driver+17+for+SQL+Server&TrustServerCertificate=yes

Example trusted connection:
    mssql+pyodbc://SERVER/DATABASE?driver=ODBC+Driver+17+for+SQL+Server&trusted_connection=yes&TrustServerCertificate=yes

Notes:
- This stores local state in ./erd_mapper_state.json
- It does not modify your source database.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError


STATE_FILE = Path("erd_mapper_state.json")


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
    relationship_type: str = "manual"  # explicit_fk, inferred, manual, conditional
    cardinality: str = "many-to-one"   # one-to-one, one-to-many, many-to-one, many-to-many
    join_type: str = "LEFT JOIN"
    active: bool = True
    confidence: float = 1.0
    condition_sql: str = ""            # e.g. a.Item_Type = 3
    extra_join_sql: str = ""           # e.g. AND a.ValidTo IS NULL
    description: str = ""
    source_alias: str = "src"
    target_alias: str = "tgt"
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

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
class ErdState:
    connection_label: str = ""
    database_name: str = ""
    loaded_at: str = ""
    tables: Dict[str, TableInfo] = field(default_factory=dict)
    relationships: Dict[str, Relationship] = field(default_factory=dict)


# -----------------------------------------------------------------------------
# State helpers
# -----------------------------------------------------------------------------


def table_key(schema_name: str, table_name: str) -> str:
    return f"{schema_name}.{table_name}" if schema_name else table_name


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
    }


def deserialize_state(payload: Dict[str, Any]) -> ErdState:
    tables: Dict[str, TableInfo] = {}
    for k, t in payload.get("tables", {}).items():
        cols = [ColumnInfo(**c) for c in t.get("columns", [])]
        t_clean = {kk: vv for kk, vv in t.items() if kk != "columns"}
        tables[k] = TableInfo(**t_clean, columns=cols)

    relationships: Dict[str, Relationship] = {}
    for k, r in payload.get("relationships", {}).items():
        relationships[k] = Relationship(**r)

    return ErdState(
        connection_label=payload.get("connection_label", ""),
        database_name=payload.get("database_name", ""),
        loaded_at=payload.get("loaded_at", ""),
        tables=tables,
        relationships=relationships,
    )


def save_state(state: ErdState, path: Path = STATE_FILE) -> None:
    path.write_text(json.dumps(serialize_state(state), indent=2), encoding="utf-8")


def load_state(path: Path = STATE_FILE) -> ErdState:
    if not path.exists():
        return default_state()
    return deserialize_state(json.loads(path.read_text(encoding="utf-8")))


def merge_tables_keep_metadata(existing: Dict[str, TableInfo], incoming: Dict[str, TableInfo]) -> Dict[str, TableInfo]:
    """Refresh columns/row counts while preserving user-entered purpose/module/notes."""
    merged = dict(incoming)
    for k, old in existing.items():
        if k in merged:
            merged[k].purpose = old.purpose
            merged[k].module = old.module
            merged[k].notes = old.notes
            old_comments = {c.column_name: c.comment for c in old.columns if c.comment}
            for col in merged[k].columns:
                col.comment = old_comments.get(col.column_name, col.comment)
    return merged


# -----------------------------------------------------------------------------
# DB introspection
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

    # SQL Server fast path using sys.partitions
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

    # Generic fallback can be slow. Only count small/moderate schemas on demand.
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

    # Strong: source Associate_Id to target Associate_Id / Id
    if sc == tc and (sc.endswith("id") or sc.endswith("no") or sc.endswith("number")):
        score += 0.45

    # Strong: source Property_Id to target Properties.Property_Id or Properties.Id
    if sc in {f"{tt}id", f"{tt_singular}id", f"{tt}no", f"{tt_singular}no"}:
        score += 0.45

    # Target column is likely PK/ID
    if tc in {"id", f"{tt}id", f"{tt_singular}id", f"{tt}no", f"{tt_singular}no"}:
        score += 0.25

    # Common council/database patterns
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
        "exported_at": datetime.utcnow().isoformat(),
        "database_name": state.database_name,
        "loaded_at": state.loaded_at,
        "instructions_for_chatgpt": (
            "Use this schema map to write SQL queries. Prefer active relationships. "
            "Respect conditional relationships, especially where a source table uses Item_Type, Module, Status, Date ranges, "
            "or other discriminator columns to determine which target table applies. "
            "When uncertain, ask for confirmation or produce a SELECT preview before INSERT/UPDATE/DELETE."
        ),
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
    lines.append(f"Database: `{state.database_name or 'Unknown'}`")
    lines.append(f"Loaded at: `{state.loaded_at or 'Unknown'}`")
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
    if "." in full_table:
        schema, table = full_table.split(".", 1)
        return schema, table
    return "", full_table


def get_table_columns(state: ErdState, full_table: str) -> List[str]:
    t = state.tables.get(full_table)
    if not t:
        return []
    return [c.column_name for c in sorted(t.columns, key=lambda x: x.ordinal_position)]


# -----------------------------------------------------------------------------
# Main Streamlit app
# -----------------------------------------------------------------------------


def main() -> None:
    st.set_page_config(page_title="Entity Relation Mapper", layout="wide")
    state = ensure_state()

    st.title("Entity Relation Mapper")
    st.caption("Load database tables, map relationships, add conditional joins, and export a ChatGPT-ready ERD map.")

    with st.sidebar:
        st.header("Database")
        connection_label = st.text_input("Connection label", value=state.connection_label or "Local / Client DB")
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
            test_clicked = st.button("Test", use_container_width=True)
        with col_b:
            load_clicked = st.button("Load DB", type="primary", use_container_width=True)

        st.divider()
        if st.button("Save state", use_container_width=True):
            save_state(state)
            st.success(f"Saved to {STATE_FILE}")

        uploaded_state = st.file_uploader("Import saved ERD state JSON", type=["json"])
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
                use_container_width=True,
            )

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
                state.database_name = database_name
                state.loaded_at = datetime.utcnow().isoformat()
                state.tables = merge_tables_keep_metadata(state.tables, incoming_tables)

                # Keep user manual/conditional relationships and add/update explicit FK relationships.
                existing_non_auto = {
                    k: r for k, r in state.relationships.items()
                    if r.relationship_type not in {"explicit_fk", "inferred"}
                }
                state.relationships = {**explicit, **existing_non_auto}
                save_state(state)
                st.success(f"Loaded {len(state.tables)} tables and {len(explicit)} explicit foreign-key relationships.")
                st.rerun()

    metric_cols = st.columns(4)
    metric_cols[0].metric("Tables", len(state.tables))
    metric_cols[1].metric("Relationships", len(state.relationships))
    metric_cols[2].metric("Active", sum(1 for r in state.relationships.values() if r.active))
    metric_cols[3].metric("Conditional", sum(1 for r in state.relationships.values() if r.relationship_type == "conditional"))

    tab_tables, tab_relationships, tab_infer, tab_conditional, tab_erd, tab_export = st.tabs([
        "Tables",
        "Relationships",
        "Infer Links",
        "Conditional Links",
        "ERD View",
        "Export for ChatGPT",
    ])

    # ---------------------------------------------------------------------
    # Tables tab
    # ---------------------------------------------------------------------
    with tab_tables:
        st.subheader("Tables and columns")
        if not state.tables:
            st.info("Load a database or import a saved ERD state to begin.")
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

            st.dataframe(columns_df(t), use_container_width=True, hide_index=True)

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
        df = relationships_df(state)
        if df.empty:
            st.info("No relationships yet. Load explicit foreign keys, infer links, or add manual relationships.")
        else:
            type_filter = st.multiselect(
                "Filter by type",
                sorted(df["type"].dropna().unique().tolist()),
                default=sorted(df["type"].dropna().unique().tolist()),
            )
            filtered = df[df["type"].isin(type_filter)] if type_filter else df
            st.dataframe(filtered.drop(columns=["id"]), use_container_width=True, hide_index=True)

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
        if len(state.tables) >= 2:
            table_names = sorted(state.tables.keys(), key=str.lower)
            c1, c2 = st.columns(2)
            with c1:
                source_full = st.selectbox("Source table", table_names, key="manual_source_table")
                source_col = st.selectbox("Source column", get_table_columns(state, source_full), key="manual_source_col")
            with c2:
                target_full = st.selectbox("Target table", table_names, key="manual_target_table")
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

    # ---------------------------------------------------------------------
    # Inference tab
    # ---------------------------------------------------------------------
    with tab_infer:
        st.subheader("Infer likely relationships")
        st.write(
            "This scans column names such as `Associate_Id`, `Property_Id`, `Item_Id`, `Customer_Id`, "
            "and tries to match them against likely ID columns in other tables. Review before accepting."
        )
        min_conf = st.slider("Minimum confidence", 0.40, 0.95, 0.65, 0.05)
        if st.button("Run inference"):
            with st.spinner("Inferring likely relationships..."):
                inferred = infer_relationships(state.tables, min_confidence=min_conf)
            st.session_state.inferred_relationships = inferred
            st.success(f"Found {len(inferred)} possible relationships.")

        inferred_relationships: Dict[str, Relationship] = st.session_state.get("inferred_relationships", {})
        if inferred_relationships:
            candidate_df = pd.DataFrame([relationship_to_export_dict(r) for r in inferred_relationships.values()])
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
                use_container_width=True,
                hide_index=True,
                column_config={"id": None},
            )
            if st.button("Accept selected inferred relationships", type="primary"):
                accepted_ids = edited.loc[edited["accept"] == True, "id"].tolist()  # noqa: E712
                for rid in accepted_ids:
                    state.relationships[rid] = inferred_relationships[rid]
                save_state(state)
                st.success(f"Accepted {len(accepted_ids)} inferred relationships.")
                st.rerun()

    # ---------------------------------------------------------------------
    # Conditional relationships tab
    # ---------------------------------------------------------------------
    with tab_conditional:
        st.subheader("Conditional relationships")
        st.write(
            "Use this when a table links to different target tables depending on a discriminator field, "
            "such as `Item_Type = 3` meaning Property, `Item_Type = 1200` meaning Animal, etc."
        )

        if len(state.tables) >= 2:
            table_names = sorted(state.tables.keys(), key=str.lower)
            c1, c2 = st.columns(2)
            with c1:
                source_full = st.selectbox("Source/link table", table_names, key="cond_source_table")
                source_col = st.selectbox("Source item/key column", get_table_columns(state, source_full), key="cond_source_col")
                discriminator_col = st.selectbox(
                    "Discriminator column",
                    [""] + get_table_columns(state, source_full),
                    key="cond_discriminator_col",
                )
                discriminator_value = st.text_input("Discriminator value", placeholder="e.g. 3, 1039, 1200")
            with c2:
                target_full = st.selectbox("Target table", table_names, key="cond_target_table")
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
Condition: Associations_Role_Based.Item_Type = 3
Meaning: Item_Type 3 represents Property relationships.

Associations_Role_Based.Item_Id -> RegApps.RegApp_Id
Condition: Associations_Role_Based.Item_Type = 1039
Meaning: Item_Type 1039 represents Regulatory Applications.

Associations_Role_Based.Item_Id -> Animals.Animal_Id
Condition: Associations_Role_Based.Item_Type = 1200
Meaning: Item_Type 1200 represents Animal records.

Associations_Role_Based.Item_Id -> RegEntities.RegEntity_Id
Condition: Associations_Role_Based.Item_Type = 1080
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
        if not state.tables:
            st.info("Load tables first.")
        else:
            dot = export_dot(state, only_active=only_active)
            st.graphviz_chart(dot, use_container_width=True)
            with st.expander("Mermaid ERD text"):
                mermaid = export_mermaid(state, only_active=only_active)
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
        selected_tables = st.multiselect(
            "Limit export to selected tables, optional",
            sorted(state.tables.keys(), key=str.lower),
            default=[],
        )

        c1, c2 = st.columns(2)
        with c1:
            md = export_markdown(state, selected_tables=selected_tables or None, only_active=only_active)
            st.download_button(
                "Download ChatGPT Markdown",
                data=md,
                file_name="chatgpt_erd_context.md",
                mime="text/markdown",
                use_container_width=True,
            )
        with c2:
            js = export_json(state, only_active=only_active)
            st.download_button(
                "Download JSON",
                data=js,
                file_name="chatgpt_erd_context.json",
                mime="application/json",
                use_container_width=True,
            )

        st.write("Preview:")
        st.code(md[:20000], language="markdown")
        if len(md) > 20000:
            st.warning("Preview truncated. Download the full Markdown export.")


if __name__ == "__main__":
    main()
