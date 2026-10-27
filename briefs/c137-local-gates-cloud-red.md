# c137: the local gates run is green on clean main in a cloud container

Cloud build thread brief. Build advisor (10), Oct 27, against claude-settings main 6a3e842.
Base: main 6a3e842 (after batch #704). Never rebase onto main after review. Send your green,
reviewed head to the build advisor; never merge.

## Why
Lanes report the local gates red on clean main in cloud containers. Triage measured
`python3 -m unittest lint.test_check_silent_undo` green on main 9264397 in a fresh clone
(depth 50 and depth 1; git 2.43; 1 skip for missing ssh-keygen). So the red needs something a
lane has and a fresh clone lacks: a git worktree, the session's own checkout, a second runner of
the local gates, or pytest. Unmeasured. A guard that cries wolf is spent, so this ranks ahead of
new checks.

## Task
1. Reproduce red. Try each shape in turn: a `git worktree add` checkout of main; the session's
   pre-cloned checkout; two runners at once; pytest instead of unittest. Record which shape goes
   red, with the failing test and its message (one line each).
2. Fix the cause in the fixture or the tool, never by a skip.
3. Add that shape to the test, red first on the old code, then green.

## Done when
The shape that was red is a test case, shown red on main 6a3e842 and green on your head, and
`bin/verdict python3 -m unittest discover -s lint` is green in that shape. If no shape goes red,
report the shapes tried and stop; that is a finding, not a failure.

Review: one fresh Sonnet reviewer (it touches a check's verdict). Report cap 20 lines.
Port: no; it lives in claude-settings.
