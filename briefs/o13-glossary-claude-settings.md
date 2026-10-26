# o13: one word per meaning, a proposal for shiv's yes

Cloud build thread brief. Build advisor (4), Oct 26, against claude-settings main 3b96ce8.
Base: main 3b96ce8. claude-settings only; never push to other repos. Push roadmap edits to the
branch only; only Triage the roadmap (3) republishes.

## Done already

GLOSSARY.md with 17 workflow terms landed in #597 (batch #595). This lane does not redo it.

## Rulings

- shiv, Oct 26 (page item 10, a): a lane proposes one word per meaning, for his yes.
- shiv's gripe, Oct 26: too many overlapping words (gates, harnesses, steps, checks, tests and
  more). The fix covers them all, not only those examples.
- shiv, Oct 26: claude-settings holds only terms that matter in every repo; each repo its own
  domain terms. Other repos follow the roll-out ruling (item 16); do not touch them.

## Task (proposal only; rename nothing yet)

1. List every workflow word that shares a meaning with another, across GLOSSARY.md, CLAUDE.md,
   rules, agents/, skills/, hooks/ messages, lint/ messages, output-styles/ and docs/. Measure use
   counts with grep; never estimate.
2. For each group: the meanings in play (quote the defining sentence and its file), the word you
   propose for each meaning, the words to retire, the use count each change touches, and the
   risk (a hook, check or rule anchor that reads the word).
3. Write it to plans/o13-one-word-per-meaning.md on the roadmap branch (pull before the write).
   Plain words first, one table per group, a pick for each. Cap: 2 pages.
4. Send a 10-line summary with the file path to "Answer all waiting decisions in one place"
   (cmsg_01DoF7thf3iq2Srr1UsfXgh2ADTZhQexksM43HTmuCPZMa) for shiv's waiting page, and the same to
   the build advisor. The rename lane is briefed only after shiv's yes.

## Report

Cap 15 lines: Done, Deviations, Next. Include "Port to other repos: yes or no, and why".
Report to "Advise the claude-settings build (4)" (cmsg_01DoF7thf3iq2Srr1UsfXgh2EyHwiKacoTT56k4JHuc2RT).
