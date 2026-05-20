
from __future__ import annotations

from html import escape
from typing import Dict, List, Tuple


def _full_table(schema_name: str, table_name: str) -> str:
    schema = (schema_name or "").strip()
    table = (table_name or "").strip()
    return f"{schema}.{table}" if schema else table


def _relationship_tables(rel) -> tuple[str, str]:
    source_full = getattr(rel, "source_full_table", None) or _full_table(
        getattr(rel, "source_schema", ""),
        getattr(rel, "source_table", ""),
    )
    target_full = getattr(rel, "target_full_table", None) or _full_table(
        getattr(rel, "target_schema", ""),
        getattr(rel, "target_table", ""),
    )
    return source_full, target_full


def _safe_node_id(value: str) -> str:
    import re

    text = re.sub(r"[^A-Za-z0-9_]+", "_", str(value or "")).strip("_")
    if not text:
        text = "node"
    if text[0].isdigit():
        text = "_" + text
    return text


def _table_full_name(table_key: str, table) -> str:
    return getattr(table, "full_name", None) or _full_table(
        getattr(table, "schema_name", ""),
        getattr(table, "table_name", ""),
    ) or table_key


def _important_columns(table, relationships, table_full: str, max_columns: int = 10):
    rel_cols = set()
    for rel in relationships:
        source_full, target_full = _relationship_tables(rel)
        if source_full == table_full:
            rel_cols.add(getattr(rel, "source_column", ""))
        if target_full == table_full:
            rel_cols.add(getattr(rel, "target_column", ""))

    columns = list(getattr(table, "columns", []) or [])

    def priority(col):
        name = getattr(col, "column_name", "")
        lower = name.lower()
        is_pk = bool(getattr(col, "is_primary_key", False))
        is_rel = name in rel_cols
        is_id_like = (
            lower == "id"
            or lower.endswith("_id")
            or lower.endswith("id")
            or lower.endswith("_key")
            or lower.endswith("key")
            or lower.endswith("_number")
            or lower.endswith("number")
        )
        return (not is_pk, not is_rel, not is_id_like, getattr(col, "ordinal_position", 999999))

    columns = sorted(columns, key=priority)
    return columns[:max_columns], len(columns) > max_columns


def _layout_tables_by_relationship_flow(tables, relationships, spacing_mode: str = "Comfortable"):
    table_names = []
    table_lookup = {}

    for table_key, table in tables:
        table_full = _table_full_name(table_key, table)
        table_names.append(table_full)
        table_lookup[table_full] = (table_key, table)

    spacing_lookup = {
        "Compact": {"x_gap": 120, "y_gap": 70},
        "Comfortable": {"x_gap": 190, "y_gap": 100},
        "Wide": {"x_gap": 280, "y_gap": 130},
    }
    spacing = spacing_lookup.get(spacing_mode, spacing_lookup["Comfortable"])

    node_width = 330
    node_height_base = 72

    incoming = {name: set() for name in table_names}
    outgoing = {name: set() for name in table_names}

    for rel in relationships:
        src, tar = _relationship_tables(rel)
        if src in incoming and tar in incoming and src != tar:
            outgoing[src].add(tar)
            incoming[tar].add(src)

    level = {name: 0 for name in table_names}
    for _ in range(max(1, len(table_names)) * 2):
        changed = False
        for src in table_names:
            for tar in outgoing[src]:
                proposed = level[src] + 1
                if proposed > level[tar]:
                    level[tar] = proposed
                    changed = True
        if not changed:
            break

    if len(set(level.values())) == 1 and len(table_names) > 3:
        ordered = sorted(
            table_names,
            key=lambda n: (-(len(incoming[n]) + len(outgoing[n])), n.lower()),
        )
        for idx, name in enumerate(ordered):
            level[name] = idx % 3

    levels: Dict[int, List[str]] = {}
    for name in table_names:
        levels.setdefault(level[name], []).append(name)

    for lvl, names in levels.items():
        names.sort(key=lambda n: (len(incoming[n]), -len(outgoing[n]), n.lower()))

    positions = {}

    for lvl in sorted(levels):
        names = levels[lvl]
        x = 60 + lvl * (node_width + spacing["x_gap"])

        for row, table_full in enumerate(names):
            table_key, table = table_lookup[table_full]
            selected_cols, truncated = _important_columns(table, relationships, table_full, max_columns=10)
            node_height = node_height_base + (len(selected_cols) + (1 if truncated else 0)) * 22
            y = 60 + row * (node_height + spacing["y_gap"] + 80)

            positions[table_full] = {
                "x": x,
                "y": y,
                "w": node_width,
                "h": node_height,
                "table": table,
                "table_key": table_key,
                "selected_cols": selected_cols,
                "truncated": truncated,
                "level": lvl,
            }

    return positions


def _edge_path(source_pos, target_pos, edge_index: int, edge_style: str = "Orthogonal") -> Tuple[str, float, float]:
    sx = source_pos["x"]
    sy = source_pos["y"]
    sw = source_pos["w"]
    sh = source_pos["h"]

    tx = target_pos["x"]
    ty = target_pos["y"]
    tw = target_pos["w"]
    th = target_pos["h"]

    offset = ((edge_index % 5) - 2) * 12

    if tx > sx:
        x1 = sx + sw
        y1 = sy + sh / 2 + offset
        x2 = tx
        y2 = ty + th / 2 + offset
    elif tx < sx:
        x1 = sx
        y1 = sy + sh / 2 + offset
        x2 = tx + tw
        y2 = ty + th / 2 + offset
    else:
        x1 = sx + sw / 2 + offset
        y1 = sy + sh
        x2 = tx + tw / 2 + offset
        y2 = ty

    mid_x = (x1 + x2) / 2
    mid_y = (y1 + y2) / 2

    if edge_style == "Curved":
        path = f"M {x1:.1f} {y1:.1f} C {mid_x:.1f} {y1:.1f}, {mid_x:.1f} {y2:.1f}, {x2:.1f} {y2:.1f}"
    else:
        if abs(x2 - x1) < 30:
            side_x = max(sx + sw, tx + tw) + 90 + abs(offset)
            path = (
                f"M {x1:.1f} {y1:.1f} "
                f"L {side_x:.1f} {y1:.1f} "
                f"L {side_x:.1f} {y2:.1f} "
                f"L {x2:.1f} {y2:.1f}"
            )
            mid_x = side_x
        else:
            path = (
                f"M {x1:.1f} {y1:.1f} "
                f"L {mid_x:.1f} {y1:.1f} "
                f"L {mid_x:.1f} {y2:.1f} "
                f"L {x2:.1f} {y2:.1f}"
            )

    return path, mid_x, mid_y


def _relationship_label(rel, show_relationship_labels: bool, show_condition_labels: bool) -> str:
    parts = []

    if show_relationship_labels:
        parts.append(f"{getattr(rel, 'source_column', '')} → {getattr(rel, 'target_column', '')}")

    if show_condition_labels:
        condition = (getattr(rel, "condition_sql", "") or "").strip()
        extra = (getattr(rel, "extra_join_sql", "") or "").strip()

        if condition:
            cond_short = " ".join(condition.split())
            if len(cond_short) > 95:
                cond_short = cond_short[:92] + "..."
            parts.append(f"Condition: {cond_short}")

        if extra:
            extra_short = " ".join(extra.split())
            if len(extra_short) > 75:
                extra_short = extra_short[:72] + "..."
            parts.append(f"Extra: {extra_short}")

    return " | ".join(parts)


def build_dependency_free_erd_viewer(
    state,
    height: int = 820,
    show_relationship_labels: bool = True,
    show_condition_labels: bool = True,
    edge_style: str = "Orthogonal",
    spacing_mode: str = "Comfortable",
) -> str:
    """Build a pure HTML/SVG interactive ERD viewer.

    No Graphviz, Mermaid, or system executable is required.
    """
    relationships = list(getattr(state, "relationships", {}).values())
    tables = list(getattr(state, "tables", {}).items())

    positions = _layout_tables_by_relationship_flow(tables, relationships, spacing_mode=spacing_mode)

    table_cards = []
    for table_full, pos in positions.items():
        selected_cols = pos["selected_cols"]
        col_html = []
        for col in selected_cols:
            cname = escape(getattr(col, "column_name", ""))
            dtype = escape(getattr(col, "data_type", ""))
            pk = " <span class='pk'>PK</span>" if bool(getattr(col, "is_primary_key", False)) else ""
            col_html.append(f"<div class='col'><span>{cname}</span><small>{dtype}{pk}</small></div>")
        if pos["truncated"]:
            col_html.append("<div class='col muted'>… more columns</div>")

        table_cards.append(
            f"""
            <div class="table-card" id="{_safe_node_id(table_full)}"
                 style="left:{pos['x']}px; top:{pos['y']}px; width:{pos['w']}px;">
                <div class="table-title">{escape(table_full)}</div>
                <div class="table-cols">{''.join(col_html)}</div>
            </div>
            """
        )

    edge_lines = []
    edge_labels = []

    for idx, rel in enumerate(relationships):
        source_full, target_full = _relationship_tables(rel)
        if source_full not in positions or target_full not in positions:
            continue

        sp = positions[source_full]
        tp = positions[target_full]
        path, mid_x, mid_y = _edge_path(sp, tp, idx, edge_style=edge_style)

        rel_type = (getattr(rel, "relationship_type", "") or "").lower()
        has_condition = bool((getattr(rel, "condition_sql", "") or "").strip())
        css_class = "edge-path conditional" if rel_type == "conditional" or has_condition else "edge-path"

        edge_lines.append(
            f"<path class='{css_class}' d='{path}' marker-end='url(#arrow)' />"
        )

        label = _relationship_label(rel, show_relationship_labels, show_condition_labels)
        if label:
            edge_labels.append(
                f"<div class='edge-label' style='left:{mid_x - 115}px; top:{mid_y - 18}px;'>{escape(label)}</div>"
            )

    max_x = max([p["x"] + p["w"] for p in positions.values()] + [1000]) + 280
    max_y = max([p["y"] + p["h"] for p in positions.values()] + [700]) + 260

    return f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<style>
  html, body {{
    margin: 0;
    padding: 0;
    overflow: hidden;
    background: #f8fafc;
    font-family: Arial, sans-serif;
  }}
  .toolbar {{
    height: 46px;
    display: flex;
    gap: 8px;
    align-items: center;
    padding: 7px 10px;
    background: #ffffff;
    border-bottom: 1px solid #e5e7eb;
    box-sizing: border-box;
  }}
  .toolbar button {{
    border: 1px solid #d1d5db;
    background: #ffffff;
    border-radius: 8px;
    padding: 6px 10px;
    cursor: pointer;
    font-size: 13px;
  }}
  .toolbar button:hover {{
    background: #f3f4f6;
  }}
  .hint {{
    color: #6b7280;
    font-size: 12px;
    margin-left: 8px;
  }}
  #viewport {{
    width: 100vw;
    height: {height - 46}px;
    overflow: hidden;
    cursor: grab;
    background:
      linear-gradient(45deg, #f1f5f9 25%, transparent 25%),
      linear-gradient(-45deg, #f1f5f9 25%, transparent 25%),
      linear-gradient(45deg, transparent 75%, #f1f5f9 75%),
      linear-gradient(-45deg, transparent 75%, #f1f5f9 75%);
    background-size: 24px 24px;
    background-position: 0 0, 0 12px, 12px -12px, -12px 0px;
  }}
  #viewport.dragging {{
    cursor: grabbing;
  }}
  #canvas {{
    position: relative;
    width: {max_x}px;
    height: {max_y}px;
    transform-origin: 0 0;
    will-change: transform;
  }}
  .edge-layer {{
    position: absolute;
    left: 0;
    top: 0;
    width: {max_x}px;
    height: {max_y}px;
    pointer-events: none;
    z-index: 1;
  }}
  .edge-path {{
    fill: none;
    stroke: #334155;
    stroke-width: 2.7;
    opacity: 0.96;
    filter: drop-shadow(0 1px 1px rgba(15,23,42,0.12));
  }}
  .edge-path.conditional {{
    stroke: #1d4ed8;
    stroke-width: 3.1;
  }}
  .edge-label {{
    position: absolute;
    z-index: 5;
    max-width: 280px;
    padding: 5px 7px;
    border: 1px solid #94a3b8;
    background: rgba(255,255,255,0.97);
    border-radius: 8px;
    color: #0f172a;
    font-size: 11px;
    line-height: 1.28;
    box-shadow: 0 3px 10px rgba(15,23,42,0.13);
  }}
  .table-card {{
    position: absolute;
    z-index: 3;
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 14px;
    box-shadow: 0 5px 16px rgba(15,23,42,0.13);
    overflow: hidden;
  }}
  .table-title {{
    background: #e2e8f0;
    border-bottom: 1px solid #cbd5e1;
    padding: 10px 12px;
    font-weight: 700;
    color: #0f172a;
    font-size: 13px;
  }}
  .table-cols {{
    padding: 7px 10px 10px;
  }}
  .col {{
    display: flex;
    justify-content: space-between;
    gap: 10px;
    padding: 3px 0;
    border-bottom: 1px solid #f1f5f9;
    font-size: 12px;
    color: #1e293b;
  }}
  .col small {{
    color: #64748b;
    white-space: nowrap;
  }}
  .col.muted {{
    color: #94a3b8;
    font-style: italic;
  }}
  .pk {{
    color: #b45309;
    font-weight: 700;
  }}
</style>
</head>
<body>
  <div class="toolbar">
    <button onclick="zoomOut()">− Zoom out</button>
    <button onclick="zoomIn()">+ Zoom in</button>
    <button onclick="resetView()">Reset</button>
    <button onclick="fitToScreen()">Fit</button>
    <span id="zoomLabel" class="hint">100%</span>
    <span class="hint">Mouse wheel to zoom. Drag to pan. Conditional links are highlighted.</span>
  </div>
  <div id="viewport">
    <div id="canvas">
      <svg class="edge-layer" viewBox="0 0 {max_x} {max_y}">
        <defs>
          <marker id="arrow" markerWidth="16" markerHeight="16" refX="13" refY="5" orient="auto" markerUnits="strokeWidth">
            <path d="M0,0 L0,10 L15,5 z" fill="#334155"></path>
          </marker>
        </defs>
        {''.join(edge_lines)}
      </svg>
      {''.join(edge_labels)}
      {''.join(table_cards)}
    </div>
  </div>

<script>
let scale = 1;
let translateX = 20;
let translateY = 20;
let isDragging = false;
let lastX = 0;
let lastY = 0;

const viewport = document.getElementById("viewport");
const canvas = document.getElementById("canvas");
const zoomLabel = document.getElementById("zoomLabel");

function applyTransform() {{
  canvas.style.transform = `translate(${{translateX}}px, ${{translateY}}px) scale(${{scale}})`;
  zoomLabel.textContent = `${{Math.round(scale * 100)}}%`;
}}

function zoomAt(cx, cy, factor) {{
  const oldScale = scale;
  scale = Math.min(5, Math.max(0.1, scale * factor));
  const actual = scale / oldScale;
  translateX = cx - (cx - translateX) * actual;
  translateY = cy - (cy - translateY) * actual;
  applyTransform();
}}

function zoomIn() {{
  zoomAt(viewport.clientWidth / 2, viewport.clientHeight / 2, 1.2);
}}

function zoomOut() {{
  zoomAt(viewport.clientWidth / 2, viewport.clientHeight / 2, 1 / 1.2);
}}

function resetView() {{
  scale = 1;
  translateX = 20;
  translateY = 20;
  applyTransform();
}}

function fitToScreen() {{
  const width = {max_x};
  const height = {max_y};
  const sx = (viewport.clientWidth - 40) / width;
  const sy = (viewport.clientHeight - 40) / height;
  scale = Math.min(2.2, Math.max(0.1, Math.min(sx, sy)));
  translateX = 20;
  translateY = 20;
  applyTransform();
}}

viewport.addEventListener("wheel", function(e) {{
  e.preventDefault();
  const rect = viewport.getBoundingClientRect();
  const x = e.clientX - rect.left;
  const y = e.clientY - rect.top;
  const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
  zoomAt(x, y, factor);
}}, {{ passive: false }});

viewport.addEventListener("mousedown", function(e) {{
  isDragging = true;
  lastX = e.clientX;
  lastY = e.clientY;
  viewport.classList.add("dragging");
}});

window.addEventListener("mousemove", function(e) {{
  if (!isDragging) return;
  translateX += e.clientX - lastX;
  translateY += e.clientY - lastY;
  lastX = e.clientX;
  lastY = e.clientY;
  applyTransform();
}});

window.addEventListener("mouseup", function() {{
  isDragging = false;
  viewport.classList.remove("dragging");
}});

window.addEventListener("load", function() {{
  fitToScreen();
}});

applyTransform();
</script>
</body>
</html>
"""


def render_graphviz_bytes(dot_source: str, output_format: str):
    return None, (
        "Graphviz SVG/PNG image rendering requires the Graphviz system executable "
        "to be installed and available on PATH. The dependency-free ERD viewer, DOT "
        "download, and Mermaid download do not require it."
    )
