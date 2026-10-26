# o13: one word per meaning (proposal for shiv's yes)

Checked against claude-settings main 3b96ce8. This renames nothing. After your yes, one lane
makes the prose changes, and the code changes go to a second lane with a reviewer.

**How the counts were taken.** `grep -ioP '\b<word>\b'` over tracked files. "Prose" is every `.md`
file in CLAUDE.md, GLOSSARY.md, agents/, skills/, output-styles/, docs/, decisions/, debts/, hooks/
and lint/. "Code" is the non-`.md` files in hooks/, lint/ and skills/; it includes variable names,
tests and hook API values, so it is a ceiling, not the number of messages. The vendored
`impeccable` skill is left out: it is upstream text and not ours to rename.

**The rule I used.** Keep the word that already has a GLOSSARY.md row or is the platform's own
name. Retire the extra word in prose. Never rename a rule anchor, a record slug, a file name, a
hook API value or a CI check name in this pass: each is an id, and something reads it.

## 1. Stopping a bad act: gate, guard, check, lint, mechanism

| Meaning (where it is defined) | Word | Retire | Prose / code | Risk |
|---|---|---|---|---|
| A hook that refuses or asks before a tool call or a reply lands ("A hook rule that refuses, or asks about, one act", GLOSSARY guard; "a gate whose script ... is missing refuses the call", `gate-hooks-fail-closed`) | **guard** | gate (this sense) | gate 222 / 486 | `report_gate.py`, `ste_gate.py`, `feedback_gate.py` file names stay |
| A lint, test or CI job that passes or fails a change (GLOSSARY check; "CI is the merge gate", CLAUDE.md) | **check** | gate (this sense), "merge gate" | 1 / 5 | none |
| Any file that enforces a rule ("kind `gate`: a file ... plus the proof that the gate WORKS", `lint/rule_audit.py`) | **check** | gate | 15 rows of `"kind": "gate"` in `rule_mechanisms.json` | `rule_audit.py` KINDS reads the value; rename it in the code lane only |

"guard, gate or check" in CLAUDE.md (13 uses, all in the review-cap rule) becomes "guard or
check". `lint` stays as a folder name and a kind of check, not a third enforcement word.
The CI workflow `gates.yml` keeps its name: branch protection reads the job name.

## 2. Proving code works: test, suite, harness, proof

| Meaning | Word | Retire | Prose / code | Risk |
|---|---|---|---|---|
| One test case or test file | **test** | — | — | none |
| Every test a check runs ("the full suites", CLAUDE.md) | **suite** | — | 42 / 143 | none |
| A script that breaks the code on purpose to prove the tests catch it ("the mutation harnesses", CLAUDE.md; `hooks/mutate_guard.py`) | **mutation test** | harness | 5 / 18 | `agents/builder.md` and `agents/reviewer.md` say "harness" |
| The recorded failing run on the old code ("The test-author's recorded red run is the red proof", CLAUDE.md) | **red run** | proof (this sense) | 23 / 39 | none |

"harness" otherwise means Claude Code itself, or banchi's `make harness`, which is a banchi word.

## 3. A unit of work: step, lane, task

The GLOSSARY.md "Open" list already names three meanings of **step**.

| Meaning | Word | Retire | Prose / code | Risk |
|---|---|---|---|---|
| One item of planned work on the roadmap (`speak-cite-id-plus-gloss`) | **step** | — | step 198 / 785 | none |
| One `- name:` entry in a CI job (`lint/rule_audit.py`, kind `ci`) | **CI step**, always with "CI" | bare step | 3 / 3 | none; GitHub's own word |
| One command in a shell chain (`decisions/ask-steps-run-alone.md`) | **command** | step | 1 / 0 | slug stays |
| One isolated branch of work (GLOSSARY lane) | **lane** | — | — | none |
| What one brief asks one agent to do (`roles-brief-contents`) | **task** | — | 83 / 161 | none |

## 4. Who does the work: session, agent, worker, subagent

| Meaning | Word | Retire | Prose / code | Risk |
|---|---|---|---|---|
| A top-level Claude Code conversation | **session** | — | — | none |
| Anything the Agent tool or a workflow starts ("Fan tasks out to workers", CLAUDE.md) | **agent** | worker, subagent | worker 24 / 49; subagent 89 / 345 | anchor `roles-one-role-per-worker` stays; `SubagentStop` and `subagent_type` are platform names and stay |

## 5. What the owner says: ruling, word, grant, approval, pass

| Meaning | Word | Retire | Prose / code | Risk |
|---|---|---|---|---|
| The owner's answer to a question (GLOSSARY ruling) | **ruling** | "decision" when it means the owner's choice | — | none |
| The owner's leave to do an act, once or standing ("merged only when I name the act", "merge grant") | **grant** | word ("my word", "owner's word"), approval | word 24 / 2 (phrase); approval 8 / 50 | anchor `outcomes-word-covers-named-act` stays; `guard.py` ask texts say "owner's word" |
| A prompt that starts with `override` and lets one refusal through (GLOSSARY override pass) | **override** | pass (noun) | "override pass" 13 / 28; bare noun "pass" 10 / 0 | slug and anchor `owner-override-pass` stay. Reason: "pass" already means a check passed, so "a pass the owner typed" reads two ways |

## 6. A filed record: record, decision, entry

| Meaning | Word | Retire | Prose / code | Risk |
|---|---|---|---|---|
| One file in `decisions/` or `debts/` ("Give each record its own file", CLAUDE.md) | **record** | entry | entry 63 / 448 | anchor `git-one-entry-per-question` stays; most code uses are JSON "entries", not records |
| A record for one question (GLOSSARY decision) | **decision** | — | — | none |

## 7. What a review finds: finding, defect, hole, gap

| Meaning | Word | Retire | Prose / code | Risk |
|---|---|---|---|---|
| Anything a reviewer reports | **finding** | issue (this sense) | issue 12 / 13 | none |
| Wrong behaviour | **defect** | bug | bug 3 / 10 | none |
| A guard or check that lets through what main refuses ("A safety hole is ...", CLAUDE.md) | **safety hole**, always both words | bare hole | hole 49 / 26 | none |
| A known gap, once filed | **debt** or **note** (GLOSSARY) | gap | gap 61 / 198 | none |

## 8. Saying no: refuse, block, deny

| Meaning | Word | Retire | Prose / code | Risk |
|---|---|---|---|---|
| A guard stops an act | **refuse** | block, deny in prose | refuse 263; block 146; deny 112 (prose) | `"deny"`, `"block"` and `"ask"` are hook API values in code (2,369 and 737 hits) and stay |

## 9. Review cycles: round, try

| Meaning | Word | Retire | Prose / code | Risk |
|---|---|---|---|---|
| One review and its fix ("at most three review rounds"; "round 1, try 1", CLAUDE.md) | **round** | try | try 15 / 34 | **`guard.py` reads the brief marker `Try 3 of 3`** to allow an Opus builder. Renaming it to `Round 3 of 3` is a guard change: code lane, reviewer, and both markers accepted for 14 days so running sessions are not refused |

## Checked, no change

owner (462 prose) against user (31): owner wins and GLOSSARY already says so; the 31 "user"
uses that mean you change in the prose lane. brief, plan and spec do not overlap here (spec is a
repo word). verdict and report do not overlap.

## Your pick, and mine

- **A. Yes to all nine.** Prose lane first, no code: it reads at most 911 prose uses, and edits only those in the retired sense. Code lane second: `"kind": "gate"`, the `Try 3 of 3` marker, and guard ask texts that say "owner's word". **My pick:** it ends the overlap in one go, and the risky renames get a reviewer.
- **B. Yes to groups 1 to 4 only.** Those are the words in your gripe. The rest wait.
- **C. Edit the list first.** Tell me a group to change, and I rewrite this file.

Either way, GLOSSARY.md gains a row for each new word and a "Not" cell for each retired one, so
`lint/check_glossary.py` keeps new file paths off the retired words.

Port to other repos: yes, with each repo's own glossary. The workflow words (groups 1, 3, 4, 5, 6,
8, 9) come from these shared rules, so they port with them. Each repo keeps its domain words, such
as banchi's `harness` and q_max's `gate`.
