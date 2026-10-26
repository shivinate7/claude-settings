# c49: a ruling on a behaviour covers every test that expects the old behaviour

Repo: claude-settings. Mode: solo (three prose files and one record). Checked at 149f4bc.

## Why

Owner gripe, 2026-10-26. A session on another repo asked the owner a second time whether it may change
an old test. The owner had already ruled the old behaviour out at 21:27 (a rule save must not clear the
partly-sent mark). The session wrote: "Your word covered one test. A failing test only changes on your
word." A second test, and maybe three more, expected the same ruled-out behaviour.

Cause, two rules read together:
- outcomes-tests-are-claims (a failing test is a claim, not law) and its 3-class sort in agents/builder.md
  and agents/reviewer.md have no class for "the owner already ruled this behaviour out". The session put
  the test in class (c), "the rule may be stale", which says STOP and wait for the owner's word.
- outcomes-word-covers-named-act (my word covers the act it names, never a variant) was read as "the word
  named one test", so each further test looked like a variant.

The rules are right about acts (a merge, a delete, a push). They are wrong about rulings: a ruling names a
behaviour, and a test that expects the old behaviour is only one route to it.

## Change

1. CLAUDE.md, rule outcomes-tests-are-claims: add one sentence. A test that expects a behaviour the owner
   already ruled out is re-pointed, not asked about: cite the ruling and its time, show it red on the old
   behaviour and green on the new.
2. CLAUDE.md, rule outcomes-word-covers-named-act: add one sentence. A ruling on a behaviour covers every
   test and code path that expects the old behaviour.
3. agents/builder.md and agents/reviewer.md, the 3-class sort: add class (d), "the owner already ruled
   this behaviour out". The builder reports the test change it needs (builders do not edit tests; a
   test-author does), and cites the ruling. When one test of a ruled behaviour fails, find every test that
   expects the same behaviour in one pass (search, then run them), and re-point them all in the same lane.
   Report the list. The reviewer checks that each re-pointed test expects exactly the ruled-out behaviour,
   and flags any that pins something next to it; that one goes back to class (c).
4. Class (c) stays for a test whose behaviour has no ruling. It still goes to the owner.
5. docs/records.md and lint/rule_mechanisms.json: keep their lines for the two rules true.

Keep the CLAUDE.md word count flat or lower: rewrite in place, cut words elsewhere in the same two rules if
needed. Report the count before and after.

## Done when

- The rule audit and STE lints pass (`verdict` on the lint suite the repo's CI runs for CLAUDE.md and
  agents/).
- A reader can answer "may I re-point the second test?" from the text alone: yes, cite the 21:27 ruling.

Report cap: 15 lines.
