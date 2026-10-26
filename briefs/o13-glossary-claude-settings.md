# o13: one name per thing, the claude-settings glossary

Cloud build thread brief. Build advisor (2), Oct 26, against claude-settings main bf084df.
Base: main bf084df; never rebase onto main after review. claude-settings only: each child repo's own
GLOSSARY.md is Roll out; do not touch other repos. Where the file lives in the shared layout is o2's;
put it at the repo root now.

## Rulings

- Owner, Oct 26: GLOSSARY.md. claude-settings holds only terms that matter in every repo; each repo
  holds its own domain terms and never redefines a global one.
- Advisor picks, standing: pointed at from CLAUDE.md, not inlined; borrow from mattpocock/skills
  ubiquitous-language, credited, rather than install it.

## Task

1. GLOSSARY.md: the workflow nouns as one table (term, meaning in one STE sentence, home: the file
   or record that owns it, "not:" names to avoid). Start from: lane, batch, integration PR,
   worktree, handoff, step, ruling, decision, debt, note, guard, gate, check, owner, override pass,
   orchestrator, builder, reviewer. Take each meaning from the rule or record that defines it; never
   invent one. A term with two meanings in the repo today: list it, pick neither, park it in the PR body.
2. CLAUDE.md: one pointer sentence (STE). agents/builder.md, agents/reviewer.md and the Plan brief
   path: one line each to check new names against the glossary.
3. A cheap CI check: each row's home path exists, and no changed file adds a path segment that a
   row lists under "not:". Give it one home in lint/ and a step in gates.yml.
4. Optional, only if small: a glossary skill that seeds a repo's GLOSSARY.md from a template.

## Failure classes and proof

- Test-author first, red on main: a row whose home is missing fails; a new path using a "not:"
  name fails; a mention of a "not:" word in prose does not (false alarm); a clean tree passes.
- Rule count: rule_audit's pinned counts move only by any new anchor; say which bucket.
- A fresh Sonnet reviewer reads the diff (it adds a check).

## Report

Cap 20 lines: Done, Deviations, Next. Send the green, reviewed head and branch to
"Advise the claude-settings build (2)". No question for shiv: park any in the PR body.
