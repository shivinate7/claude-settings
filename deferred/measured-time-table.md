# A measured-time table for machine steps

**What waits.** A table of measured times for machine steps only. `bin/verdict` logs the kind,
seconds and exit of each run. It does not log this yet. CI times come from `gh run list`. The
table keeps the last 20 runs per kind. Each figure prints its n and its spread.

**Why it waits.** The owner ruled that "no estimates for agent work; rule now, table later."
The rule is `style-no-unmeasured-estimate`, which gives no time for agent work without a
measured range and its sample count. Research found that agents misjudge their own task time by
2.6-7x (AgentTime, arXiv 2610.09944; Monperrus summary of Garikaparthi). No study shows that
history fixes it. Evidence so far: local PR CI takes 8-10 min (13 runs), and main CI takes
10-15 min (13 runs).

**What keeps it from being lost.** This file.

**Trigger.** When the owner asks for the table. Then `bin/verdict` logs the per-run kind, seconds
and exit, and the table reads CI times from `gh run list`.
