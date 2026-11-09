# Windows main runs go red on jobs that passed on the batch head

- **What.** Two main push runs went red on Windows only, and each blocked the next batch until a rerun went green.
  - Sweep: run 42063704930 (main 5a416cc87), checks-windows-sweep. Six AgentEndReapTests mutants read `WRONG CAUSE … saw: FAILED (errors=1)`. The same head passed on attempt 2. The cause is unknown: the driver kept only FAIL lines, so the ERROR traceback was lost.
  - Rest: run 42080963752 (main c4b7f47ab), checks-windows-rest. Exit 143 about 0.2 s into `test_a_host_without_ps_skips_and_leaves_no_holder`, at 13m04s of a 28-min cap, with no failing test. Later steps ran, so the runner did not cancel the job. Python's `os.kill` exits 15 on Windows; an MSYS `kill` on a non-MSYS process exits 143. Probable cause: `kill_holder` passed a stale MSYS pid to a new shell, which killed an unrelated Windows process.
- **Where.** `janitor/test_session_end_sweep.py` (`kill_holder`), `janitor/test_sweep.py` (AgentEndReapTests), and the WRONG CAUSE report in `hooks/mutate_shared.py`.
- **Decision.** `test-strategy-reset` (a test must not fail on runner speed).
- **Retire.** The lane windows-main-run-flakes stops each holder at most once, with no pid kill on Windows, and makes WRONG CAUSE print the ERROR line and the exception. Rest closes after 10 green checks-windows-rest runs on main with no exit 143. Sweep closes when the next red names its exception and that cause is fixed, or after 10 green checks-windows-sweep runs on main.
