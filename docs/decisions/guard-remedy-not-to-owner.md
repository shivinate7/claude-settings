# A Stop refusal's steps live in this record, not in chat

## The ruling

Question: where does a Stop refusal's remedy live when the owner sees the refusal in chat? Ruling: coordinator, 2026-11-07 12:26 CST, option 1a, answering owner ask `ask-mw6pwif5wv` (a past-ruling refusal that reached the owner).

- Each refusal from `lint/report_guard.py` (the Stop hook that checks each reply) opens with one owner line, except a notes fix (R14; not built; step `notes-fix-no-owner-line`): one plain sentence that names the check and cites this record, `guard-remedy-not-to-owner`.
- The steps live under that check's heading in `## Steps per check`.
- No verdict changes. Only the text moves.
- Scope: Stop refusals only. `hooks/question_form.py` keeps its own text, `DEPARTS_REASON` included. So does `hooks/call_judge.py`, a PreToolUse hook: a check that could not run prints `UNVETTED_REMEDY` with the `Unvetted:` marker, and a ruling found prints the facts-only text (coordinator pick, 2026-11-12 09:19 CST). `call_judge.py` leaves the Stop text as is. A Stop refusal shows only the miss that `departs_hit` names.
- R14, the owner's ruling on notes fixes (2026-11-10 16:22 CST, "fixed my notes question: yes"): a Stop refusal about a session's own notes (feedback log, handoff) is fixed with no line to the owner, since the reply did not change. guard.log still records it. Not built yet. Step `notes-fix-no-owner-line` builds it. Its builder first confirms that a Stop can end with no text.

## Incident, risk and cost

Incident: owner ask `ask-mw6pwif5wv`, 2026-11-07 12:09 CST. A past-ruling model call timed out. The Unvetted refusal reached the owner in chat, though its steps were for the session. Risk kind: named incident.

Build: done in `lint/report_guard.py`. `owner_line()` is the one home of the owner line and the cite. The suite `lint/test_report_guard_remedy.py` checks each block path it has a fixture for. Its docstring lists the rest. Each refusal text holds facts only: which check, what is wrong, which Done line, which model.

Cost: none at run time. No process starts, no file is written and no timer runs. Unmeasured: how often a session reads this record before it acts on a refusal.

## Steps per check

Each heading names the check, then its text. Landed turns: the check runs only on a turn that landed a commit, push or merge. Any reply: the check runs on every Stop. Each refusal also carries the shared tails below, with the exceptions they name. Find the heading that matches the owner line.

### Report-shape guard: no report (landed turns)

Text: `BLOCK_REASON`.

- Send the report now, as the next thing you write.
- The report is one blockquote. Its bold labels are Done, Deviations, Input Needed and Next, in that order. Drop a label that does not apply.
- No code fence. Nothing after the report.
- Prose may sit above the report. Keep the reply above it as it stands. Do not write it again.
- No correction tail here, because the report is missing.

### Report-shape guard: Done kind (landed turns)

Text: inline, in the landed-turn checks.

- Give each Done line its kind: BUILT, RECORDED or OTHER. The refusal quotes the line.
- A BUILT or RECORDED line also names a PR or commit.

### Model-name guard (landed turns)

Text: `MODELS_REASON`, with two detail forms in its brackets.

- A Done item that agents built or reviewed names each one's role and model, like "(builder sonnet, reviewer sonnet)".
- For "no model named for <role>": name that role's model in the Done item.
- For "'<role> <model>' matches no <role> spawn, which ran <models>": name a model that the spawn ran on.

### Unstarted guard (landed turns)

Text: `UNSTARTED_REASON`. It applies when the turn ran a builder.

- Next holds an "Unstarted:" line. Name each queued item with every question answered that you left unstarted, with its reason.
- If none, write "Unstarted: none".

### Answered guard (any reply)

Text: `ANSWERED_REASON`, rule `answered-needs-source` (a claim of "answered" needs its source).

- On each listed line, add where the answer came from: a link, `#<n>`, a commit, a file path, `item <n>`, a session or inbox id, or the time. Put it on the same line.
- Or say what is meant, in other words.
- A mention of the word, not a claim, can go in an inline code span.
- Lines inside a code fence, and lines that end in a question mark, are not checked.

### Recovered guard (any reply whose report shape holds)

Text: two inline facts in `recovered_problem`. The two line forms below live here only.

- If a compaction came before this report, and the report has no carry line since, add the missing line under Deviations, inside the report's blockquote:
  - `Recovered: <each fact, with its source: git, page or digest>`, or `Recovered: none`.
  - `Handoff gave: <facts the handoff supplied that the summary did not>`, or `Handoff gave: none`.
- If a Recovered item names no source, end it with git, page or digest. Items split on ";" outside parentheses. An item that starts with "none" or "nothing" needs no source.

### Departs-from guard (any reply with a pick)

Text: the miss from `departs_hit` in `hooks/question_form.py`, in the owner line. `DEPARTS_REASON` is not shown here; it stays for the waiting page and the question box. Rule `question-departs` (a pick says how it departs from main).

- Write one line: "Departs from: <what on main> — <what changes>". Fill both sides. The change must differ from main.
- If the change is new, write "Departs from: main — adds <X>".
- If the change only restates what main does, do not ask. Act on main's behaviour.
- The refusal names the miss. It may be: no Departs from line; no separator (an em dash, " - " or " -- ") between the two sides; an empty side; a placeholder side; or a change side that says no change. It names the word that says so.

### Mistake guard (landed turns with a valid report)

Text: `MISTAKE_REASON`. Rule `building-mistake-names-its-guard` (a mistake names the guard that would have stopped it).

- A mistake is a strong sign that a guard or check is missing. Name that guard in Deviations, in one of three ways:
  - `step:<slug>`, a roadmap step that will build it;
  - the word "debt" in Deviations;
  - a guard, check or hook, with a PR or commit reference, in the same sentence.
- The refusal quotes the clause that admits the mistake.

### Pick guard: owner route (any reply with a question)

Text: `OWNER_REFUSAL`. Owner ruling, 2026-11-01 23:31 CST.

- Send the question to the page writer in the same turn it is asked.
- The route: `send_message` to the page writer by its session id. The refusal names the writer's id when it is known. If the writer is unknown, the refusal names the waiting page: read it with `ArtifactData` get, then `send_message` the question to its writer.
- In a repo with no waiting page, this check does not refuse. The question box counts instead.

### Lane pick guard (lane sessions)

Text: `LANE_REFUSAL`.

- A lane's own chat does not reach the owner. Send the question to your parent now: `send_message` with session_id `@parent`. A lane's page writer also counts.

### Rewrite-stamp guard (landed turns)

Text: inline, in `rewrite_stamp_problem`, from `owner_line()`. Rule `rewrite-cite-predates-ruling` (a rewrite claimed for a ruling must be committed after that ruling).

- The refusal names the decision, its last commit date, and the ruling it is said to be rewritten for.
- Rewrite the record, fetch the branch that holds the rewrite, or say it is not rewritten yet.

### Hand-off guard (any reply with a "Why yours" line)

Text: `HAND_OFF_NO_CITE`, `HAND_OFF_NO_DATE`, two inline forms, and `HAND_OFF_TAIL`. Rule `output-never-hand-off-doable-step` (a step the session can do is not handed to the owner).

- A "Why yours" line gives a capability reason with no cite. End the line with one of:
  - `(route <id>)`, where the id is in the route rows file and its outcome on this surface is refused or asks;
  - a tool that the auto-mode classifier refused this session, named in backticks;
  - `(measured <YYYY-MM-DD>, <check and result>)`.
  A check name is no cite. If no row, refusal or measurement fits, the act may be one this session can do. Do it.
- A measurement with no date, or no check and result: write `(measured <YYYY-MM-DD>, <check and result>)`.
- The route row says the act works on this surface, so it is not the owner's. The refusal names the row and the route. Do the act through that route.
- The route id is in no row of the route rows file (the refusal names the id): cite an id the file holds, or name a tool refused this session in backticks.

### Refusal guard (any reply)

Text: `refusal_reason`. Decision `refusals-reach-the-owner` (a refused tool reaches the owner).

- Add an Input Needed line "allow `<tool_name>`?" for each tool. Put the tool's name in place of `<tool_name>`.
- Add a line in the repo's debt notes file (`notes.md`) that names the tool.
- Or, if the refusal was right, write "`<tool_name>`: refusal was right" on one line, with the tool's full name in place of the placeholder.
- A built-in tool, such as Edit or Bash, goes in backticks. An MCP tool goes by its full name.

### Past-ruling guard (any reply with a question)

Text: `RELAY_RULE_REASON`. Rule `past-ruling` (a question that a past ruling already settles).

- Drop the question if the ruling settles it.
- Or add a `Based on (ruling): <id>` line that names that ruling and says why the owner is asked again. Use the id that the refusal names. The refusal gives the id, its date, and what it decides. When the judge's reason holds wording that tells the session what to do (`session_wording`), the refusal keeps the verdict and the id and drops that text.

### Unvetted guard (any reply with a question)

Text: `UNVETTED_REASON`. Rule `past-ruling`, when the check cannot run.

- Add the line `Unvetted: <why it could not be checked>` to the question, in the reply, and send it again.
- The refusal gives the why. It may name unreadable sources, a model error or timeout, a cited record that was not in the list, or an error in the check.
- The check runs first every time. The Unvetted line decides only when the check cannot run.

### Question-keys guard (two questions in one reply, or since the owner's last message)

Text: `KEYS_REASON`. Rule `question-keys` (two questions cannot share an option key).

- Give each question its own keys. For example, 1a and 1b for the first question, 2a and 2b for the second.
- Send the questions again.
- The same key, the same option text and the same question, reworded or not, is one question sent again. It is not a clash.

### Triage hold (triage sessions, any reply)

Text: `HOLD_REASON`. Decision `session-tiers` (the duties of the triage session, the standing session that writes the roadmap).

- Dispose of each stalled step that the refusal names: resume it, pause it, or mark it done.
- Rebuild the roadmap. Then end.
- Or name the steps under Input Needed to escalate them to the owner.
- A Stop after this refusal is released once Input Needed names every stalled step. An owner override also lifts it.

### Cite-gloss guard (landed turns)

Text: inline, in the main check.

- A record id appears with no short gloss after it. Write the id, then a few plain words that say what it is, like "D12, short titles for records".

## Shared tails

- Every refusal, except a notes fix (R14; not built; step `notes-fix-no-owner-line`), opens with the owner line from `owner_line()`, which cites this record, and ends with ` (rule reports-order-of-labels)`. That rule says the report's four labels go in order: Done, Deviations, Input Needed, Next. On the rewrite after a refusal, a triage hold alone has no tail.
- Correction rule, no text in any refusal: after any refusal but a missing report, post only the corrected lines, as a short correction, and post none for a fix to a session's own notes (not built; step `notes-fix-no-owner-line`; see the ruling). Never send the report again. The owner has read the report before a refusal lands, so a resent report doubles it. A missing report asks for the report itself, and its reply carries every other fix too.
- The system message notes (`NO_PAGE_NOTE`, the hand-off guard's UNKNOWN lines and the route flags) and the stderr lines are not refusals. They never stop a reply, and they fall outside this record.

Kind: process
Home: lint/report_guard.py
