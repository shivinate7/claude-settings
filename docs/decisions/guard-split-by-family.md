# The guard splits into one module per rule family

## The ruling

Owner, 2026-10-12 and 2026-10-13:

- Use flat files beside `guard.py`: `guard_core.py` and one `guard_<family>.py` for each family in `hooks/test_guard.py` `FAMILIES`. Why: the installers copy files, not folders.
- `guard.py` stays the only entry point. Every name another file imports from `guard` keeps resolving through it.
- Each split PR is proven by the full suite and the mutation test in CI. The case list and the kill count must not drop.

Owner, 2026-11-25 19:06 CST, relayed by the coordinating session (Sim Manager), on moving families out of `guard.py`: "is a great idea, and should be mechanizable rather than just a one time thing (also prob deduplication of guards?)"

Owner, 2026-11-25 19:09 CST, same relay, refusing a size budget and a growth check: "if we're principled then we should just never see this kind of bloat, the gap/miss here was good practices ... the guards should've just been better split files"

## What it means

The lane reads the rulings this way; the owner's words are quoted above.

- A new rule goes in its family's module, `hooks/guard_<family>.py`. A rule with no family gets a new module and a `FAMILIES` row.
- `hooks/guard.py` is the dispatcher: the loader, `judge`, `judge_shell`, `never_lifted`, `main`, and one index line per rule. It takes no new rule body.
- A family module may define `hit(call)` and `shell_hit(call)`. The dispatcher calls each one that exists, in `_FAMILY_MODULES` order: `hit` for every judged call, `shell_hit` for every shell command. A hit refuses with `guard_core.refuse` and a literal rule id, or returns. So a new rule in a family edits that family's file only.
- No size budget and no growth check guards this. The practice does.
- Two rules that refuse the same act are merged into one. The lane reports each pair to the owner before it merges them.

## The mistake and its harm

- The Oct 13 split left `guard.py` at 1,852 lines. This record was deleted as done on Oct 17 (commit 706f1bc175). With no standing rule, each new rule landed in `guard.py`: 5,416 lines by Nov 8 and 8,977 on Nov 25.
- Harm: 17 open PRs edited the one file on Nov 25, and met in its rule index, its import block and its dispatch functions.

## State

- Built: the Oct split (16 `guard_*.py` modules), and the `hit` and `shell_hit` calls.
- In progress: lane `guard-split` moves the families still in `guard.py` into their modules, one PR per family.
- Not covered by `hit`: a rule that no override lifts still adds its test to `never_lifted`, and a SubagentStop rule still edits `judge_stop`.

## Related

- Decision `guard-guards-mistakes-only`: what a guard is for.
- Debt `guard-split-f821-lint-gap`: the lint gap the test split left.

Kind: process
Home: hooks/guard.py
