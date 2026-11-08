# A message to an agent stays inside its role

## The ruling

A SendMessage to an agent is judged by the role that agent was spawned in (`roles-one-role-per-agent`, each agent is one role). A builder is not told to change a test. A test-author is not told to change product code. `hooks/guard.py` refuses the message with `message-role-scope`. The refusal names the role to send the work to (a test-author, or a builder) and never the path (`git-remedy-never-names-target`). An owner override lifts it, and it is not in `never_lifted`: the owner may mean the message.

The receiver's role is the `subagent_type` of the newest Agent or Task spawn whose answer names the agent. The guard reads the parent transcript (`transcript_path`): the spawn is an assistant `tool_use` named Agent or Task, and the answer is the user `tool_result` for that `tool_use_id`, whose top-level `toolUseResult.agentId` equals `to`. A plugin prefix is dropped and the name is normalised with `role_key`. No transcript, no spawn record, `main`, an unreadable file, and any role but builder and test-author: the role is unknown, and an unknown role passes.

A builder's target is a test path (`is_test_rel`, the predicate of `builder_test_path`). A `mutate_*.py` file stays a builder's (decision `builders-cannot-edit-tests`). A test-author's target is a path `author_path_ok` rejects that has a file extension and is not `.md`. A workflow file passes: a test-author may add a whole test-run step, and a message cannot show which edit it asks for.

## The mistake

2026-11-07, about 21:20 CST. Lane `lane-lint-no-silent-pass` sent a running builder a message that asked it to edit a test: "`merge/test_lane_lint.py ~683: ... holds for any Liftable. Replace it with an assert on ...`". The role guards judge the builder's own write, and a message is no write.

## The harm, stated honestly

This rule saves a wasted round. It does not stop an unseen test change. `role_write_hit` (`builder-test-edit`) already refuses the builder's Edit or Write of that test, and the SubagentStop builder-diff check (`builder-diff`) already refuses a test change that reaches its tree. So the builder never lands the edit. The message only costs a turn of the builder refusing, and a report that the orchestrator then routes to a test-author. Refusing the message at the sender saves that turn and tells the sender the right route at once.

## What a message edits

The verdict is per sentence. A refusal needs an edit verb: edit, change, fix, update, modify, replace, rewrite, add, remove, delete, drop, re-point, write, make (`make the fix in X`). The verb must govern a path:

- the path follows the verb in the same clause, or leads the clause (`X.py: add a case`), or
- the verb's clause names no path of its own, and an earlier clause of the same sentence names it (`Look at X, then fix it`), else the sentence right before does. The sentence form is the incident form: "X.py ~683: ... . Replace it with ...". A path that a read verb names carries, a path that a run verb names does not.

A test node id (`X.py::case`) names its file.

A prohibition is no order: `not`, `don't`, `never` or `without` earlier in the clause clears the verb. A path is not governed when it is the object of run, read, check or show, when it goes green or passes (`make X green`, `make X pass`), when it follows `to pass`, `to match` or `to satisfy` (the target), when it follows `the rule in` or another spec noun and `in`, `of` or `from` (the spec), or when it sits inside a command (`python3 ...`, `verdict ...`, or a backtick span of several words). A clause ends at `;`, `then`, `so`, a sentence end, and an `and` before a word that is neither an edit verb, a determiner nor a path. A verb after a determiner (`the fix`) is a noun. A verb after another agent's name (`the builder will fix guard.py`) or after `I` or `we` is that agent's act, not the receiver's.

## Accepted limits

The guard stops Claude's mistakes, not an attacker (`guard-guards-mistakes-only`).

- A message that names no path (`fix the failing case`) passes. The sender names the file in the incident form and in most messages; the builder's own write guards stay behind it.
- A path built in a way the reader does not see (a glob, a variable, `the file above`) passes.
- A verb outside the list (`touch`, `tweak`, `patch`) passes.
- A carry reaches the nearest earlier clause of the sentence, else one sentence back. A path two sentences back is not read. `Run X. Fix the failure` carries nothing, because X was run, though the failure may sit in X.
- `Fix guard.py. Add a note to your report.`, sent to a test-author, is refused: the verb's clause names no path, so it takes guard.py from the sentence before.
- `Make sure X ...` is no edit, but a prohibition worded another way (`avoid changing X`, `leave X alone`) is not read as one.
- A word with no slash is a path only with a known file extension. A path with a slash and an unknown extension counts.
- A message that names another agent, or `I` or `we`, before the verb passes. `Ask the builder to fix guard.py` is a hand-off and is right to pass. `The builder should also edit tests/x.py`, sent to a builder, is a miss.
- A test-author's workflow edit passes, and a path outside every repository passes (as in `role_write_hit`).
- The role comes from the spawn only. A session started with `--agent builder` has no spawn record and passes.
- `mcp__claude-code-remote__send_message` is not judged. It addresses a session, not an agent, and a session has no spawn role.

## Cost

One more guard process start per SendMessage, as the matcher in `settings.json` now lists `SendMessage` beside the existing `sendmessage_state.py` hook. One transcript read per SendMessage whose message edits a path: a line scan that parses only lines naming `subagent_type` or the agent id. A plain message reads no transcript. No timer, no long-lived process, no file written beyond the refusal's one guard.log line.

## Measure

`MUTATE_ONLY=message-role: hooks/test_guard.py`: the `message-role` cases, 7 refusals and 13 passes. `hooks/mutate_guard.py` carries one mutant per edge those cases pin, labelled `message-role:`.

Kind: process
Home: hooks/guard.py
