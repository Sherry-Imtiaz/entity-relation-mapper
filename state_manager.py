from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict

from config import STATE_FILE
from models import ColumnInfo, ErdState, Relationship, RelationshipContext, TableInfo


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
