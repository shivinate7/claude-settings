# c190-press-links (lane session session_013NEJL1ufZNt8hafVCH6uyP)

Draft PR #819, branch c190-press-links, head 92618aba. Sent to the batch runner for batch 22.

- Built: guard rules press-link and command-in-item, record docs/decisions/act-in-place.md, SKILL.md option `links` and task `command`, page option links and a closed "Show the command" box with Copy.
- Main 1ce1fcb7 (batch 21: multi-pick and ranked cards) merged in at 26fd767d; option links now work on those cards; ranked-card press fix 92618aba.
- Review: rounds 1-2 FAIL, round 3 PASS (net value positive); merge review: resolution sound, its test findings fixed. Design: all screens PASS on 92618aba.
- Gates on head: ci-job checks --lint, silent-undo --strict, ste-changed PASS; guard suite PASS on 26fd767d (no guard change since). Page suite 242/245; 2 fail on main too, 1 flaky.
- Lane rulings: command box closed (house rule ux-machine-text-hidden); a failed Copy opens it; an unnumbered press passes with any link; command-in-item judges tasks only. Notes in docs/debts/notes.md.
- Open: c188 (reserved option keys) is still todo, though the step says due after it.
