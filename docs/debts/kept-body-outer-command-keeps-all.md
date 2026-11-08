# A heredoc file write beside an ordinary outer command keeps every body

**What.** When a command writes a file by heredoc, the guard drops the body from its read only if every outer command word is a known reader or a literal visible script. `git`, `mkdir`, `cd`, `touch`, `chmod`, `sed`, `gh` and others are not on that list, so `cat > n.md <<'EOF' ... EOF && git add n.md` and `mkdir -p d && cat > d/x.md <<'EOF'` keep the body. A body that quotes a refused act, such as a decision record about a force push or a machine-wide kill, is then refused. Main drops a non-script body there. Measured: 2 of 40 decision records flip from allow to deny with `git add` or `mkdir` beside the write. Claude writes records this way in normal work, and this lane hit it on 2026-11-08 while filing this debt.

**Where.** `hooks/guard_core.py`, `_outer_runs_nothing_unseen`, called from `_kept_headers` and `strip_heredoc_bodies`.

**Decision.** an-agent-outside-its-home-tree-must-stop (an agent outside its home tree must stop).

**Retire.** The outer test runs only when a heredoc writes a file that something can run (a script by header, name or mode), or the outer words that run nothing (`git add`, `git status`, `git diff`, `mkdir`, `touch`) pass it. A row in `hooks/test_guard.py`, filter "heredoc replay kept body", writes a record that quotes a refused act with `git add` beside it, and allows.
