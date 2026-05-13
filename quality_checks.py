
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from models import ErdState, Relationship, TableInfo


def _full_table(schema_name: str, table_name: str) -> str:
    schema = (schema_name or "").strip()
    table = (table_name or "").strip()
    return f"{schema}.{table}" if schema else table


def _relationship_tables(rel: Relationship) -> Tuple[str, str]:
    source_full = getattr(rel, "source_full_table", None) or _full_table(
        getattr(rel, "source_schema", ""),
        getattr(rel, "source_table", ""),
    )
    target_full = getattr(rel, "target_full_table", None) or _full_table(
        getattr(rel, "target_schema", ""),
        getattr(rel, "target_table", ""),
    )
    return source_full, target_full


def _context_tables(state: ErdState, context_id: Optional[str]) -> Dict[str, TableInfo]:
    if not context_id:
        return dict(state.tables)

    context = state.relationship_contexts.get(context_id)
    if not context:
        return {}

    table_keys = set(getattr(context, "table_keys", []) or [])
    if not table_keys:
        table_keys = set(getattr(context, "tables", []) or [])

    return {key: table for key, table in state.tables.items() if key in table_keys}


def _context_relationships(state: ErdState, context_id: Optional[str]) -> Dict[str, Relationship]:
    if not context_id:
        return dict(state.relationships)

    return {
        rel_id: rel
        for rel_id, rel in state.relationships.items()
        if getattr(rel, "context_id", "") == context_id
    }


def build_export_quality_report(state: ErdState, context_id: Optional[str] = None) -> Dict[str, Any]:
    tables = _context_tables(state, context_id)
    relationships = _context_relationships(state, context_id)

    table_keys: Set[str] = set(tables.keys())
    relationship_table_keys: Set[str] = set()

    broken_relationships: List[Dict[str, Any]] = []
    missing_descriptions: List[Dict[str, Any]] = []
    conditional_missing_condition: List[Dict[str, Any]] = []

    active_relationships = []
    conditional_relationships = []

    for rel in relationships.values():
        source_full, target_full = _relationship_tables(rel)
        is_active = bool(getattr(rel, "active", True))
        rel_type = (getattr(rel, "relationship_type", "") or "").lower()
        condition_sql = (getattr(rel, "condition_sql", "") or "").strip()

        if is_active:
            active_relationships.append(rel)

        if rel_type == "conditional" or condition_sql:
            conditional_relationships.append(rel)
            if not condition_sql:
                conditional_missing_condition.append(
                    {
                        "relationship_id": getattr(rel, "id", ""),
                        "issue": "Conditional relationship is missing condition SQL.",
                        "source": source_full,
                        "target": target_full,
                    }
                )

        if source_full in table_keys:
            relationship_table_keys.add(source_full)
        if target_full in table_keys:
            relationship_table_keys.add(target_full)

        if source_full not in table_keys or target_full not in table_keys:
            broken_relationships.append(
                {
                    "relationship_id": getattr(rel, "id", ""),
                    "issue": "Relationship references a table outside the export scope or a missing table.",
                    "source": source_full,
                    "target": target_full,
                    "source_found": source_full in table_keys,
                    "target_found": target_full in table_keys,
                }
            )

        if not (getattr(rel, "description", "") or "").strip():
            missing_descriptions.append(
                {
                    "relationship_id": getattr(rel, "id", ""),
                    "source": source_full,
                    "target": target_full,
                    "issue": "Relationship is missing a business description.",
                }
            )

    tables_without_relationships = sorted(table_keys - relationship_table_keys)

    columns_included = sum(len(getattr(table, "columns", []) or []) for table in tables.values())

    context = state.relationship_contexts.get(context_id) if context_id else None

    report = {
        "context_id": context_id or "",
        "context_name": getattr(context, "name", "Whole database") if context else "Whole database",
        "context_type": getattr(context, "context_type", "") if context else "",
        "tables_included": len(tables),
        "columns_included": columns_included,
        "relationships_included": len(relationships),
        "active_relationships": len(active_relationships),
        "conditional_relationships": len(conditional_relationships),
        "broken_relationships": broken_relationships,
        "broken_relationship_count": len(broken_relationships),
        "tables_without_relationships": tables_without_relationships,
        "tables_without_relationship_count": len(tables_without_relationships),
        "relationships_missing_descriptions": missing_descriptions,
        "relationships_missing_descriptions_count": len(missing_descriptions),
        "conditional_relationships_missing_condition_sql": conditional_missing_condition,
        "conditional_relationships_missing_condition_sql_count": len(conditional_missing_condition),
    }

    report["score"] = score_export_quality(report)
    report["status"] = quality_status_label(report["score"])
    report["warnings"] = build_quality_warnings(report)

    return report


def score_export_quality(report: Dict[str, Any]) -> int:
    score = 100

    if report.get("tables_included", 0) == 0:
        return 0

    if report.get("broken_relationship_count", 0) > 0:
        score -= 20

    if report.get("relationships_included", 0) == 0:
        score -= 15

    if report.get("tables_without_relationship_count", 0) > 0:
        score -= 10

    if report.get("relationships_missing_descriptions_count", 0) > 0:
        score -= 10

    if report.get("conditional_relationships_missing_condition_sql_count", 0) > 0:
        score -= 10

    return max(0, min(100, score))


def quality_status_label(score: int) -> str:
    if score >= 90:
        return "Excellent"
    if score >= 75:
        return "Good"
    if score >= 50:
        return "Needs Review"
    return "Incomplete"


def build_quality_warnings(report: Dict[str, Any]) -> List[str]:
    warnings: List[str] = []

    if report.get("tables_included", 0) == 0:
        warnings.append("No tables are included in the export scope.")

    if report.get("relationships_included", 0) == 0:
        warnings.append("No relationships are included. SQL guidance may be incomplete.")

    if report.get("broken_relationship_count", 0) > 0:
        warnings.append("Some relationships reference missing or out-of-scope tables.")

    if report.get("tables_without_relationship_count", 0) > 0:
        warnings.append("Some included tables are not connected by relationships.")

    if report.get("relationships_missing_descriptions_count", 0) > 0:
        warnings.append("Some relationships are missing business descriptions.")

    if report.get("conditional_relationships_missing_condition_sql_count", 0) > 0:
        warnings.append("Some conditional relationships are missing condition SQL.")

    return warnings


def report_to_issue_rows(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    for table_name in report.get("tables_without_relationships", []):
        rows.append(
            {
                "category": "Table without relationship",
                "item": table_name,
                "issue": "Table is included in the export but has no mapped relationship.",
            }
        )

    for item in report.get("broken_relationships", []):
        rows.append(
            {
                "category": "Broken relationship",
                "item": item.get("relationship_id", ""),
                "issue": item.get("issue", ""),
                "source": item.get("source", ""),
                "target": item.get("target", ""),
            }
        )

    for item in report.get("relationships_missing_descriptions", []):
        rows.append(
            {
                "category": "Missing relationship description",
                "item": item.get("relationship_id", ""),
                "issue": item.get("issue", ""),
                "source": item.get("source", ""),
                "target": item.get("target", ""),
            }
        )

    for item in report.get("conditional_relationships_missing_condition_sql", []):
        rows.append(
            {
                "category": "Missing condition SQL",
                "item": item.get("relationship_id", ""),
                "issue": item.get("issue", ""),
                "source": item.get("source", ""),
                "target": item.get("target", ""),
            }
        )

    return rows
