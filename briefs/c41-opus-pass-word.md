# c41: an Opus-only pass word, for one session and a time

Cloud build thread brief. Build advisor (3), Oct 26, against claude-settings main 3b96ce8.
Base: main 3b96ce8; never rebase onto main after review. Push roadmap edits to the branch only;
only "Triage the roadmap (3)" republishes the roadmap page.

## Ruling

shiv, Oct 26 (waiting page item 14, option a): build the Opus-only pass word.

## Task

Extend the override pass's one home, hooks/override_pass.py (decision owner-override-pass), with
a second prompt word that lifts only the guard rule subagent-model-cap's asks for this session and
its subagents until it expires. Shape (advisor pick, Oct 25): `opus 2h`, `opus 15m`, and optionally
one role, `opus builders 2h`. `opus off` ends it. Same parsing discipline as `override`: only the
whole prompt grants; anything ambiguous grants nothing.

1. Red first: tests that an Opus spawn outside Plan, Explore and a builder's try 3 still asks
   with no pass, and asks today even after `opus 2h` (the word is unknown).
2. Green: with `opus 2h`, that spawn passes; every other refusal and ask in the guard stands
   (prove with at least three other rules); the pass expires on time; a subagent's call honours
   it; a session cannot grant it to itself (state/ stays frozen to Claude's writes).
3. The role form, if built: `opus builders 2h` lifts only builder spawns. If it costs more than
   it buys, leave it out and say why.
4. Record: rewrite decision owner-override-pass in place (or add a slug entry if it is a new
   question), and one CLAUDE.md touch where rule roles-sonnet-is-the-ceiling names how the owner
   raises Opus. guard.log logs each grant and each lift.

## Fences

- One home: hooks/override_pass.py and the subagent-model-cap rule's own code. No second pass
  file format unless the existing one cannot hold a scope; say which.
- c70 (#617) is changing guard refusal messages; keep clear of message text.

## Failure classes and proof

- Changes a guard's verdict: review rounds per roles-review-cap-three, fresh Sonnet reviewer from
  round 1, the net-value test after round 3 if reached.
- Run the guard suite and hooks/mutate_guard.py through `verdict`; add a mutant for the new scope
  check and show it killed.

## Report

Add one line, "Port to other repos: yes or no, and why" (shiv's ruling on c52, Oct 26). Cap 20
lines: Done, Deviations, Next. Send the green, reviewed head and branch to "Advise the
claude-settings build (3)". Do not merge, and do not rebase onto main. No question for shiv:
park any in the PR body.
