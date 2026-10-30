"""Catat status tiap sumber data tambahan ke logs/sources_status.json (supaya bisa dicek tanpa membuka log GitHub)."""
import json, os
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "logs", "sources_status.json")


def record(source, ok, detail=""):
    try:
        cur = json.load(open(PATH))
    except Exception:
        cur = {}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    e = cur.get(source, {})
    e["ok"] = bool(ok)
    e["detail"] = str(detail)[:300]
    e["last_run"] = now
    if ok:
        e["last_ok"] = now
    else:
        e["last_error"] = now
    cur[source] = e
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    with open(PATH, "w") as f:
        json.dump(cur, f, indent=1, sort_keys=True)
