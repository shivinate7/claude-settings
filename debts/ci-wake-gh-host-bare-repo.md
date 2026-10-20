# ci_wake drops the host from a github.com repo

- **What.** For a github.com PR, ci_wake passes a bare -R owner/repo. If the hook's env sets GH_HOST to an enterprise host, gh may read that host, and the watch then gives a false CI unknown line. Unmeasured.
- **Where.** hooks/ci_wake.py, repo_of_url.
- **Decision.** `ci-wait-reads-run-status` (the CI wait reads the run's status).
- **Retire.** Keep the host for github.com too (-R github.com/owner/repo). Check: a case with GH_HOST set and a github.com PR url.
