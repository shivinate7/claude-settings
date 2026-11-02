# Step 2 is judged by the real bugs it lets through

## The ruling

Owner, 2026-10-28 13:40 CDT (waiting page item 34, pick b), roadmap step c95, step 2: count the real Windows or Mac bugs that reach main, and weigh that count against what step 2 saves. Take step 2 in a repo only when the money and waiting it saves is worth more than the cost of fixing those bugs. The count is per repo.

- Not the count of every failure that only the full set catches. Flaky timing failures outnumber real bugs about 4 to 1, so that count mostly measures noise (item 34, option a, not picked).
- Not a judgment by green runs on main. The owner rejected it on Oct 28 at 02:36 CDT.
- Price here: no GitHub Actions minutes are billed to claude-settings (owner, 2026-10-28 13:23 CDT, waiting page item 38, pick a). So step 2 stays off in claude-settings. A repo that pays for minutes may turn it on.

Measured input, from 551 runs on Oct 13 to 28: about 5 real Windows or Mac bugs would have slipped through in 15.5 days (about 3 a week). About 20 failures came from flaky timing tests. Main went red 34 times, and 24 of those were flaky timing tests.

Kind: process
Home: .github/workflows/checks.yml
