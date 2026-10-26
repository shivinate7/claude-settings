# o13: one word per meaning

**Ruled.** shiv, Oct 26: yes to all nine groups. The code is renamed too, so the words shiv
uses and the words in the code match with no conversion table. Other repos take a one-time
conversion. Counts were checked against claude-settings main 3b96ce8.

**How the counts were taken.** `grep -ioP '\b<word>\b'` over tracked files. "Prose" is every `.md`
file in CLAUDE.md, GLOSSARY.md, agents/, skills/, output-styles/, docs/, decisions/, debts/, hooks/
and lint/. "Code" is the non-`.md` files in hooks/, lint/ and skills/; it includes variable names,
tests and hook API values, so it is a ceiling, not the number of messages. The vendored
`impeccable` skill is left out: it is upstream text and not ours to rename.

**The rule.** Keep the word that already has a GLOSSARY.md row. Retire the extra word everywhere
we own it: prose, hook and lint messages, file names, identifiers, rule anchors, record slugs, rule
kinds and the CI workflow name. Each rename changes every reader in the same PR. The "Risk"
column lists what that touches. Only Claude Code's own names stay, because the platform defines
them: the hook values `deny`, `block` and `ask`, the `SubagentStop` event, `subagent_type`, and
the Task tool. Code that emits them wraps them in a function named with our word, so `refuse()`
returns `deny`. A renamed hook file keeps an exit-0 stub at its old path for 14 days, because a
running session keeps the hook list it read at start (`gate-hooks-fail-closed`). The stub is then
deleted.

## 1. Stopping a bad act: gate, guard, check, lint, mechanism

| Meaning (where it is defined) | Word | Retire | Prose / code | Risk |
|---|---|---|---|---|
| A hook that refuses or asks before a tool call or a reply lands ("A hook rule that refuses, or asks about, one act", GLOSSARY guard; "a gate whose script ... is missing refuses the call", `gate-hooks-fail-closed`) | **guard** | gate (this sense) | gate 222 / 486 | rename `lint/report_gate.py`, `lint/ste_gate.py`, `hooks/feedback_gate.py`, `lint/test_gates.py`, and records `gate-hooks-fail-closed`, `ste-gate-fixes-not-nags`, `recovery-must-not-gate-on-its-own-state`, anchor `verification-recovery-not-gated-on-own-state` |
| A lint, test or CI job that passes or fails a change (GLOSSARY check; "CI is the merge gate", CLAUDE.md) | **check** | gate (this sense), "merge gate" | 1 / 5 | none |
| Any file that enforces a rule ("kind `gate`: a file ... plus the proof that the gate WORKS", `lint/rule_audit.py`) | **check** | gate | 15 rows of `"kind": "gate"` in `rule_mechanisms.json` | rename the kind and `rule_audit.py` KINDS together |

"guard, gate or check" in CLAUDE.md (13 uses, all in the review-cap rule) becomes "guard or
check". `lint` stays as a folder name and a kind of check, not a third enforcement word.
The CI workflow `gates.yml` and its job become `checks`. Branch protection names the required job,
so the lane updates it in the same step, or every PR waits on a job that never runs.

## 2. Proving code works: test, suite, harness, proof

| Meaning | Word | Retire | Prose / code | Risk |
|---|---|---|---|---|
| One test case or test file | **test** | — | — | none |
| Every test a check runs ("the full suites", CLAUDE.md) | **suite** | — | 42 / 143 | none |
| A script that breaks the code on purpose to prove the tests catch it ("the mutation harnesses", CLAUDE.md; `hooks/mutate_guard.py`) | **mutation test** | harness | 5 / 18 | `agents/builder.md`, `agents/reviewer.md`; rename `.github/scripts/harness-scope.sh` and `lint/test_harness_scope.py` |
| The recorded failing run on the old code ("The test-author's recorded red run is the red proof", CLAUDE.md) | **red run** | proof (this sense) | 23 / 39 | none |

"harness" otherwise means Claude Code itself, or banchi's `make harness`, which is a banchi word.

## 3. A unit of work: step, lane, task

The GLOSSARY.md "Open" list already names three meanings of **step**.

| Meaning | Word | Retire | Prose / code | Risk |
|---|---|---|---|---|
| One item of planned work on the roadmap (`speak-cite-id-plus-gloss`) | **step** | — | step 198 / 785 | none |
| One `- name:` entry in a CI job (`lint/rule_audit.py`, kind `ci`) | **CI step**, always with "CI" | bare step | 3 / 3 | none; GitHub's own word |
| One command in a shell chain (`decisions/ask-steps-run-alone.md`) | **command** | step | 1 / 0 | rename record `ask-steps-run-alone` |
| One isolated branch of work (GLOSSARY lane) | **lane** | — | — | none |
| What one brief asks one agent to do (`roles-brief-contents`) | **task** | — | 83 / 161 | none |

## 4. Who does the work: session, agent, worker, subagent

| Meaning | Word | Retire | Prose / code | Risk |
|---|---|---|---|---|
| A top-level Claude Code conversation | **session** | — | — | none |
| Anything the Agent tool or a workflow starts ("Fan tasks out to workers", CLAUDE.md) | **agent** | worker, subagent | worker 24 / 49; subagent 89 / 345 | rename anchor `roles-one-role-per-worker`, records `subagent-model-cap` and `subagent-powershell-tool`; `SubagentStop` and `subagent_type` are platform names |

## 5. What the owner says: ruling, word, grant, approval, pass

| Meaning | Word | Retire | Prose / code | Risk |
|---|---|---|---|---|
| The owner's answer to a question (GLOSSARY ruling) | **ruling** | "decision" when it means the owner's choice | — | none |
| The owner's leave to do an act, once or standing ("merged only when I name the act", "merge grant") | **grant** | word ("my word", "owner's word"), approval | word 24 / 2 (phrase); approval 8 / 50 | rename anchor `outcomes-word-covers-named-act`; `guard.py` ask texts say "owner's word" |
| A prompt that starts with `override` and lets one refusal through (GLOSSARY override pass) | **override** | pass (noun) | "override pass" 13 / 28; bare noun "pass" 10 / 0 | rename record `owner-override-pass`. Reason: "pass" already means a check passed, so "a pass the owner typed" reads two ways |

## 6. A filed record: record, decision, entry

| Meaning | Word | Retire | Prose / code | Risk |
|---|---|---|---|---|
| One file in `decisions/` or `debts/` ("Give each record its own file", CLAUDE.md) | **record** | entry | entry 63 / 448 | rename anchor `git-one-entry-per-question`; most code uses are JSON "entries", not records, and stay |
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
| A guard stops an act | **refuse** | block, deny in prose | refuse 263; block 146; deny 112 (prose) | `deny`, `block`, `ask` are hook API values (2,369 and 737 code hits): kept inside `refuse()`; rename records `cite-by-id-blocks-unread-file`, `reply-judge-samples-never-blocks`, anchor `verification-never-dry-run-blocklist` |

## 9. Review cycles: round, try

| Meaning | Word | Retire | Prose / code | Risk |
|---|---|---|---|---|
| One review and its fix ("at most three review rounds"; "round 1, try 1", CLAUDE.md) | **round** | try | try 15 / 34 | **`guard.py` reads the brief marker `Try 3 of 3`** to allow an Opus builder. Renaming it to `Round 3 of 3` is a guard change, so it gets a reviewer. Both markers pass for 14 days, so a brief already sent is not refused. Rename anchor `roles-third-try-steps-up` |

## Checked, no change

owner (462 prose) against user (31): owner wins and GLOSSARY already says so; the 31 "user"
uses that mean you change in the prose lane. brief, plan and spec do not overlap here (spec is a
repo word). verdict and report do not overlap.

## How it lands

1. **One lane per group, in claude-settings.** Each lane renames prose, messages, files,
   identifiers, anchors and slugs for its group in one PR, with every reader. A lane that touches
   a guard or a check gets a reviewer. It reads at most 911 prose uses and edits only the retired
   sense.
2. **GLOSSARY.md** gains a row for each word and a "Not" cell for each retired one.
3. **The glossary check widens** from file paths to identifiers, rule anchors, record slugs and
   hook messages, so a retired word cannot come back in code. Prose stays a reviewer's job,
   because a word like "pass" has a correct sense too.
4. **Other repos: a one-time conversion.** The `compliance-check` skill gains a step that runs
   the widened glossary check over the whole repo and lists each retired word, so each repo's
   session converts once. Each repo keeps its own domain words, such as banchi's `harness` and
   q_max's `gate`, in its own GLOSSARY.md. Every repo change waits for shiv's plan check first.

Port to other repos: yes, by the one-time conversion in step 4. The workflow words come from the
shared rules, so a repo that keeps the old words drifts from them.
