
from __future__ import annotations
from html import escape


def _full_table(schema_name: str, table_name: str) -> str:
    schema = (schema_name or '').strip()
    table = (table_name or '').strip()
    return f'{schema}.{table}' if schema else table


def _relationship_tables(rel) -> tuple[str, str]:
    source_full = getattr(rel, 'source_full_table', None) or _full_table(getattr(rel, 'source_schema', ''), getattr(rel, 'source_table', ''))
    target_full = getattr(rel, 'target_full_table', None) or _full_table(getattr(rel, 'target_schema', ''), getattr(rel, 'target_table', ''))
    return source_full, target_full


def _table_full_name(table_key: str, table) -> str:
    return getattr(table, 'full_name', None) or _full_table(getattr(table, 'schema_name', ''), getattr(table, 'table_name', '')) or table_key


def _important_columns(table, relationships, table_full: str, max_columns: int = 10):
    rel_cols = set()
    for rel in relationships:
        source_full, target_full = _relationship_tables(rel)
        if source_full == table_full:
            rel_cols.add(getattr(rel, 'source_column', ''))
        if target_full == table_full:
            rel_cols.add(getattr(rel, 'target_column', ''))
    columns = list(getattr(table, 'columns', []) or [])
    def priority(col):
        name = getattr(col, 'column_name', '')
        lower = name.lower()
        is_pk = bool(getattr(col, 'is_primary_key', False))
        is_rel = name in rel_cols
        is_id_like = lower == 'id' or lower.endswith('_id') or lower.endswith('id') or lower.endswith('_key')
        return (not is_pk, not is_rel, not is_id_like, getattr(col, 'ordinal_position', 999999))
    columns = sorted(columns, key=priority)
    return columns[:max_columns], len(columns) > max_columns


def build_dependency_free_erd_viewer(state, height: int = 760) -> str:
    relationships = list(getattr(state, 'relationships', {}).values())
    tables = list(getattr(state, 'tables', {}).items())
    node_width = 300
    node_height_base = 72
    row_gap = 140
    col_gap = 100
    cols = 3 if len(tables) >= 3 else max(1, len(tables))
    positions = {}

    for idx, (table_key, table) in enumerate(tables):
        table_full = _table_full_name(table_key, table)
        selected_cols, truncated = _important_columns(table, relationships, table_full)
        node_height = node_height_base + (len(selected_cols) + (1 if truncated else 0)) * 22
        row = idx // cols
        col = idx % cols
        x = 40 + col * (node_width + col_gap)
        y = 40 + row * (node_height + row_gap + 110)
        positions[table_full] = {'x': x, 'y': y, 'w': node_width, 'h': node_height, 'table': table, 'cols': selected_cols, 'truncated': truncated}

    table_cards = []
    for table_full, pos in positions.items():
        col_html = []
        for col in pos['cols']:
            cname = escape(getattr(col, 'column_name', ''))
            dtype = escape(getattr(col, 'data_type', ''))
            pk = " <span class='pk'>PK</span>" if bool(getattr(col, 'is_primary_key', False)) else ''
            col_html.append(f"<div class='col'><span>{cname}</span><small>{dtype}{pk}</small></div>")
        if pos['truncated']:
            col_html.append("<div class='col muted'>… more columns</div>")
        table_cards.append(f"""
        <div class='table-card' style='left:{pos['x']}px; top:{pos['y']}px; width:{pos['w']}px;'>
          <div class='table-title'>{escape(table_full)}</div>
          <div class='table-cols'>{''.join(col_html)}</div>
        </div>
        """)

    edge_lines, edge_labels = [], []
    for rel in relationships:
        source_full, target_full = _relationship_tables(rel)
        if source_full not in positions or target_full not in positions:
            continue
        sp, tp = positions[source_full], positions[target_full]
        x1, y1 = sp['x'] + sp['w'], sp['y'] + sp['h']/2
        x2, y2 = tp['x'], tp['y'] + tp['h']/2
        if x2 < x1:
            x1, y1 = sp['x'] + sp['w']/2, sp['y'] + sp['h']
            x2, y2 = tp['x'] + tp['w']/2, tp['y']
        mid_x = (x1 + x2)/2
        path = f'M {x1} {y1} C {mid_x} {y1}, {mid_x} {y2}, {x2} {y2}'
        label = f"{getattr(rel, 'source_column', '')} → {getattr(rel, 'target_column', '')}"
        cond = ' '.join((getattr(rel, 'condition_sql', '') or '').split())
        extra = ' '.join((getattr(rel, 'extra_join_sql', '') or '').split())
        if cond:
            label += ' | Condition: ' + (cond[:87] + '...' if len(cond) > 90 else cond)
        if extra:
            label += ' | Extra: ' + (extra[:67] + '...' if len(extra) > 70 else extra)
        edge_lines.append(f"<path class='edge-path' d='{path}' marker-end='url(#arrow)' />")
        edge_labels.append(f"<div class='edge-label' style='left:{mid_x-90}px; top:{(y1+y2)/2-12}px;'>{escape(label)}</div>")

    max_x = int(max([p['x'] + p['w'] for p in positions.values()] + [1000]) + 180)
    max_y = int(max([p['y'] + p['h'] for p in positions.values()] + [700]) + 180)

    return f"""
<!DOCTYPE html><html><head><meta charset='utf-8'/>
<style>
html,body{{margin:0;padding:0;overflow:hidden;background:#f8fafc;font-family:Arial,sans-serif;}}
.toolbar{{height:46px;display:flex;gap:8px;align-items:center;padding:7px 10px;background:#fff;border-bottom:1px solid #e5e7eb;box-sizing:border-box;}}
.toolbar button{{border:1px solid #d1d5db;background:#fff;border-radius:8px;padding:6px 10px;cursor:pointer;font-size:13px;}}
.toolbar button:hover{{background:#f3f4f6;}} .hint{{color:#6b7280;font-size:12px;margin-left:8px;}}
#viewport{{width:100vw;height:{height-46}px;overflow:hidden;cursor:grab;background:#f8fafc;}}
#viewport.dragging{{cursor:grabbing;}} #canvas{{position:relative;width:{max_x}px;height:{max_y}px;transform-origin:0 0;will-change:transform;}}
.edge-layer{{position:absolute;left:0;top:0;width:{max_x}px;height:{max_y}px;pointer-events:none;z-index:1;}}
.edge-path{{fill:none;stroke:#64748b;stroke-width:1.8;}} .edge-label{{position:absolute;z-index:3;max-width:250px;padding:4px 6px;border:1px solid #cbd5e1;background:rgba(255,255,255,.94);border-radius:8px;color:#334155;font-size:11px;line-height:1.25;box-shadow:0 1px 4px rgba(15,23,42,.08);}}
.table-card{{position:absolute;z-index:2;background:#fff;border:1px solid #cbd5e1;border-radius:14px;box-shadow:0 4px 14px rgba(15,23,42,.10);overflow:hidden;}}
.table-title{{background:#e2e8f0;border-bottom:1px solid #cbd5e1;padding:9px 11px;font-weight:700;color:#0f172a;font-size:13px;}}
.table-cols{{padding:7px 10px 10px;}} .col{{display:flex;justify-content:space-between;gap:10px;padding:3px 0;border-bottom:1px solid #f1f5f9;font-size:12px;color:#1e293b;}}
.col small{{color:#64748b;white-space:nowrap;}} .col.muted{{color:#94a3b8;font-style:italic;}} .pk{{color:#b45309;font-weight:700;}}
</style></head><body>
<div class='toolbar'><button onclick='zoomOut()'>− Zoom out</button><button onclick='zoomIn()'>+ Zoom in</button><button onclick='resetView()'>Reset</button><button onclick='fitToScreen()'>Fit</button><span id='zoomLabel' class='hint'>100%</span><span class='hint'>No Graphviz dependency. Mouse wheel to zoom. Drag to pan.</span></div>
<div id='viewport'><div id='canvas'><svg class='edge-layer' viewBox='0 0 {max_x} {max_y}'><defs><marker id='arrow' markerWidth='10' markerHeight='10' refX='8' refY='3' orient='auto' markerUnits='strokeWidth'><path d='M0,0 L0,6 L9,3 z' fill='#64748b'></path></marker></defs>{''.join(edge_lines)}</svg>{''.join(edge_labels)}{''.join(table_cards)}</div></div>
<script>
let scale=1,translateX=20,translateY=20,isDragging=false,lastX=0,lastY=0; const viewport=document.getElementById('viewport'), canvas=document.getElementById('canvas'), zoomLabel=document.getElementById('zoomLabel');
function applyTransform(){{canvas.style.transform=`translate(${{translateX}}px, ${{translateY}}px) scale(${{scale}})`; zoomLabel.textContent=`${{Math.round(scale*100)}}%`;}}
function zoomAt(cx,cy,factor){{const old=scale; scale=Math.min(5,Math.max(.1,scale*factor)); const actual=scale/old; translateX=cx-(cx-translateX)*actual; translateY=cy-(cy-translateY)*actual; applyTransform();}}
function zoomIn(){{zoomAt(viewport.clientWidth/2,viewport.clientHeight/2,1.2);}} function zoomOut(){{zoomAt(viewport.clientWidth/2,viewport.clientHeight/2,1/1.2);}}
function resetView(){{scale=1;translateX=20;translateY=20;applyTransform();}} function fitToScreen(){{const sx=(viewport.clientWidth-40)/{max_x}, sy=(viewport.clientHeight-40)/{max_y}; scale=Math.min(2.2,Math.max(.1,Math.min(sx,sy))); translateX=20;translateY=20;applyTransform();}}
viewport.addEventListener('wheel',function(e){{e.preventDefault(); const r=viewport.getBoundingClientRect(); zoomAt(e.clientX-r.left,e.clientY-r.top,e.deltaY<0?1.12:1/1.12);}},{{passive:false}});
viewport.addEventListener('mousedown',function(e){{isDragging=true;lastX=e.clientX;lastY=e.clientY;viewport.classList.add('dragging');}});
window.addEventListener('mousemove',function(e){{if(!isDragging)return; translateX+=e.clientX-lastX; translateY+=e.clientY-lastY; lastX=e.clientX; lastY=e.clientY; applyTransform();}}); window.addEventListener('mouseup',function(){{isDragging=false;viewport.classList.remove('dragging');}}); window.addEventListener('load',fitToScreen); applyTransform();
</script></body></html>"""


def render_graphviz_bytes(dot_source: str, output_format: str):
    return None, 'Graphviz SVG/PNG image rendering requires the Graphviz system executable. The dependency-free ERD viewer, DOT download, and Mermaid download do not require it.'
