from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from models import ErdState

VALID_RELATIONSHIP_TYPES = {"explicit_fk", "imported", "manual", "inferred", "conditional"}
VALID_JOIN_TYPES = {"LEFT JOIN", "INNER JOIN", "RIGHT JOIN", "FULL OUTER JOIN"}
VALID_CARDINALITIES = {"one-to-one", "one-to-many", "many-to-one", "many-to-many"}

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

