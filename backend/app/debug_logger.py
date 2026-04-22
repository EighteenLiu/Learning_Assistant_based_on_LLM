from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


SESSION_ID = "2c45df"
LOG_PATH = Path(__file__).resolve().parents[2] / "debug-2c45df.log"


def debug_log(
    *,
    hypothesisId: str,
    location: str,
    message: str,
    data: dict[str, Any] | None = None,
    runId: str = "pre-diagnose",
) -> None:
    """
    Append one NDJSON log line for this debug session.
    Keep payload free of secrets/PII.
    """

    payload = {
        "sessionId": SESSION_ID,
        "runId": runId,
        "hypothesisId": hypothesisId,
        "location": location,
        "message": message,
        "data": data or {},
        "timestamp": int(time.time() * 1000),
    }

    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=True) + "\n")
    except Exception:
        # Never block app behavior due to debug logging failures.
        pass

