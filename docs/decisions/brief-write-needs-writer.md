# A read-only agent's brief never orders a file write

## The ruling

Rule `brief-write-needs-writer` in `hooks/guard.py` refuses an Agent, Task or Workflow spawn to a read-only role whose brief orders a file write. Its home is `brief_write_hit`, called at step 9e3, after the brief-destructive check at step 9e2. Layer: owner fan-out grant, 2026-11-11 13:51 CST (restart plan R42), step `brief-write-needs-writer`.

- The mistake: an Explore agent was briefed to write a file. It has no write tool, so it wrote one by a shell redirect (retrospective, 2026-11-11 20:41 CST).
- The harm: the agent writes outside its role's tools by a route no tool guard judged, or stalls on a refusal. The file lands in a checkout other sessions share.
- Judged: the read-only roles, from `READ_ONLY` in `hooks/agent_brief.py`, plugin prefix stripped, as `brief_destructive_hit` reads them. A writing role, the default role and a spawn with no role pass. A missing `READ_ONLY` makes the set empty, so the rule passes everything.
- Design: the rule reads every spawn, so a false alarm costs more than a missed odd phrasing (rule `verification-cry-wolf-guard-is-spent`). Each reading asks for a precise shape: a command-form verb, and a destination that is path-shaped or "a file".
- Path-shaped: a word that ends in an extension, starts with `~/` or `./`, or holds a slash that is no word pair (`PASS/FAIL`, `and/or`).
- What is read, in two passes of pure text work:
  - command-shaped parts (`_brief_commands`, shared with `brief-destructive-git`): a `tee` or a redirect whose target is path-shaped. A comparison (`count > 0`, `age > max_age`) names no path, so it passes. A quoted `>` is text, but a quoted target (`> 'a.md'`) is read. A target of `/dev/null` or under any session scratchpad passes.
  - prose lines outside a fence, emphasis and quote marks removed, one clause at a time. A clause ends at a sentence mark, a comma, "and", "then" or "but".
    - A write verb counts only when its clause holds nothing before it but lead-in words (please, then, so, when done, you must) or a wrapper (remember to, be sure to, make sure to, your job is to, the agent should).
    - The first destination word after the verb decides. It must lead to a path-shaped word, or to a determiner and "file" ("to a markdown file"). Any other first destination is no order: "Make a plan to add a rule to hooks/guard.py", "as short as README.md".
    - Compose verbs (write, create, make) send output only by to, into, onto, as, named or called. Their first "in" names a topic: "Write a report describing each gap in docs/x.md" is no order. Place verbs (put, place, save, store, dump, append, redirect, add, record, log, output, draft, generate) also take in, inside, at and under.
    - A task names a code change with add, update, record and log, and a Plan or refuter brief carries the task word for word. So these four count only when the object is the agent's own output: "your" or "finding(s)" before the destination ("Add your findings to a.md"), or after "with" in "update a.md with the findings".
    - "make sure" and "ensure" are wrappers, not verbs. Inside one, a passive ("is saved to a.md") orders a write; "Make sure the rule in docs/x.md matches the code" does not.
    - Also: "create a file"; a `tee <path>` in prose outside a backtick span; "use", "call" or "invoke" the Write tool.
- Passes: a negator in the verb's clause before it (`_brief_prohibits`) or between it and the destination ("Write nothing to a.md"). Also a `Must deny:` or `Add a case:` line, a negating heading's cover, "write-up", and a word that holds a command name inside it ("committee").
- The refusal names the remedy: a writer role (record-writer, builder or test-author), or have the agent report the text in its reply.
- The override lifts it (`owner-override`).
- Limits. These orders pass, and Claude could write each in normal work:
  - an order broken across lines ("Write the findings" then "to docs/audit.md" on the next line).
  - a noun between the article and the path: "the audit doc docs/audit.md".
  - a destination that is not path-shaped: "to notes", "to disk", and `> out` in a backtick span, a fence or a `$ ` line.
  - a compose verb with "in": "Write the findings in docs/audit.md".
  - a non-path destination word before the path: "Save the findings as a table in docs/audit.md".
  - an object joined by "and" or a comma: "Write the findings and the verdict to audit.md".
  - add, update, record or log with an object that is neither "your" nor a finding: "Add a summary to audit.md".
  - a verb or lead-in outside the lists, and an order in another language.
  - a lead-in "do not forget to": "Do not forget to write the findings to docs/audit.md".
- Limits. These are false alarms: a Plan, refuter or reviewer brief that quotes a builder's task with a place or compose verb into a path ("Put the new helper in hooks/lib.py", "Write the new rule to hooks/guard.py", "Generate the map in docs/map/index.md") is denied. The override lifts it, or the brief words the task as a goal ("The helper belongs in hooks/lib.py").
- Cost: pure text work inside the guard call already running. No process start, no file written.

Protected by the `brief-write-needs-writer:` cases in `tests/guard/s28508-rule9.py` (selector `MUTATE_ONLY=brief-write-needs-writer`), red before the rule landed.

Kind: process
Home: hooks/guard.py
