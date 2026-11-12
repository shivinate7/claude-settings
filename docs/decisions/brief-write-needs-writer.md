# A read-only agent's brief never orders a file write

## The ruling

Rule `brief-write-needs-writer` in `hooks/guard.py` refuses an Agent, Task or Workflow spawn to a read-only role whose brief orders a file write. Its home is `brief_write_hit`, called at step 9e3, after the brief-destructive check at step 9e2. Layer: owner fan-out grant, 2026-11-11 13:51 CST (restart plan R42), step `brief-write-needs-writer`.

- The mistake: an Explore agent was briefed to write a file. It has no write tool, so it wrote one by a shell redirect (retrospective, 2026-11-11 20:41 CST).
- The harm: the agent writes outside its role's tools by a route no tool guard judged, or stalls on a refusal. The file lands in a checkout other sessions share.
- Judged: the read-only roles, from `READ_ONLY` in `hooks/agent_brief.py`, plugin prefix stripped, as `brief_destructive_hit` reads them. A writing role, the default role and a spawn with no role pass. A missing `READ_ONLY` makes the set empty, so the rule passes everything; the shell guard still judges the write at run time.
- What is read, in two passes of pure text work:
  - command-shaped parts (`_brief_commands`, shared with `brief-destructive-git`): a `tee` with an operand, or a redirect into a path. A quoted `>` is text, but a quoted target (`> 'a.md'`) is read. A target of `/dev/null`, under any session scratchpad, or a number (`count > 0`) is no repo write and passes.
  - prose lines outside a fence, with emphasis and quote marks around words removed: a write verb (write, save, store, dump, append, create, make, put, place, redirect) with only lead-in words in its clause before it (the list takes "so" and "when done"). The clause ends at a sentence mark, a comma, "then" or "but". After the verb, a destination word (to, into, onto, in, inside, as, at, under, named, called) must lead to a path (an extension, or a slash that is no word pair such as PASS/FAIL; an article or "file" may sit before it) or to "a file" ("to a new markdown file"). "in", "inside", "at" and "under" count only when no other preposition sits between the verb and them, so "Make a table of the rules in hooks/guard.py" is no order. Also: "create a file"; a `tee <path>` in prose; "use", "call" or "invoke" the Write tool.
- Passes: a negator in the verb's clause before it (`_brief_prohibits`) or between it and the destination ("Write nothing to a.md"), a `Must deny:` or `Add a case:` line, a negating heading's cover, prose with no file as its object, "write-up", and a word that holds a command name inside it ("committee").
- The refusal names the remedy: a writer role (record-writer, builder or test-author), or have the agent report the text in its reply.
- The override lifts it (`owner-override`).
- Accepted limits: a destination with no extension, no slash and no "file" ("write it to notes") is no order here. A comma inside the object ("Save the notes, logs to a.md") ends the clause, so the path after it is not read. A clause with a lead-in word outside the list ("Make sure you save it to a.md", "Check that the code should write to a.json") is read as no order. An order in a form this scan has no verb for passes. A one-slash path with no extension reads as a path unless it is all capitals or a stock word pair (`and/or`, `yes/no`). Claude is unlikely to write the passing forms by mistake (`guard-guards-mistakes-only`).
- Cost: pure text work inside the guard call already running. No process start, no file written.

Protected by the `brief-write-needs-writer:` cases in `tests/guard/s28508-rule9.py` (134 cases), red before the rule landed.

Kind: process
Home: hooks/guard.py
