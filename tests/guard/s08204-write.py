# section 8204
FAMILY = "write"
FAMILIES["write"] = "the silent write"
# The throwaway cases below read ROOT/tmp as the system temp. Every other write case keeps its
# NOGIT, GITMAIN or PROJ cwd outside it, so each stays a real checkout whatever the system temp is.
TEMP_DIR = os.path.join(ROOT, "tmp")
#
# Rule 1c, the owner's ruling. CLAUDE.md: "Never discard a command's output." A discarding
# redirect denies on any of the six subcommands, whatever git itself would have printed. git's
# own `-q`/`--quiet` flag is judged per subcommand, against `QUIET_FLAG_SUBCOMMANDS`, MEASURED
# 2026-09-19 and 2026-09-20 in throwaway repos, never a shared checkout, all six. `push`, `merge`,
# and `rebase` deny on the flag alone: each one's success and its own no-op are both silent at
# exit 0, so the flag erases the one line that told a real write from one that moved nothing.
# `commit`, `tag`, and `cherry-pick` carve out: `commit`'s refusal and no-op both keep their own
# stream and a nonzero exit; `tag` has no `-q`/`--quiet` at all, so the flag is always a loud,
# immediate option-parsing failure (exit 129); `cherry-pick`'s short form is invalid the same way,
# and its long form still prints a full summary, conflict, or "nothing to commit" in every state.

sh("silent-write: push's own quiet flag needs no redirect at all",
   VCS + " push --quiet", "deny", "silent-write", carries="moved nothing", cwd=NOGIT)
sh("silent-write: merge's own quiet flag needs no redirect at all, MEASURED 2026-09-20",
   VCS + " merge --quiet feature/x", "deny", "silent-write", carries="moved nothing", cwd=NOGIT)
sh("silent-write: rebase's own quiet flag needs no redirect at all, MEASURED 2026-09-20",
   VCS + " rebase -q main", "deny", "silent-write", carries="moved nothing", cwd=NOGIT)
sh("silent-write: discarding a write command output denies, stdout alone",
   VCS + " commit -m x >/dev/null", "deny", "silent-write", carries="a redirect silences",
   cwd=NOGIT)
sh("silent-write: both streams discarded together",
   VCS + " commit -q -m x >/dev/null 2>&1", "deny", "silent-write", cwd=NOGIT)
# The backslash-semicolon control: `\;` is text, so this is one commit with a silenced redirect.
# A repo cwd is needed, so this uses the default.
sh("silent-write: a backslash before ; then a silenced commit redirect denies, default cwd",
   VCS + " commit -m foo\\; >/dev/null", "deny", "silent-write")
sh("silent-write: a tag silenced by a discarded stream, its own flag does not exist",
   VCS + " tag -a v1 -m x >/dev/null 2>&1", "deny", "silent-write", cwd=NOGIT)
sh("silent-write: a cherry-pick silenced by a discarded stream",
   VCS + " cherry-pick --quiet abc1234 >/dev/null 2>&1", "deny", "silent-write", cwd=NOGIT)
sh("silent-write: the Windows null device denies with no quiet flag at all",
   VCS + " commit -m x 2>NUL", "deny", "silent-write", cwd=NOGIT)
sh("silent-write: PowerShell's null variable denies with no quiet flag at all",
   VCS + " commit -m x 2>$null", "deny", "silent-write", tool="PowerShell", cwd=NOGIT)

sh("silent-write: an ordinary commit stays allowed", VCS + " commit -m x", "allow", cwd=NOGIT)
sh("silent-write: an ordinary push stays allowed", VCS + " push", "allow", cwd=NOGIT)
sh("silent-write: commit's own quiet flag is a carve-out, MEASURED 2026-09-19",
   VCS + " commit -q -m x", "allow", cwd=NOGIT)
sh("silent-write: commit's own quiet flag stays a carve-out with -a as well",
   VCS + " commit -q -a -m x", "allow", cwd=NOGIT)
sh("silent-write: tag's own quiet flag is a carve-out, MEASURED 2026-09-20 (tag has no -q at all)",
   VCS + " tag -a v1 -m x -q", "allow", cwd=NOGIT)
sh("silent-write: tag's own long quiet flag is a carve-out too, same measurement",
   VCS + " tag -a v1 -m x --quiet", "allow", cwd=NOGIT)
sh("silent-write: cherry-pick's short quiet flag is a carve-out, MEASURED 2026-09-20 "
   "(-q is not a cherry-pick option)",
   VCS + " cherry-pick -q abc1234", "allow", cwd=NOGIT)
sh("silent-write: cherry-pick's long quiet flag is a carve-out too, MEASURED 2026-09-20 "
   "(every state still prints in full)",
   VCS + " cherry-pick --quiet abc1234", "allow", cwd=NOGIT)
sh("silent-write: fetch's own quiet flag is a carve-out",
   VCS + " fetch -q", "allow", cwd=NOGIT)
sh("silent-write: fetch discarding both streams is a carve-out",
   VCS + " fetch --quiet origin main >/dev/null 2>&1", "allow", cwd=NOGIT)
sh("silent-write: an abort lands nothing, so it is carved out",
   VCS + " merge --abort 2>/dev/null", "allow", cwd=NOGIT)
sh("silent-write: the exit-code test shape rule 1b already relies on",
   VCS + " rev-parse -q --verify HEAD >/dev/null 2>&1", "allow", cwd=NOGIT)
sh("silent-write: an ordinary read discarding its output is a carve-out",
   VCS + " status --porcelain >/dev/null 2>&1", "allow", cwd=NOGIT)
sh("silent-write: 2>&1 alone duplicates a stream and discards nothing",
   VCS + " commit -m x 2>&1", "allow", cwd=NOGIT)

# Gaps found in Banchi's scripts/silent-write-guard.py.
sh("silent-write gap: pull silenced, both streams, with -C",
   VCS + " -C " + NOGIT + " pull --ff-only >/dev/null 2>&1", "deny", "silent-write", cwd=NOGIT)
sh("silent-write gap: a fetch that moves a ref (refspec) silenced",
   VCS + " fetch origin main:main >/dev/null", "deny", "silent-write", cwd=NOGIT)
sh("silent-write gap: pull's own quiet flag",
   VCS + " pull -q", "deny", "silent-write", cwd=NOGIT)
sh("silent-write gap: make merge silenced by a discarded stderr",
   "make merge PR=5 2>/dev/null", "deny", "silent-write", cwd=NOGIT)
sh("silent-write gap: gh pr merge silenced by a discarded stdout",
   "gh pr merge 5 --merge >/dev/null", "deny", "silent-write", cwd=NOGIT,
   env_path=GHMAIN + os.pathsep + PY_PATH, config=MERGECFG)
sh("silent-write gap: commit with stderr closed",
   VCS + " commit -m x 2>&-", "deny", "silent-write", cwd=NOGIT)
sh("silent-write gap: push with stdout closed",
   VCS + " push >&-", "deny", "silent-write", cwd=NOGIT)

sh("silent-write gap, allow: a dry-run fetch moves nothing",
   VCS + " fetch --dry-run >/dev/null", "allow", cwd=NOGIT)
sh("silent-write gap, allow: a dry-run fetch into a local ref moves nothing",
   VCS + " fetch origin main:main --dry-run >/dev/null", "allow", cwd=NOGIT)
sh("silent-write gap, allow: a dry-run pull moves nothing",
   VCS + " pull --dry-run >/dev/null", "allow", cwd=NOGIT)
sh("silent-write gap, allow: pull with no redirect",
   VCS + " pull", "allow", cwd=NOGIT)
sh("silent-write gap, allow: make test is not a merge",
   "make test >/dev/null", "allow", cwd=NOGIT)
sh("silent-write gap, allow: gh pr view is a read",
   "gh pr view 5 >/dev/null", "allow", cwd=NOGIT)
# HELD: the owner kept "output to a file" allowed until measured. Pinned as allowed on purpose;
# Banchi's guard refuses it. Do not flip without a measurement.
sh("silent-write gap, allow (held, unmeasured): output to a file is not discarded",
   VCS + " commit -m x > /tmp/log 2>&1", "allow", cwd=NOGIT)

# Pipes: a write whose pipe tail is silenced is silenced.
sh("silent-write pipe: cat discards the piped output",
   VCS + " commit -m x 2>&1 | cat >/dev/null", "deny", "silent-write", cwd=NOGIT)
sh("silent-write pipe: tail discards the piped output",
   VCS + " push origin b 2>&1 | tail -1 >/dev/null", "deny", "silent-write", cwd=NOGIT)
sh("silent-write pipe: wc discards the piped output",
   VCS + " commit -m x 2>&1 | wc -l >/dev/null", "deny", "silent-write", cwd=NOGIT)
sh("silent-write pipe: |& into cat discards the piped output",
   VCS + " commit -m x |& cat >/dev/null", "deny", "silent-write", cwd=NOGIT)
sh("silent-write pipe: make merge, cat discards",
   "make merge ARGS=5 2>&1 | cat >/dev/null", "deny", "silent-write", cwd=NOGIT)
sh("silent-write pipe: gh pr merge, tail discards",
   "gh pr merge 5 --squash 2>&1 | tail -1 >/dev/null", "deny", "silent-write", cwd=NOGIT,
   env_path=GHMAIN + os.pathsep + PY_PATH, config=MERGECFG)
sh("silent-write pipe: >&/dev/null shorthand",
   VCS + " commit -m x >&/dev/null", "deny", "silent-write", cwd=NOGIT)

sh("silent-write pipe, allow: the tail prints",
   VCS + " commit -m x 2>&1 | tail -5", "allow", cwd=NOGIT)
sh("silent-write pipe, allow: a read piped to a discard",
   VCS + " log | cat >/dev/null", "allow", cwd=NOGIT)
sh("silent-write pipe, allow: tee prints",
   VCS + " commit -m x | tee /tmp/l", "allow", cwd=NOGIT)

# The narrowed rule: a silenced read, and a temp-folder cwd, stay allowed; `fetch -q src:dst` writes only under refs/.


def _build_throwaway():
    """A real repository under the silent-write temp folder, made the way `git init` makes one."""
    make_repo(THROWAWAY, {"base.txt": "base\n"})


THROWAWAY = os.path.join(ROOT, "tmp", "throwaway")   # built on first use, under TEMP_DIR
TSLASH = slash(THROWAWAY)                            # the same path as a shell command names it
lazy_fixture([THROWAWAY], _build_throwaway)

# (1) Reads under a write verb. Silenced, each one still moves nothing.
sh("silent-write read: tag -ln1 silenced lists tags",
   VCS + " tag -ln1 >/dev/null", "allow", cwd=GITMAIN)
sh("silent-write read: tag -l silenced lists tags",
   VCS + " tag -l >/dev/null", "allow", cwd=GITMAIN)
sh("silent-write read: tag --list silenced lists tags",
   VCS + " tag --list >/dev/null", "allow", cwd=GITMAIN)
sh("silent-write read: cherry-pick --help silenced prints usage",
   VCS + " cherry-pick --help >/dev/null", "allow", cwd=GITMAIN)
sh("silent-write read: merge --help silenced prints usage",
   VCS + " merge --help >/dev/null", "allow", cwd=GITMAIN)
sh("silent-write read: rebase --help silenced prints usage",
   VCS + " rebase --help >/dev/null", "allow", cwd=GITMAIN)
sh("silent-write read: commit -h silenced prints usage",
   VCS + " commit -h >/dev/null", "allow", cwd=GITMAIN)
sh("silent-write read: merge-base silenced reads a base",
   VCS + " merge-base HEAD HEAD >/dev/null", "allow", cwd=GITMAIN)
sh("silent-write read: push --dry-run silenced moves nothing",
   VCS + " push --dry-run >/dev/null", "allow", cwd=GITMAIN)
sh("silent-write read: push -n, the dry-run short form, silenced moves nothing",
   VCS + " push -n >/dev/null", "allow", cwd=GITMAIN)
sh("silent-write read: the remedy's own loud form is allowed",
   VCS + " push origin zz9 2>&1 | tail -1", "allow", cwd=GITMAIN)

# (1, bypasses) A flag-shaped token that is a value, or a flag that is not the read, stays denied.
sh("silent-write read bypass: --dry-run as a message value is a real commit",
   VCS + ' commit -m "--dry-run" >/dev/null', "deny", "silent-write", cwd=GITMAIN)
sh("silent-write read bypass: -h as a message value is a real commit",
   VCS + " commit -m -h >/dev/null", "deny", "silent-write", cwd=GITMAIN)
sh("silent-write read bypass: --help inside a message is a real commit",
   VCS + ' commit -m "fix --help" >/dev/null', "deny", "silent-write", cwd=GITMAIN)
sh("silent-write read bypass: commit -n is no-verify, not a dry run",
   VCS + " commit -n -m x >/dev/null", "deny", "silent-write", cwd=GITMAIN)
sh("silent-write read bypass: tag -d deletes a tag, it does not list",
   VCS + " tag -d v1 >/dev/null", "deny", "silent-write", cwd=GITMAIN)
sh("silent-write read bypass: a silenced tag create is a write",
   VCS + " tag v1 >/dev/null", "deny", "silent-write", cwd=GITMAIN)

# (2) A silenced write whose folder is a throwaway under the temp folder is allowed.
sh("silent-write throwaway: a discarded commit in a throwaway repo",
   VCS + " commit -m x >/dev/null", "allow", cwd=THROWAWAY)
sh("silent-write throwaway: -C names the throwaway repo, and it is judged there",
   VCS + " -C " + TSLASH + " commit -m x >/dev/null", "allow", cwd=GITMAIN)
sh("silent-write throwaway: cd into the throwaway repo, and it is judged there",
   "cd " + TSLASH + " && " + VCS + " commit -m x >/dev/null", "allow", cwd=GITMAIN)
# A variable folder is read where the shell runs the commit, as its literal twin is.
sh("silent-write throwaway: a variable folder holding the throwaway repo, cd \"$R\" then a discarded commit, is allowed",
   "R=" + TSLASH + "; cd \"$R\" && " + VCS + " commit -m x >/dev/null", "allow", cwd=GITMAIN)
sh("silent-write real: a variable folder holding the real checkout, cd \"$R\" then a discarded commit, is refused",
   "R=" + slash(GITMAIN) + "; cd \"$R\" && " + VCS + " commit -m x >/dev/null", "deny", "silent-write",
   cwd=THROWAWAY)
sh("silent-write real: the literal twin, cd into the real checkout then a discarded commit, is refused",
   "cd " + slash(GITMAIN) + " && " + VCS + " commit -m x >/dev/null", "deny", "silent-write", cwd=THROWAWAY)
# A variable is read only from a plain assignment that runs in this shell. A walk that reads the throwaway
# folder in the first and third rows allows the commit; the one-quote row is denied either way. Judged from the
# real checkout, each row stays denied.
sh("silent-write [cdvar-unread]: D=<throwaway> mkdir -p, cd \"$D\", then a discarded commit from the real checkout, is refused",
   "D=" + TSLASH + " mkdir -p \"$D\"; cd \"$D\" && " + VCS + " commit -m x >/dev/null 2>&1", "deny", "silent-write",
   cwd=GITMAIN)
sh("silent-write [cdvar-unread]: R=<throwaway>, a quote, R=<real>, cd \"$R\", then a discarded commit, is refused",
   "R=" + TSLASH + "; echo \"it's\"; R=" + slash(GITMAIN) + "; cd \"$R\" && " + VCS + " commit -m x >/dev/null 2>&1",
   "deny", "silent-write", cwd=GITMAIN)
sh("silent-write [cdvar-unread]: as the row before, with a second quote after R=<real>, is refused",
   "R=" + TSLASH + "; echo \"it's\"; R=" + slash(GITMAIN) + "; echo \"it's\"; cd \"$R\" && " + VCS
   + " commit -m x >/dev/null 2>&1", "deny", "silent-write", cwd=GITMAIN)
# A `[ -d <missing> ] &&` may fail, so the assignment after it may not run and the cd target is unknown:
# the discarded commit is refused. A walk that reads the assignment as run allows the commit and fails this row.
# The row after it is its twin with the assignment first, which runs, so the throwaway repo is judged.
sh("silent-write [cdvar-unread]: [ -d <missing> ] && R=<throwaway>, cd \"$R\", then a discarded commit, is refused",
   "[ -d " + slash(os.path.join(ROOT, "no-such-folder")) + " ] && R=" + TSLASH + "; cd \"$R\" && " + VCS
   + " commit -m x >/dev/null 2>&1", "deny", "silent-write", cwd=GITMAIN)
sh("silent-write [cdvar-unread]: control: R=<throwaway> && cd \"$R\", then a discarded commit, is allowed",
   "R=" + TSLASH + " && cd \"$R\" && " + VCS + " commit -m x >/dev/null 2>&1", "allow", cwd=GITMAIN)
# A `ls <missing> &&` may fail, so the cd after it may not run and the commit's folder is unknown: the
# discarded commit is refused. A walk that reads the cd as run allows the commit; the product denies it, as
# the row expects.
sh("silent-write [cdvar-unread]: R=<throwaway>; ls <missing> && cd \"$R\", then a discarded commit from the real checkout, is refused",
   "R=" + TSLASH + "; ls " + slash(os.path.join(ROOT, "no-such-folder")) + " && cd \"$R\"; " + VCS
   + " commit -m x >/dev/null 2>&1", "deny", "silent-write", cwd=GITMAIN)
# A value that starts with a quoted ~ is not a tilde the shell expands, so it stays unknown, and an unknown folder is
# refused for a commit from the real checkout.
sh("silent-write [cdvar-unread]: control: R=\"~/tilde~dir\" quoted, cd \"$R\", then a discarded commit from the real checkout, is refused",
   "R=\"~/tilde~dir\"; cd \"$R\" && " + VCS + " commit -m x >/dev/null 2>&1", "deny", "silent-write", cwd=GITMAIN)
sh("silent-write throwaway: --git-dir names the throwaway repo, and it is judged there",
   VCS + " --git-dir=" + TSLASH + "/.git commit -m x >/dev/null", "allow", cwd=GITMAIN)
sh("silent-write throwaway: a discarded pipe tail in a throwaway repo",
   VCS + " commit -m x 2>&1 | cat >/dev/null", "allow", cwd=THROWAWAY)
sh("silent-write throwaway: a quiet push in a throwaway repo is still a write, a push is never a throwaway",
   VCS + " push -q", "deny", "silent-write", carries="moved nothing", cwd=THROWAWAY)
sh("silent-write throwaway: a quiet merge in a throwaway repo",
   VCS + " merge -q feature/x", "allow", cwd=THROWAWAY)
sh("silent-write throwaway: this session's own scratchpad",
   VCS + " commit -m x >/dev/null", "allow",
   cwd=os.path.join(ROOT, "tmp", FAKE_SESSION, "scratchpad", "notes"), session=FAKE_SESSION)
TEMP_DIR = None   # the system temp itself, for this one case
sh("silent-write throwaway: a folder under the system temp dir counts as a throwaway",
   VCS + " commit -m x >/dev/null", "allow", cwd=NOGIT)
TEMP_DIR = os.path.join(ROOT, "tmp")

# (2, kept) A real checkout outside the throwaway folder is still judged, quiet flags too.
sh("silent-write real: a discarded commit in a real checkout",
   VCS + " commit -m x >/dev/null", "deny", "silent-write", cwd=GITMAIN)
sh("silent-write real: a quiet push in a real checkout",
   VCS + " push -q", "deny", "silent-write", cwd=GITMAIN)
sh("silent-write real: a quiet merge in a real checkout",
   VCS + " merge -q feature/x", "deny", "silent-write", cwd=GITMAIN)
sh("silent-write real: a throwaway -C, then a quiet push in the real cwd",
   VCS + " -C " + TSLASH + " commit -m x >/dev/null && " + VCS + " push -q",
   "deny", "silent-write", cwd=GITMAIN)
sh("silent-write real: a real --git-dir is judged where it points, not the throwaway cwd",
   VCS + " --git-dir=" + slash(GITMAIN) + "/.git commit -m x >/dev/null", "deny", "silent-write",
   cwd=THROWAWAY)
sh("silent-write real: a real -C target is judged where it runs, not the throwaway cwd",
   VCS + " -C " + slash(GITMAIN) + " commit -m x >/dev/null", "deny", "silent-write",
   cwd=THROWAWAY)
sh("silent-write real: an if-test of a silenced merge stays denied (unmeasured; keep)",
   "if " + VCS + " merge feature/x >/dev/null 2>&1; then echo y; fi", "deny", "silent-write",
   cwd=GITMAIN)

# (3) `fetch -q src:dst` is a write only when dst is under refs/heads/ or refs/remotes/.
sh("silent-write fetch: a quiet fetch into refs/tmp moves no branch",
   VCS + " fetch -q origin main:refs/tmp/x", "allow", cwd=GITMAIN)
sh("silent-write fetch: a forced quiet fetch into refs/tmp moves no branch",
   VCS + " fetch -q origin +main:refs/tmp/x", "allow", cwd=GITMAIN)
sh("silent-write fetch: a quiet fetch into refs/heads is a write",
   VCS + " fetch -q origin main:refs/heads/x", "deny", "silent-write", cwd=GITMAIN)
sh("silent-write fetch: a quiet fetch into refs/remotes is a write",
   VCS + " fetch -q origin main:refs/remotes/origin/x", "deny", "silent-write", cwd=GITMAIN)
sh("silent-write fetch: a short dst resolves to refs/heads, so it is a write",
   VCS + " fetch -q origin main:main", "deny", "silent-write", cwd=GITMAIN)
sh("silent-write fetch: one dst under refs/heads makes the whole fetch a write",
   VCS + " fetch -q origin a:refs/tmp/a b:main", "deny", "silent-write", cwd=GITMAIN)
sh("silent-write fetch: a bare quiet fetch is a read",
   VCS + " fetch -q origin main", "allow", cwd=GITMAIN)

# (4) The refusal names its command by kind and position, the flag it hit, and one loud form.
sh("silent-write reason: a quiet push names command 3 of 4, the push, the flag, and the loud form",
   "echo a && " + VCS + " status && " + VCS + " push -q origin zz9 && echo done",
   "deny", "silent-write",
   carries=("command 3 of 4", "the push", "-q", "2>&1 | tail -1"),
   lacks=("zz9", VCS + " push -q", "echo done"), cwd=GITMAIN)
sh("silent-write reason: a discarded commit names command 2 of 2, the commit, the redirect, "
   "and the loud form",
   VCS + " add zz9 && " + VCS + " commit -m qq7 2>/dev/null", "deny", "silent-write",
   carries=("command 2 of 2", "the commit", ">/dev/null", "2>&1 | tail -1"),
   lacks=("qq7", "zz9", VCS + " commit -m"), cwd=GITMAIN)
sh("silent-write reason: a piped discard counts the pipe's stages as commands",
   VCS + " commit -m qq7 2>&1 | cat >/dev/null", "deny", "silent-write",
   carries=("command 1 of 2", "the commit"), lacks=("qq7", "cat >/dev/null"), cwd=GITMAIN)

# Scanner (building-scanner-respects-strings): a quote or a comment opener changes nothing outside
# its own quotes, and a comment hides nothing from a real write before it.
sh("silent-write scanner: a comment opener inside a message does not hide a discard",
   VCS + ' commit -m "x # y" 2>/dev/null', "deny", "silent-write", cwd=GITMAIN)
sh("silent-write scanner: block and line openers inside a message do not hide a discard",
   VCS + ' commit -m "see // and /* here" >/dev/null', "deny", "silent-write", cwd=GITMAIN)
sh("silent-write scanner: a real comment after a discard is still a discard",
   VCS + " commit -m x >/dev/null # the note", "deny", "silent-write", cwd=GITMAIN)
sh("silent-write scanner: a flag named in a comment after a discard is still a discard",
   VCS + " commit -m x >/dev/null # --dry-run", "deny", "silent-write", cwd=GITMAIN)
sh("silent-write scanner: a discard named only in a comment is not a discard",
   VCS + " commit -m x # 2>/dev/null", "allow", cwd=GITMAIN)
sh("silent-write scanner: a lone quote after a discard does not hide it",
   VCS + " commit -m x 2>/dev/null; echo don't", "deny", "silent-write", cwd=GITMAIN)
sh("silent-write scanner: a lone quote in a throwaway message",
   VCS + ' commit -m "it\'s" >/dev/null', "allow", cwd=THROWAWAY)
sh("silent-write scanner: a multi-line message in a throwaway",
   VCS + ' commit -m "line one\nline two" >/dev/null', "allow", cwd=THROWAWAY)
sh("silent-write scanner: a multi-line message, then a real discard",
   VCS + ' commit -m "line one\nline two" 2>/dev/null', "deny", "silent-write", cwd=GITMAIN)
sh("silent-write scanner: a quoted git -C in a message does not move the judgement",
   VCS + ' commit -m "git -C ' + TSLASH + ' x" >/dev/null', "deny", "silent-write", cwd=GITMAIN)
sh("silent-write scanner: a discard quoted in echo is text",
   'echo "' + VCS + ' commit -m x >/dev/null"', "allow", cwd=GITMAIN)
sh("silent-write scanner: a discard named inside a message is text",
   VCS + ' commit -m "log >/dev/null"', "allow", cwd=GITMAIN)
sh("silent-write scanner: a discard named before a space inside a message is text, with a lone quote "
   "and a comment opener in the same string",
   VCS + ' commit -m "log >/dev/null now, it\'s # here"', "allow", cwd=GITMAIN)
sh("silent-write scanner: a discard named before a space inside an echo string is text, with a lone "
   "quote and a comment opener in the same string",
   'echo "log >/dev/null now, it\'s # here"', "allow", cwd=GITMAIN)

# Each DENY is a bypass of the narrowed rule, each ALLOW a false alarm. Cases marked "hold" must keep their verdict.

# (a) The quote walk, `unquoted_at`. A `\"` inside double quotes, a `$'...'` string, and a
# PowerShell backtick escape each end a quote early or late, so a real redirect reads as text.
sh("silent-write quote walk: an escaped quote inside a message does not close it, so the redirect after it is real",
   VCS + r' commit -m "a \" b" >/dev/null', "deny", "silent-write", carries="a redirect silences",
   cwd=GITMAIN)
sh("silent-write quote walk: a $'...' string with an escaped quote closes before the redirect",
   VCS + r" commit -m $'a\'b' >/dev/null", "deny", "silent-write", carries="a redirect silences",
   cwd=GITMAIN)
sh("silent-write quote walk: a PowerShell backtick escape closes nothing, so the redirect after it is real",
   VCS + r' commit -m "x`"" >$null', "deny", "silent-write", tool="PowerShell",
   carries="a redirect silences", cwd=GITMAIN)

# (b) The throwaway cwd. Each shell below ends in a real checkout, while the guard reads a temp
# folder that the shell has already left. The walker does not parse the move: pushd, Set-Location,
# a bare cd, cd -, a subshell cd. Or a `-C` that a `--git-dir` overrides, or an env var that the
# hook expands but the shell reassigns first.
sh("silent-write throwaway bypass: pushd moves the shell out of the temp folder into a real checkout",
   "pushd " + slash(GITMAIN) + " && " + VCS + " commit -m x >/dev/null",
   "deny", "silent-write", carries="a redirect silences", cwd=THROWAWAY)
sh("silent-write throwaway bypass: Set-Location moves a PowerShell shell out of the temp folder",
   "Set-Location " + slash(GITMAIN) + "; " + VCS + " commit -m x >$null",
   "deny", "silent-write", tool="PowerShell", carries="a redirect silences", cwd=THROWAWAY)
sh("silent-write throwaway bypass: a bare cd leaves the temp folder for the home folder",
   "cd " + TSLASH + " && cd && " + VCS + " commit -m x >/dev/null",
   "deny", "silent-write", carries="a redirect silences", cwd=GITMAIN)
sh("silent-write throwaway bypass: cd - returns the shell to a real checkout",
   "cd " + TSLASH + " && cd - && " + VCS + " commit -m x >/dev/null",
   "deny", "silent-write", carries="a redirect silences", cwd=GITMAIN)
sh("silent-write throwaway bypass: a cd inside a subshell does not carry out of it",
   "(cd " + TSLASH + " && true); " + VCS + " commit -m x >/dev/null",
   "deny", "silent-write", carries="a redirect silences", cwd=GITMAIN)
sh("silent-write throwaway bypass: a --git-dir after -C names the real repository",
   VCS + " -C " + TSLASH + " --git-dir=" + slash(GITMAIN) + "/.git commit -m x >/dev/null",
   "deny", "silent-write", carries="a redirect silences", cwd=GITMAIN)
sh("silent-write throwaway bypass: an env var reassigned to . names the real cwd, not the temp folder",
   "TEMP=. && " + VCS + ' -C "$TEMP" commit -m x >/dev/null',
   "deny", "silent-write", carries="a redirect silences", cwd=GITMAIN)
sh("silent-write throwaway hold: an env var that expands into the temp folder, then .. out of it, "
   "is judged where it lands",
   VCS + ' -C "$TEMP/../' + os.path.basename(GITMAIN) + '" commit -m x >/dev/null',
   "deny", "silent-write", carries="a redirect silences", cwd=GITMAIN)
sh("silent-write throwaway push: a discarded push from a temp clone to a real remote is a write",
   VCS + " push " + slash(GITMAIN) + " feat >/dev/null", "deny", "silent-write",
   carries="a redirect silences", cwd=THROWAWAY)

# (c) VALUE_FLAGS gaps. A value flag takes the next token as its value, so a dry-run word there is
# text, and the write is real.
sh("silent-write read bypass: push -o takes -n as its push option value, so the push is real",
   VCS + " push -o -n origin feat >/dev/null", "deny", "silent-write",
   carries="a redirect silences", cwd=GITMAIN)
sh("silent-write read bypass: push --push-option takes -n as its value, so the push is real",
   VCS + " push --push-option -n origin feat >/dev/null", "deny", "silent-write",
   carries="a redirect silences", cwd=GITMAIN)
sh("silent-write read bypass: commit --trailer takes -h as its value, so the commit is real",
   VCS + " commit --trailer -h -m x >/dev/null", "deny", "silent-write",
   carries="a redirect silences", cwd=GITMAIN)

# (d) A Git Bash /tmp path names the temp folder, so a silenced write there is a throwaway. Windows
# only: on POSIX, /tmp is a real folder, and the fixture temp folder is not /tmp.
if os.name == "nt":
    sh("silent-write false alarm: git -C /tmp under the Windows temp folder is a throwaway",
       VCS + " -C /tmp/throwaway commit -m x >/dev/null", "allow", cwd=GITMAIN)

# (e) The remedy names the program that refused and the loud form. It never reduces to the bare verb,
# which a re-run would turn into a different write, and it never names the forbidden target.
sh("silent-write remedy: a silenced push to main gives the loud form, not the bare verb, nor the target",
   VCS + " push origin main:main >/dev/null", "deny", "silent-write",
   carries="2>&1 | tail -1", lacks=(VCS + " push 2>&1", "main:main"), cwd=GITMAIN)
sh("silent-write remedy: a silenced make merge names make merge, not the git merge it rewrites to",
   "make merge PR=5 2>/dev/null", "deny", "silent-write", carries="make merge",
   lacks=VCS + " merge 2>&1", cwd=NOGIT)
sh("silent-write remedy: a silenced gh pr merge names gh pr merge, not the git merge it rewrites to",
   "gh pr merge 5 --merge >/dev/null", "deny", "silent-write", carries="gh pr merge",
   lacks=VCS + " merge 2>&1", cwd=NOGIT)

# (f) Hold: a single command is command 1 of 1, pinned so the command count cannot drift.
sh("silent-write command: a single silenced commit says command 1 of 1",
   VCS + " commit -m x 2>/dev/null", "deny", "silent-write", carries="command 1 of 1",
   lacks="command 1 of 2", cwd=GITMAIN)

# (g) Scanner cases for the quote walk: a multi-line message that names a discard as text, then a
# backtick inside a quoted message.
sh("silent-write scanner: a multi-line message that names a discard as text, then a real discard after it",
   VCS + ' commit -m "line one\n>/dev/null here" 2>/dev/null', "deny", "silent-write", cwd=GITMAIN)
sh("silent-write scanner: a backtick inside a message does not hide a real discard after it",
   VCS + ' commit -m "`x`" >/dev/null', "deny", "silent-write", carries="a redirect silences",
   cwd=GITMAIN)

# Each DENY below is a bypass, and each ALLOW is a false alarm. The LIMIT cases
# at the end pin what the guard does not see, labelled as limits, so the gap stays on record.

# (a) The quote walk, a doubled backslash outside quotes. Two backslashes are one escaped backslash,
# and the quote after them opens. The walk must not read the pair as an escaped quote.
sh("silent-write quote walk: a doubled backslash before a single quote is one escape, so the quote opens and the redirect after it is real",
   VCS + r" commit -m \\'a b' >/dev/null", "deny", "silent-write", carries="a redirect silences",
   cwd=GITMAIN)
sh("silent-write quote walk: a doubled backslash before a double quote is one escape, so the quote opens and the redirect after it is real",
   VCS + r' commit -m \\"a b" >/dev/null', "deny", "silent-write", carries="a redirect silences",
   cwd=GITMAIN)
# Scanner cases for the same walk (building-scanner-respects-strings): a comment opener inside the
# quote, a message that spans lines, and a lone quote in text after the discard.
sh("silent-write scanner: a comment opener inside a doubled-backslash message does not hide the redirect",
   VCS + r' commit -m \\"x # y" >/dev/null', "deny", "silent-write", carries="a redirect silences",
   cwd=GITMAIN)
sh("silent-write scanner: a doubled backslash before a quote in a multi-line message, then a real discard",
   VCS + " commit -m \\\\'line one\nline two' >/dev/null", "deny", "silent-write",
   carries="a redirect silences", cwd=GITMAIN)
# HOLD: the walk keeps a lone quote in text from hiding a discard.
sh("silent-write scanner: a lone quote after a doubled backslash does not hide a discard",
   VCS + r" commit -m \\x >/dev/null; echo don't", "deny", "silent-write",
   carries="a redirect silences", cwd=GITMAIN)

# (b) The throwaway cwd, for the orchestrator's own writes. Only a local git write can be a throwaway.
# A pull request merge and a make target are never throwaway, however silent and however temp the cwd.
sh("silent-write throwaway bypass: gh pr merge silenced from a temp cwd is still a merge",
   "gh pr merge 5 -R o/r >/dev/null", "deny", "silent-write", carries="gh pr merge",
   env_path=GHMAIN + os.pathsep + PY_PATH, config=MERGECFG, cwd=THROWAWAY)
sh("silent-write throwaway bypass: gh pr merge silenced after a cd into the temp folder is still a merge",
   "cd " + TSLASH + " && gh pr merge 5 -R o/r >/dev/null", "deny", "silent-write",
   carries="gh pr merge", env_path=GHMAIN + os.pathsep + PY_PATH, config=MERGECFG, cwd=GITMAIN)
sh("silent-write throwaway bypass: make merge silenced from a temp cwd is still a merge",
   "make merge >/dev/null", "deny", "silent-write", carries="make merge", cwd=THROWAWAY)

# (c) A cd on the left of a pipe runs in a subshell. The shell that runs the commit never left
# the real checkout, so the real checkout judges it.
sh("silent-write throwaway bypass: a cd on the left of a pipe runs in a subshell, so the real cwd takes the commit",
   "cd " + TSLASH + " | cat; " + VCS + " commit -m x >/dev/null",
   "deny", "silent-write", carries="a redirect silences", cwd=GITMAIN)

# (d) VALUE_FLAGS. A value flag takes the next token whatever it is, so -h or -n in that
# slot is a value, never help or dry-run. The write is real, so the discard denies.
sh("silent-write read bypass: commit -- ends the options, so -h after it is a pathspec, not help",
   VCS + " commit -s -- -h >/dev/null", "deny", "silent-write", carries="a redirect silences",
   cwd=GITMAIN)
sh("silent-write read bypass: rebase --exec takes -h as its command, so the rebase is real",
   VCS + " rebase --exec -h >/dev/null", "deny", "silent-write", carries="a redirect silences",
   cwd=GITMAIN)
sh("silent-write read bypass: commit --pathspec-from-file takes -h as its file, so the commit is real",
   VCS + " commit --pathspec-from-file -h >/dev/null", "deny", "silent-write",
   carries="a redirect silences", cwd=GITMAIN)
sh("silent-write read bypass: push --receive-pack takes -n as its program, so the push is real",
   VCS + " push --receive-pack -n origin feat >/dev/null", "deny", "silent-write",
   carries="a redirect silences", cwd=GITMAIN)

# (e) False alarms. A flag that takes no value, or a value glued to its flag, leaves the next token
# a flag. The dry run is then a dry run, and the silenced command moves nothing.
sh("silent-write false alarm: push -u takes no value, so --dry-run after it is a dry run",
   VCS + " push -u --dry-run origin main >/dev/null", "allow", cwd=GITMAIN)
sh("silent-write false alarm: commit -s takes no value, so --dry-run after it is a dry run",
   VCS + " commit -s --dry-run >/dev/null", "allow", cwd=GITMAIN)
sh("silent-write false alarm: commit -mfoo glues its value, so --dry-run after it is a dry run",
   VCS + " commit -mfoo --dry-run >/dev/null", "allow", cwd=GITMAIN)

# The five cases below are PowerShell escapes and openers in the silent write. They sit in the ROOT/tmp
# section, so their NOGIT cwd (under ROOT, outside ROOT/tmp) is not a throwaway. Under the system temp,
# the throwaway allow decides them, so the case would not test the quote walk.
# A PowerShell escape or opener that quote_advance does not read (a backtick outside quotes, a `<# #>`
# comment, a here-string) flips the quote state, so the silenced commit after it reads as quoted text.
# The lone apostrophe must keep denying.
sh("silent-write: a backtick-escaped quote in PowerShell, then a silenced commit, denies",
   "echo `\"; " + VCS + " commit -m x >/dev/null", "deny", "silent-write",
   carries="a redirect silences", tool="PowerShell", cwd=NOGIT)
sh("silent-write: a PowerShell block comment with a quote, then a silenced commit, denies",
   '<# " #>; ' + VCS + " commit -m x >/dev/null", "deny", "silent-write",
   carries="a redirect silences", tool="PowerShell", cwd=NOGIT)
sh("silent-write: a PowerShell comment opener inside a string, then a silenced commit, denies",
   'echo "<#"; ' + VCS + " commit -m x >/dev/null", "deny", "silent-write",
   carries="a redirect silences", tool="PowerShell", cwd=NOGIT)
sh("silent-write: a PowerShell here-string with an odd quote, then a silenced commit, denies",
   '@"\nsay "hi\n"@\n' + VCS + " commit -m x >/dev/null", "deny", "silent-write",
   carries="a redirect silences", tool="PowerShell", cwd=NOGIT)
sh("silent-write: a lone apostrophe in PowerShell text, then a silenced commit, still denies",
   "echo don't; " + VCS + " commit -m x >/dev/null", "deny", "silent-write",
   carries="a redirect silences", tool="PowerShell", cwd=NOGIT)

# (f) Owner ruling 2026-10-15: these two deny.
# A quote inside $( ) in a message, and a --git-dir under the temp folder, each still hide a
# discarded commit or merge in a real checkout.
sh("silent-write: a quote inside $( ) in a message does not hide a discarded commit, denies",
   VCS + r''' commit -m "$(printf '"')" >/dev/null''', "deny", "silent-write",
   carries="a redirect silences", cwd=GITMAIN)
sh("silent-write: the PowerShell tool, a quote inside $( ) in a message does not hide a discarded commit, denies",
   VCS + r''' commit -m "$(printf '"')" >/dev/null''', "deny", "silent-write",
   carries="a redirect silences", tool="PowerShell", cwd=GITMAIN)
# Windows only: a Git Bash /tmp path names the temp folder, so the case needs it.
if os.name == "nt":
    sh("silent-write: a --git-dir under the temp folder does not hide a discarded merge in a real checkout, denies",
       VCS + " --git-dir=/tmp/x/.git merge foo >/dev/null", "deny", "silent-write",
       carries="a redirect silences", cwd=GITMAIN)

# A here-string opener mid-word must not hide the discarded commit after it.
sh("silent-write: a PowerShell here-string opener mid-word, then a silenced commit, denies",
   "echo foo@'\nx'; " + VCS + " commit -m x >/dev/null\n'@'", "deny", "silent-write",
   carries="a redirect silences", tool="PowerShell", cwd=NOGIT)

TEMP_DIR = None   # back to the system temp for the sections below


# =========================================================================== 3. push and delete
