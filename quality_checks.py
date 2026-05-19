
from __future__ import annotations

import copy
import re
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from models import ErdState, Relationship, TableInfo


def normalise_table_key(value: str) -> str:
    text = (value or "").strip()
    text = text.replace("[", "").replace("]", "").replace('"', "").replace("`", "")
    text = re.sub(r"\s+", "", text)
    return text.lower()


def full_table(schema_name: str, table_name: str) -> str:
    schema = (schema_name or "").strip()
    table = (table_name or "").strip()
    return f"{schema}.{table}" if schema else table


def relationship_tables(rel: Relationship) -> Tuple[str, str]:
    source_full = getattr(rel, "source_full_table", None) or full_table(
        getattr(rel, "source_schema", ""),
        getattr(rel, "source_table", ""),
    )
    target_full = getattr(rel, "target_full_table", None) or full_table(
        getattr(rel, "target_schema", ""),
        getattr(rel, "target_table", ""),
    )
    return source_full, target_full


def table_lookup(state: ErdState) -> Dict[str, str]:
    lookup: Dict[str, str] = {}

    for key, table in getattr(state, "tables", {}).items():
        candidates = {
            key,
            getattr(table, "full_name", ""),
            full_table(getattr(table, "schema_name", ""), getattr(table, "table_name", "")),
            getattr(table, "table_name", ""),
        }

        for candidate in candidates:
            if candidate:
                lookup[normalise_table_key(candidate)] = key

    return lookup


def resolve_table_key(state: ErdState, table_ref: str) -> Optional[str]:
    if table_ref in getattr(state, "tables", {}):
        return table_ref
    return table_lookup(state).get(normalise_table_key(table_ref))


def _normalise_context_ids(
    context_id: Optional[str] = None,
    context_ids: Optional[Iterable[str]] = None,
) -> Optional[List[str]]:
    if context_ids is not None:
        return [cid for cid in context_ids if cid]
    if context_id:
        return [context_id]
    return None


def context_relationships(
    state: ErdState,
    context_id: Optional[str] = None,
    context_ids: Optional[Iterable[str]] = None,
    active_only: bool = False,
) -> Dict[str, Relationship]:
    ids = _normalise_context_ids(context_id, context_ids)
    id_set = set(ids or [])

    relationships: Dict[str, Relationship] = {}
    for rel_id, rel in getattr(state, "relationships", {}).items():
        if ids is not None and getattr(rel, "context_id", "") not in id_set:
            continue
        if active_only and not bool(getattr(rel, "active", True)):
            continue
        relationships[rel_id] = rel

    return relationships


def _table_refs_from_context(context) -> Set[str]:
    refs = set(getattr(context, "table_keys", []) or [])
    if not refs:
        refs = set(getattr(context, "tables", []) or [])
    if not refs:
        refs = set(getattr(context, "assigned_tables", []) or [])
    return refs


def context_tables(
    state: ErdState,
    context_id: Optional[str] = None,
    context_ids: Optional[Iterable[str]] = None,
) -> Dict[str, TableInfo]:
    ids = _normalise_context_ids(context_id, context_ids)
    if ids is None:
        return dict(getattr(state, "tables", {}))

    resolved: Dict[str, TableInfo] = {}
    for cid in ids:
        context = getattr(state, "relationship_contexts", {}).get(cid)
        if not context:
            continue
        for ref in _table_refs_from_context(context):
            key = resolve_table_key(state, ref)
            if key and key in state.tables:
                resolved[key] = state.tables[key]

    return resolved


def infer_tables_from_relationships(state: ErdState, relationships: Dict[str, Relationship]) -> Dict[str, TableInfo]:
    inferred: Dict[str, TableInfo] = {}

    for rel in relationships.values():
        source_full, target_full = relationship_tables(rel)
        source_key = resolve_table_key(state, source_full)
        target_key = resolve_table_key(state, target_full)

        if source_key and source_key in state.tables:
            inferred[source_key] = state.tables[source_key]
        if target_key and target_key in state.tables:
            inferred[target_key] = state.tables[target_key]

    return inferred


def build_scoped_state_from_context(
    state: ErdState,
    context_id: Optional[str] = None,
    context_ids: Optional[Iterable[str]] = None,
    active_only: bool = True,
    connected_only: bool = True,
):
    scoped = copy.deepcopy(state)
    scoped.relationships = context_relationships(
        state,
        context_id=context_id,
        context_ids=context_ids,
        active_only=active_only,
    )

    ids = _normalise_context_ids(context_id, context_ids)
    if ids is None:
        if connected_only:
            scoped.tables = infer_tables_from_relationships(state, scoped.relationships)
        else:
            scoped.tables = dict(getattr(state, "tables", {}))
        return scoped

    inferred = infer_tables_from_relationships(state, scoped.relationships)
    assigned = context_tables(state, context_ids=ids)

    if connected_only:
        scoped.tables = inferred
    else:
        scoped.tables = {**assigned, **inferred}

    return scoped


def context_label(state: ErdState, context_id: Optional[str] = None, context_ids: Optional[Iterable[str]] = None) -> str:
    ids = _normalise_context_ids(context_id, context_ids)
    if ids is None:
        return "Whole database"

    labels = []
    for cid in ids:
        ctx = getattr(state, "relationship_contexts", {}).get(cid)
        labels.append(getattr(ctx, "name", cid) if ctx else cid)
    return ", ".join(labels) if labels else "Selected contexts"


def build_export_quality_report(
    state: ErdState,
    context_id: Optional[str] = None,
    context_ids: Optional[Iterable[str]] = None,
    selected_relationship_ids: Optional[List[str]] = None,
    infer_tables_from_relationships: bool = True,
    active_only: bool = True,
) -> Dict[str, Any]:
    ids = _normalise_context_ids(context_id, context_ids)

    if selected_relationship_ids:
        selected = set(selected_relationship_ids)
        relationships = {
            rel_id: rel
            for rel_id, rel in getattr(state, "relationships", {}).items()
            if rel_id in selected and (not active_only or bool(getattr(rel, "active", True)))
        }
    else:
        relationships = context_relationships(state, context_ids=ids, active_only=active_only)

    tables = context_tables(state, context_ids=ids)

    if infer_tables_from_relationships and relationships:
        inferred = infer_tables_from_relationships_fn(state, relationships)
        if selected_relationship_ids or not tables:
            tables = inferred
        else:
            tables = {**tables, **inferred}

    table_key_set: Set[str] = set(tables.keys())
    relationship_table_keys: Set[str] = set()

    broken_relationships: List[Dict[str, Any]] = []
    missing_descriptions: List[Dict[str, Any]] = []
    conditional_missing_condition: List[Dict[str, Any]] = []

    active_relationship_count = 0
    conditional_relationship_count = 0

    for rel in relationships.values():
        source_full, target_full = relationship_tables(rel)
        source_key = resolve_table_key(state, source_full)
        target_key = resolve_table_key(state, target_full)

        source_found = bool(source_key and source_key in table_key_set)
        target_found = bool(target_key and target_key in table_key_set)

        if bool(getattr(rel, "active", True)):
            active_relationship_count += 1

        rel_type = (getattr(rel, "relationship_type", "") or "").lower()
        condition_sql = (getattr(rel, "condition_sql", "") or "").strip()

        if rel_type == "conditional" or condition_sql:
            conditional_relationship_count += 1
            if not condition_sql:
                conditional_missing_condition.append(
                    {
                        "relationship_id": getattr(rel, "id", ""),
                        "issue": "Conditional relationship is missing condition SQL.",
                        "source": source_full,
                        "target": target_full,
                    }
                )

        if source_found and source_key:
            relationship_table_keys.add(source_key)
        if target_found and target_key:
            relationship_table_keys.add(target_key)

        if not source_found or not target_found:
            broken_relationships.append(
                {
                    "relationship_id": getattr(rel, "id", ""),
                    "issue": "Relationship references a table outside the export scope or a missing table.",
                    "source": source_full,
                    "target": target_full,
                    "source_found": source_found,
                    "target_found": target_found,
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

    tables_without_relationships = sorted(
        [getattr(tables[key], "full_name", key) for key in table_key_set - relationship_table_keys]
    )

    columns_included = sum(len(getattr(table, "columns", []) or []) for table in tables.values())
    label = context_label(state, context_ids=ids)

    report = {
        "context_id": context_id or "",
        "context_ids": list(ids or []),
        "context_name": label,
        "context_type": "Multi-context" if ids and len(ids) > 1 else "",
        "selected_relationships": list(selected_relationship_ids or []),
        "tables_included": len(tables),
        "columns_included": columns_included,
        "relationships_included": len(relationships),
        "active_relationships": active_relationship_count,
        "conditional_relationships": conditional_relationship_count,
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


def infer_tables_from_relationships_fn(state: ErdState, relationships: Dict[str, Relationship]) -> Dict[str, TableInfo]:
    return infer_tables_from_relationships(state, relationships)


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
