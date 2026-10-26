# c50: deleting a hook script never breaks a session that is still running

Cloud build thread brief. Build advisor, Oct 26, against claude-settings main 3f71d6b.

## Incident

A session deleted a hook script after checking installs on both machines, but not sessions still
running. A live session keeps the hook list it read at start. It kept calling the deleted script,
and Edit and Write failed for that session and every agent it started, until it restarted.

## Facts at 3f71d6b

- Most settings.json hook commands already fail open on a missing script (`[ -f "$g" ] || exit 0`).
- hooks/guard.py and hooks/rm_prompt_answer.py fail closed on a missing script by design: they
  print "claude-settings gate not runnable (script missing)". Safety guards stay fail-closed
  (decision on fail-closed guards; c15 note).
- Precedent: lint/ste_gate.py and lint/md_sweep.py were kept as exit-0 stubs for old installs
  after their hooks left settings.json (debt ste-stubs-delete).

## Task

1. Find the cause. Use git log on hooks/, lint/ and janitor/ to list hook scripts deleted in the
   last 30 days, and the settings.json command form that called each at the time. Name which
   form broke: an old entry with no missing-script check, a fail-closed entry, or something else.
2. Fix it in one home. Pick the cheapest one that covers the cause:
   (a) a CI check (in lint/, run by gates.yml) that fails when a script referenced by settings.json
   at the previous release tag or at main~N is deleted with no stub left in its place; the stub
   is an exit-0 file with its delete date, removed one release later; or
   (b) every non-guard entry fails open, and the guard entries keep failing closed but are never
   deleted without a stub.
   Recommended: (a), since it follows the ste_gate precedent and keeps the guard fail-closed.
   Record the rule in place in the decision that owns hook wiring (find it with git grep).

## Failure classes

- A check that passes when the script is missing but the old settings still call it. Red case
  first: a fixture where settings at the base commit call a script the head deletes with no stub.
- A false alarm on a script that no settings version ever called. Green control.
- Any change that turns a fail-closed guard into fail-open. Out of scope; the reviewer checks it.

## Roles

Orchestrate: test-author, builder, fresh reviewer (it changes a check's verdict). Base: main.
PR stops at green; merge waits for c53 (merge.py from the cloud) or shiv's merge.py run.

## Report (25 lines max)

Done, Deviations, Input Needed, Next. Name the cause found, the PR, the red then green tests.
