# A CI check-in never waits past the cache cap

## The ruling

The guard refuses a `send_later` call that waits on CI for longer than the cap (rule `ci-wait-cap`, in `hooks/guard.py`). The cap is `cap_minutes()` in `hooks/ci_wait_cap.py`, which reads `hooks/ci_wait_cap.json` on each call. The guard holds no copy of the number.

- A message waits on CI when it holds, in any letter case, the whole word `CI` or `checks`, or the phrase `PR run` or `workflow run`. The whole message is read. A substring (`decision`, `specific`) and the word `check` alone do not count.
- The wait is `delay_minutes`, or an `at` time (ISO-8601 with an offset, read against `local_time.clock()`) after now. The limit is inclusive: a wait of exactly the cap passes. A call with no CI reading, or with neither field, passes.
- The reason names `send_later`, `delay_minutes` and the cap, and steers to a shorter wait.
- An agent's call is refused first, as `agent-no-remote-tools`.
- A missing or malformed cap file raises. The guard logs the crash and lets the call through. A made-up default would hide a lost source.

Mistake: a session sets a CI check-in longer than the 1-hour prompt cache allows. Harm: the wake pays a full context rewrite of the session. Rule `git-ci-wait-checks-in` said "never past 55 minutes" and nothing enforced it.

Known false alarm: a message that holds the word `checks` or `CI` for another reason, and waits long, is refused. The owner's override lifts it (decision `guard-guards-mistakes-only`, guards stop Claude's mistakes). Known gap: the guard reads the cap, not the cache in force. Under the 5-minute cache (overage, API key, cloud provider, subagent) a wait at the cap still misses the cache (decision `ci-wait-reads-run-status`, the fallback).

Cost: no new process. The check reads the message once, in the guard run that already starts for each `send_later` call (unmeasured). A CI message with a wait also reads one data file and, for an `at`, the clock (unmeasured).

Tests: family `ci-wait-cap` in `hooks/test_guard.py` (cases in `tests/guard/s43200-ci-wait-cap.py`), and `hooks/test_ci_wait_cap.py` for the data file and reader.

Kind: process
Home: hooks/guard.py
