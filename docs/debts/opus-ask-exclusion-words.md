# Exclusion words in a plain model ask hold the excluded roles

**What.** A plain model ask (a prompt that names Opus or Fable) that names two or more roles, joined to an exclusion the scope read does not list, holds exactly the excluded roles until its stated length, else until the next report or 2h. Examples: "everything but builders and reviewers", "other than", "apart from", "aside from", "leave out", "builders and reviewers stay on sonnet". Reachable in normal work, by code read. The `NEGATIONS` set is a fixed list, so any other exclusion word passes. Harm: Opus spend on the excluded roles. The `opus-grant` line logs the roles, and `opus off` ends the hold. Found by review round 3, 2026-11-04.

**Where.** `_ask_scope` and its `NEGATIONS` set in `hooks/override.py`, read by `grant_model_ask`. The judge it calls, `model_ask`, sits in `hooks/call_judge.py`.

**Decision.** owner-override (an owner override lets a refused or asked act through).

**Retire.** Either add `but`, `other`, `apart`, `aside`, `save`, `leave`, `out`, `sonnet`, `haiku`, `excepted`, `excluded`, `stay`, `stays` and `remain` to `NEGATIONS`, or make `model_ask` answer false for an exclusion. The check: a plain-ask case that gives "everything but builders and reviewers" and expects no hold. Reading the code, that case holds both roles now, so it is red on the current code (unmeasured).
