# A cannot-claim for an act outside the table needs one probe

## Ruling

A reply that says this session cannot do an act outside the table must run one probe in its turn, or say `unchecked`. Owner grant, 2026-11-15 13:30 CST, for the check below.

Rule `output-never-hand-off-doable-step` (a step the session can do is not handed to the owner) needs a check before any hand-off. The cannot-claim check, part (vi) of decision `claims-carry-backing` (a definitive prose claim carries its backing), reads only table acts: pr-open, pr-merge, push, pr-edit and github-reach. It does not see a claim that this session cannot do an act outside that table. This record covers that case. Its id is `cant-claim-needs-probe`.

The waiting-page sibling is decision `task-names-its-check` (a waiting-page task names the check that shows only the owner can do it).

The check is a predicate beside `cannot_problem` in `lint/report_guard.py`. It blocks once when a reply sentence:

- holds a CANNOT_FORMS phrase (the list in `lint/_clause.py`),
- has the writer as its subject (`own_subject`, `lint/_clause.py`),
- names an act outside the table, so `cannot_problem` skips it, and
- sits in a turn with zero tool calls.

The turn is the records after the last message. A peer's ack is read as the cannot-claim call site reads it (`last_incoming_index`, `lint/report_guard.py`).

Status: not built. Lane `cant-claim-needs-probe` builds the predicate and its cases in `lint/test_report_guard_cannot.py`. CI already runs that file.

## Incident

- The mistake. On 2026-11-15 the mailaudit cloud coordinator told the owner, "I cannot import it myself." It ran no probe. Its environment listed the service host as proxy-authenticated. One GET then showed that read and write both worked.
- The mistake class. A claim that a session cannot do an act outside the table, with no try of that act in the turn.
- The harm. The owner was told to do an act the session could do. The host was reachable.

## Forms added

"have no access", "no access to" and bare "unable" join `CANNOT_FORMS` (`lint/_clause.py`). `cannot_problem` reads that list, so the old check needs a case for each form.

The hand-off guard does not read `CANNOT_FORMS`. Its `CAPABILITY_RE` reads `CANT_FORMS`, `COULD_NOT_FORMS` and its own word list (`_CAPABILITY_CORE`, `lint/report_guard.py`). A new form reaches the hand-off guard only through those lists.

## What passes

- The whole word `unchecked` in the sentence.
- A `(route <id>)` cite (a route row, the glossary term) or a dated `(measured <date>, <check and result>)` cite.
- Text in quotes or code spans. `_mask` reads it as blank.
- A subject that is not the writer: it, the guard, the lane, a builder, the session, a draft PR. "this session" is the writer.
- A question. A sentence that ends in `?`.
- A line quoted with `>`, such as an agent's report. This skip is new for this predicate. Today's line reader, `_prose_lines`, strips the `>` and reads the body. So the old check counts such lines, as part (vi) says under "What it cannot see". If the skip lands in the shared reader, that note goes stale and needs a rewrite.
- A pasted guard refusal, when quoted or in a code span. The builder tests an unquoted paste. If none of the skips holds, it adds one.
- Reused skips, as the old check has them:
  - A conditional or a negator before the phrase (`_clause.conditional`, `_clause.negated_near`).
  - `until` and `before`.
  - The doubt, promise and wait words after the phrase (`CANNOT_SKIP_NEXT_RE`).
  - The `Unvetted:` label.
  - A Why yours line that the hand-off guard judges.
  - A sentence with the words rule, ruling, decision or grant (lane ruling, 2026-11-07 23:22 CST).

## Refuse once

One refusal per Stop. It lists each sentence the predicate holds and joins any other reason. A table-act sentence in a turn with no tool call is `cannot_problem`'s. The predicate skips it, so the two reasons join into one refusal.

The remedy names no act. Rule `git-remedy-never-names-target` (a refusal's remedy never names the forbidden target) applies: "run one probe, or say `unchecked`."

With `stop_hook_active` set (the flag a Stop rewrite carries), the check stays quiet, as the report checks do. It runs on every Stop, landed or not.

If the transcript reader does not load, the check prints UNKNOWN to stderr and does not block. `cannot_problem` does the same.

## Cost

A regex over the reply, and one pass over the turn's records already in hand. It starts no process, writes no file, and starts no timer or log. It reads the turn only for a reply sentence that holds a cannot-phrase.

Rule `outcomes-mechanize-rules` (each check states its cost and a test proves it) applies. The lane's test will prove zero process starts and zero file writes. That test is not built yet, so the cost is stated, not proven.

## What it cannot see

- A turn with any tool call passes, even one unrelated file read. The gate counts calls, not probes.
- A probe in an earlier turn does not count. The gate reads this turn only.
- A claim whose subject is another party: "the builder cannot import it."
- A claim outside the phrase list, such as "only the owner can" or "it is impossible."
- A hand-off with no cannot-phrase, such as "import it yourself" or "you need to import it." Nothing blocks these. The Stop reply judge (`hooks/reply_judge.py`, a model that never blocks) judges reports with an Input Needed label for their checks.

## Measure

Decision `claims-carry-backing`, part (vi), has a ruling from 2026-11-07 23:50 CST: "only a table act is a claim." Its measure, 12 of 12 phrase hits false on 400 main commit messages, covers commit messages only. Commit messages have no turns, and that check had no zero-tool-call gate. So the measure does not cover this check.

The false-alarm rate on real replies is unmeasured. The predicate is not built, so it cannot run on any reply. The transcripts in `~/.claude/projects` come from one session tree: three files, the session and two of its subagents. No labelled set of real replies exists. A rate needs one.

Decision `guard-that-cries-wolf-is-spent` (a guard that goes red when nothing is wrong is spent) sets the bar: a check that fires on right replies teaches the reader to scroll past it. Rule `verification-trust-guard-after-red` (trust a guard once it goes red on the defect it guards) sets the test: the lane's first red case is the incident reply, a turn with no tool call that says "I cannot import it myself."

Kind: process
Home: rule:output-never-hand-off-doable-step
