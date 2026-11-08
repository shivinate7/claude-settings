# An agent asks before it runs another agent's scratchpad script

## The ruling

The rule `scratchpad-owner` in `hooks/guard.py` asks before an agent runs a scratchpad file that another agent of its session wrote. Source: the incident below, 2026-11-08 06:57 CST. No owner ruling is named.

- The mistake: a builder agent in lane `notes-fix-large-1` ran `probe2.py`, a script that another agent had left in the session's shared scratchpad. No guard stopped it.
- The harm: the builder ran code it never read, with effects its brief never named.
- Why the scratchpad is shared: the guard keys a scratchpad by session id, and an agent carries its parent's session id. So every agent of one session shares one scratchpad (note `scratchpad-shared-per-session`).
- Test: could Claude run another agent's script by mistake? Yes, as the incident shows. So the guard covers it (`guard-guards-mistakes-only`, guards stop Claude's mistakes, never an attacker).

## The check

- Record at write. A call with a valid `agent_id` that writes a file under this session's scratchpad records that `agent_id` as the file's writer. The record is a small sidecar under the scratchpad. The writes it covers are the Write, Edit, MultiEdit and NotebookEdit targets, and a shell write target as `_shell_write_hit` (`hooks/guard_frozen.py`) reads it.
- Judge at run. A Bash call with a valid `agent_id` that runs a scratchpad file gets "ask" when the record names another agent. A run is an interpreter word (`python*`, `bash`, `sh`, `node`, `perl`, `ruby`), `source` or `.`, or the path as the command word. The path may be absolute, or follow a `cd`.
- Passes:
  - the caller's own file, where the record names the same `agent_id`;
  - a file with no record;
  - a call with no `agent_id`, since the top-level session may hand a script to its agent on purpose;
  - a read, which runs no code.
- Ceiling: a file written by a route the guard cannot see (`python -c`, a variable path) has no record, so it passes. An ask there would be a false alarm. The scratchpad false alarm in trial `other-checkout-scratch-false-alarm` is the precedent: a guard refused a session's own scratchpad. A guard that goes red when nothing is wrong is spent (`guard-that-cries-wolf-is-spent`).
- Why a guard, not one scratch folder per agent: an agent cannot know its own `agent_id` to name a folder, and a folder rule in a brief has no check.

## Cost

- One small sidecar write per agent write into the scratchpad. Nothing for any other call.
- One stat and one read per scratchpad script an agent runs.
- No process, timer or log. The guard reads the sidecar on that run, so that run is its only reader.
- A test proves this cost (`outcomes-mechanize-rules`), in step `scratchpad-file-ownership`.

## Override and done check

- The owner's typed override lifts it (`owner-override`).
- Done check, step `scratchpad-file-ownership` (the roadmap step that builds the guard): a red test where the guard asks before an agent runs a scratchpad script it did not write. Red first, then green (`verification-trust-guard-after-red`).

Kind: process
Home: hooks/guard.py
