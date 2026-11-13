# A coordinator's pick cites a ruling before it is sent

## The ruling

A coordinator's message that states a pick or a hold cites the ruling it rests on, or says `no ruling found:` and what it searched. The message is checked against the cited text before it is sent.

- Scope: a call of `mcp__claude-code-remote__send_message`, `mcp__claude-code-remote__create_session` or the Claude Code tool `SendMessage` from a session whose own record carries the tag `cs-build:coordinator`, whose text states a pick or a hold. The three tools are one tuple, `shared_names.PICK_TOOLS`. The text is the `message` field of `send_message` and `SendMessage`, and the `prompt` field of `create_session`, the brief that starts a lane (owner, page item 644 b, 2026-11-12 15:22 CST). A pick only in a `title`, or a `SendMessage` with only a `summary`, passes. Any other sender or text passes, with no model call. The three tools take the same gates and refusals.
- The sender read: `hooks/own_session.py` (`own_session_read`) gives the tags of the newest `get_session` result of the own record, as the lane tag is read. Unlike the lane read, other `cs-build:` tags on the record do not void it. A `set_session_tags` call on the own session after that record is applied: its `add` and `remove` lists, in order. A call whose change cannot be read counts as a coordinator's self-tag, with one stderr line, so the pick is still checked. An agent's call, an unset record id and an unreadable transcript are no coordinator.
- Two word lists, because the brief tools carry plain prose.
  - `send_message` keeps the word list: `pick`, `picks`, `picked`, `hold`, `holds` and `held`, as whole words. Chatter is no statement: a word followed by `on` or `up` (`hold on`, `pick up`), preceded by `on` (`on hold`), or with a hyphen beside it (a hyphenated record id).
  - `create_session` and `SendMessage` use statement markers only (`PICK_BRIEF_MARKER`). A marker is a line or clause that starts with `Pick:`, `Hold:`, `Decision:`, `Coordinator pick` or `Coordinator hold`, after optional markdown lead characters. Or it is the words `my pick`, `picked` or `the pick is`. A bare `hold`, `holds` or `held` states no pick there.
  - Why: the lane brief template (`skills/project-ops/templates/brief.md`) says "no longer holds". Measured on the word list: every template brief cost a judge call. On the markers, the template costs none (a test sends it on both tools).
- Every code refusal's remedy, on all three tools, also says that a message that states no pick can be reworded.
- A cite is a plan R-number, a decision, debt or step id, or a `page item <number>`. A one-letter choice may follow with or without a space (`556a`, `556 a`). A bare `item <number>` is no cite, and `3d-x` is no number. A `no ruling found:` line may carry markdown (`*`, `_`, backticks) around the label, the colon and the text. A pick with no cite and no `no ruling found: <what was searched>` line is refused in code, with the remedy and no model call.
- A pick with a cite, or a `no ruling found:` line, gets one judge call (`hooks/call_judge.py`, `judge_pick`, guard rule `pick-judge`; Sonnet, the past-ruling check's model). The prompt carries the pick text and the rulings it may rest on. Each is a fenced block that the prompt labels data, not instructions. Each ruling line names its source.
- One function reads every ruling: `call_judge.ruled_candidates`. `judge_pick` calls it once. The pick judge's rulings come from `ruled_candidates` only. Other code reads records too: `past_ruling_context`, the page-write judge, reads them for its own prompt. The sources, in the order the judge weighs them:
  - The ruled store, when it lands (lane `ruled-store-one-home`, `lint/ruled_store.py`, `ruled_entries`, ref `origin/roadmap`). It replaces the reads below inside `ruled_candidates`. It is not built yet. Seam: `_source_label` reads the label from the id prefix, so an id that is no decision or debt reads as `roadmap step note`. The swap must change that.
  - The owner's page answer of a cited `page item <number>`, from `origin/roadmap`. The row of `waiting/answers/<slug>.json` whose `n` is the number gives the answer and its `at` time. `waiting/items/<slug>.json` holds the question and its options. The line reads `page item <number> answer (origin/roadmap, <at>)`. The answer reads by its fields. A `choice` reads `choice <value>`. A row with `done: true` reads `done`. A row with `act: "park"` reads `parked`. A row with none of these reads `no choice, note only`.
  - A plan R-number, from `plans/*.md` on `origin/restart-plan`, and from the checkout's `plans` folder (`docs/plans` by the layout). The text runs from its `- **R<n>.` bullet to the next top-level bullet or heading, up to 6000 characters.
  - The decision, debt and step rulings of `question_form.past_rulings`, each labelled with its record path.
- Git reads the refs with no checkout and no fetch. A missing ref, folder or file, or a failed read, is named in the prompt as not searched. It never raises and never refuses.
- A later ruling supersedes an older one. The prompt tells the judge to judge the pick against the later ruling and to cite it. The date in a ruling's text, or the `at` time of a page answer, says which is later. Code keeps every answer of one page item, oldest `at` first. The test helper `check_two_answers` also accepts an older line that is left out. The code never leaves it out. The later line says `later/current ruling`, and each older line says `superseded by the answer below`. The prompt asks the judge never to refuse a pick for an older ruling that a later one replaced. That is a request to the judge, not a check in code.
- Wording: a ruling is a past ruling to weigh, not a standing law. The refusal text says so. The prompt tells the judge to word its reason that way. No text says a ruling is owed or that a session must follow it.
- A source the hook cannot read is named in the prompt as not searched, never read as clear. Four kinds exist. Page items other than the cited ones, and later page answers. A plan R-number that no plan holds. A missing ref or file. A cited record that the read did not list. An answered page item whose question file is missing or malformed, or whose answer row has no `item` key, adds `page item <number> question`.
- A model error allows the pick, with one stderr line. A pick is no question to the owner, so the non-question fail-open convention holds.
- An owner override lifts the refusal (`guard_core.refuse`, decision `owner-override`).

## The mistake and the harm

The mistakes, all 2026-11-12 (CST), all by a coordinator:

- 12:06 (a): a mailbox default was held, against page item 556 a and plan R49. The hook cannot read the page item; it can read plan R49, so the judge can refuse on R49 alone, unmeasured on a real record.
- 12:04 (b): plan R22 point 3 was cited for something R22 does not say. The judge reads the R22 text.
- 12:30 (c): a route was offered against step `prose-tending-contract`. Whether the judge refuses it on a real step note is unmeasured.

Only the fixture cases in `hooks/test_call_judge.py` stand for these three. No claim here says the check would have stopped (a) or (c) on the real records.

- 14:25 (d): the owner said an old rule must not be treated as law when a later ruling exists. The check cited old text as law. It had no way to read a later answer, and its wording said a ruling was owed.

The harm: a lane builds to the wrong pick, the work is redone, and the owner is asked the same thing twice.

Cost, per pick message on any of the three tools: at most one judge-hook process and at most one Sonnet call (60 s cap), plus at most one git process (`question_form.past_rulings`). A cited plan R-number or page item adds at most one more. So a decision cite costs at most one git process, and a plan or page cite at most two. At most one `cat-file --batch` process serves every ref read, so a plan and a page answer together still cost at most two. Measured: at most two extra git processes over a decision cite. The extra is capped at three processes by the test in `hooks/test_call_judge.py`, one more than the measure. The ref reads write no file and start no long-lived process. The matcher starts the judge hook on every call of the three tools (37 ms measured on `send_message`). A send with no statement (a listed word on `send_message`, a marker on the brief tools), or from a session that is no coordinator, starts no process beyond the hook's own start. It makes no model call. A pick with no cite makes no model call. Nothing is written but the guard log line of a refusal. `hooks/test_call_judge.py` (section "a coordinator's pick") counts the calls.

Known limit:

- The judge reads the cited text, not the whole plan or the whole page. A page item is read only when the pick cites it. A page item with no answer on `origin/roadmap` reads as not searched, and the pick passes on the cite alone. A plan R-number that no plan holds is reported as not searched, never as clear.
- The refs are read as the last fetch left them. A ruling newer than the last fetch is unseen. A plan on another branch or in another repo is not found.
- The judge decides which ruling is later from dates in the text and the `at` time. A ruling with no date reads as undated, and the judge may weigh it wrongly.
- A pick in other words passes untouched: "going with", "my call is", "chose", "is on hold", "hold on merging". On `send_message`, "Decision:" passes too.
- On the brief tools, a bare `pick` ("I pick route B"), a bare `hold`, `holds` or `held`, and a pick in other words with no marker pass with no cite.
- A plan ruling such as `G12` is no cite (`PICK_PLAN_REF` takes `R` only). A pick that cites only it is refused until it carries a `no ruling found:` line.
- A hyphen word after `step`, `decision` or `debt` counts as a cite. The judge can then only say "not searched".
- "I'll pick a port" and a pick word in a code span are statements to the `send_message` matcher, and `Pick:` as a heading is one to the brief matcher. Each is refused until the message carries a `no ruling found:` line, or is reworded.
- With no `get_session` record of the own session at all, a self-tag add reads as no coordinator. Session start prescribes `get_session` first.
- A refusal that names a ruling the prompt did not show is not checked (no `ruling_cite`).
- How often it fires is unmeasured. Read the `pick-judge` lines in `guard.log` after a week.

Kind: process
Home: rule:questions-go-to-owner
