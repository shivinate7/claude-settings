# Outbox: c140-shared-resource-owner

- c140 part 1 (a shared machine names one owning repo): draft PR #743, head c1aecd35. The local gates pass, and the round-2 review approved. It is ready to join a batch.
- c141 (the roll-out to other repos): each repo adds a `shared-resources` entry to `.claude/layout-extras.json`. The HA Green entry names owner shivinate7/home-app and the preflight path in that repo. Each repo then runs `lint/check_shared_resources.py` in its CI. The decision `shared-resource-owner` holds the convention.
