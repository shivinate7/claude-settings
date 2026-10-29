# c190-press-links (lane session session_013NEJL1ufZNt8hafVCH6uyP)

Branch c190-press-links, head d6f441a4 (round 3 red cases). No PR yet.

- Built: guard rules press-link and command-in-item (hooks/guard.py, block "the owner acts in place"), record docs/decisions/act-in-place.md, SKILL.md fields option `links` and task `command`, page.html option links and a closed "Show the command" box with Copy.
- Review: round 1 FAIL (fixed), round 2 FAIL on one blocking finding (a press split across task steps). Round 3 builder (Opus, Round 3 of 3) is fixing it; then the round 3 review with the net-value test.
- Design: review FAIL on task link tap size, fixed; re-check PASS on 9b612dd6.
- Lane rulings: command box closed (house rule ux-machine-text-hidden); a failed Copy opens it (noted exception); an unnumbered press passes with any link; command-in-item judges tasks only. Notes in docs/debts/notes.md.
- c188 (reserved option keys) is still todo, though the step says due after it.
- Local page suite: 2 viewer "1200 wide" cases red on origin/main too; the pinned Playwright browser is missing on this box.
