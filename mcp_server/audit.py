import json
import threading
from datetime import datetime, timezone
from pathlib import Path

AUDIT_LOG = Path(__file__).parent.parent / "logs" / "audit.jsonl"
_lock = threading.Lock()


def log_event(tool: str, args: dict, result: dict, success: bool):
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "tool": tool,
        "args": {k: v for k, v in args.items() if k != "params"},
        "success": success,
        "error": result.get("error") if not success else None,
    }
    AUDIT_LOG.parent.mkdir(exist_ok=True)
    with _lock:
        with open(AUDIT_LOG, "a") as f:
            f.write(json.dumps(entry) + "\n")


def get_recent_events(n: int = 50) -> list[dict]:
    if not AUDIT_LOG.exists():
        return []
    lines = AUDIT_LOG.read_text().splitlines()
    return [json.loads(line) for line in lines[-n:] if line.strip()]
