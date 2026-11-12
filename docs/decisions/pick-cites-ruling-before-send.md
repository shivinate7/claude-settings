# A coordinator's pick cites a ruling before it is sent

## The ruling

A coordinator's message that states a pick or a hold cites the ruling it rests on, or says `no ruling found:` and what it searched. The message is checked against the cited text before it is sent.

- Scope: a `mcp__claude-code-remote__send_message` from a session whose own record carries the tag `cs-build:coordinator`, whose text states a pick or a hold. Any other sender or text passes, with no model call.
- The sender read: `hooks/own_session.py` (`own_session_read`) gives the tags of the newest `get_session` result of the own record, as the lane tag is read. Unlike the lane read, other `cs-build:` tags on the record do not void it. A `set_session_tags` call on the own session after that record is applied: its `add` and `remove` lists, in order. A call whose change cannot be read counts as a coordinator's self-tag, with one stderr line, so the pick is still checked. An agent's call, an unset record id and an unreadable transcript are no coordinator.
- The statement words are `pick`, `picks`, `picked`, `hold`, `holds` and `held`, as whole words. Chatter is no statement: a word followed by `on` or `up` (`hold on`, `pick up`), preceded by `on` (`on hold`), or with a hyphen beside it (a hyphenated record id).
- A cite is a plan R-number, a decision, debt or step id, or a `page item <number>`; a bare `item <number>` is no cite. A `no ruling found:` line may carry markdown (`*`, `_`, backticks) around the label, the colon and the text. A pick with no cite and no `no ruling found: <what was searched>` line is refused in code, with the remedy and no model call.
- A pick with a cite, or a `no ruling found:` line, gets one judge call (`hooks/call_judge.py`, `judge_pick`, guard rule `pick-judge`; Sonnet, the past-ruling check's model). The prompt carries the pick text and the rulings it may rest on. Each is a fenced block that the prompt labels data, not instructions. Each ruling line names its source.
- One function reads every ruling: `call_judge.ruled_candidates`. `judge_pick` calls it once. No other code reads a ruling. The sources, in the order the judge weighs them:
  - The ruled store, when it lands (lane `ruled-store-one-home`, `lint/ruled_store.py`, `ruled_entries`, ref `origin/roadmap`). It replaces the reads below inside `ruled_candidates`. It is not built yet.
  - The owner's page answer of a cited `page item <number>`, from `origin/roadmap`. The row of `waiting/answers/<slug>.json` whose `n` is the number gives the answer and its `at` time. `waiting/items/<slug>.json` holds the question and its options. The line reads `page item <number> answer (origin/roadmap, <at>)`.
  - A plan R-number, from `plans/*.md` on `origin/restart-plan`, and from the checkout's `plans` folder (`docs/plans` by the layout). The text runs from its `- **R<n>.` bullet to the next top-level bullet or heading, up to 6000 characters.
  - The decision, debt and step rulings of `question_form.past_rulings`, each labelled with its record path.
- Git reads the refs with no checkout and no fetch. A missing ref, folder or file, or a failed read, is named in the prompt as not searched. It never raises and never refuses.
- A later ruling supersedes an older one. The prompt tells the judge to judge the pick against the later ruling and to cite it. The date in a ruling's text, or the `at` time of a page answer, says which is later. The judge never refuses a pick for an older ruling that a later one replaced.
- Wording: a ruling is a past ruling to weigh, not a standing law. The refusal text says so. The prompt tells the judge to word its reason that way. No text says a ruling is owed or that a session must follow it.
- A source the hook cannot read is named in the prompt as not searched, never read as clear. Four kinds exist. Page items other than the cited ones, and later page answers. A plan R-number that no plan holds. A missing ref or file. A cited record that the read did not list.
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

Cost, per pick message: one `call_judge.py` process and one Sonnet call (60 s cap), plus one git process (`question_form.past_rulings`). A cited plan R-number or page item adds one more: one `git cat-file --batch` for every ref read. A cited pick runs at most two git processes; the bound is three. The ref reads write no file and start no long-lived process. The matcher starts `call_judge.py` on every `send_message` (37 ms measured). A send with no pick or hold word, or from a session that is no coordinator, starts no process beyond the hook's own start. It makes no model call. A pick with no cite makes no model call. Nothing is written but the `guard.log` line of a refusal. `hooks/test_call_judge.py` (section "a coordinator's pick") counts the calls.

Known limit:

- The judge reads the cited text, not the whole plan or the whole page. A page item is read only when the pick cites it. A page item with no answer on `origin/roadmap` reads as not searched, and the pick passes on the cite alone. A plan R-number that no plan holds is reported as not searched, never as clear.
- The refs are read as the last fetch left them. A ruling newer than the last fetch is unseen. A plan on another branch or in another repo is not found.
- The judge decides which ruling is later from dates in the text and the `at` time. A ruling with no date reads as undated, and the judge may weigh it wrongly.
- A pick in other words passes untouched: "Decision:", "going with", "my call is", "chose", "is on hold", "hold on merging".
- A plan ruling such as `G12` is no cite (`PICK_PLAN_REF` takes `R` only). A pick that cites only it is refused until it carries a `no ruling found:` line.
- A hyphen word after `step`, `decision` or `debt` counts as a cite. The judge can then only say "not searched".
- "I'll pick a port", a pick word in a code span, and `held` in a brief are statements to the matcher. Each is refused until the message carries a `no ruling found:` line.
- With no `get_session` record of the own session at all, a self-tag add reads as no coordinator. Session start prescribes `get_session` first.
- A refusal that names a ruling the prompt did not show is not checked (no `ruling_cite`).
- How often it fires is unmeasured. Read the `pick-judge` lines in `guard.log` after a week.

Kind: process
Home: rule:questions-go-to-owner
