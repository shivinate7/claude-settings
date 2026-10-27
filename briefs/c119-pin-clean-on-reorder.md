# c119: a settings save that only reorders keys must not stop the pin from moving

Builder lane, claude-settings, from main d4e1b86b. Report cap: 25 lines.

## The defect (measured on the Mac, Oct 27 09:18 CDT)

~/.claude/settings.json is a link into the pin. A settings save (app or CLI) rewrites the file
with its keys reordered and no value changed. `merge/install_from_main.sh`'s `move_pin` then sees a
tracked change in the pin and fails with "the pinned checkout ... has tracked changes" on every
session start. The Mac's pin is stuck at 2ad85de6, so no merge reaches it.

## The fix

In `merge/install_from_main.sh`, before the tracked-changes refusal in `move_pin`: when the only
tracked change in the pin is `settings.json`, and it parses to the same JSON as `HEAD:settings.json`,
restore it from HEAD (`git -C "$pin" checkout -- settings.json`) and go on. Any other change, or a
value change in settings.json, still refuses as today. Compare with `python3 -c` (json.load, `==`).
With no working python3, or a file that does not parse, keep today's refusal: fail safe.

Use the same check in the old-tree sweep (the loop that skips a tree with tracked changes), so an
old tree holding only a reordered settings.json is removed and not kept for ever.

Do not stop linking settings.json into the pin. That is the larger change, and this one is enough.

## Tests (red first, in merge/test_install_from_main.sh)

1. A pin whose settings.json holds HEAD's keys in another order: the pin moves to main, and the
   pin's settings.json equals main's. Red on main.
2. A pin whose settings.json changes one value: still refused, pin not moved.
3. A pin with the reorder plus a change to another tracked file: still refused.
4. An old `-live-<hex>` tree with only a reordered settings.json is swept.

## Done when

The four cases pass, `bash merge/test_install_from_main.sh` is green, and `bin/ci-job gates --base
origin/main` passes. Commit trailers as the project requires. Push the lane branch, send the green,
reviewed head to the build advisor, and never merge.

## Note for the advisor, not the lane

The session-start hook runs `bash merge/install_from_main.sh` from the clone after it fast-forwards
local main, so once this merges, a Mac clone on main self-heals at its next session start with no
manual step. A clone checked out on another branch runs that branch's copy and does not.
