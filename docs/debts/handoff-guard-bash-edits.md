# A shell edit of a handoff skips the handoff-sections rule

**What.** The `handoff-sections` rule judges only Write, Edit and MultiEdit. A Bash edit of a handoff (a `python` write, `sed -i`, a redirect) is caught only by the Stop flag after the turn. Mistake: Claude edits its handoff in the shell and drops a required section. Harm: the missing section is found one turn late. Reported 2026-11-08 (lane handoff-sections-kept). Read again on main: the rule text still names only the three file tools.

**Where.** `hooks/guard.py`, rule `handoff-sections`.

**Decision.** `precompact-handoff` (checkpoints keep the handoff current), item 14 (a handoff keeps every required section). The debt `stamp-shell-write-not-judged` holds the same gap for the checked-stamp rule.

**Retire.** A red case, a `sed -i` or a `python` write that removes a required section from a handoff, expects a refusal. Test file: `hooks/test_guard.py`.
