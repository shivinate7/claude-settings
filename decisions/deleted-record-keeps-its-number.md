# A deleted numbered record keeps its number

## The question

May a branch delete a numbered record? Which number does the next claim take?

## The ruling

Settled by the owner. The stamp engine states the rule.

1. A numbered record may be deleted. Mode `check` does not refuse a removed record.
2. The claim takes a number above every number in the tree, in the tip of `--base`, and in
   every commit of the history of `--base`. So a deleted record keeps its number.
3. A kind may keep a `RETIRED` list in its folder. The claim counts each listed number as
   taken. The list is append-only.
4. A shallow clone, or a history that git cannot read, refuses the claim. A cut-short history
   could hand out a low number.
5. The heading format reads no `RETIRED` list.

Kind: build
Plan: decisions/deleted-record-keeps-its-number.md#the-ruling (all)
Home: actions/stamp/stamp.mjs

## Holes, named

- After a kind's folder or file is moved, numbers used under the old path are not seen. Debt
  `moved-kind-path-forgets-numbers` (a moved kind folder forgets its old numbers).

## Related

- The stamp README, "Modes" and "The retired-numbers list", states the rule for adopters.
