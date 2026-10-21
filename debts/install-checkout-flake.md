# The install.sh checkout-detection suite fails then passes on Windows CI

- **What.** On Windows CI the `install.sh` checkout-detection suite failed, then passed on rerun, twice on 2026-10-20: caseF1 in the morning (#527), and caseG1 at 23:00 (#533, run 39528566602; "expected ... main is 2 commits behind origin/main ... got ... on main, 0 dirty files"). Each failure blocked a merge.
- **Where.** `hooks/test_install_src.sh`, the checkout-detection cases, in the `gates-windows` job.
- **Decision.** none.
- **Retire.** Find the race (likely fetch or ref timing in the fixture) and fix it. The cases pass on repeat Windows runs.
