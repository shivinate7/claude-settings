# A message to an agent stays inside its role

## The ruling

A SendMessage to an agent is judged by the role that agent was spawned in (`roles-one-role-per-agent`, each agent is one role). A builder is not told to change a test. A test-author is not told to change product code. `hooks/guard.py` refuses the message with `message-role-scope`. The refusal names the role to send the work to (a test-author, or a builder) and never the path (`git-remedy-never-names-target`). An owner override lifts it, and it is not in `never_lifted`: the owner may mean the message.

The receiver's role is the `subagent_type` of the newest Agent or Task spawn whose answer names the agent. The guard reads the parent transcript (`transcript_path`). The spawn is an assistant `tool_use` named Agent or Task. The answer is the user `tool_result` for that `tool_use_id`, whose top-level `toolUseResult.agentId` equals `to`. A plugin prefix is dropped and the name is normalised with `role_key`. No transcript, no spawn record, `main`, an unreadable file, and any role but builder and test-author: the role is unknown, and an unknown role passes.

A builder's target is a test path (`is_test_rel`, the predicate of `builder_test_path`). A `mutate_*.py` file stays a builder's (decision `builders-cannot-edit-tests`). A test-author's target is a path `author_path_ok` rejects that has a file extension and is not `.md`. A workflow file passes: a test-author may add a whole test-run step, and a message cannot show which edit it asks for.

## The mistake

2026-11-07, about 21:20 CST. Lane `lane-lint-no-silent-pass` sent a running builder a message that asked it to edit a test: "`merge/test_lane_lint.py ~683: ... holds for any Liftable. Replace it with an assert on ...`". The role guards judge the builder's own write, and a message is no write.

## The harm, stated honestly

This rule saves a wasted round. It does not stop an unseen test change. `role_write_hit` (`builder-test-edit`) already refuses the builder's Edit or Write of that test, and the SubagentStop builder-diff check (`builder-diff`) already refuses a test change that reaches its tree. So the builder never lands the edit. The message only costs a turn of the builder refusing, and a report that the orchestrator then routes to a test-author. Refusing the message at the sender saves that turn and tells the sender the right route at once.

## What a message edits

The verdict is per clause. A refusal needs an edit verb: edit, change, fix, update, modify, replace, rewrite, add, remove, delete, drop, re-point, write, make (`make the fix in X`). Each edit verb governs one object:

- The object is the first path after the verb in its clause, and a path joined to it by `and`, `or` or a comma. A later path is a spec or a target: `Make guard.py handle the case in tests/x.py` and `Fix guard.py for/as/to satisfy ... tests/x.py` edit guard.py only.
- With no path right after the verb (a determiner or `file` may sit between), a noun phrase then `in`, `at`, `of`, `to` or `into` and the path governs that path (`Fix the failing case in X`, `Make the fix in X`, `Add a case to X`). After another preposition (`for`, `as`, `with`) the path is a spec.
- A noun phrase whose head is note, report or summary governs nothing (`Make a note of the failures in X`).
- A test noun as the head (case, cases, test, assert) makes the path a spec when a test-author is sent it (`Add red cases for the empty brief in hooks/guard.py`). A builder is still judged on that path.
- With no object, a path that leads the clause is governed (`X.py: add a case`, `The assertion at X is not specific, replace it`).
- A clause whose edit verb names no path takes one from the nearest earlier clause of its sentence (`Look at X, then fix it`), else from the sentence right before. That is the incident form: "X.py ~683: ... . Replace it with ...". A path an edit verb governed carries to any such clause. A path a read verb named, or a path that led its clause, carries only to an anaphor right after the edit verb: it, that, them, or a role noun after the/this/that/these. A test-side noun (assert, assertion, case, cases, test, tests, expected value, fixture) carries only a test path. A product-side noun (guard, bug, code, hook, function, fix) carries only a product path. A role noun is an anaphor only when it ends the clause, or a comma or a preposition (`to`, `with`, `in`) follows it. Another word after it makes a noun compound, which is no anaphor: `Fix the assertion error`, `Write the guard tests`. So `Read X. Replace that assert.` and `X:683 holds. Fix the tests.` carry a test path, and `CI is red on hooks/guard.py. Fix the guard.` carries a product path. `Read X. Fix the cause.` carries nothing. An anaphor that goes green is a goal and takes no path (`Red cases are in X. Make them green.`, `Make that pass.`): the green word must follow the anaphor at once, with no comma between. One filler may sit between: `all`, `finally`, or `new` and a noun (`Make them all pass`, `Make that new case pass`). `Make it pass by <gerund> X` edits X. A role noun X narrows the carry to its side: `by changing the expected value to 3` carries a test path, and `by fixing the guard` carries a product path only. Any other X keeps the anaphor's side. Ruling: lane, 2026-11-07 22:40 CST, process-only. The role nouns, the quoted carry and the edit gerund: ruling, lane, 2026-11-08 01:08 CST, process-only. A path a run verb names never carries.

A test node id (`X.py::case`) names its file.

A prohibition is no order. `not`, `don't`, `never` or `without` right before an edit verb clears that verb only, with one adverb allowed between (`don't just fix`). `Don't forget to update X` is an order, and in `Don't just fix A, also update B` the update of B is an order. A negation before another word (`is not specific`) clears nothing. A cleared verb still takes its object, so a later verb of the clause does not read that path as leading the clause.

A path is not governed when it is the object of run, read, check or show, or when it goes green or passes (`make X green`, `make X pass`). Nor is it governed when it follows `pass`, `match` or `satisfy` (the target), or sits inside a command or a quoted example (`python3 ...`, `verdict ...`, or a backtick or double-quoted span of several words). A path inside a double-quoted span is still a read path for a carry: `Quote: "X:12 is wrong". Fix it.` carries X. A clause ends at `;`, `then`, `so`, a sentence end, and an `and` before a word that is neither an edit verb, a determiner nor a path. A verb after a determiner (`the fix`) is a noun. A verb after another agent's name (`the builder will fix guard.py`) or after `I` or `we` is that agent's act, not the receiver's.

## Accepted limits

The guard stops Claude's mistakes, not an attacker (`guard-guards-mistakes-only`). A false alarm costs more than a rare miss here, because the write guards still stop the edit itself.

- A message that names no path (`fix the failing case`) passes. The sender names the file in the incident form and in most messages; the builder's own write guards stay behind it.
- A path built in a way the reader does not see (a glob, a variable, `the file above`) passes.
- A verb outside the list (`touch`, `tweak`, `patch`) passes.
- A carry reaches the nearest earlier clause of the sentence, else one sentence back. A path two sentences back is not read. `Run X. Fix the failure` carries nothing, because X was run, though the failure may sit in X.
- A read path, or a path that led its clause, carries only to an anaphor right after the verb, and only across clauses. `Read X. Fix the failing case.`, `Read X and fix it` and `X is wrong. Fix the failing assert.` pass.
- A noun compound is no anaphor, so `Read tests/x.py. Fix the fixture bug.` and `Fix the guard tests` pass. A role noun before `and` is a compound too: `Fix the tests and the guard` carries nothing.
- `Make it pass by <gerund> X`, where X is a path, carries nothing, because that clause names a path. X is not governed either, so `Make it pass by editing tests/x.py` to a builder passes. A compound X (`by fixing the guard code`) keeps the anaphor's side.
- `finally` as a goal filler has no case of its own.
- A double-quoted span of several words is data, so an order written in quotes (`Do this: "edit tests/x.py"`) passes. So does a quoted order inside an `Ask:` line. Only a later pathless edit with an anaphor carries a quoted path.
- `Fix guard.py. Add a note to your report.`, sent to a test-author, is refused: the verb's clause names no path, and guard.py was governed in the sentence before.
- A path after a preposition that is no location passes, though the message may mean it: `Fix the bug for tests/x.py`. A path that is not the first after the verb passes: `Fix guard.py and the case in tests/x.py`.
- A test-author is not refused `Add a case to hooks/guard.py`: a test noun object makes the path a spec.
- `Make sure X ...` is no edit, but a prohibition worded another way (`avoid changing X`, `leave X alone`) is not read as one.
- A word with no slash is a path only with a known file extension. A path with a slash and an unknown extension counts.
- A message that names another agent, or `I` or `we`, before the verb passes. `Ask the builder to fix guard.py` is a hand-off and is right to pass. `The builder should also edit tests/x.py`, sent to a builder, is a miss.
- A test-author's workflow edit passes, and a path outside every repository passes (as in `role_write_hit`).
- The role comes from the spawn only. A session started with `--agent builder` has no spawn record and passes.
- `mcp__claude-code-remote__send_message` is not judged. It addresses a session, not an agent, and a session has no spawn role.

## Cost

One more guard process start per SendMessage, as the matcher in `settings.json` now lists `SendMessage` beside the existing `sendmessage_state.py` hook. One transcript read per SendMessage whose message edits a path: a line scan that parses only lines naming `subagent_type` or the agent id. A plain message reads no transcript. No timer, no long-lived process, no file written beyond the refusal's one guard.log line.

## Measure

`MUTATE_ONLY=message-role: hooks/test_guard.py`: the `message-role` cases, 37 refusals, 57 passes and 1 crash check (`quotespan0`). `hooks/mutate_guard.py` carries one mutant per edge those cases pin, labelled `message-role:`.

## Spawn briefs

An Agent or Task spawn's brief is judged by the clause reader of "What a message edits". `brief_role_hit` in `hooks/guard.py` runs before the agent starts. It asks. It never denies. An override lifts it.

It stops a brief that sends a role outside its scope:

- A builder briefed to change a test.
- A test-author briefed to change product code or a Markdown file.

The ask names the role to send the work to: a test-author, a builder or a record-writer. It never names the path.

The mistake it stops: on 2026-11-08 the write guard refused two test-author edits of `docs/debts/notes.md` mid-task, at 09:18 and 09:20 CST (`test-author-scope`). The write guard still refuses the edit itself. This check asks at spawn, before the agent runs.

How it reads the role:

- The role is the spawn's `subagent_type`. The part after the last `:` is kept, then `role_key` applies. `plugin:test-author` and `Test-Author ` both read as a test-author.
- No transcript is read. `Task` is judged the same as `Agent`.

Which paths count:

- A builder: a test path only (`is_test_rel`). The exclusions below do not apply to a builder.
- A test-author: an edit of a path with a file extension that `author_path_ok` rejects. A Markdown path counts. Unlike a message, the ask says "to a record-writer".
- Shared with the message rule, these pass for a test-author: a test-noun spec (`Add red cases for ... in hooks/guard.py`), a workflow file, a `../` path, and an extensionless path such as `Makefile`.

Known gap:

- `Edit only X` and `Edit just X` pass unasked. The reader takes no object after `only` or `just`, so an off-role path in that form is not read. The message rule shares the reader and misses the same form.
- The write guard still refuses the agent's own edit. The cost is one wasted turn.
- The reverse form asks. `Fix hooks/guard.py is not your job` asks, because a negation after the path clears nothing.
- The first form is filed as a note, `brief-role-edit-only-passes`, with no fix queued.

Check:

- `MUTATE_ONLY=brief-role python3 hooks/test_guard.py` runs the 13 `brief-role` cases: 5 asks and 8 passes. The filter is a substring match on case names.
- `hooks/mutate_guard.py` has no mutant for this rule.

Cost: no transcript is read. The guard already judges `Agent` and `Task` calls (`settings.json`), so this adds no hook.

Kind: process
Home: hooks/guard.py
