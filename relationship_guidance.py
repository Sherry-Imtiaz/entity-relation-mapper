
from __future__ import annotations

from typing import Any, Dict, Optional

from models import ColumnInfo, ErdState


def is_key_like_column_name(column_name: str) -> bool:
    cname = (column_name or "").lower()
    return (
        cname == "id"
        or cname.endswith("_id")
        or cname.endswith("id")
        or "_id_" in cname
        or cname.endswith("_key")
        or cname.endswith("key")
        or "_key_" in cname
        or cname.endswith("_code")
        or cname.endswith("code")
        or "_code_" in cname
        or cname.endswith("_number")
        or cname.endswith("number")
        or "_number_" in cname
        or cname.endswith("_no")
        or cname.endswith("no")
    )


def get_column_info(state: ErdState, full_table: str, column_name: str) -> Optional[ColumnInfo]:
    table = state.tables.get(full_table)
    if not table:
        return None

    for column in table.columns:
        if column.column_name == column_name:
            return column

    return None


def suggest_relationship_options(
    state: ErdState,
    source_full_table: str,
    source_column: str,
    target_full_table: str,
    target_column: str,
    relationship_mode: str = "Standard relationship",
) -> Dict[str, Any]:
    source_info = get_column_info(state, source_full_table, source_column)
    target_info = get_column_info(state, target_full_table, target_column)

    source_pk = bool(getattr(source_info, "is_primary_key", False))
    target_pk = bool(getattr(target_info, "is_primary_key", False))
    source_key_like = source_pk or is_key_like_column_name(source_column)
    target_key_like = target_pk or is_key_like_column_name(target_column)
    matching_names = (source_column or "").lower() == (target_column or "").lower()
    same_table = source_full_table == target_full_table
    conditional = relationship_mode == "Conditional relationship"

    suggestion = {
        "cardinality": "many-to-one",
        "join_type": "LEFT JOIN",
        "confidence": 0.75,
        "relationship_type": "conditional" if conditional else "manual",
        "warning": "",
        "reason": "Default recommendation for joining a detail/source table to a related target table.",
    }

    reasons = []

    if same_table:
        suggestion["warning"] = (
            "Source and target are from the same table. This may be a self-join. "
            "Confirm this is intentional before saving."
        )
        reasons.append("The source and target table are the same, so this may represent a self-join.")

    if source_pk and target_pk:
        suggestion.update(
            {
                "cardinality": "one-to-one",
                "join_type": "INNER JOIN",
                "confidence": 0.85,
            }
        )
        reasons.append("Both selected columns appear to be primary keys, which often indicates a one-to-one relationship.")
    elif target_pk or target_key_like:
        suggestion.update(
            {
                "cardinality": "many-to-one",
                "join_type": "LEFT JOIN",
                "confidence": 0.95 if (source_key_like or matching_names) else 0.90,
            }
        )
        reasons.append("The target column appears to be a primary key or ID/key-like field.")
        if source_key_like:
            reasons.append("The source column also looks like an ID/key reference.")
        if matching_names:
            reasons.append("The source and target column names match.")
    elif source_key_like and target_key_like:
        suggestion.update(
            {
                "cardinality": "many-to-one",
                "join_type": "LEFT JOIN",
                "confidence": 0.90,
            }
        )
        reasons.append("Both selected columns look like ID/key-style fields.")
    elif matching_names:
        suggestion.update(
            {
                "cardinality": "many-to-one",
                "join_type": "LEFT JOIN",
                "confidence": 0.85,
            }
        )
        reasons.append("The source and target column names match.")

    if conditional:
        suggestion["join_type"] = "LEFT JOIN"
        suggestion["confidence"] = max(float(suggestion["confidence"]), 0.90)
        reasons.append(
            "Conditional relationships commonly use LEFT JOIN so source records are preserved while the condition controls valid matches."
        )
        reasons.append(
            "Use conditional relationships when a shared association table links to different module types using a discriminator field such as Item_Type."
        )

    suggestion["reason"] = " ".join(reasons) if reasons else suggestion["reason"]
    return suggestion
