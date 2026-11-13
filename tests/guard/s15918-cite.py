# section 15918
FAMILY = "cite"
FAMILIES["cite"] = "cite by id"
# =========================================================================== 5d. cite by id
#
# `git-cite-by-id`. A commit message or a PR body that cites a record by its path is refused. A code
# path, the word "decisions", a read of a record and a record's own file stay allowed.

CITE = "decisions/one-shared-record-stamp.md"
# Each form below reaches its own branch of the cite scan: a flag shape, a message source, or a
# path spelling. A form that only repeats another's branch is not listed.
for _name, _command in (
    ("a commit -m", VCS + ' commit -m "fix, per ' + CITE + '"'),
    ("a -am cluster", VCS + ' commit -am "see debts/later-item.md"'),
    ("the long --message=", VCS + ' commit --message="cites ' + CITE + '"'),
    ("a file named by -F", VCS + " commit -F " + slash(MSG_BAD)),
    ("a heredoc inside -m", VCS + ' commit -m "$(cat <<\'EOF\'\ntitle\n\ncites ' + CITE + '\nEOF\n)"'),
    ("a backslash path", VCS + ' commit -m "cites decisions\\one-shared-record-stamp.md"'),
    ("an attached -m value", VCS + ' commit -m"cites ' + CITE + '"'),
    ("a repo-root record path in parentheses", VCS + ' commit -m "done (' + CITE + ')"'),
    ("a record path in bold", VCS + ' commit -m "see **docs/decisions/one-shared-record-stamp.md**"'),
    ("a dot-slash record path", VCS + ' commit -m "cites ./' + CITE + '"'),
    ("a PR body", 'gh pr create --draft --title t --body "cites ' + CITE + '"'),
    ("a layout-path decision", VCS + ' commit -m "fix, per docs/' + CITE + '"'),
    ("a layout-path debt", VCS + ' commit -m "see docs/debts/later-item.md"'),
    ("a numbered record path under docs", VCS + ' commit -m "see docs/decisions/0001.md"'),
    ("a layout-path decision in a PR body",
     'gh pr create --draft --title t --body "cites docs/' + CITE + '"'),
    ("a PR body file", "gh pr edit 3 --body-file " + slash(MSG_BAD)),
):
    sh("cite-by-id: %s denies" % _name, _command, "deny", "cite-by-id", cwd=NOGIT, config=MERGECFG)
sh("cite-by-id: a message file that cannot be read is unknown, and denies",
   VCS + " commit -F " + slash(ROOT) + "/no-such-message.txt", "deny", "cite-by-id",
   carries="could not be read", cwd=NOGIT, config=MERGECFG)
# AUDIT 2026-10-17 (guard-audit-fixes, finding 7). "An unreadable -F file makes git fail, so allow it"
# does not hold for these three: the file is unreadable at hook time, and git reads it fine when the
# command runs. The same command writes it first (a redirect, or the usual `cat > f <<EOF` then
# `commit -F f`), or the shell makes it (`<(...)`). An unconditional allow would let a message that
# cites a record path through.
MSG_MADE = slash(ROOT) + "/msg-made-in-this-command.txt"   # no such file: only the command makes it
for _name, _command in (
    ("a file written by a redirect in the same command",
     "printf 'cites " + CITE + "' > " + MSG_MADE + " && " + VCS + " commit -F " + MSG_MADE),
    ("a file written by a heredoc in the same command",
     "cat > " + MSG_MADE + " <<'EOF'\ncites " + CITE + "\nEOF\n" + VCS + " commit -F " + MSG_MADE),
    ("a message made by a process substitution",
     VCS + " commit -F <(printf 'cites " + CITE + "')"),
):
    sh("cite-by-id: %s is unread at hook time, and denies" % _name, _command, "deny",
       "cite-by-id", carries="could not be read", cwd=NOGIT, config=MERGECFG)
sh("cite-by-id: a PowerShell commit denies too", VCS + ' commit -m "cites ' + CITE + '"', "deny",
   "cite-by-id", tool="PowerShell", cwd=NOGIT, config=MERGECFG)
for _name, _command in (
    ("a code path", VCS + ' commit -m "guard: fix hooks/guard.py"'),
    ("a code path in bold", VCS + ' commit -m "guard: fix **hooks/guard.py**"'),
    ("the word decisions", VCS + ' commit -m "decisions: one word, no path"'),
    ("the word debts and a folder", VCS + ' commit -m "move the debts around, see decisions/"'),
    ("an id with a gloss", VCS + ' commit -m "per D12, short titles for records"'),
    ("a record path in the add, not the message",
     VCS + " add " + CITE + " && " + VCS + ' commit -m "add the record"'),
    ("a non-record file of a record folder", VCS + ' commit -m "update decisions/ORDER.json"'),
    ("a heredoc that belongs to the command after the commit",
     VCS + ' commit -m "add" && cat > notes.txt <<\'EOF\'\nsee ' + CITE + '\nEOF'),
    ("a note message, which this rule does not read", VCS + ' notes add -m "cites ' + CITE + '"'),
    ("a URL that holds a record path",
     VCS + ' commit -m "see https://github.com/o/r/blob/main/' + CITE + '"'),
    ("a record path under another folder", VCS + ' commit -m "see lint/' + CITE + '"'),
    ("a code path under lint", VCS + ' commit -m "see lint/layout.py and hooks/guard.py"'),
    ("a message file that cites an id", VCS + " commit -F " + slash(MSG_OK)),
    ("a PR body with an id", 'gh pr create --draft --title t --body "per D12, short titles for records"'),
):
    sh("cite-by-id: %s is allowed" % _name, _command, "allow", cwd=NOGIT, config=MERGECFG)
for _name, _command in (
    ("a log of a record", VCS + " log --oneline -- " + CITE),
    ("a show of a record", VCS + " show HEAD:" + CITE),
    ("a cat of a record", "cat " + CITE),
    ("an echo that holds commit words", 'echo \'' + VCS + ' commit -m "' + CITE + '"\''),
    ("a grep for a record path", "grep -rn '" + CITE + "' ."),
    ("a heredoc that writes a record citing another",
     "cat > decisions/a.md <<'EOF'\nsee " + CITE + "\nEOF"),
    ("a log search for the path", VCS + ' log --grep="' + CITE + '"'),
    ("a PR view", "gh pr view 12 --json body"),
):
    sh("cite-by-id: %s is no message" % _name, _command, "allow", silent=True, cwd=NOGIT, config=MERGECFG)

# ---- two readings of a lone quote. Bash
# reads `echo it's` as an open single quote, and the line holding only a quote closes it. The
# commit after them is a real command, and its heredoc body is data. own_heredoc_bodies reads the
# header on one reading only, so it must still judge this commit's body. The -m form with
# a command substitution is the same shape.
LONE_PAIR = "echo it's\n'\n"
sh("cite-by-id: a lone quote pair, then a -F - commit that cites a record denies",
   LONE_PAIR + VCS + " commit -F - <<'EOF'\ntitle\n\ncites " + CITE + "\nEOF", "deny", "cite-by-id",
   cwd=NOGIT, config=MERGECFG)
sh("cite-by-id: a lone quote pair, then a -m $(cat heredoc commit that cites a record denies",
   LONE_PAIR + VCS + ' commit -m "$(cat <<\'EOF\'\ntitle\n\ncites ' + CITE + '\nEOF\n)"', "deny",
   "cite-by-id", cwd=NOGIT, config=MERGECFG)
sh("cite-by-id: a lone quote pair, then a -F - commit with a clean body is allowed",
   LONE_PAIR + VCS + " commit -F - <<'EOF'\ntitle\n\nclean body\nEOF", "allow", cwd=NOGIT,
   config=MERGECFG)

# The Drops-lines trailer (owner ruling 2026-10-12): the one place a record path may stand in a
# commit message is `Drops-lines: <path> -- <reason>`, the shape lint/check_silent_undo.py reads
# from the last paragraph of a commit. A trailer with no ` -- reason` excuses nothing. The reason
# may not cite a record path. Every other line is still judged by the cite rule.
DROPS_BODY = "title\n\nbody\n\nDrops-lines: debts/a.md -- replaced by a decision"
sh("cite-by-id: Drops-lines trailer in a commit -m body is allowed",
   VCS + ' commit -m "' + DROPS_BODY + '"', "allow", cwd=NOGIT, config=MERGECFG)
sh("cite-by-id: Drops-lines trailer in a heredoc -F - body is allowed",
   VCS + " commit -F - <<'EOF'\n" + DROPS_BODY + "\nEOF", "allow", cwd=NOGIT, config=MERGECFG)
sh("cite-by-id: a Drops-lines trailer naming a layout-path debt is allowed",
   VCS + ' commit -m "title\n\nbody\n\nDrops-lines: docs/debts/a.md -- replaced by a decision"',
   "allow", cwd=NOGIT, config=MERGECFG)
sh("cite-by-id: two Drops-lines trailers with two paths are allowed",
   VCS + ' commit -m "title\n\nDrops-lines: debts/a.md -- replaced by a decision\n'
   'Drops-lines: debts/b.md -- folded into a decision"', "allow", cwd=NOGIT, config=MERGECFG)
sh("cite-by-id: a prose cite beside a Drops-lines trailer is denied",
   VCS + ' commit -m "title\n\nbody cites debts/a.md\n\n'
   'Drops-lines: debts/a.md -- replaced by a decision"', "deny", "cite-by-id",
   cwd=NOGIT, config=MERGECFG)
sh("cite-by-id: a Drops-lines reason that cites a record path is denied",
   VCS + ' commit -m "title\n\nDrops-lines: debts/a.md -- see decisions/b.md"', "deny",
   "cite-by-id", cwd=NOGIT, config=MERGECFG)
sh("cite-by-id: a Drops-lines trailer in a gh pr create body is denied",
   'gh pr create --draft --title t --body "title\n\nDrops-lines: debts/a.md -- replaced by a decision"',
   "deny", "cite-by-id", cwd=NOGIT, config=MERGECFG)
sh("cite-by-id: Drops-lines key spelled drops-lines: is allowed",
   VCS + ' commit -m "title\n\nbody\n\ndrops-lines: debts/a.md -- replaced by a decision"',
   "allow", cwd=NOGIT, config=MERGECFG)
sh("cite-by-id: a Drops-lines trailer with no reason is denied",
   VCS + ' commit -m "title\n\nbody\n\nDrops-lines: debts/a.md"', "deny", "cite-by-id",
   cwd=NOGIT, config=MERGECFG)
sh("cite-by-id: a Drops-lines line in a middle paragraph is denied",
   VCS + ' commit -m "title\n\nDrops-lines: debts/a.md -- replaced by a decision\n\n'
   'body after the trailer"', "deny", "cite-by-id", cwd=NOGIT, config=MERGECFG)
# Owner ruling 2026-10-12. The exemption must blank one path, not the whole token after
# the key, so a second path in the same token is still judged. The lint reads that token as one path,
# which excuses no record path. A space before the colon is still the key `Drops-lines`, which
# `git interpret-trailers` reads and the lint accepts.
sh("cite-by-id: Drops-lines token with a comma-joined second path is denied",
   VCS + ' commit -m "title\n\nbody\n\nDrops-lines: debts/a.md,debts/b.md -- replaced"',
   "deny", "cite-by-id", cwd=NOGIT, config=MERGECFG)
sh("cite-by-id: Drops-lines token with a semicolon-joined second path is denied",
   VCS + ' commit -m "title\n\nbody\n\nDrops-lines: debts/a.md;debts/b.md -- replaced"',
   "deny", "cite-by-id", cwd=NOGIT, config=MERGECFG)
sh("cite-by-id: Drops-lines key with a space before the colon is allowed",
   VCS + ' commit -m "title\n\nbody\n\nDrops-lines : debts/a.md -- replaced"',
   "allow", cwd=NOGIT, config=MERGECFG)

# ---- lane-by-slug (owner ruling 2026-10-13). A commit message or PR body names a lane by its
# session number, such as `N20` or `(N16)`. That number is handed out in one chat and means nothing
# outside it, so a lane is named by its branch slug. The scan reads the same message text as
# cite-by-id. A number inside a backtick code span or a fenced block is quoted text and stays
# allowed. `NaN`, `N/A`, `IPv4N1`, `N100000` and `N+1` are no lane number. Only a commit message,
# a PR body or title, and a `gh pr merge` subject or body are read (a squash subject or body becomes
# a commit on main). A tag, a note, a log search and a PR list are other acts.
sh("lane-by-slug: the refusal names a branch slug as the remedy",
   VCS + ' commit -m "fix flaky test (N16)"', "deny", "lane-by-slug", carries="branch slug",
   cwd=NOGIT, config=MERGECFG)
for _name, _command in (
    ("a body line naming a lane", VCS + ' commit -m "title" -m "Lane N20 lands the guard."'),
    ("N3b in prose", VCS + ' commit -m "title\n\nsee N3b for the rest"'),
    ("the long --message=", VCS + ' commit --message="Lane N20 lands"'),
    ("an attached -m value", VCS + ' commit -m"Lane N20 lands"'),
    ("a -am cluster", VCS + ' commit -am "fix (N16)"'),
    ("a single-quoted message", VCS + " commit -m 'Lane N20 lands'"),
    ("a file named by -F", VCS + " commit -F " + slash(MSG_LANE)),
    ("a heredoc fed to -F -", VCS + " commit -F - <<'EOF'\ntitle\n\nLane N20 lands\nEOF"),
    ("a PR body", 'gh pr create --draft --title t --body "lands N16"'),
    ("a PR body file", "gh pr edit 3 --body-file " + slash(MSG_LANE)),
    ("a PR body behind a cd", "cd x; gh pr edit 3 -b 'lands N16'"),
    ("a lone backtick before the number",
     VCS + " commit -m 'title\n\nthe ` mark, then Lane N16 lands'"),
    ("a closed span then a bare number", VCS + " commit -m 'title\n\n`x` then N16 lands'"),
    ("an apostrophe word beside a number", VCS + ' commit -m "title\n\nDon\'t land N20"'),
    ("a hash opener inside the message", VCS + ' commit -m "title\n\n# note: Lane N16 lands"'),
    ("a slash-slash opener inside the message", VCS + ' commit -m "title\n\nsee // Lane N16 lands"'),
    ("a block opener inside the message", VCS + ' commit -m "title\n\n/* Lane N16 lands */"'),
    ("a number after a closed fence",
     VCS + " commit -F - <<'EOF'\ntitle\n\n```\nx = 1\n```\nLane N16 lands\nEOF"),
):
    sh("lane-by-slug: %s denies" % _name, _command, "deny", "lane-by-slug", cwd=NOGIT,
       config=MERGECFG)
sh("lane-by-slug: a PowerShell commit denies too", VCS + ' commit -m "Lane N16 lands"', "deny",
   "lane-by-slug", tool="PowerShell", cwd=NOGIT, config=MERGECFG)
sh("lane-by-slug: a PowerShell -F file at a native path denies", VCS + " commit -F " + MSG_LANE,
   "deny", "lane-by-slug", tool="PowerShell", cwd=NOGIT, config=MERGECFG)
for _name, _command in (
    ("a number in a code span", VCS + " commit -m 'title\n\nsee `N16` for the lane'"),
    ("a number in a fenced block",
     VCS + " commit -F - <<'EOF'\ntitle\n\n```\nLane N20 lands\n```\nEOF"),
    ("a table cell in a fenced block",
     VCS + " commit -F - <<'EOF'\ntitle\n\n```\n| lane | state |\n| N1 | done |\n```\nEOF"),
    ("a comment opener inside a fence",
     VCS + " commit -F - <<'EOF'\ntitle\n\n```\n# Lane N16 lands\n```\nEOF"),
    ("a message file with a fenced number", VCS + " commit -F " + slash(MSG_FENCE)),
    ("a PR body with a code span", "gh pr create --draft --title t --body 'see `N16` lands'"),
    ("NaN", VCS + ' commit -m "title\n\nNaN guard for the sum"'),
    ("N/A", VCS + ' commit -m "title\n\nowner: N/A"'),
    ("IPv4N1, which has no word boundary", VCS + ' commit -m "title\n\nbind the IPv4N1 address"'),
    ("N100000", VCS + ' commit -m "title\n\nbatch of N100000 rows"'),
    ("N+1, a redundancy term", VCS + ' commit -m "title\n\nadd N+1 cooling"'),
    ("a commit with no number", VCS + ' commit -m "fix guard parsing"'),
):
    sh("lane-by-slug: %s is allowed" % _name, _command, "allow", cwd=NOGIT, config=MERGECFG)
# The same lane-by-slug rule, its title and merge half. A title names a lane on create and edit, and
# a squash subject or body on merge, so each is read. The merge cases run on a green head, so merge-checks
# passes and only the lane rule can decide. A create without --draft is refused by draft-pr, so the
# allowed create carries --draft.
for _name, _command in (
    ("a create title naming a lane", 'gh pr create --title "lane N20" --body x'),
    ("an edit title in the short form", "gh pr edit 5 -t 'fix (N16)'"),
    ("a create title in the equals form", "gh pr create --title=N7 --body x"),
    ("a merge subject naming a lane", 'gh pr merge 5 --squash --subject "fix (N16)"'),
    ("a merge body naming a lane", 'gh pr merge 5 --squash --body "N20 lands"'),
):
    sh("lane-by-slug: %s denies" % _name, _command, "deny", "lane-by-slug", cwd=NOGIT,
       env_path=GREEN_ON, config=MERGECFG)
sh("lane-by-slug: a create title naming a slug is allowed",
   'gh pr create --draft --title "slug lands" --body x', "allow", cwd=NOGIT, config=MERGECFG)
sh("lane-by-slug: a bare squash merge is allowed", "gh pr merge 5 --squash", "allow", cwd=NOGIT,
   env_path=GREEN_ON, config=MERGECFG)
sh("lane-by-slug: a merge subject naming a slug is allowed",
   'gh pr merge 5 --squash --subject "lane-number-cite lands"', "allow", cwd=NOGIT,
   env_path=GREEN_ON, config=MERGECFG)
for _name, _command in (
    ("an echo", 'echo "lane N16 lands"'),
    ("a grep", "grep -rn 'N16' hooks"),
    ("a log search", VCS + " log --grep=N16 --oneline"),
    ("a git note", VCS + ' notes add -m "Lane N16 lands"'),
    ("a tag message", VCS + ' tag -a lane-v1 -m "Lane N16 cut"'),
    ("a PR list search", 'gh pr list --search "N16"'),
):
    sh("lane-by-slug: %s is no message" % _name, _command, "allow", silent=True, cwd=NOGIT,
       config=MERGECFG)


# ---- lane-by-slug. A glued short flag
# (-tN16, -t=N16, -bN16, -amN20, -am"x") and a long-option prefix (--mess=, --messa=) carry the
# message, so they are read. A double-backtick span and a ~~~ fence are quoted text, as a single
# backtick span and a ``` fence already are. A cat heredoc is no commit message, so only the
# commit's own -F - body counts. An unreadable -F file on gh pr merge fails closed, as on create and
# edit (decision guard-hooks-fail-closed).
sh("lane-by-slug: an unreadable -F file on gh pr merge is refused, not read as clean",
   "gh pr merge 5 --squash -F /nonexistent/msg.md", "deny", "cite-by-id",
   carries="could not be read", cwd=NOGIT, env_path=GREEN_ON, config=MERGECFG)
for _name, _command in (
    ("a glued -tN16 title", "gh pr create --draft -tN16 -b x"),
    ("a glued -t=N16 title", "gh pr create --draft -t=N16 -b x"),
    ("a glued -bN16 body", "gh pr create --draft -t x -bN16"),
    ("a glued -amN20 cluster", VCS + " commit -amN20"),
    ("a glued -am cluster with a quoted value", VCS + ' commit -am"fix (N16)"'),
    ("a long --mess= prefix", VCS + ' commit --mess="fix N16"'),
    ("a long --messa= prefix", VCS + ' commit --messa="fix N16"'),
):
    sh("lane-by-slug: %s denies" % _name, _command, "deny", "lane-by-slug", cwd=NOGIT,
       config=MERGECFG)
for _name, _command in (
    ("a double-backtick code span", VCS + " commit -m 'title\n\nsee ``N16`` for the lane'"),
    ("a ~~~ fence", VCS + " commit -F - <<'EOF'\ntitle\n\n~~~\nLane N16 lands\n~~~\nEOF"),
    ("a cat heredoc naming N16, then a clean commit heredoc",
     "cat <<'A' && " + VCS + " commit -F - <<'B'\nN16 notes\nA\ntitle\n\nclean body\nB"),
    ("a cat heredoc with clean notes, then a clean commit heredoc",
     "cat <<'A' && " + VCS + " commit -F - <<'B'\nclean notes\nA\ntitle\n\nclean body\nB"),
    ("a lowercase n16", VCS + ' commit -m "title\n\nsee n16 for the lane"'),
    ("N16a, the shape stops at a letter", VCS + ' commit -m "title\n\nsee N16a for the lane"'),
):
    sh("lane-by-slug: %s is allowed" % _name, _command, "allow", cwd=NOGIT, config=MERGECFG)
for _name, _command in (
    ("a number after a closed double-backtick span",
     VCS + " commit -m 'title\n\n``a`` then N16 lands'"),
    ("a number after a closed ~~~ fence",
     VCS + " commit -F - <<'EOF'\ntitle\n\n~~~\nx = 1\n~~~\nLane N16 lands\nEOF"),
):
    sh("lane-by-slug: %s denies" % _name, _command, "deny", "lane-by-slug", cwd=NOGIT,
       config=MERGECFG)
# ---- lane-by-slug. Two commits in one call each take their own heredoc body, so
# a second commit whose segment text repeats the first is still judged on its own body. A header
# inside quotes is text, and the commit's own header still takes its body. A glued value is never a
# body: a letter in a glued value is read as a value, not as a flag.
for _name, _command in (
    ("two identical heredoc commits, the second names a lane",
     VCS + " commit -F - <<EOF\nok\nEOF\n" + VCS + " commit -F - <<EOF\nN20 lands\nEOF"),
    ("two identical --amend heredoc commits, the second names a lane",
     VCS + " commit --amend -F - <<EOF\nok\nEOF\n" + VCS + " commit --amend -F - <<EOF\nN20 lands\nEOF"),
    ("a fake header inside quotes before the commit's own heredoc",
     'echo "<<EOF" ; ' + VCS + " commit -F - <<EOF\nN20\nEOF"),
    ("a lane-named heredoc commit, then a clean one",
     VCS + " commit -F - <<EOF\nN20 lands\nEOF\n" + VCS + " commit -F - <<EOF\nok\nEOF"),
):
    sh("lane-by-slug: %s denies" % _name, _command, "deny", "lane-by-slug", cwd=NOGIT,
       config=MERGECFG)
for _name, _command in (
    ("a glued base -Bmain", "gh pr create --draft -Bmain -b ok"),
    ("a glued label -lbug", "gh pr create --draft -lbug -b ok"),
    ("a glued base that holds m and then a lane number", "gh pr create --draft -BmN20 -b ok"),
    ("a glued label that holds b and then a lane number", "gh pr create --draft -lbN20 -b ok"),
    ("two identical clean heredoc commits",
     VCS + " commit -F - <<EOF\nok\nEOF\n" + VCS + " commit -F - <<EOF\nok\nEOF"),
):
    sh("lane-by-slug: %s is allowed" % _name, _command, "allow", cwd=NOGIT, config=MERGECFG)


def cite_unread_folders_case():
    """A -F message file that cannot be read is refused even when the record folders cannot be read
    either. The copy has no lint/ folder and no pointer, so the folder list is unread. The inline
    probe runs first: it must stand down and log the unread folders, so the pin proves that state.
    Fail closed: decision guard-hooks-fail-closed."""
    folder = os.path.join(ROOT, "unreadfolders")
    os.makedirs(os.path.join(folder, "cfg"), exist_ok=True)
    copy = os.path.join(folder, "hooks", "guard.py")
    os.makedirs(os.path.dirname(copy), exist_ok=True)
    copy_guard_family(os.path.dirname(copy))
    env = dict(os.environ)
    env.pop("CLAUDE_CODE_REMOTE", None)
    env["CLAUDE_CONFIG_DIR"] = os.path.join(folder, "cfg")
    env["PATH"] = GHMAIN + os.pathsep + PY_PATH

    def ask(command):
        return subprocess.run(
            [sys.executable, copy],
            input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command},
                              "cwd": NOGIT}),
            capture_output=True, text=True, env=env, timeout=60)

    probe = ask(VCS + ' commit -m "cites decisions/one-shared-record-stamp.md"')
    if "permissionDecision" in probe.stdout:
        return False, "the inline probe must stand down, got %r" % probe.stdout[:120]
    try:
        with open(os.path.join(folder, "cfg", "guard.log"), encoding="utf-8") as handle:
            logged = "cite-by-id: record folders unread" in handle.read()
    except OSError:
        logged = False
    if not logged:
        return False, "the probe must log that the record folders are unread"
    result = ask(VCS + " commit -F " + slash(ROOT) + "/no-such-message.txt")
    try:
        block = json.loads(result.stdout)["hookSpecificOutput"]
    except (ValueError, KeyError):
        return False, "an unreadable -F file must deny, got %r" % result.stdout[:120]
    if block.get("permissionDecision") != "deny" or \
            "could not be read" not in block.get("permissionDecisionReason", ""):
        return False, "want a deny that says could not be read, got %r" % result.stdout[:120]
    return True, "deny: the -F file is unread, and the record folders are unread too"


# A lane number hides from the message scan behind a wrapper the rule does not unwrap, a heredoc header read in quoted
# text, a comment or a here-string, a `<<word` inside an interpreter-fed body, or a case pattern's `)` inside an open `$(`.
# Wrapper forms: one row per wrapper walk (a bare form, a value flag, a subshell). The deep set of
# wrappers lives in the wsl section above, so this block keeps one row for each walk.
for _name, _command in (
    ("exec", "exec " + VCS + ' commit -m "fix (N20)"'),
    ("a dollar paren", "$(" + VCS + ' commit -m "fix (N20)")'),
    ("a glued subshell", "(" + VCS + ' commit -m "fix (N20)")'),
    ("a nice value flag", "nice -n 5 " + VCS + ' commit -m "fix (N20)"'),
    ("a glued subshell with a heredoc commit",
     "(" + VCS + " commit -F - <<'B'\nLane N20 lands\nB\n)"),
    ("a here-string header", "cat <<<word\n" + VCS + ' commit -m "fix (N20)"'),
    ("a quoted header", 'echo "<<EOF"\n' + VCS + ' commit -m "fix (N20)"'),
    ("a commented header", "# note <<EOF\n" + VCS + ' commit -m "fix (N20)"'),
    ("a comment opener in quotes before a heredoc commit",
     'echo "# <<EOF"\n' + VCS + " commit -F - <<'B'\nLane N20 lands\nB"),
    ("an interpreter body with a << word, then a heredoc commit",
     "python3 - <<'EOF'\nx = 1 << y\nEOF\n" + VCS + " commit -F - <<'B'\nLane N20 lands\nB"),
    ("a case pattern paren in an open dollar paren, then an interpreter body with a << word",
     "echo $(case a in (a) echo ok;; esac\npython3 - <<'EOF'\nx = 1 << y\nEOF\n"
     + VCS + " commit -F - <<'B'\nLane N20 lands\nB"),
    ("a lone apostrophe on the line before a heredoc commit",
     "echo don't\n" + VCS + " commit -F - <<'B'\nLane N20 lands\nB"),
):
    sh("guard-command-position: lane %s denies" % _name, _command, "deny", "lane-by-slug",
       cwd=NOGIT, config=MERGECFG)
# The lone-quote pair of the cite cases, with a lane named in the body: a -F - body and a -m $(cat body)
# both hide it from the same header read.
sh("guard-command-position: lane, a lone quote pair then a -F - commit naming a lane denies",
   LONE_PAIR + VCS + " commit -F - <<'EOF'\ntitle\n\nLane N20 lands\nEOF", "deny", "lane-by-slug",
   cwd=NOGIT, config=MERGECFG)
sh("guard-command-position: lane, a lone quote pair then a -m $(cat commit naming a lane denies",
   LONE_PAIR + VCS + ' commit -m "$(cat <<\'EOF\'\ntitle\n\nLane N20 lands\nEOF\n)"', "deny",
   "lane-by-slug", cwd=NOGIT, config=MERGECFG)
for _name, _command in (
    ("command", "command " + VCS + ' commit -m "fix (N20)"'),
    ("timeout", "timeout 5 " + VCS + ' commit -m "fix (N20)"'),
    ("time", "time " + VCS + ' commit -m "fix (N20)"'),
    ("a spaced subshell", "( " + VCS + ' commit -m "fix (N20)" )'),
    ("a brace group", "{ " + VCS + ' commit -m "fix (N20)"; }'),
    ("an interpreter body with a << word, then a lane -m commit",
     "python3 - <<'EOF'\nx = 1 << y\nEOF\n" + VCS + ' commit -m "fix (N20)"'),
    ("a plain heredoc body with a << word, then a heredoc lane commit",
     "cat <<'A'\nx = 1 << y\nA\n" + VCS + " commit -F - <<'B'\nLane N20 lands\nB"),
    ("an open case pattern paren in a dollar paren, then a heredoc lane commit",
     "echo $(case a in (a) echo ok;; esac\n" + VCS + " commit -F - <<'B'\nLane N20 lands\nB"),
    ("a multi-line quoted text, then a heredoc lane commit",
     'echo "first\nline"\n' + VCS + " commit -F - <<'B'\nLane N20 lands\nB"),
):
    sh("guard-command-position: lane pinned, %s denies" % _name, _command, "deny",
       "lane-by-slug", cwd=NOGIT, config=MERGECFG)
for _name, _command in (
    ("an env value flag with a clean commit", "env -u X " + VCS + ' commit -m "fix guard parsing"'),
    ("a heredoc body that names a lane", "cat <<'EOF'\n" + VCS + ' commit -m "fix (N20)"\nEOF'),
    ("a comment opener in quotes before a clean commit",
     'echo "# N20"\n' + VCS + ' commit -m "fix guard parsing"'),
    ("a glued subshell around a clean commit", "(" + VCS + ' commit -m "fix guard parsing")'),
    ("an interpreter body with a << word, then a clean heredoc commit",
     "python3 - <<'EOF'\nx = 1 << y\nEOF\n" + VCS + " commit -F - <<'B'\nclean\nB"),
):
    sh("guard-command-position: lane pinned, %s allowed" % _name, _command, "allow", cwd=NOGIT,
       config=MERGECFG)

# heredoc_offsets reads the stripped text of a plain command, which keeps no bodies, so it must not
# skip the line after a header. Without its bodies_kept flag, a commit that is the third of three
# plain heredocs is counted one header short, and reads the second body, not its own. Pinned: the
# lane is named in the third body, so the lane rule must deny. The first and second positions do
# not expose this, so they add nothing here.
sh("guard-command-position: lane in the third of three plain heredoc bodies denies",
   "cat <<'A'\nfirst body\nA\ncat <<'B'\nsecond body\nB\n" + VCS + " commit -F - <<'C'\nLane N20 lands\nC",
   "deny", "lane-by-slug", cwd=NOGIT, config=MERGECFG)

# =========================================================================== 5c-1. a message file in a scratchpad
LOG_CHECKS_EXTRA.append(("cite-by-id: a -F file that cannot be read is denied with the folders unread too",
                         cite_unread_folders_case))
