
from __future__ import annotations

import json
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

LOG_FILE = Path("erm_error_log.json")
VALID_SEVERITIES = {"INFO", "WARNING", "ERROR", "CRITICAL"}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _normalise_severity(severity: str) -> str:
    sev = (severity or "INFO").upper().strip()
    return sev if sev in VALID_SEVERITIES else "INFO"


def _safe_details(details: Any) -> Any:
    if details is None:
        return ""
    if isinstance(details, (str, int, float, bool, list, dict)):
        return details
    return str(details)


def read_logs(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    if not LOG_FILE.exists():
        return []

    try:
        data = json.loads(LOG_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return []
    except Exception:
        return []

    return data[-limit:] if limit else data


def write_logs(logs: List[Dict[str, Any]]) -> None:
    LOG_FILE.write_text(json.dumps(logs, indent=2, ensure_ascii=False), encoding="utf-8")


def clear_logs() -> None:
    write_logs([])


def log_event(severity: str, module: str, action: str, message: str, details: Any = "") -> Dict[str, Any]:
    entry = {
        "timestamp": _utc_now(),
        "severity": _normalise_severity(severity),
        "module": module or "Application",
        "action": action or "",
        "message": message or "",
        "details": _safe_details(details),
    }

    logs = read_logs()
    logs.append(entry)

    if len(logs) > 2000:
        logs = logs[-2000:]

    write_logs(logs)
    return entry


def log_info(module: str, action: str, message: str, details: Any = "") -> Dict[str, Any]:
    return log_event("INFO", module, action, message, details)


def log_warning(module: str, action: str, message: str, details: Any = "") -> Dict[str, Any]:
    return log_event("WARNING", module, action, message, details)


def log_error(module: str, action: str, message: str, details: Any = "") -> Dict[str, Any]:
    return log_event("ERROR", module, action, message, details)


def log_critical(module: str, action: str, message: str, details: Any = "") -> Dict[str, Any]:
    return log_event("CRITICAL", module, action, message, details)


def log_exception(module: str, action: str, message: str, exc: BaseException, details: Any = "") -> Dict[str, Any]:
    payload = {
        "error_type": type(exc).__name__,
        "error": str(exc),
        "traceback": traceback.format_exc(),
        "details": _safe_details(details),
    }
    return log_event("ERROR", module, action, message, payload)
