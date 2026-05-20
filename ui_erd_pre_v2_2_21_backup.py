
from __future__ import annotations
import copy
from typing import Dict, List, Optional
import streamlit as st
import streamlit.components.v1 as components
from erd_rendering import build_dependency_free_erd_viewer
from exports import export_dot, export_mermaid
from models import ErdState


def _multi_context_options(state: ErdState) -> Dict[str, str]:
    options: Dict[str, str] = {}
    for context_id, context in sorted(getattr(state, 'relationship_contexts', {}).items(), key=lambda item: getattr(item[1], 'name', item[0]).lower()):
        name = getattr(context, 'name', context_id)
        context_type = getattr(context, 'context_type', '')
        label = f'{name} ({context_type})' if context_type else name
        if label in options:
            label = f'{label} [{context_id}]'
        options[label] = context_id
    return options


def _full_table(schema_name: str, table_name: str) -> str:
    schema = (schema_name or '').strip()
    table = (table_name or '').strip()
    return f'{schema}.{table}' if schema else table


def _relationship_tables(rel) -> tuple[str, str]:
    source_full = getattr(rel, 'source_full_table', None) or _full_table(getattr(rel, 'source_schema', ''), getattr(rel, 'source_table', ''))
    target_full = getattr(rel, 'target_full_table', None) or _full_table(getattr(rel, 'target_schema', ''), getattr(rel, 'target_table', ''))
    return source_full, target_full


def _relationships_for_contexts(state: ErdState, context_ids: Optional[List[str]], active_only: bool) -> dict:
    rels = {}
    for rel_id, rel in getattr(state, 'relationships', {}).items():
        if context_ids is not None and getattr(rel, 'context_id', '') not in context_ids:
            continue
        if active_only and not bool(getattr(rel, 'active', True)):
            continue
        rels[rel_id] = rel
    return rels


def _build_scoped_state(state: ErdState, context_ids: Optional[List[str]], active_only: bool, connected_only: bool) -> ErdState:
    scoped = copy.deepcopy(state)
    scoped.relationships = _relationships_for_contexts(state, context_ids, active_only=active_only)
    if connected_only:
        connected = set()
        for rel in scoped.relationships.values():
            source_full, target_full = _relationship_tables(rel)
            connected.add(source_full); connected.add(target_full)
        scoped.tables = {k: t for k, t in getattr(state, 'tables', {}).items() if k in connected or getattr(t, 'full_name', '') in connected or _full_table(getattr(t, 'schema_name', ''), getattr(t, 'table_name', '')) in connected}
    return scoped


def _dedupe_whole_database_if_available(display_state: ErdState, is_whole_database: bool, active_only: bool) -> ErdState:
    if not is_whole_database:
        return display_state
    try:
        from relationship_duplicates import deduplicated_relationships_for_whole_database
        scoped = copy.deepcopy(display_state)
        scoped.relationships = deduplicated_relationships_for_whole_database(display_state, active_only=active_only)
        return scoped
    except Exception:
        return display_state


def _selected_context_ids_from_ui(state: ErdState) -> tuple[Optional[List[str]], str, bool]:
    mode = st.radio('ERD context selection mode', ['Whole database', 'Selected relationship contexts'], horizontal=True, key='erd_context_mode_v2220')
    if mode == 'Whole database':
        return None, 'Whole database', True
    context_options = _multi_context_options(state)
    if not context_options:
        st.warning('No relationship contexts are available.')
        return [], 'No contexts selected', False
    selected_labels = st.multiselect('Relationship contexts to include', list(context_options.keys()), default=list(context_options.keys())[:1], key='erd_context_multiselect_v2220', help='Select one or more relationship contexts to show in the ERD.')
    context_ids = [context_options[label] for label in selected_labels if label in context_options]
    label = ', '.join(selected_labels) if selected_labels else 'No contexts selected'
    return context_ids, label, False


def render_erd_tab(state: ErdState) -> None:
    st.subheader('ERD View')
    if not getattr(state, 'tables', {}):
        st.info('Load tables first.'); return
    context_ids, selected_label, is_whole_database = _selected_context_ids_from_ui(state)
    only_active = st.checkbox('Only include active relationships', value=True, key='erd_only_active_v2220')
    connected_only = st.checkbox('Show only tables connected to selected relationship contexts', value=True, key='erd_connected_only_v2220')
    display_mode = st.radio('ERD display mode', ['Dependency-free interactive viewer', 'Static Streamlit Graphviz', 'DOT source'], index=0, horizontal=True, key='erd_display_mode_v2220', help='The dependency-free viewer supports zoom and pan without Graphviz system installation.')
    display_state = _build_scoped_state(state, context_ids=context_ids, active_only=only_active, connected_only=connected_only)
    display_state = _dedupe_whole_database_if_available(display_state, is_whole_database, only_active)
    st.info(f'Current ERD scope: {selected_label}')
    st.caption(f"Tables shown: {len(getattr(display_state, 'tables', {}))} | Relationships shown: {len(getattr(display_state, 'relationships', {}))}")
    if not getattr(display_state, 'tables', {}):
        st.warning('No tables are available for this ERD scope. Check the selected contexts or table import.'); return
    dot = export_dot(display_state, only_active=False)
    mermaid = export_mermaid(display_state, only_active=False)
    if display_mode == 'Dependency-free interactive viewer':
        viewer_height = st.slider('Interactive viewer height', min_value=400, max_value=1200, value=760, step=40, key='erd_dependency_free_height_v2220')
        html = build_dependency_free_erd_viewer(display_state, height=viewer_height)
        components.html(html, height=viewer_height, scrolling=False)
    elif display_mode == 'Static Streamlit Graphviz':
        st.graphviz_chart(dot, width='stretch')
    else:
        st.code(dot, language='dot')
    st.markdown('### Downloads')
    dot_col, mermaid_col = st.columns(2)
    with dot_col:
        st.download_button('Download DOT', data=dot, file_name='erd_graphviz.dot', mime='text/plain')
    with mermaid_col:
        st.download_button('Download Mermaid', data=mermaid, file_name='erd_mermaid.mmd', mime='text/plain')
    with st.expander('Why SVG/PNG downloads are disabled by default'):
        st.write('SVG and PNG image export require the Graphviz system executable called `dot`. That executable is separate from the Python package and is often not available on local Windows machines or Streamlit Cloud unless installed as a system package. The dependency-free interactive viewer, DOT download, Mermaid download, and static Streamlit Graphviz view do not require server-side Graphviz image rendering.')
        st.code('Streamlit Cloud optional packages.txt:\ngraphviz', language='text')
    with st.expander('Mermaid export text'):
        st.code(mermaid, language='mermaid')
