# A read-only agent's brief never orders a file write

## The ruling

Rule `brief-write-needs-writer` in `hooks/guard.py` refuses an Agent, Task or Workflow spawn to a read-only role whose brief orders a file write. Its home is `brief_write_hit`, called at step 9e3, after the brief-destructive check at step 9e2. Layer: owner fan-out grant, 2026-11-11 13:51 CST (restart plan R42), step `brief-write-needs-writer`.

- The mistake: an Explore agent was briefed to write a file. It has no write tool, so it wrote one by a shell redirect (retrospective, 2026-11-11 20:41 CST).
- The harm: the agent writes outside its role's tools by a route no tool guard judged, or stalls on a refusal. The file lands in a checkout other sessions share.
- Judged: the read-only roles, from `READ_ONLY` in `hooks/agent_brief.py`, plugin prefix stripped, as `brief_destructive_hit` reads them. A writing role, the default role and a spawn with no role pass. A missing `READ_ONLY` makes the set empty, so the rule passes everything.
- Design: the rule reads every spawn, so a false alarm costs more than a missed odd phrasing (rule `verification-cry-wolf-guard-is-spent`). Each reading asks for a precise shape: a command-form verb, and a destination that is path-shaped or "a file".
- Path-shaped: a word that ends in a known file extension (`BRIEF_WRITE_EXTENSIONS`), starts with `~/` or `./`, or holds a slash that is no word pair (`PASS/FAIL`, `and/or`). A dotted name such as `total.length` is no file, so `count > total.length` passes. A file with an extension the list lacks and no slash (`audit.bak`) passes. After `>` or `tee`, a word of the form `self.name`, `this.name` or `cls.name` is an attribute, not a file, so `size > self.log` passes, but `> out.log` and `> docs/a.log` stay files.
- What is read, in two passes of pure text work:
  - command-shaped parts (`_brief_commands`, shared with `brief-destructive-git`): a `tee` or a redirect whose target is path-shaped. A redirect in prose outside a span or quote ("run cat v > audit.md") is read the same way: its target needs a letter, a `>` at the line start is a quote mark, and a `<` ends the target, so `<Button>Save</Button>` names no file. In prose, a quote mark between two word characters is text (`Don't`, `it's`), so two apostrophes do not hide a redirect between them. A prose target of a name, a slash and a number (`if latency > budget/2`) is a division, not a path. A comparison (`count > 0`, `age > max_age`) names no path, so it passes. A quoted `>` is text, but a quoted target (`> 'a.md'`) is read. A target of `/dev/null` or under any session scratchpad passes.
  - prose lines outside a fence, emphasis and quote marks removed, one clause at a time. A clause ends at a sentence mark, a comma, "and", "then" or "but".
    - A write verb counts only when its clause holds nothing before it but lead-in words (please, then, so, when done, you must) or a wrapper (remember to, be sure to, make sure to, your job is to, the agent should).
    - The first destination word after the verb decides. It must lead to a path-shaped word, or to a determiner and "file" ("to a markdown file"). Any other first destination is no order: "Make a plan to add a rule to hooks/guard.py", "as short as README.md".
    - Compose verbs (write, create, make) send output only by to, into, onto, as, named, called or at. Their first "in", "inside" or "under" names a topic: "Write a report describing each gap in docs/x.md" is no order. Place verbs (put, place, save, store, dump, append, redirect, add, record, log, output, draft, generate) also take in, inside, at and under. A compose verb's "at" is a destination only when at most three words sit between the verb and it. None of those words may be "of", "about", "for", "on", "with", "from", "by", "that", "which" or an -ing word. Examples: "Write a report at docs/review.md" is an order, "Write a summary of the check at hooks/guard.py" is not.
    - A compose or place verb, a short object that names the agent's own output (report, findings, review, audit, summary, verdict, notes, result, analysis, answer, output, plan), a colon and a path: "Write the report: docs/review.md".
    - "Create", "write" or "update" with a path, "with", and "your" or "finding(s)" after it: "Create docs/review.md with your report".
    - A task names a code change with add, update, record and log, and a Plan or refuter brief carries the task word for word. So these four count only when the object is the agent's own output: "your" or "finding(s)" before the destination ("Add your findings to a.md"), or after "with" in "update a.md with the findings".
    - "make sure" and "ensure" are wrappers, not verbs. Inside one, a passive ("is saved to a.md") orders a write; "Make sure that the rule in docs/x.md matches the code" does not.
    - Also: "create a file"; a `tee <path>` in prose outside a backtick span; "use", "call" or "invoke" the Write tool. A test or other name after it ("the write tool test") is no call. The nouns output, docs and results are no call either, unless a save verb and a path follow in the same clause: "Use the Write tool results to save docs/x.md" is an order.
    - A verb inside a backtick span is a quoted phrase, so the "at", colon and "with" forms above skip it.
    - Reading cost: a verb reads at most 400 characters before it and 800 after it (`BRIEF_WRITE_WINDOW`, `BRIEF_WRITE_REACH` in `hooks/guard.py`). Count checks (`long_line_growth_check`, `long_line_bound_check` in `tests/guard/s28508-rule9.py`) bound what the reader slices from a 36 KB one-line brief: the count grows no more than 2.5 times when the line doubles, and stays within four 400-character windows per write verb.
- Passes: a negator in the verb's clause before it (`_brief_prohibits`) or between it and the destination ("Write nothing to a.md"). A negator, a comma, an aside from a closed list and a second comma keep the negator's window when the order comes next. The order is a run verb (run, use, call, execute, type) or the write verb itself: "Do not, under any circumstances, write to docs/audit.md". Any other word after the aside starts an order: "Do not, at any time, skip it: run `git reset --hard`" and "Never, ever, forget to run `git reset --hard`" are orders. The list is in `BRIEF_DESTRUCTIVE_ASIDES` (under any circumstances, in any case, in any event, at any time, for any reason, at all, ever), and `brief-destructive-git` shares it. Any other aside is an order: "No, really, run `git reset --hard`". Before the Write tool, "may not", "may never", "will not", "will never" and the short form of "will not" are negators; a bare "may" or "will" is not. Also a `Must deny:` or `Add a case:` line, a negating heading's cover, "write-up", and a word that holds a command name inside it ("committee").
  - A negating heading's cover needs a run verb within two words after the negator, so "Do not:" alone does not cover its list.
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
  - a destination more than 800 characters after its verb with no sentence mark, comma, "and", "then" or "but" between them. The reach (`BRIEF_WRITE_REACH`) bounds the read cost.
  - a file extension that `BRIEF_WRITE_EXTENSIONS` lacks and a path with no slash: "to audit.bak". The list holds the common code, text, data, image and archive types, plus notes, markdown, text, out and ipynb. It lacks bak, rtf, jsonc, mdc, vue, tf, lua and sqlite, so "Save the report to review.bak" passes.
  - a passive inside "make sure" or "ensure" more than 200 characters after the wrapper: "Make sure <300 chars> the report is saved to docs/a.md". The cap in `BRIEF_WRITE_ENSURE` bounds the read cost.
  - a prose redirect to a name, a slash and a number: "run cat v > logs/2026" reads as a division.
  - a compose verb with "at" and a later word: "Write the full review report at docs/review.md" has four words before "at", so "at" reads as a topic. So does any object with an -ing word, "of", "about", "for", "on", "with", "from", "by", "that" or "which" before it.
  - a redirect in prose with no space before the `>`: "run cat v>audit.md". The redirect pattern wants a non-word character before it.
  - a quoted target in prose: `run cat v > "audit.md"`. A quote in prose is text, so its target is not read. A quoted target inside a backtick span is read.
  - a verb or lead-in outside the lists, and an order in another language.
  - a lead-in "do not forget to": "Do not forget to write the findings to docs/audit.md".
- Limits. These are false alarms:
  - a colon form whose object names the output but whose path is the subject of the next words: "Write the findings: hooks/guard.py line 3400 reads it wrong." is denied.
  - a negator with an aside that the reader does not take: a curly apostrophe ("Don’t, under any circumstances, write to docs/a.md"), a second aside ("must never, ever, under any circumstances, write"), and "Under no circumstances, run" are denied.
  - an unfenced tag whose body is a path: `<a href="x">docs/a.md</a>` is denied.
  - a Plan, refuter or reviewer brief that quotes a builder's task with a place or compose verb into a path ("Put the new helper in hooks/lib.py", "Write the new rule to hooks/guard.py", "Generate the map in docs/map/index.md") is denied. The override lifts it, or the brief words the task as a goal ("The helper belongs in hooks/lib.py").
- Cost: pure text work inside the guard call already running. No process start, no file written.

Protected by the `brief-write-needs-writer:` cases in `tests/guard/s28508-rule9.py` (selector `MUTATE_ONLY=brief-write-needs-writer`), red before the rule landed.

Kind: process
Home: hooks/guard.py
