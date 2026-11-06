---
paths:
  - "hooks/**"
---

# Hooks

This is the one exception to rule `outcomes-mechanize-rules` (tracking reads on demand, never on every tool call). Locally, an agent's own write may read the machine load once, inside the guard hook already running for it. So may the own write of a session with an own id, to brake a lane session (decision `machine-load-brake`, the machine-load brake).
