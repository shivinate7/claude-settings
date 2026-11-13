# A plan gets a refuter

## The ruling

Owner, 2026-11-06 12:43 CST, waiting-page item 279, pick d. Audit finding: the reviewer reviews
"against the brief you were given" (`agents/reviewer.md`), so a wrong plan passes every review round.
Nothing argued back against a Plan agent.

- After a Plan agent returns, the orchestrator spawns one refuter (`agents/refuter.md`). The
  refuter is a read-only agent on Opus.
- Its brief holds the task brief the planner got and the plan the planner returned, word for word,
  and nothing else. It never holds the planner's reasoning or the orchestrator's view.
- It tries to refute the plan's premises (`premise-format`) and to find a simpler route. It gives one
  verdict: `holds`, `revise` or `refuted`.
- A clash, a `revise` or `refuted` verdict the orchestrator does not take, goes to the orchestrator first.
  When the clash stakes a rule, money or an act that cannot be undone, it goes to the owner as a question
  (rule `questions-go-to-owner`).
- The verdict goes on the plan record's `Refuter:` line. Lane step-done-needs-check, pending, adds that line.
  This record adds no second line.

## Mechanism

- Role file: `agents/refuter.md`.
- Rule line: `roles-plan-gets-refuter` in `CLAUDE.md`. The role is also in the role list of
  `roles-one-role-per-agent` and the Opus list of `roles-sonnet-is-the-ceiling`.
- Model: the refuter row of decision `agent-model-cap`, the model-per-role table.
- Guard: the Opus spawn guard (`hooks/guard.py`, the standing Opus roles) lets a refuter spawn on Opus.
  The role name has one home in code, `REFUTER_ROLE` in `hooks/guard_core.py`.
- Check: pending in lane step-done-needs-check. It fails a plan record with no `Refuter:` line.

## Term

Owner, 2026-11-06, waiting-page item 282, pick b (step `debate-glossary-word`, one word for the agent
that argues back): the word is "refuter".

## Known gaps

- The check sees only plan records added in the plans home. Most Plan agent output never becomes a
  record. The rule line covers those, by instruction only.
- Blindness is by instruction only: the agent file and the rule line. No hook reads the refuter's
  brief. Unmeasured.
- The pending check accepts any role on the `Refuter:` line, so an orchestrator's own read would pass.
  Coordinator, 2026-11-06 12:56 CST, pick a: lane step-done-needs-check lands after this one and makes
  the check require the role in `REFUTER_ROLE`.

## Why

Protects: a wrong premise in a plan is caught before a builder builds on it. The reviewer judges the
build against the brief and cannot catch it.

## Cost

One Opus call per plan, at high effort (unmeasured). No file, timer, process or log.

## Done check

`hooks/test_guard.py` and `hooks/test_agent_brief.py` hold the refuter cases, red on the old code.
A refuter on Opus is allowed. A reviewer on Opus is still refused. The agent brief treats the
refuter as read-only.

Kind: process
Home: rule:roles-plan-gets-refuter
