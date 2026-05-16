
from __future__ import annotations

from typing import Optional, Tuple


def render_graphviz_bytes(dot_source: str, output_format: str) -> Tuple[Optional[bytes], str]:
    """Render Graphviz DOT to bytes using the local graphviz renderer.

    Returns:
        (bytes_or_none, error_message)
    """
    try:
        import graphviz
    except Exception:
        return None, (
            "The Python graphviz package is not installed. "
            "Install it with: pip install graphviz"
        )

    try:
        graph = graphviz.Source(dot_source)
        rendered = graph.pipe(format=output_format)
        return rendered, ""
    except Exception as exc:
        return None, (
            "Could not render Graphviz image. Make sure the Graphviz desktop/system "
            "renderer is installed and available on PATH. Error: " + str(exc)
        )
