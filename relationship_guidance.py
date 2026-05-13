
from __future__ import annotations

from typing import Any, Dict, Optional

from models import ColumnInfo, ErdState


CARDINALITY_DEFAULTS = {
    "many-to-one": {
        "join_type": "LEFT JOIN",
        "confidence": 0.95,
        "reason": "Selected cardinality is many-to-one, so LEFT JOIN is recommended to preserve all source/detail records while joining to the parent/reference table.",
    },
    "one-to-many": {
        "join_type": "LEFT JOIN",
        "confidence": 0.90,
        "reason": "Selected cardinality is one-to-many, so LEFT JOIN is recommended to preserve the source/master records while joining related detail records.",
    },
    "one-to-one": {
        "join_type": "INNER JOIN",
        "confidence": 0.95,
        "reason": "Selected cardinality is one-to-one, so INNER JOIN is recommended when both sides are expected to have matching records.",
    },
    "many-to-many": {
        "join_type": "LEFT JOIN",
        "confidence": 0.80,
        "reason": "Selected cardinality is many-to-many, so LEFT JOIN is recommended unless you are intentionally filtering to only matched records.",
    },
}


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
    selected_cardinality: Optional[str] = None,
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

    cardinality = selected_cardinality or "many-to-one"
    defaults = CARDINALITY_DEFAULTS.get(cardinality, CARDINALITY_DEFAULTS["many-to-one"])

    suggestion: Dict[str, Any] = {
        "cardinality": cardinality,
        "join_type": defaults["join_type"],
        "confidence": defaults["confidence"],
        "relationship_type": "conditional" if conditional else "manual",
        "warning": "",
        "reason": defaults["reason"],
    }

    reasons = [defaults["reason"]]

    if same_table:
        suggestion["warning"] = (
            "Source and target are from the same table. This may be a self-join. "
            "Confirm this is intentional before saving."
        )
        reasons.append("The selected source and target table are the same, so this may represent a self-join.")

    if cardinality == "one-to-one":
        if source_pk and target_pk:
            suggestion["confidence"] = 0.95
            reasons.append("Both selected columns appear to be primary keys, which supports a one-to-one relationship.")
        elif source_key_like and target_key_like:
            suggestion["confidence"] = 0.90
            reasons.append("Both selected columns look like ID/key fields, which may support a one-to-one relationship.")
        else:
            suggestion["confidence"] = 0.80
            reasons.append("The selected fields do not both look like primary keys, so review the one-to-one assumption.")

    elif cardinality == "many-to-one":
        suggestion["join_type"] = "LEFT JOIN"
        if target_pk or target_key_like:
            suggestion["confidence"] = 0.95 if (source_key_like or matching_names) else 0.90
            reasons.append("The target column appears to be a primary key or ID/key-like field.")
        if source_key_like:
            reasons.append("The source column looks like an ID/key reference.")
        if matching_names:
            reasons.append("The source and target column names match.")

    elif cardinality == "one-to-many":
        suggestion["join_type"] = "LEFT JOIN"
        if source_pk or source_key_like:
            suggestion["confidence"] = 0.90
            reasons.append("The source column appears to be an ID/key-like field, which can support one-to-many relationships.")
        if target_key_like:
            reasons.append("The target column also appears to be an ID/key-like field.")

    elif cardinality == "many-to-many":
        suggestion["join_type"] = "LEFT JOIN"
        suggestion["confidence"] = 0.80
        reasons.append("Many-to-many relationships often require a bridge/association table. Confirm the selected tables represent that structure.")

    if conditional:
        suggestion["join_type"] = "LEFT JOIN"
        suggestion["confidence"] = max(float(suggestion["confidence"]), 0.90)
        reasons.append(
            "Conditional relationship mode is selected, so LEFT JOIN is recommended to preserve source records while the condition controls valid matches."
        )
        reasons.append(
            "Conditional relationships are useful when a shared association table links to different module types using a discriminator field such as Item_Type."
        )

    suggestion["reason"] = " ".join(reasons)
    return suggestion
