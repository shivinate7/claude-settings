# Outbox: c140-shared-resource-owner

- c140 part 1 (a shared machine names one owning repo): draft PR #743, head 851f61ad. origin/main 4e913588 (batch 4) is merged in. The conflict in docs/debts/notes.md is resolved, with both sides' lines kept. The local gates pass, and the silent-undo check is clean. Waiting for batch 5.
- c141 (the roll-out to other repos): each repo adds a `shared-resources` entry to `.claude/layout-extras.json`. The HA Green entry names owner shivinate7/home-app and the preflight path in that repo. Each repo then runs `lint/check_shared_resources.py` in its CI. The decision `shared-resource-owner` holds the convention.
