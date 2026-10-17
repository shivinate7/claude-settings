# The merge command runs from the clone, with no install

## The question

How does the code of the merge command reach a device, and how does a run stay current?

## The ruling

Settled by the owner.

1. **No install of the tool.** `merge/` and `actions/stamp` run from the claude-settings
   checkout that the device's `~/.claude/CLAUDE.md` includes. `landed-dirs.txt` names neither
   folder. Only the shim `bin/merge` lands, and it holds no merge logic.
2. **The command updates itself before every merge.** It never refuses to merge for an old
   copy. When it cannot prove fresh code, it warns loudly and goes on.
3. **`--dev` runs the checkout's own tree,** for work on the tool itself. Only that flag does it
   without a warning. A failed fetch also runs the checkout's tree, and prints a warning.

Kind: build
Plan: decisions/merge-runs-from-the-clone.md#the-ruling (all)
Home: merge/launch.py

## Related

- The README, "The `merge` command", states the lookup order and the warning block.
- Decision merge-reinstalls-from-main (each merge reinstalls from the main checkout).
