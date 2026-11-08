# An agent asks before it runs or overwrites another agent's scratchpad file

## The ruling

The rule `scratchpad-owner` in `hooks/guard.py` asks when an agent runs or overwrites a scratchpad file that another agent of its session wrote. Sources: the incidents below. No owner ruling is named.

- The run incident: a builder agent in lane `notes-fix-large-1` ran `probe2.py`, a script that another agent had left in the session's shared scratchpad. No guard stopped it (2026-11-08 06:57 CST).
- The overwrite incident: a test-author took its commit message from a shared scratchpad file that another agent had overwritten. No guard stopped it (PR #1931, a pull request, 2026-11-08).
- The harm: an agent runs code it never read, or uses text another agent wrote, with effects its brief never named. An overwrite can also replace another agent's work.
- Why the scratchpad is shared: the guard keys a scratchpad by session id, and an agent carries its parent's session id. So every agent of one session shares one scratchpad (note `scratchpad-shared-per-session`).
- Test: could Claude run or overwrite another agent's file by mistake? Yes, as both incidents show. So the guard covers it (`guard-guards-mistakes-only`, guards stop Claude's mistakes, never an attacker).

## The check

- Record at write. A call with a valid `agent_id` that writes a file under this session's scratchpad records that `agent_id` as the file's writer. The record is a small sidecar under the scratchpad. The writes it covers are the Write, Edit, MultiEdit and NotebookEdit targets, and a shell write target as `_shell_write_hit` (`hooks/guard_frozen.py`) reads it.
- Judge at write. A call with a valid `agent_id` that writes over a scratchpad file whose record names another agent gets "ask". Write tools and shell write targets both count. Appends count too, such as `>>`. A write that passes records its writer as the latest.
- An `rm` or `mv` of another agent's file asks too (lane ruling, 2026-11-08). It is judged, not recorded: a removed or moved file is no agent's text. Of the removers, `rm` and `mv` are judged and not recorded. `rmdir` also asks, as a write, and records the asker; it fails on a file, so that does no harm.
- The record is written before the overwrite ask, because an approval in the UI never reaches the guard again. It keeps the previous writer and the file's mtime. While the file's mtime still equals the stored one, the write did not land, so the guard judges by the previous writer. The mtimes are compared for equality, never by order.
- Judge at run. A Bash call with a valid `agent_id` that runs a scratchpad file gets "ask" when the record names another agent. A run is an interpreter word (`python*`, `bash`, `sh`, `node`, `perl`, `ruby`), `source` or `.`, or the path as the command word. The path may be absolute, or follow a `cd`.
- Passes:
  - a first write, to a file with no record; the write then records its writer;
  - a rewrite of the agent's own file, where the record names the same `agent_id`;
  - a call with no `agent_id`, since the top-level session may hand a script to its agent on purpose;
  - a read, which runs no code.
- Ceiling: a file written by a route the guard cannot see (`python -c`) has no record, so it passes. The same holds for an overwrite by such a route. An ask there would be a false alarm. A `cp` destination is the copier's file, and an `mv` destination carries its source's record. A `touch`, `dd of=`, `curl -o` or `>|` target is not recorded (note `scratchpad-owner-rare-writes`). The scratchpad false alarm in trial `other-checkout-scratch-false-alarm` is the precedent: a guard refused a session's own scratchpad. A guard that goes red when nothing is wrong is spent (`guard-that-cries-wolf-is-spent`).
- Why a guard, not one scratch folder per agent: an agent cannot know its own `agent_id` to name a folder, and a folder rule in a brief has no check.

## Cost

- One small sidecar write per agent write into the scratchpad. Nothing for any other call.
- One stat and one read of the sidecar per agent write to a scratchpad file, and per scratchpad script an agent runs.
- No process, timer or log. The guard reads the sidecar on that call, so that call is its only reader.
- A test proves this cost (`outcomes-mechanize-rules`), in step `scratchpad-file-ownership`.

## Override and done check

- The owner's typed override lifts it (`owner-override`).
- Done check, step `scratchpad-file-ownership` (the roadmap step that builds the guard): red tests where the guard asks before an agent runs a scratchpad script it did not write, and before it overwrites a scratchpad file another agent wrote. Red first, then green (`verification-trust-guard-after-red`).

Kind: process
Home: hooks/guard.py
