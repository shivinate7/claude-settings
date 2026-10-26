---
name: waiting-page
description: Use when a session has a question, a decision or a task for the owner, when it starts a turn with items open on the waiting page, or when a repo makes its waiting page. Puts every item waiting on the owner on one page per repo, and reads the owner's answers back.
---

The waiting page is one private page per repo or project. It holds every item that waits on the
owner, from every session. The page is fixed. All content lives in its database, through the
ArtifactData tool. Rule `questions-go-to-owner` (questions go to the owner) sends each question
here. Decision `questions-go-to-owner` holds the rulings.

## Find the page

Run `python3 ~/.claude/lint/layout.py waiting-page <repo root>`. It prints the URL, or `unknown`.
The URL is the `waiting-page` key in the repo's extras file, `.claude/layout-extras.json`.

- `unknown` is not an error. Ask in the reply while anything runs, else in the terminal question
  box, and say in one line that the repo has no waiting page.
- Never guess a URL, and never use the page of another repo.

## The database

- `items/<id>`: one per waiting item. Fields: `id`, `n` (a stable number the owner answers by),
  `kind` (`decision` or `task`), `status` (`open` or `closed`), `added` (ISO time), `ref` (each id
  with its plain name), `title`, `owner` (the session or thread name), `home` (the step, PR or
  record the answer goes to), `context` (plain text, line breaks kept).
  - A decision adds `options` (a list of `{key, label, how, gain, lose}`), `pick` (the key you
    recommend) and `why`.
  - A task adds `steps` (a list of strings), `links` (a list of `{label, url}`) and `minutes`.
- `answers/<id>`: the page writes it when the owner presses Save. Fields: `item`, `n`, `at` (ISO
  time), `note`, and `choice` (a decision) or `done: true` (a task). "Accept every pick" writes
  `choice` equal to `pick`, with the note `accepted pick`.
- `meta/page`: `checked` (what the items were measured against) and `parked` (a list of
  `{ref, note}`).

The page hides an item with status `closed`. It shows an item as answered when `answers/<id>` exists.

## Add an item

1. Read the open items with `ArtifactData list items`. Take the next free `n`. Never reuse an `n`
   while its item is open.
2. Write it with `ArtifactData set items/<id>`. Make `id` a slug of the question, 32 characters
   or fewer. Never reuse an `id`. If a slug is taken, add a suffix.
3. Ask the owner where the item is seen (ruling 3a, narrowed by ruling 3b):
   - While an agent, a lane or a background command runs, open no question box. Put the question
     and the page URL in the reply, and keep orchestrating. A box stops the session until the owner
     answers, and what runs goes on with no one to brake it.
   - With nothing running, ask in the terminal question box too, and put the page URL in the box.
4. Keep working on what does not depend on the answer.

## Read the answers

A save on the page wakes no session. Read the answers at the start of each turn while you have an
item open: `ArtifactData list answers`. An answer typed in the chat counts the same.

- An answer saved on the page counts as the owner's word for the item it names, and only for that
  item (ruling 2a). The same answer in the terminal box counts the same. If the two disagree,
  the later one wins: compare the answer's `at` with the time of the terminal answer.
- An answer is clear only when three things hold. Its `item` is the item's `id`. Its `at` is
  later than the item's `added`. Its `choice` is the `key` of one of the item's `options`.
- Never write `answers/`. Only the owner's Save writes it. A session that writes it forges the
  owner's word. This sentence is the only guard: ArtifactData writes as the owner, so nothing can
  tell a session's write from the owner's Save.

## Route and close

1. Move the answer to the item's home: the decision entry, the roadmap step or the PR, as rule
   `output-answer-has-a-home` (an answer has a home) says.
2. Close the item: `ArtifactData update items/<id> {"status": "closed"}`, pinned to the version
   you read (`if_version`). Then delete `answers/<id>`, so the answer cannot count for a later item.
3. If the answer is not clear, rewrite the item's `context`, delete `answers/<id>` (pinned to its
   version), and leave the item open. Say in the terminal what was not clear.

## Make a repo's page

Do this at the repo's roll-out to the layout, on the owner's word for that repo.

1. Load the `artifact-capabilities` skill.
2. Publish `page.html` from this skill folder as a new private artifact with the `db` capability
   only. Change nothing in the page.
3. Write `meta/page` with `checked` and an empty `parked`.
4. Put the URL in the repo's extras file: `"waiting-page": "<url>"`. The extras file also marks the
   repo as rolled out, so add the key only in that roll-out.
5. Check with `python3 ~/.claude/lint/layout.py waiting-page <repo root>`.

A local session can write to the database (measured on the Mac, Oct 26). A Windows session is
unmeasured.
