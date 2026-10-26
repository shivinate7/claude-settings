# Plan: a page per session for questions waiting on the owner

Roadmap step o10 (a page per session for questions waiting on you). Plan only. Nothing here is
built yet.

A busy session publishes one live page. The page shows the session's plan (done, now, next) and
each open question. The owner answers on the page. The answer goes back to the session, and the
session goes on.

## How a question reaches the owner today

- Rule `questions-go-to-owner` (questions go to the owner): a session brings each question to
  the owner, names what it does meanwhile, and keeps working.
- The output style `shiv-stylisms` sets the question shape: a `Goal:` line, a `Problem:` line,
  one to three `Based on:` lines, then options, all inside the question box.
- Step c31 (a question waiting on you reaches you) found that the desktop app already shows a
  banner for a waiting question. No push was added.
- Step c28 (a step left to you comes as a one-click command) makes a step for the owner a
  runnable block.

The gap: each question lives in one terminal. The owner must open each session to read and
answer it. o10 gives each session one page that holds all its open questions.

## Kept apart from o8

Step o8 (a living roadmap page per repo) is the lasting page. It reads each item from its one
home. o10 is the live page of one session. It lives only while the session has open questions.
A later o8 page may link to each live session page. This plan does not change o8.

## What the platform offers

Checked on 2026-10-26, in a claude.ai cloud project session on the owner's account. "Tool doc"
is the text of the Artifact, ArtifactComments and ArtifactData tool descriptions in that
session. "Skill" is the `artifact-capabilities` skill, runtime contract 0.2.91. It lists the
capabilities this account may declare.

| Fact | State | Where checked |
|---|---|---|
| A cloud session can publish a private page with the Artifact tool. | Checked | Tool doc |
| A page may declare `artifact`, `comments`, `db`, `user` and `downloads`. | Checked | Skill roster |
| With `artifact`, a page saves itself as a new version from a viewer's press. | Checked | Skill, `artifact` section |
| A cloud session that published a page watches it. A republish from elsewhere wakes the session with a new turn. | Checked | Tool doc, ArtifactComments "Watching" |
| A comment sent to Claude on a watched page wakes the session. A plain comment does not. | Checked | Tool doc, ArtifactComments |
| A session reads and writes the page's `db` rows with the ArtifactData tool. | Checked | Tool doc |
| A page can put text on the clipboard. | Unknown | Not tested in the claude.ai viewer frame |
| The local Claude Code CLI on Max has the Artifact tool. | Unknown | The tool doc names `/artifacts` in the terminal, but no local session was tested |
| A local session's watch wakes it the same way as a cloud session's. | Unknown | The tool doc says "in this remote session" only |
| Which plan this account is (Max or Enterprise). | Unknown | Not shown to the session |
| Comments sent to Claude need in-organization sharing (Enterprise). | Unknown | Roadmap note only; not shown in the tool doc |
| A session on an API key cannot publish a page. | Unknown | Roadmap note only; not tested |

The checked facts give a third path that the step note does not name: the page saves the
answers into itself, and that save wakes the session. It needs no paste and no comment. It is
checked for cloud sessions only.

## Path A: "Copy answers" (build first)

It works wherever a page can be published, and it needs no wake.

1. **Publish.** When a session has its first open question, it writes one page and publishes
   it. It republishes the same file on each change, so the link stays the same.
2. **What the page shows.**
   - A header: the session name, the repo, the branch, and the time of the last publish.
   - The plan: Done, Now, Next, one line each.
   - One card per open question: Goal, Problem, Based on, the options with what each gains and
     loses, the recommendation, and what the session does meanwhile.
3. **How the owner answers.** The owner picks one option per card, or writes a short free-text
   answer. A per-viewer draft sits in browser storage, so a reload keeps it.
4. **The answer block.** One button builds one plain-text block with every answer. The owner
   copies it and pastes it into the session. If the clipboard is refused, the page shows the
   block in a text box to select by hand.
5. **The return.** The block opens with a fixed first line, `Answers from the questions page`,
   then one line per question: its id, the picked option label, and any free text. The session
   reads the block as the owner's own message, so it is the owner's ruling. The session then
   files each answer per rule `output-answer-has-a-home` and republishes the page with that
   question closed.

## Path B: the page saves the answers (cloud sessions)

The page declares `artifact`. "Send answers" saves the page with the answers in its data. The
save wakes the publishing cloud session. The session re-reads the page with the Artifact tool
and acts on the answers.

- It needs no paste, and it does not depend on comments.
- Only a writer can save. The owner is the writer, so this fits a page for one owner.
- The answer is the owner's own act on the page. Whether a session may treat a page save as
  the owner's word needs a ruling (see "Deferred for shiv", item 3).
- Path A's button stays on the page as the fallback.

## Path C: comments sent to Claude (Enterprise)

Each question card is a comment target. The owner writes the answer as a comment and sends it
to Claude. The session wakes, reads the thread with ArtifactComments, replies, and resolves it.
This path needs a watch and in-organization sharing. Both are unknown for local sessions.

## What a session must hold

- One page file per session, in its scratchpad, and the page link.
- Each question's id, so an answer line maps to one question.
- No `db` capability for paths A and B. The page is its own record.

## Cost (rule `outcomes-mechanize-rules`)

| Item | Path A | Path B | Path C |
|---|---|---|---|
| Processes started | none | none | none |
| Files written | one page file per session, rewritten on each change | the same | the same |
| How often | one publish per new or closed question | the same, plus one owner save per batch of answers | the same, plus one reply per thread |
| Watcher or timer | none | none; the platform's watch wakes the session (c26, watching costs less than what it watches) | the same as B |

No hook, timer or new process. A publish happens only when a question opens or closes.

## Rules and parts the build would need

- A skill or output-style section that gives the publish trigger and the page shape. The
  build names its home. This plan changes no rule.
- If the owner picks path B, a rule change: a page save by the owner counts as the owner's
  word.
- A check that the page's question cards carry the same fields as the question box (Goal,
  Problem, Based on, options, recommendation).

## Deferred for shiv

Each item waits on the owner. The session builds path A meanwhile, since every option below
keeps path A.

1. **When a session publishes a page.**
   - (a) At its first open question. Gain: no page for a session with no question. Loss: a
     first question has no page history.
   - (b) For every session at start. Gain: a page for each session. Loss: many idle pages.
   - Recommendation: (a).
2. **Which return path the build adds after path A.**
   - (a) Path A only. Gain: least to build. Loss: a paste each time.
   - (b) Add path B. Gain: no paste in cloud sessions. Loss: needs the ruling in item 3.
   - (c) Add path C. Gain: answers live in threads. Loss: depends on Enterprise sharing,
     unknown today.
   - Recommendation: (b), after a local test shows whether a local session wakes too.
3. **Whether a page save counts as the owner's word.**
   - (a) Yes, for the owner's own save on a page only the owner can write. Gain: path B works.
     Loss: a new rule to guard.
   - (b) No; only a typed message counts. Gain: no new rule. Loss: no path B.
   - Recommendation: (a).
4. **Whether the terminal question box stays when a page exists.**
   - (a) Keep both; the box links to the page. Gain: no loss when the page fails. Loss: the
     question shows twice.
   - (b) The page only. Gain: one place. Loss: no answer path when publish fails.
   - Recommendation: (a).

## Unknowns to measure before the build

- One local session on Max: can it publish, and does a save or comment wake it?
- The clipboard from the claude.ai viewer frame.
- Whether this account is Max or Enterprise, and whether comments need in-organization sharing.
