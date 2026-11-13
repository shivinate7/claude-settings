# An agent runs only its own read copy of a scratchpad file, and never overwrites another agent's

## The ruling

The rule `scratchpad-owner` in `hooks/guard.py` refuses when an agent runs or overwrites a scratchpad file that another agent of its session wrote. An agent runs only its own copy of such a file, made from a read of it, and never another agent's file. Sources: the incidents below, and the owner's grant that he never wants to be asked (coordinator relay, 2026-11-11 10:01 CST), which turned each ask into a refusal. A refusal is stricter than an ask, so it opens no safety hole.

- The run incident: a builder agent in lane `notes-fix-large-1` ran `probe2.py`, a script that another agent had left in the session's shared scratchpad. No guard stopped it (2026-11-08 06:57 CST).
- The overwrite incident: a test-author took its commit message from a shared scratchpad file that another agent had overwritten. No guard stopped it (PR #1931, a pull request, 2026-11-08).
- The harm: an agent runs code it never read, or uses text another agent wrote, with effects its brief never named. An overwrite can also replace another agent's work.
- Why the scratchpad is shared: the guard keys a scratchpad by session id, and an agent carries its parent's session id. So every agent of one session shares one scratchpad (note `scratchpad-shared-per-session`).
- Test: could Claude run or overwrite another agent's file by mistake? Yes, as both incidents show. So the guard covers it (`guard-guards-mistakes-only`, guards stop Claude's mistakes, never an attacker).

## The check

- Record at write. A call with a valid `agent_id` that writes a file under this session's scratchpad records that `agent_id` as the file's writer. The record is a small sidecar under the scratchpad. The writes it covers are the Write, Edit, MultiEdit and NotebookEdit targets, and a shell write target as `_shell_write_hit` (`hooks/guard_frozen.py`) reads it.
- Judge at write. A call with a valid `agent_id` that writes over a scratchpad file whose record names another agent is refused. Write tools and shell write targets both count. Appends count too, such as `>>`. A write that passes records its writer as the latest.
- An `rm` or `mv` of another agent's file is refused too (lane ruling, 2026-11-08). It is judged, not recorded: a removed or moved file is no agent's text. Of the removers, `rm` and `mv` are judged and not recorded. `rmdir` is refused as a write too, and records the agent only when it passes.
- A refused write moves no record: the first writer stays the writer. An owner override that lifts the refusal moves the record to the agent, because the approved write lands (`on_lift` of `refuse` in `hooks/guard_core.py`).
- The remedy names a fresh file name of the agent's own. For a run it says to read the file, write an own copy under a fresh name, and run that. It never tells the agent to ask or to overwrite.
- Judge at run. A Bash call with a valid `agent_id` that runs a scratchpad file is refused when the record names another agent. A run is an interpreter word (`python*`, `bash`, `sh`, `node`, `perl`, `ruby`), `source` or `.`, a runner word (`uv run`, `bun run`, `npx tsx`, `pytest`, `python -m pytest`, `py`, `stdbuf`, `ionice`), or the path as the command word. A verb runner (`uv run`, `bun run`, `deno run`, `npx tsx`) runs its script word: the first plain word after the verb and its flags. A flag in the verb's table of flags that take a value skips its value too (`uv run --env-file D python F` judges `python`, then F). Any other flag skips only itself: a `--flag=value`, a flag with no value (`uv run -q F`, `deno run -A F`) and an unknown flag (`uv run --unknown-flag F` judges F). The words after the script word are arguments of the command it runs, and are not judged (`uv run ruff check F` runs `ruff`; `uv run -q mine.py D` runs `mine.py`). An unknown flag that takes a value makes its value the script word, so the real script is a miss. The tables are in `hooks/guard.py` (`SCRATCHPAD_VERB_VALUE_FLAGS`), each with its source. Pytest judges every plain argument. The path may be absolute, or follow a `cd`. The check also reads a command inside `$(...)`, backticks or `bash -c`, a `<` redirect into an interpreter, and a pipe into one.
- Passes:
  - a first write, to a file with no record; the write then records its writer;
  - a rewrite of the agent's own file, where the record names the same `agent_id`;
  - a call with no `agent_id`, since the top-level session may hand a script to its agent on purpose;
  - a read, which runs no code.
- Ceiling: a file written by a route the guard cannot see (`python -c`) has no record, so it passes. The same holds for an overwrite by such a route. A refusal there would be a false alarm. A `cp` destination is the copier's file, and an `mv` destination carries its source's record, or its call's writer when the same call wrote the source (`cat > x.tmp <<EOF && mv x.tmp x.py`). A `touch`, `dd of=`, `curl -o`, `wget -O`, `perl -pi`, `unlink`, `shred -u` or `>|` target is neither judged nor recorded (note `scratchpad-owner-rare-writes`). The scratchpad false alarm in trial `other-checkout-scratch-false-alarm` is the precedent: a guard refused a session's own scratchpad. A guard that goes red when nothing is wrong is spent (`guard-that-cries-wolf-is-spent`).
- Why a guard, not one scratch folder per agent: an agent cannot know its own `agent_id` to name a folder, and a folder rule in a brief has no check.

## Cost

- One small sidecar write per agent write into the scratchpad (unmeasured). Nothing for any other call.
- One stat and one read of the sidecar per agent write to a scratchpad file, and per scratchpad script an agent runs (unmeasured).
- No process, timer or log. The guard reads the sidecar on that call, so that call is its only reader.
- A test proves this cost (`outcomes-mechanize-rules`), in step `scratchpad-file-ownership`.

## Override and done check

- The owner's typed override lifts it (`owner-override`).
- Done check, step `scratchpad-file-ownership` (the roadmap step that builds the guard): red tests where the guard refuses an agent that runs a scratchpad script it did not write, or overwrites a scratchpad file another agent wrote. Red first, then green (`verification-trust-guard-after-red`).

Kind: process
Home: hooks/guard.py
