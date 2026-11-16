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

The turn is the records after the last message. A peer's ack of a send of the turn starts no turn. Each peer acks a send to its own session id. Only the parent, by the id in the lane record, also acks a send to `@parent` (`_turn_acks`, `lint/report_guard.py`).

Status: built in `cannot_problem` (`lint/report_guard.py`). Its cases are in `lint/test_report_guard_cannot.py`, which CI runs.

## Incident

- The mistake. On 2026-11-15 the mailaudit cloud coordinator told the owner, "I cannot import it myself." It ran no probe. Its environment listed the service host as proxy-authenticated. One GET then showed that read and write both worked.
- The mistake class. A claim that a session cannot do an act outside the table, with no try of that act in the turn.
- The harm. The owner was told to do an act the session could do. The host was reachable.

## Forms added

"have no access", "no access to", "don't have access", "lack access", "no permission to" and bare "unable" join `CANNOT_FORMS` (`lint/_clause.py`). `cannot_problem` reads that list, so the old check needs a case for each form.

The hand-off guard does not read `CANNOT_FORMS`. Its `CAPABILITY_RE` reads `CANT_FORMS`, `COULD_NOT_FORMS`, the access and permission forms (`ACCESS_FORMS`, `lint/_clause.py`, which `CANNOT_FORMS` holds too) and its own word list (`_CAPABILITY_CORE`, `lint/report_guard.py`). A new form reaches the hand-off guard only through those lists. A Why yours line with an access form, such as "I lack access to the mailbox, so the import is yours.", needs a cite as any capability line does.

## What passes

- The whole word `unchecked` inside the sentence of the claim. A parenthetical after the full stop is the next sentence, so it does not count.
- A `(route <id>)` cite (a route row, the glossary term) or a dated `(measured <date>, <check and result>)` cite.
- Text in quotes or code spans. `_mask` reads it as blank.
- A subject that is not the writer: it, the guard, the lane, a builder, the session, a draft PR. "this session" is the writer.
- A question. A sentence that ends in `?`.
- A past claim (could not, couldn't) that hands no step to the owner. A past claim with a hand-off ("so you'll need to run it", or "You'll need to run it yourself." as the next sentence on the same line) is read.
- A judgement, not an access claim: a claim whose object is a fact, a choice or a size, not a system or an act on one (`judged_object`, `lint/_clause.py`).
  - A fact: a clause that why, how, whether or if opens ("can't see why the test fails", "can't predict how long it will take"). What and where may name a thing ("can't see what is in the bucket"), so they open no fact.
  - A fact or a remark: a verb whose object is only ever one (`FACT_VERBS`: determine, confirm, predict, explain, decide, agree, comment ...). A pronoun object ("can't confirm that", "can't import that") carries no kind, so this one short list is the rule's only verb list. Verify, check, test, see and find act on a system and are not in it.
  - A choice: a between ("can't decide between A and B"), or a need the act waits on ("we can't ship this without the migration"). A need that is access ("without the token", "without the VPN"; `ACCESS_NOUNS`) keeps the claim.
  - A size: a measure of the work in the clause ("can't fix this in one line"). A time ("in time") is no size, so "can't reach it in time" keeps the claim.
  - A find of nothing ("can't see any issues").
  - The rule reads the object, not a longer verb list. So a new verb of judgement needs no edit when its object is a why-clause, a between, a need or a size.
- A sentence that names its check: an exit code, a status form, or a backtick span or tool name beside a result word.
  - A span or a tool name alone names the object of the act, not its result ("can't import `inbox.mbox`", "can't run `make build`"). It counts only beside a result word (returned, failed, exited ...) in its own clause, with at most three words between. A result word whose subject is the writer names no call ("I ran `make build`").
  - A status form has a status word before or after the number: "HTTP 500", "status 407", "returned 403", "500 error" (`STATUS_FORM_PATTERN`, `lint/_clause.py`). A bare count after a comma ("500 rows") is no status.
  - A bare word ("I tried and it failed") names none.
- A line quoted with `>`, such as an agent's report, in a quote with no report label, and a row of a labelled quote that another writer's label opens ("Agent report:"). This skip is new for this predicate. Today's line reader, `_prose_lines`, strips the `>` and reads the body. So the old check counts such lines, as part (vi) says under "What it cannot see". If the skip lands in the shared reader, that note goes stale and needs a rewrite.
- A pasted guard refusal, when quoted or in a code span. The builder tests an unquoted paste. If none of the skips holds, it adds one.
- Reused skips, as the old check has them:
  - A conditional or a negator before the phrase (`_clause.conditional`, `_clause.negated_near`).
  - `until` and `before`.
  - The doubt, promise and wait words after the phrase (`CANNOT_SKIP_NEXT_RE`).
  - The `Unvetted:` label.
  - A Why yours line that the hand-off guard judges.
  - A sentence with the words rule, ruling, decision or grant (lane ruling, 2026-11-07 23:22 CST).

## Refuse once

One refusal per Stop. It lists each sentence the predicate holds and joins any other reason. A sentence that holds a table claim is `cannot_problem`'s alone, and is listed once, under that reason.

The remedy names no act. Rule `git-remedy-never-names-target` (a refusal's remedy never names the forbidden target) applies: "run one probe, or say `unchecked`."

With `stop_hook_active` set (the flag a Stop rewrite carries), the check stays quiet, as the report checks do. It runs on every Stop, landed or not.

If the transcript reader does not load, the check prints UNKNOWN to stderr and does not block. `cannot_problem` does the same.

## Cost

Every Stop that holds a human message runs the ack scan (report_guard.py _turn_acks), whether or not the reply holds a cannot-phrase. That scan reads the whole transcript for peer messages and sends to a parent. It reads the transcript again for the session's own record only when it finds both (report_guard.py _own_lane_read). The caller then finds the last incoming message (_transcript.py last_incoming_index). The turn's tool calls are read only for a reply sentence that holds a cannot-phrase (report_guard.py cannot_problem). The check starts no process, writes no file, and starts no timer or log.

Rule `outcomes-mechanize-rules` (each check states its cost and a test proves it) applies. No test proves zero process starts and zero file writes, so the cost is stated, not proven.

## What it cannot see

- A turn with any tool call passes, even one unrelated file read. The check counts calls, not probes.
- A probe in an earlier turn does not count. The check reads this turn only.
- A claim whose subject is another party: "the builder cannot import it."
- A claim outside the phrase list, such as "only the owner can" or "it is impossible."
- A hand-off two sentences after a past claim, or on another line from it. It passes as a past claim with no hand-off.
- A hand-off with no cannot-phrase, such as "import it yourself" or "you need to import it." Nothing blocks these. The Stop reply judge (`hooks/reply_judge.py`, a model that never blocks) judges reports with an Input Needed label for their checks.

## Measure

Decision `claims-carry-backing`, part (vi), has a ruling from 2026-11-07 23:50 CST: "only a table act is a claim." Its measure, 12 of 12 phrase hits false on 400 main commit messages, covers commit messages only. Commit messages have no turns, and that check had no zero-tool-call condition. So the measure does not cover this check.

The false-alarm rate on real replies is unmeasured. The predicate has run on no real reply. The transcripts in `~/.claude/projects` come from one session tree: three files, the session and two of its agents. No labelled set of real replies exists. A rate needs one.

Decision `guard-that-cries-wolf-is-spent` (a guard that goes red when nothing is wrong is spent) sets the bar: a check that fires on right replies teaches the reader to scroll past it. Rule `verification-trust-guard-after-red` (trust a guard once it goes red on the defect it guards) sets the test: the lane's first red case is the incident reply, a turn with no tool call that says "I cannot import it myself."

Kind: process
Home: rule:output-never-hand-off-doable-step
