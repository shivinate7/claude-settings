# A page decision gets a refuter's case against its pick

## The ruling

Owner, 2026-11-06, waiting-page item 284, pick a (step `challenger-page-against`, the best case against
the pick). Each waiting-page item that carries a `pick` and is not closed carries `against`: the strongest case against the
recommended pick, written by a blind refuter. The owner reads it before he picks. Owner, item 282 b: the
word is "refuter".

- Blind: the refuter sees the item's `context`, its options and the pick keys. It never sees `why`.
- An item with a pick and no options gets `against: "unknown (no options)"`, with no call.
- A failed call writes `against: "unknown (<reason>)"`, never a blank or a pass (decision
  `ci-unknown-is-red`, an unknown read is red in CI).
- The model is one setting, `REFUTER_MODEL` in `skills/waiting-page/refute_item.py`: Sonnet. Owner,
  item 289, 2026-11-06 13:59 CST: "for now let's do sonnet for all".

## Mechanism

- Script: `skills/waiting-page/refute_item.py <item.json>`. The writer runs it on the item file before
  `ArtifactData set` with `file_path`. It calls `decision_watch.invoke_model`, the one home of model calls
  from hooks and scripts.
- Guard: `hooks/question_form.py` refuses an `items` write that carries a `pick`, is not closed, and has
  no non-blank `against`. It needs no `kind`: an update may carry only the pick. The refuter's scope is the
  same set.
- Page: `skills/waiting-page/page.html` draws `against` under the pick, labelled "Best case against".

Why a script and not a PreToolUse hook that adds the field: the hooks docs leave `updatedInput` on
ArtifactData unproven. In auto mode a changed call may be denied, and the order of parallel hooks is
not documented (code.claude.com/docs/en/hooks, read 2026-11-06).

## Known gaps

- The guard checks that `against` is there, not that the refuter wrote it. A writer could type one.
  Blindness holds by the script, not by the guard. Unmeasured.
- An update that changes `options` or `context` but carries no `pick` keeps the old `against`.
- The model-per-role table (decision `agent-model-cap`) lists agents. The refuter here is a script's
  model call, not an agent, so its model lives in `REFUTER_MODEL` alone.

## Why

Protects: the owner sees the best counter-argument before he picks. A pick that read well only because
of its own `why` meets its case against.

## Cost

One Sonnet call, at medium effort, per open decision write that carries a `pick`. It is run by the
writer, in its own turn. No file kept, no timer, no process, no log.

## Done check

`skills/waiting-page/test_refute_item.py`, `hooks/test_question_form.py` (the `against` cases) and
`skills/waiting-page/tests/page.test.mjs` (the "Best case against" cases), red on main 4f2e2059.

Kind: rule
Home: skills/waiting-page/refute_item.py
Home: hooks/question_form.py
