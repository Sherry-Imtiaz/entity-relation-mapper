
from __future__ import annotations

import base64
from typing import Optional, Tuple


def render_graphviz_bytes(dot_source: str, output_format: str) -> Tuple[Optional[bytes], str]:
    """Render Graphviz DOT to bytes using the local Graphviz renderer."""
    try:
        import graphviz
    except Exception:
        return None, "The Python graphviz package is not installed. Install it with: pip install graphviz"

    try:
        graph = graphviz.Source(dot_source)
        return graph.pipe(format=output_format), ""
    except Exception as exc:
        return None, (
            "Could not render Graphviz image. Make sure the Graphviz desktop/system renderer "
            "is installed and available on PATH. Error: " + str(exc)
        )


def build_interactive_svg_viewer(svg_bytes: bytes, height: int = 720) -> str:
    """Build an HTML pan/zoom viewer around a rendered SVG."""
    svg_text = svg_bytes.decode("utf-8", errors="replace")
    svg_text = svg_text.replace('<?xml version="1.0" encoding="UTF-8" standalone="no"?>', "")
    svg_text = svg_text.replace('<?xml version="1.0" encoding="UTF-8"?>', "")

    return f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<style>
  html, body {{ margin: 0; padding: 0; overflow: hidden; background: #f8fafc; font-family: Arial, sans-serif; }}
  .toolbar {{ height: 44px; display: flex; gap: 8px; align-items: center; padding: 6px 10px; background: #fff; border-bottom: 1px solid #e5e7eb; box-sizing: border-box; }}
  .toolbar button {{ border: 1px solid #d1d5db; background: #fff; border-radius: 8px; padding: 6px 10px; cursor: pointer; font-size: 13px; }}
  .toolbar button:hover {{ background: #f3f4f6; }}
  .hint {{ color: #6b7280; font-size: 12px; margin-left: 8px; }}
  #viewport {{ width: 100vw; height: {height - 44}px; overflow: hidden; cursor: grab; background: #f8fafc; }}
  #viewport.dragging {{ cursor: grabbing; }}
  #canvas {{ transform-origin: 0 0; will-change: transform; display: inline-block; }}
  #canvas svg {{ max-width: none !important; height: auto !important; background: white; box-shadow: 0 1px 12px rgba(15, 23, 42, 0.12); }}
</style>
</head>
<body>
  <div class="toolbar">
    <button onclick="zoomOut()">− Zoom out</button>
    <button onclick="zoomIn()">+ Zoom in</button>
    <button onclick="resetView()">Reset</button>
    <button onclick="fitToScreen()">Fit</button>
    <span id="zoomLabel" class="hint">100%</span>
    <span class="hint">Mouse wheel to zoom. Drag to pan.</span>
  </div>
  <div id="viewport"><div id="canvas">{svg_text}</div></div>
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
function zoomIn() {{ zoomAt(viewport.clientWidth / 2, viewport.clientHeight / 2, 1.2); }}
function zoomOut() {{ zoomAt(viewport.clientWidth / 2, viewport.clientHeight / 2, 1 / 1.2); }}
function resetView() {{ scale = 1; translateX = 20; translateY = 20; applyTransform(); }}
function fitToScreen() {{
  const svg = canvas.querySelector("svg");
  if (!svg) {{ resetView(); return; }}
  let bbox;
  try {{ bbox = svg.getBBox(); }} catch (e) {{ resetView(); return; }}
  const width = bbox.width || svg.clientWidth || 1000;
  const height = bbox.height || svg.clientHeight || 600;
  const sx = (viewport.clientWidth - 40) / width;
  const sy = (viewport.clientHeight - 40) / height;
  scale = Math.min(2.5, Math.max(0.1, Math.min(sx, sy)));
  translateX = 20; translateY = 20; applyTransform();
}}
viewport.addEventListener("wheel", function(e) {{
  e.preventDefault();
  const rect = viewport.getBoundingClientRect();
  zoomAt(e.clientX - rect.left, e.clientY - rect.top, e.deltaY < 0 ? 1.12 : 1 / 1.12);
}}, {{ passive: false }});
viewport.addEventListener("mousedown", function(e) {{ isDragging = true; lastX = e.clientX; lastY = e.clientY; viewport.classList.add("dragging"); }});
window.addEventListener("mousemove", function(e) {{
  if (!isDragging) return;
  translateX += e.clientX - lastX;
  translateY += e.clientY - lastY;
  lastX = e.clientX; lastY = e.clientY;
  applyTransform();
}});
window.addEventListener("mouseup", function() {{ isDragging = false; viewport.classList.remove("dragging"); }});
window.addEventListener("load", fitToScreen);
applyTransform();
</script>
</body>
</html>
"""


def svg_download_link(svg_bytes: bytes) -> str:
    encoded = base64.b64encode(svg_bytes).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"
