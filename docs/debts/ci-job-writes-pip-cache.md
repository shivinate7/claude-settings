# A full ci-job run writes to the pip cache, and no step is named as the writer

**What.** A full run of `lint/test_ci_job.py` rewrites an entry in `~/.cache/pip/http-v2`. The step or test that writes it is not identified.

**Where.** `lint/test_ci_job.py`, and `bin/ci-job`, which runs the CI steps that the test plans.

**Decision.** `none`.

**Retire.** `lint/test_ci_job.py`, a case red first on the current code: a full run with `PIP_CACHE_DIR` set to an empty folder leaves that folder empty. The case goes green when no step writes the pip cache.
