# section 43000
FAMILY = "fetch-head"  # FETCH_HEAD_RULE, the rule id the refusal names, is set in this section
FETCH_HEAD_RULE = "fetch-head-read"

# FETCH_HEAD is one file per checkout, and every fetch in that checkout rewrites it, so a read of it can
# return another fetch's ref. The refusal's remedy is the fetch into a named remote-tracking ref, then a
# read of that ref. The check is text: the fetch is pinned exactly, and the read by any of its git verbs.
REMEDY_FETCH = "git fetch origin <b>:refs/remotes/origin/<b>"
REMEDY_READ = ("git show origin/<b>", "git log origin/<b>", "git diff origin/<b>", "git rev-parse origin/<b>",
               "git cat-file -p origin/<b>")


def fetch_head_refused(name, command, **kw):
    """One case: `command` reads FETCH_HEAD with no git fetch of the same command before the read, so it is denied.
    The refusal names the fetch into origin/<b> and a read of origin/<b>, and never names FETCH_HEAD."""
    sh(name, command, "deny", FETCH_HEAD_RULE, carries=(REMEDY_FETCH, REMEDY_READ), lacks="FETCH_HEAD", **kw)


# A read of FETCH_HEAD with no fetch in its own command: each form is denied. A fetch in an earlier call is not
# in this command, so each read alone denies.
for _cmd in (
    VCS + " show FETCH_HEAD:p.txt",
    VCS + " show FETCH_HEAD",
    VCS + " log FETCH_HEAD",
    VCS + " log -1 --format=%B FETCH_HEAD",
    VCS + " rev-parse FETCH_HEAD",
    VCS + " rev-parse --verify FETCH_HEAD^{commit}",
    VCS + " diff FETCH_HEAD",
    VCS + " diff HEAD...FETCH_HEAD -- hooks",
    VCS + " cat-file -p FETCH_HEAD:hooks/guard.py",
    VCS + " merge --ff-only FETCH_HEAD",
    VCS + ' log -1 "FETCH_HEAD"',
    VCS + " -C " + slash(GITWT) + " show FETCH_HEAD:p.txt",
    VCS + " log -1 --format=%B FETCH_HEAD | head -5",
    "SHA=$(" + VCS + " rev-parse FETCH_HEAD)",
    "cd " + slash(GITWT) + " && " + VCS + " show FETCH_HEAD:p.txt",
    VCS + " status && " + VCS + " show FETCH_HEAD:p.txt",
    "echo x; " + VCS + " log FETCH_HEAD",
):
    fetch_head_refused("fetch-head read, no fetch in its command: %s" % _cmd.replace(slash(GITWT), "<lane>")[:44],
                       _cmd, cwd=GITWT)

# The fetch must come before the read. One that follows it does not clear the read, and a fetch named only in
# quotes is no fetch. A long chain with its fetch last is the full-size form of the first.
fetch_head_refused("fetch-head read, a fetch after the read in the same command does not clear it, denies",
                   VCS + " show FETCH_HEAD:p.txt && " + VCS + " fetch -q origin feat:refs/remotes/origin/feat",
                   cwd=GITWT)
fetch_head_refused("fetch-head read, a fetch named only inside quotes is no fetch, denies",
                   'echo "' + VCS + ' fetch -q origin feat:refs/remotes/origin/feat" && ' + VCS
                   + " show FETCH_HEAD:p.txt", cwd=GITWT)
fetch_head_refused("fetch-head read, a long chain whose fetch comes after the read, denies",
                   " && ".join([VCS + " status", VCS + " log -1", VCS + " diff --stat",
                                VCS + " show FETCH_HEAD:p.txt",
                                VCS + " fetch -q origin feat:refs/remotes/origin/feat"]), cwd=GITWT)

# Scanner cases: a comment opener, a lone quote or a newline inside text must not hide the read after it
# (building-scanner-respects-strings).
fetch_head_refused("fetch-head read, a hash opener inside quotes does not hide the read, denies",
                   'echo "# note"; ' + VCS + " log FETCH_HEAD", cwd=GITWT)
fetch_head_refused("fetch-head read, a double slash inside quotes does not hide the read, denies",
                   'echo "// note"; ' + VCS + " log FETCH_HEAD", cwd=GITWT)
fetch_head_refused("fetch-head read, a slash-star inside quotes does not hide the read, denies",
                   'echo "/* note"; ' + VCS + " log FETCH_HEAD", cwd=GITWT)
fetch_head_refused("fetch-head read, a lone apostrophe inside double quotes does not hide the read, denies",
                   "echo \"Don't\"; " + VCS + " log FETCH_HEAD", cwd=GITWT)
fetch_head_refused("fetch-head read, a lone apostrophe in unquoted text does not hide the read, denies",
                   "echo don't; " + VCS + " log FETCH_HEAD", cwd=GITWT)
fetch_head_refused("fetch-head read, a newline inside a quoted string does not hide a read on the next line, denies",
                   "echo \"first line\nsecond line\"\n" + VCS + " log FETCH_HEAD", cwd=GITWT)

# A shell that runs a script given as its argument runs that script's reads too: the inner script is walked.
fetch_head_refused("fetch-head read in a bash -c script, the inner script is walked, denies",
                   'bash -c "' + VCS + ' show FETCH_HEAD"', cwd=GITWT)

# Allowed: a read of origin/<b>, which is the remedy's own read. A fetch alone, and a fetch earlier in the same
# command, with the read after it of FETCH_HEAD or of origin/<b>. A long chain with its fetch first is the
# full-size form.
for _cmd in (
    VCS + " show origin/feat:p.txt",
    VCS + " log origin/feat --format=%s",
    VCS + " diff origin/main...HEAD",
    VCS + " rev-parse origin/feat",
    VCS + " cat-file -p origin/feat:p.txt",
    VCS + " log -1 --format=%B origin/feat",
):
    sh("fetch-head allowed, a read of origin/<b>: %s" % _cmd[:44], _cmd, "allow", cwd=GITWT)
for _name, _cmd in (
    ("a fetch alone", VCS + " fetch -q origin feat:refs/remotes/origin/feat"),
    ("a fetch of all refs alone", VCS + " fetch -q origin"),
    ("a fetch then a read of origin/<b>",
     VCS + " fetch -q origin feat:refs/remotes/origin/feat && " + VCS + " show origin/feat:p.txt"),
    ("a fetch then a read of FETCH_HEAD, joined by &&",
     VCS + " fetch -q origin feat:refs/remotes/origin/feat && " + VCS + " show FETCH_HEAD:p.txt"),
    ("a fetch then a read of FETCH_HEAD, joined by ;",
     VCS + " fetch -q origin feat:refs/remotes/origin/feat; " + VCS + " log FETCH_HEAD --format=%s"),
    ("a cd, a fetch, then a read of FETCH_HEAD",
     "cd " + slash(GITWT) + " && " + VCS + " fetch -q origin feat:refs/remotes/origin/feat && "
     + VCS + " rev-parse FETCH_HEAD"),
    ("a long chain whose fetch comes before the read",
     " && ".join([VCS + " fetch -q origin feat:refs/remotes/origin/feat", VCS + " status", VCS + " log -1",
                  VCS + " diff --stat", VCS + " show FETCH_HEAD:p.txt"])),
    ("a fetch, then a read of FETCH_HEAD in a $( ) text of the same command",
     VCS + " fetch x && SHA=$(" + VCS + " rev-parse FETCH_HEAD)"),
):
    sh("fetch-head allowed, %s" % _name, _cmd, "allow", cwd=GITWT)

# Allowed: FETCH_HEAD named where nothing reads it: an echo, a grep over files, a grep pattern for a git log or a
# piped grep of a read of origin, a commit message, and quoted text that names a read. The empty command is the
# empty state of the same check.
for _name, _cmd, _dir in (
    ("an echo of the bare name", "echo FETCH_HEAD", NOGIT),
    ("an echo of the quoted name", 'echo "FETCH_HEAD"', NOGIT),
    ("a grep over a file", "grep FETCH_HEAD file.txt", NOGIT),
    ("a grep over folders", "grep -rn FETCH_HEAD hooks tests", NOGIT),
    ("a quoted echo of a read", 'echo "git show FETCH_HEAD:p"', NOGIT),
    ("a quoted hash-opener echo of a read", 'echo "# git show FETCH_HEAD:p"', NOGIT),
    ("a quoted two-line echo that names a read", "echo \"first line\ngit log FETCH_HEAD\"", NOGIT),
    ("a quoted apostrophe that names the name", "echo \"Don't read FETCH_HEAD\"", NOGIT),
    ("a commit message that names the name", VCS + ' commit -m "fix: FETCH_HEAD race"', NOGIT),
    ("a commit message of the bare name, as the value of -m", VCS + " commit -m FETCH_HEAD", NOGIT),
    ("a log grep for the bare name, as the value of --grep", VCS + " log --grep FETCH_HEAD", GITWT),
    ("a log grep for the name, over origin", VCS + " log origin/feat --grep=FETCH_HEAD --oneline", GITWT),
    ("a read of origin piped to grep for the name",
     VCS + " show origin/feat:hooks/guard.py | grep FETCH_HEAD", GITWT),
    ("a diff of origin piped to grep for the name",
     VCS + " diff origin/main...HEAD -- hooks | grep FETCH_HEAD", GITWT),
    ("an empty command", "", NOGIT),
):
    sh("fetch-head allowed, %s" % _name, _cmd, "allow", cwd=_dir)
