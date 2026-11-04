---
paths:
  - "hooks/**"
---

# Hooks

This is the one exception to rule `outcomes-mechanize-rules` (tracking reads on demand, never on every tool call). Locally, an agent's own write, and a session's own write when it has an own id (to brake a lane session), may read the machine load once, inside the guard hook already running for it (decision `machine-load-brake`, the machine-load brake).
