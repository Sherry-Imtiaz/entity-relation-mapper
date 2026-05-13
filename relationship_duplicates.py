
from __future__ import annotations
import copy, dataclasses, re
from typing import Dict, Iterable, List, Optional, Tuple
from models import ErdState, Relationship

def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).lower()

def full_table(schema_name: str, table_name: str) -> str:
    return f"{schema_name}.{table_name}" if schema_name else table_name

def relationship_tables(rel: Relationship) -> Tuple[str, str]:
    return (
        getattr(rel, "source_full_table", None) or full_table(getattr(rel, "source_schema", ""), getattr(rel, "source_table", "")),
        getattr(rel, "target_full_table", None) or full_table(getattr(rel, "target_schema", ""), getattr(rel, "target_table", "")),
    )

def relationship_signature_from_values(source_schema: str, source_table: str, source_column: str, target_schema: str, target_table: str, target_column: str, relationship_type: str = "", condition_sql: str = "", extra_join_sql: str = "") -> Tuple[str, ...]:
    return (_clean(full_table(source_schema, source_table)), _clean(source_column), _clean(full_table(target_schema, target_table)), _clean(target_column), _clean(relationship_type), _clean(condition_sql), _clean(extra_join_sql))

def relationship_signature(rel: Relationship) -> Tuple[str, ...]:
    source_full, target_full = relationship_tables(rel)
    source_schema, source_table = source_full.split(".", 1) if "." in source_full else ("", source_full)
    target_schema, target_table = target_full.split(".", 1) if "." in target_full else ("", target_full)
    return relationship_signature_from_values(source_schema, source_table, getattr(rel, "source_column", ""), target_schema, target_table, getattr(rel, "target_column", ""), getattr(rel, "relationship_type", ""), getattr(rel, "condition_sql", ""), getattr(rel, "extra_join_sql", ""))

def find_duplicate_relationships(state: ErdState, signature: Tuple[str, ...], exclude_relationship_id: Optional[str] = None) -> List[Relationship]:
    matches = []
    for rel_id, rel in getattr(state, "relationships", {}).items():
        if exclude_relationship_id and rel_id == exclude_relationship_id:
            continue
        if relationship_signature(rel) == signature:
            matches.append(rel)
    return matches

def context_name(state: ErdState, context_id: str) -> str:
    context = getattr(state, "relationship_contexts", {}).get(context_id)
    return getattr(context, "name", context_id) if context else context_id

def duplicate_context_names(state: ErdState, duplicates: Iterable[Relationship]) -> List[str]:
    names = []
    for rel in duplicates:
        name = context_name(state, getattr(rel, "context_id", ""))
        if name not in names:
            names.append(name)
    return names

def relationship_id_for_context(context_id: str, source_schema: str, source_table: str, source_column: str, target_schema: str, target_table: str, target_column: str, relationship_type: str, condition_sql: str = "", extra_join_sql: str = "") -> str:
    raw = "|".join([context_id or "", source_schema or "", source_table or "", source_column or "", target_schema or "", target_table or "", target_column or "", relationship_type or "", condition_sql or "", extra_join_sql or ""])
    return re.sub(r"[^A-Za-z0-9_]+", "_", raw).strip("_")[:220]

def _add_tables_to_context(context, table_keys: List[str]) -> None:
    for attr in ["table_keys", "tables", "assigned_tables"]:
        if hasattr(context, attr):
            current = list(getattr(context, attr) or [])
            for key in table_keys:
                if key and key not in current:
                    current.append(key)
            setattr(context, attr, current)

def create_or_get_shared_context(state: ErdState, table_keys: Optional[List[str]] = None):
    shared_id, shared_name = "shared_relationships", "Shared Relationships"
    if shared_id in getattr(state, "relationship_contexts", {}):
        context = state.relationship_contexts[shared_id]
        _add_tables_to_context(context, table_keys or [])
        return context
    from models import RelationshipContext
    if dataclasses.is_dataclass(RelationshipContext):
        field_names = {f.name for f in dataclasses.fields(RelationshipContext)}
        defaults = {"id": shared_id, "name": shared_name, "context_type": "Shared", "description": "Common relationships reused across multiple relationship contexts.", "comments": "Created automatically for duplicate/shared relationship handling.", "table_keys": list(table_keys or []), "tables": list(table_keys or []), "assigned_tables": list(table_keys or [])}
        kwargs = {k: v for k, v in defaults.items() if k in field_names}
        context = RelationshipContext(**kwargs)
    else:
        context = RelationshipContext(id=shared_id, name=shared_name)
    state.relationship_contexts[shared_id] = context
    return context

def deduplicated_relationships_for_whole_database(state: ErdState, active_only: bool = True) -> Dict[str, Relationship]:
    grouped: Dict[Tuple[str, ...], List[Relationship]] = {}
    for rel in getattr(state, "relationships", {}).values():
        if active_only and not bool(getattr(rel, "active", True)):
            continue
        grouped.setdefault(relationship_signature(rel), []).append(rel)
    result = {}
    for idx, (_sig, rels) in enumerate(grouped.items(), start=1):
        base = copy.deepcopy(rels[0])
        contexts = duplicate_context_names(state, rels)
        context_text = ", ".join(contexts)
        existing = (getattr(base, "description", "") or "").strip()
        if context_text:
            base.description = f"{existing}\\nContexts: {context_text}" if existing else f"Contexts: {context_text}"
        base.id = f"dedup_{idx}_{getattr(base, 'id', idx)}"
        result[base.id] = base
    return result
