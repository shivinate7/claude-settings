# c80 + c85: a refusal offers the override line, and the override reaches every gate

Cloud build thread brief. Build advisor (7), Oct 27, against claude-settings main b5969a2 or newer
(o13 lane C renamed the pass: decision owner-override, hooks/override.py, guard_core
set_override_context and set_override_veto). claude-settings only. Never rebase onto main after
review. Send the green, reviewed head to the build advisor; never merge. One lane: same files.

## Goal

When an override would lift a refusal, the refusal prints the exact line the owner types. Every
gate an override should reach does reach it, and a gate that cannot be reached says that no
override lifts it. Owner gripes, Oct 26: "i imagined override just overrides anything anywhere",
and the owner has to remember the syntax.

## Inputs

- c80, option (a): `guard_core.refuse()` appends the line that would lift that refusal. Take the
  syntax from hooks/override.py, its one home. A shiv-stylisms line says an agent offers that
  line as a ready answer to accept or copy. Text from an agent grants nothing, so printing the line
  cannot let a session grant itself an override. Rule git-remedy-never-names-target still holds.
  Where a refusal already gives a lossless fix (the c70 sweep), keep that fix first and put the
  override line second. Option (b), an AskUserQuestion answer that grants it, is deferred.
- c85: move each gate an override cannot reach behind refuse(), as #645 did for SendMessage:
  the Agent prompt judge in settings.json, the AskUserQuestion agent hook, the pkill and killall
  deny entries, the bin/rm and bin/merge shims, and the missing-module deny in hooks/guard.py.
  Where that cannot be done (a platform deny list, a shim outside Python), the refusal says that no
  override lifts it. The owner's own exclusions stay: frozen paths, git env vars, a kill of pid 0,
  1 or -1, the role and model guards, and worktree-home.
- Rewrite decision owner-override in place: its "Outside every override" list now matches what is
  built. Keep rule_audit pins true, and say why they move.
- This changes guards, so the review cap and the net-value test apply (rule roles-review-cap-three).

## Proof

Test-author first. Cases red on main: a refusal that an override lifts prints the override line,
and one with no override prints the no-override line. Each moved gate is lifted by an override
and refused without one. Then green. Run mutate_guard on the touched guard modules. Quick checks:
rule_audit, test_check_glossary, check_mod_versions, hook_catalog --check, check_silent_undo
--strict, shellcheck on changed *.sh, `bin/ste-changed origin/main`, and the guard suites.

## Report

At most 25 lines: draft PR, head, red-run proof, verdicts, reviewer rounds and net value (fresh Sonnet reviewer).
Port: yes, the guard is global.
