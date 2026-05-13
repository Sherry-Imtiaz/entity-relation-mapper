
from __future__ import annotations

import json
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from logger import clear_logs, read_logs

SEVERITY_ORDER = {"CRITICAL": 0, "ERROR": 1, "WARNING": 2, "INFO": 3}


def _logs_to_dataframe(logs: List[Dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for entry in logs:
        details = entry.get("details", "")
        if isinstance(details, (dict, list)):
            details = json.dumps(details, ensure_ascii=False)
        rows.append({"timestamp": entry.get("timestamp", ""), "severity": entry.get("severity", ""), "module": entry.get("module", ""), "action": entry.get("action", ""), "message": entry.get("message", ""), "details": details})
    return pd.DataFrame(rows)


def _apply_sort(df: pd.DataFrame, sort_by: str, direction: str) -> pd.DataFrame:
    if df.empty:
        return df
    ascending = direction in {"Ascending", "Oldest first", "A to Z"}
    if sort_by == "Severity / log type":
        sorted_df = df.copy()
        sorted_df["_severity_order"] = sorted_df["severity"].map(SEVERITY_ORDER).fillna(99)
        return sorted_df.sort_values("_severity_order", ascending=ascending).drop(columns=["_severity_order"])
    if sort_by == "Timestamp":
        return df.sort_values("timestamp", ascending=ascending)
    column = {"Module": "module", "Action": "action", "Message": "message"}.get(sort_by, "timestamp")
    return df.sort_values(column, ascending=ascending)


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
        selected_severity = st.selectbox("Severity", severities, help="Filter log entries by severity level.", key="logs_filter_severity")
    with filter_col2:
        modules = ["All"] + sorted([m for m in df["module"].dropna().unique().tolist() if m])
        selected_module = st.selectbox("Module", modules, help="Filter log entries by app module or page.", key="logs_filter_module")
    with filter_col3:
        search_text = st.text_input("Search logs", placeholder="Search message, action, or details", help="Search across action, message, and details.", key="logs_search_text")
    sort_col1, sort_col2 = st.columns(2)
    with sort_col1:
        sort_by = st.selectbox("Sort logs by", ["Timestamp", "Severity / log type", "Module", "Action", "Message"], key="logs_sort_by", help="Choose the field used to sort the log table.")
    with sort_col2:
        direction_options = ["Newest first", "Oldest first"] if sort_by == "Timestamp" else ["Ascending", "Descending"]
        direction = st.selectbox("Sort direction", direction_options, key="logs_sort_direction")
    filtered = df.copy()
    if selected_severity != "All":
        filtered = filtered[filtered["severity"] == selected_severity]
    if selected_module != "All":
        filtered = filtered[filtered["module"] == selected_module]
    if search_text.strip():
        needle = search_text.strip().lower()
        filtered = filtered[filtered.apply(lambda row: needle in " ".join([str(v).lower() for v in row.values]).lower(), axis=1)]
    filtered = _apply_sort(filtered, sort_by, direction)
    metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
    metric_col1.metric("Total logs", len(df))
    metric_col2.metric("Filtered logs", len(filtered))
    metric_col3.metric("Warnings", int((df["severity"] == "WARNING").sum()))
    metric_col4.metric("Errors/Critical", int(((df["severity"] == "ERROR") | (df["severity"] == "CRITICAL")).sum()))
    st.dataframe(filtered, width="stretch", hide_index=True)
    download_col, clear_col = st.columns([2, 1])
    with download_col:
        st.download_button("Download logs JSON", data=json.dumps(logs, indent=2, ensure_ascii=False), file_name="erm_error_log.json", mime="application/json")
    with clear_col:
        if st.button("Clear logs", type="secondary", help="Clear all local application logs."):
            clear_logs()
            st.success("Logs cleared.")
            st.rerun()
