# A read-only agent's brief never orders a file write

## The ruling

Rule `brief-write-needs-writer` in `hooks/guard.py` refuses an Agent, Task or Workflow spawn to a read-only role whose brief orders a file write. Its home is `brief_write_hit`, called at step 9e3, after the brief-destructive check at step 9e2. Layer: owner fan-out grant, 2026-11-11 13:51 CST (restart plan R42), step `brief-write-needs-writer`.

- The mistake: an Explore agent was briefed to write a file. It has no write tool, so it wrote one by a shell redirect (retrospective, 2026-11-11 20:41 CST).
- The harm: the agent writes outside its role's tools by a route no tool guard judged, or stalls on a refusal. The file lands in a checkout other sessions share.
- Judged: the read-only roles, from `READ_ONLY` in `hooks/agent_brief.py`, plugin prefix stripped, as `brief_destructive_hit` reads them. A writing role, the default role and a spawn with no role pass. A missing `READ_ONLY` makes the set empty, so the rule passes everything; the shell guard still judges the write at run time.
- What is read, in two passes of pure text work:
  - command-shaped parts (`_brief_commands`, shared with `brief-destructive-git`): a `tee` with an operand, or a redirect into a path, with quoted text cut out first. A target of `/dev/null`, or under any session scratchpad, is no repo write and passes.
  - prose lines outside a fence: an imperative write verb (write, save, store, dump, append, create, make) with only lead-in words in its clause before it, then a path (an extension or a slash) after to, into, in, as, at, named or called; "create a file"; "use the Write tool". Other verb forms (saves, wrote) are no order.
- Passes: a negator in the verb's clause (`_brief_prohibits`), a `Must deny:` or `Add a case:` line, a negating heading's cover, prose with no file as its object, and a word that holds a command name inside it ("committee").
- The refusal names the remedy: a writer role (record-writer, builder or test-author), or have the agent report the text in its reply.
- The override lifts it (`owner-override`).
- Accepted limits: a path with no extension and no slash ("write it to notes") is no order here. An order in a form this scan has no verb for passes. A clause with a lead-in word outside the list ("Check that the code should write to a.json") is read as no order. Claude is unlikely to write the passing forms by mistake (`guard-guards-mistakes-only`).
- Cost: pure text work inside the guard call already running. No process start, no file written.

Protected by the `brief-write-needs-writer:` cases in `tests/guard/s28508-rule9.py` (53 cases), red before the rule landed.

Kind: process
Home: hooks/guard.py
