#!/usr/bin/env python3
"""At a startup, stops the session when its model is below the floor, or when the machine is full. Prints nothing otherwise.

A SessionStart hook for source `startup` only (decisions agent-model-cap and machine-load-brake). It reads the
payload `model` and asks guard.floor_hit, the one home of the floor, whether the session tool would be refused for it.
If not, and the session is local, it reads the load once (guard.read_load) and asks guard.load_full for the readings
over the full line. A cloud session is never load-braked; the model floor still applies there. A hit prints one
line, {"continue": false, "stopReason": ...}, naming the model or the readings and the decision. The model is
checked first, so a run prints one stop at most.

Fail-open: bad JSON, a payload that is not an object, or any error prints nothing and exits 0. It never exits 2,
starts no process and writes no file.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import guard  # noqa: E402  the one home of the floor, the load reading and the cloud check


def stop_reason(payload) -> str:
    """Why this start stops, or "" when it does not."""
    if not isinstance(payload, dict) or payload.get("source") != "startup":
        return ""
    model = guard.floor_hit(guard.SESSION_TOOL, {"model": payload.get("model")})
    if model:
        return ("This session runs model %s, below the floor. Start it on Sonnet or Opus (decision agent-model-cap)."
                % model)
    if guard.is_cloud():
        return ""
    full = guard.load_full(guard.read_load())
    if full:
        return ("The machine is full: %s. Close sessions or free space, then start again (decision machine-load-brake)."
                % ", ".join(full))
    return ""


def main() -> int:
    try:
        reason = stop_reason(json.loads(sys.stdin.read()))
        if reason:
            print(json.dumps({"continue": False, "stopReason": reason}))
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
