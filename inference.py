from __future__ import annotations

import re
from typing import Dict, List, Tuple

from models import Relationship, TableInfo


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

