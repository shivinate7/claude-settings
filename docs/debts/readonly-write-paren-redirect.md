# A descriptor duplicate before a `)` reads as a file

- **What.** A read-only agent's shell call (a reviewer or Explore, for example) is refused though it writes nothing when a `)` follows a descriptor duplicate, as in `x=$(git status 2>&1)`, `out=$(python3 -c "print(1)" 2>&1)`, `(ls 2>&1)` and `(cd /tmp && ls >&2)`. The target reads as `&1)`, not `&1`, so it counts as a file, and a reviewer meets this often; the refusal's remedy (write to your scratchpad) misleads.
- **Where.** The read-only shell rule (`readonly-shell-write`) in the guard hook, `hooks/guard.py`: the descriptor-duplicate match in `_redirect_targets`, which `readonly_write_hit` calls.
- **Decision.** `guard-guards-mistakes-only` (a guard stops Claude's mistakes, not an attacker's; a false alarm is spent).
- **Retire.** Strip a closing `)` from a descriptor-duplicate target, and add refusal-free cases for those four commands to `tests/guard/s42841-readonly-shell-write.py` (the read-only shell section file). `hooks/test_guard.py` (the guard test suite, which runs that folder's section files) runs them green.
