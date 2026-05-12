from __future__ import annotations

from typing import Any, List, Optional, Tuple

from models import ColumnInfo, ErdState, TableInfo
from validation import get_context_tables, get_relationships_for_context

try:
    from streamlit_flow.elements import StreamlitFlowEdge, StreamlitFlowNode
    from streamlit_flow.state import StreamlitFlowState
except ImportError:
    StreamlitFlowEdge = None
    StreamlitFlowNode = None
    StreamlitFlowState = None

def is_key_like_column(column: ColumnInfo) -> bool:
    cname = column.column_name.lower()
    return (
        column.is_primary_key
        or cname == "id"
        or cname.endswith("_id")
        or cname.endswith("id")
        or cname.endswith("_key")
        or cname.endswith("key")
        or cname.endswith("_code")
        or cname.endswith("code")
        or cname.endswith("_number")
        or cname.endswith("number")
        or cname.endswith("_no")
        or cname.endswith("no")
    )


def split_visual_columns_for_table(
    table: TableInfo,
    max_key_columns: int = 6,
    max_other_columns: int = 6,
) -> Tuple[List[ColumnInfo], List[ColumnInfo], int]:
    """Split columns into key-like and other groups for clearer ERD node display."""
    columns = sorted(table.columns, key=lambda x: x.ordinal_position)
    key_columns = [col for col in columns if is_key_like_column(col)]
    other_columns = [col for col in columns if not is_key_like_column(col)]

    visible_key_columns = key_columns[:max_key_columns]
    visible_other_columns = other_columns[:max_other_columns]
    hidden_count = max(0, len(columns) - len(visible_key_columns) - len(visible_other_columns))

    return visible_key_columns, visible_other_columns, hidden_count


def build_table_node_content(table: TableInfo) -> str:
    """Build compact table-style Markdown content for a Streamlit Flow ERD node."""
    line_break = chr(10)
    key_columns, other_columns, hidden_count = split_visual_columns_for_table(table)
    row_count = f"{table.row_count:,}" if table.row_count is not None else "-"
    schema = table.schema_name or "no schema"

    rows: List[str] = []

    for col in key_columns:
        marker = "PK" if col.is_primary_key else "KEY"
        rows.append(f"| {marker} | `{col.column_name}` |")

    for col in other_columns:
        rows.append(f"|  | `{col.column_name}` |")

    if hidden_count:
        rows.append(f"| … | _{hidden_count} more columns_ |")

    if not rows:
        rows.append("|  | _No columns loaded_ |")

    content_lines = [
        f"**{table.table_name}**",
        f"`{schema}`  ·  Rows: `{row_count}`",
        "",
        "| Type | Column |",
        "|---|---|",
        *rows,
    ]

    return line_break.join(content_lines)


def get_visual_columns_for_table(table: TableInfo, max_columns: int = 14) -> List[ColumnInfo]:
    """Backward-compatible helper returning key-like fields first."""
    columns = sorted(table.columns, key=lambda x: x.ordinal_position)
    key_columns = [col for col in columns if is_key_like_column(col)]
    other_columns = [col for col in columns if not is_key_like_column(col)]
    return (key_columns + other_columns)[:max_columns]


def build_streamlit_flow_state_for_context(state: ErdState, context_id: str) -> Optional[Any]:
    """Build a Streamlit Flow state for the active relationship context."""
    if StreamlitFlowState is None or StreamlitFlowNode is None or StreamlitFlowEdge is None:
        return None

    scoped_tables = get_context_tables(state, context_id)
    relationships = get_relationships_for_context(state, context_id)
    nodes = []
    edges = []

    sorted_tables = sorted(scoped_tables.values(), key=lambda t: t.full_name.lower())
    for idx, table in enumerate(sorted_tables):
        x_pos = (idx % 3) * 500
        y_pos = (idx // 3) * 330
        nodes.append(
            StreamlitFlowNode(
                id=table.full_name,
                pos=(x_pos, y_pos),
                data={"content": build_table_node_content(table)},
                node_type="default",
                source_position="right",
                target_position="left",
                style={
                    "width": "380px",
                    "minHeight": "210px",
                    "border": "1px solid #94A3B8",
                    "borderRadius": "10px",
                    "padding": "10px",
                    "backgroundColor": "#FFFFFF",
                    "boxShadow": "0 4px 12px rgba(15, 23, 42, 0.08)",
                    "fontSize": "11px",
                    "lineHeight": "1.25",
                    "color": "#0F172A",
                },
            )
        )

    for rel in relationships.values():
        if rel.source_full_table not in scoped_tables or rel.target_full_table not in scoped_tables:
            continue
        label = f"{rel.source_column} → {rel.target_column}"
        if rel.condition_sql:
            label += " [conditional]"
        edges.append(
            StreamlitFlowEdge(
                id=rel.id,
                source=rel.source_full_table,
                target=rel.target_full_table,
                label=label,
                animated=bool(rel.condition_sql),
            )
        )

    return StreamlitFlowState(nodes=nodes, edges=edges)


def build_streamlit_flow_state_from_erd_state(display_state: ErdState) -> Optional[Any]:
    """Build a Streamlit Flow state from any ERD state for visualisation only."""
    if StreamlitFlowState is None or StreamlitFlowNode is None or StreamlitFlowEdge is None:
        return None

    nodes = []
    edges = []
    sorted_tables = sorted(display_state.tables.values(), key=lambda t: t.full_name.lower())

    for idx, table in enumerate(sorted_tables):
        x_pos = (idx % 3) * 500
        y_pos = (idx // 3) * 330
        nodes.append(
            StreamlitFlowNode(
                id=table.full_name,
                pos=(x_pos, y_pos),
                data={"content": build_table_node_content(table)},
                node_type="default",
                source_position="right",
                target_position="left",
                style={
                    "width": "380px",
                    "minHeight": "210px",
                    "border": "1px solid #94A3B8",
                    "borderRadius": "10px",
                    "padding": "10px",
                    "backgroundColor": "#FFFFFF",
                    "boxShadow": "0 4px 12px rgba(15, 23, 42, 0.08)",
                    "fontSize": "11px",
                    "lineHeight": "1.25",
                    "color": "#0F172A",
                },
            )
        )

    for rel in display_state.relationships.values():
        if rel.source_full_table not in display_state.tables or rel.target_full_table not in display_state.tables:
            continue
        label = f"{rel.source_column} → {rel.target_column}"
        if rel.condition_sql:
            label += " [conditional]"
        edges.append(
            StreamlitFlowEdge(
                id=rel.id,
                source=rel.source_full_table,
                target=rel.target_full_table,
                label=label,
                animated=bool(rel.condition_sql),
            )
        )

    return StreamlitFlowState(nodes=nodes, edges=edges)

