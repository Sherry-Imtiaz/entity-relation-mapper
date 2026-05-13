
from __future__ import annotations

import json
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from logger import clear_logs, read_logs


def _logs_to_dataframe(logs: List[Dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for entry in logs:
        details = entry.get("details", "")
        if isinstance(details, (dict, list)):
            details = json.dumps(details, ensure_ascii=False)
        rows.append(
            {
                "timestamp": entry.get("timestamp", ""),
                "severity": entry.get("severity", ""),
                "module": entry.get("module", ""),
                "action": entry.get("action", ""),
                "message": entry.get("message", ""),
                "details": details,
            }
        )
    return pd.DataFrame(rows)


def render_logs_tab(state=None) -> None:
    st.subheader("Logs & Errors")
    st.caption("Review recent application events, warnings, and errors recorded locally for troubleshooting.")

    logs = read_logs()

    if not logs:
        st.info("No logs recorded yet.")
        return

    df = _logs_to_dataframe(logs)

    filter_col1, filter_col2, filter_col3 = st.columns(3)

    with filter_col1:
        severities = ["All"] + sorted([s for s in df["severity"].dropna().unique().tolist() if s])
        selected_severity = st.selectbox(
            "Severity",
            severities,
            help="Filter log entries by severity level.",
            key="logs_filter_severity",
        )

    with filter_col2:
        modules = ["All"] + sorted([m for m in df["module"].dropna().unique().tolist() if m])
        selected_module = st.selectbox(
            "Module",
            modules,
            help="Filter log entries by app module or page.",
            key="logs_filter_module",
        )

    with filter_col3:
        search_text = st.text_input(
            "Search logs",
            placeholder="Search message, action, or details",
            help="Search across action, message, and details.",
            key="logs_search_text",
        )

    filtered = df.copy()

    if selected_severity != "All":
        filtered = filtered[filtered["severity"] == selected_severity]

    if selected_module != "All":
        filtered = filtered[filtered["module"] == selected_module]

    if search_text.strip():
        needle = search_text.strip().lower()
        filtered = filtered[
            filtered.apply(
                lambda row: needle in " ".join([str(v).lower() for v in row.values]).lower(),
                axis=1,
            )
        ]

    metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
    metric_col1.metric("Total logs", len(df))
    metric_col2.metric("Filtered logs", len(filtered))
    metric_col3.metric("Errors", int((df["severity"] == "ERROR").sum()))
    metric_col4.metric("Critical", int((df["severity"] == "CRITICAL").sum()))

    st.dataframe(filtered.sort_values("timestamp", ascending=False), width="stretch", hide_index=True)

    download_col, clear_col = st.columns([2, 1])

    with download_col:
        st.download_button(
            "Download logs JSON",
            data=json.dumps(logs, indent=2, ensure_ascii=False),
            file_name="erm_error_log.json",
            mime="application/json",
        )

    with clear_col:
        if st.button("Clear logs", type="secondary", help="Clear all local application logs."):
            clear_logs()
            st.success("Logs cleared.")
            st.rerun()
