# Exclusion words in a plain Opus ask grant the excluded roles

**What.** A plain Opus ask that names two or more roles, joined to an exclusion the scope read does not list, grants exactly the excluded roles. The grant reaches only the agents spawned for that ask. It ends at the owner's next typed prompt or 2h after the ask, whichever comes first. Examples: "everything but builders and reviewers", "other than", "apart from", "aside from", "leave out", "builders and reviewers stay on sonnet". Two or more roles joined by a plain list are granted, on main too, timed 2h there (coordinator, 2026-11-04 08:14 CST, under Cockpit item 226 b). Reachable in normal work, by code read. The `NEGATIONS` set is a fixed list, so any other exclusion word passes. Harm: Opus spend on the excluded roles. The grant line announces it, and `opus off` ends it. Found by review round 3, 2026-11-04.

**Where.** The plain-ask scope read `_ask_scope` and its `NEGATIONS` set in `hooks/override.py`. The judge it calls, `opus_ask`, sits in `hooks/call_judge.py`.

**Decision.** owner-override (an owner override lets a refused or asked act through).

**Retire.** Either add `but`, `other`, `apart`, `aside`, `save`, `leave`, `out`, `sonnet`, `haiku`, `excepted`, `excluded`, `stay`, `stays` and `remain` to `NEGATIONS`, or make `opus_ask` answer false for an exclusion. The check: a plain-ask case that gives "everything but builders and reviewers" and expects no grant. It is red at this lane head and green after the fix.
