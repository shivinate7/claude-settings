# A claim that a waiting-page item is answered matches the page

## The ruling

The answered-claim check refuses a sent message or brief that says a waiting-page item is answered, when the
page's data in git holds no owner answer for that item. Its rule is `brief-checks-answered-claims-match-page`.
It judges sent messages and briefs only. The sibling check `answered-needs-source` judges reply lines, in the
Stop hook (`lint/report_guard.py`).

Written from the owner's incident feedback (owner, 2026-11-15 13:30 CST, forwarded mailaudit coordinator
feedback item 3).

**The incident.** On 2026-11-15 the mailaudit coordinator told triage that an owner item was "already
answered". The only source was the coordinator's own recommendation. Harm: the receiver acts on a grant the
owner never gave. Risk kind: incident.

## What it judges

- Judged calls and fields:
  - `SendMessage`, field `message`.
  - `mcp__claude-code-remote__send_message`, field `message`.
  - `mcp__claude-code-remote__create_session`, field `prompt`.
- Other tools are not judged. A brief sent by any other tool passes.
- A claim is one sentence that holds all three of these:
  - An item reference: `item <n>`, `items <n> and <m>`, `item #<n>` or `page:<n>`, in any case. A letter after
    the number, such as `874d` or `806 d`, does not matter. A number alone in a code span counts. Each number in a
    list is judged.
  - The whole word `answered`, `approved` or `ruled`, in any case. `unanswered`, `overruled` and a word joined
    by a hyphen, such as `answered-needs-source`, are not the word.
  - No negator in the same clause before the word. A clause ends at `. ; : ! ? ,`, a dash, or a spaced hyphen.
    The negator list is `ANSWERED_NEGATOR_RE` in `lint/report_guard.py`. The check imports it and keeps no copy.
- A sentence is the prose of one paragraph: its lines are joined, so a break inside a claim does not hide it. A
  blank line, a list item or a heading ends the paragraph.
- Not judged:
  - A sentence that ends in `?`. Closing `*`, `_`, `)`, quotes or spaces after the mark do not change this.
  - Text in a fenced block, and text in an inline code span, except a span that holds only an item number.
  - The word as a list name: after `the`, `a`, `each`, `every` or `any` ("from the answered list"), or before
    `list`, `tab`, `section`, `column`, `queue` and like names. After `all`, only before a noun such as `items`
    ("all answered items"). "Items 874 and 875 are all answered" is a claim.
  - The word as a condition: after `until`, `unless`, `if`, `when`, `pending`, `awaiting`, `wait for` and like
    words in the same clause ("wait until item 874 is answered").
  - The word after `once`, `before` or `after` in the same clause, when its verb is not past ("after item 874
    is answered"). A past verb (`was`, `were`, `had`, `got`) makes it a claim: "I merged once item 874 was
    answered".
  - The word as a need: after `needs to be`, `must be`, `should be`, `has to be` and like words ("item 874
    needs to be answered").
  - A correction that ends by taking the claim back ("... was answered, and it is not").
  - A claim that cites the owner and a time in parentheses, such as "(owner, 2026-11-15 13:30 CST)". Only
    `owner` counts. "(coordinator, ...)" does not.
  - A claim that names an item by its id slug alone, with no number.

## What the page data is

- The folder is the export folder of the waiting-page entry in the repo's layout registry. Without one, it is
  `waiting-data`. The folder sits on the record branch, which is the `record-branch` key of the repo's extras
  file, or `roadmap` by default. Both come from `feedback_guard.waiting_copy`.
- The refs read are `refs/heads/<record branch>` and `refs/remotes/origin/<record branch>`, each one that
  exists. One `git grep` reads both refs, under `items` and `answers`, for the `"n"` and `"lastAnswer"` lines.
- Nothing is read from the working tree or from the live page.
- An item counts as answered when either of these holds in either ref:
  - An `answers/<id>.json` file holds the item's number as `n`.
  - An `items/<id>.json` file holds the item's number as `n` and has a `lastAnswer` key.

## What it does

- A claimed number that the page data holds, with no answer, refuses the call. The first such number refuses.
  - The refusal names the number and the sentence.
  - It gives the remedy: cite the owner's answer and its time in parentheses, such as
    "(owner, 2026-11-15 13:30 CST)", or say "recommended, not answered".
  - It says that the page writer exports first, when the owner answered after the last export (skill
    `waiting-page`).
  - An owner override lifts it. `refuse()` in `hooks/guard.py` takes the override (decision `owner-override`).
- A claimed number that the page data holds, with an answer, passes.
- A claimed number that the page data does not hold passes, with one stderr line.
- A read that fails passes, with one stderr line. A failed read is: no repo root, a layout error, no record
  branch in either ref, a git error or timeout, an unexpected grep line, or any exception. Unknown is not clear.

## Cost

- A call with no claim sentence starts no process. The text is first tested for the claim word and an item
  reference. Those tests are regex tests in the running hook.
- A claim sentence starts at most two processes. Both are `git`: `git for-each-ref`, then one `git grep`. The
  second runs only when a ref exists. One 5 second deadline covers both. The layout and folder reads open files
  only.
- Files written: none. A refusal writes the one guard.log line that every refusal writes.
- Runs: once per call to one of the three judged tools.
- Tests that prove the zero-process part: `test_a_message_with_no_claim_starts_no_process` and
  `test_a_tool_that_is_not_judged_starts_no_process` in `hooks/test_answered_claims.py`.

## Known limits

- An item named only by its id slug is not judged. Only numbers count.
- Store lag: an owner answer given after the last export is not in git yet. A claim of that answer is refused.
  The remedy is the export (skill `waiting-page`), or an owner override.
- The owner citation is read as words. The check does not look the cited answer up on the page.
- The refs are read without a fetch. A record branch that origin has moved since the last fetch is stale until
  the next fetch.
- The check is inert where no record branch ref holds the page data, so every claim passes with one stderr line.
  In `claude-settings`, `origin/roadmap` holds the data under `waiting`, so the check is inert only in a clone
  that has not fetched that ref.
- A condition word or a list name near the claim word exempts it, so "when item 874 was answered, we moved on"
  passes. Only `once`, `before` and `after` read the verb's tense.
- A simple past with no helper verb reads as a condition after `once`, `before` or `after`: "I merged once the
  owner approved item 874" passes.
- A future or a hope is read as a claim: "item 874 will be answered tomorrow" is refused.
- The noun list after `all` and the need words are fixed lists. A word outside them is read as a claim.
- A claim split over two sentences passes. The item in one sentence and the claim word in the next do not match.
- The check reads words, not meaning. A claim worded another way, such as "owner said yes", "accepted" or
  "signed off", is not judged.
- A negator earlier in the same clause exempts the claim word. A negator in an earlier clause does not.
- A brief sent by a tool other than the three judged tools is not judged.

Kind: process
Home: hooks/answered_claims.py
