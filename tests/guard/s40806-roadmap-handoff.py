# section 40806
FAMILY = "merge"  # rule roadmap-one-writer's lane handoff allow: GUARD_FAMILY=merge runs these cases
#
# The lane handoff allow of rule roadmap-one-writer (decision session-tiers). A lane session pushes its handoff,
# roadmap/outbox/<slug>-handoff.md, to the record branch. That push is allowed only when every path it adds or
# changes against the record branch's origin tip is that one file, and its slug is the lane's own: a cs-step tag of
# the lane's own record, or the checkout's branch with a leading lane/ removed. Triage keeps its full allow. Every
# other push to the record branch is refused, as today.
#
# The changed paths are read with git against refs/remotes/origin/roadmap, the tip the guard reads with no fetch. A
# local roadmap branch is never the base, so a lane cut from one carries that branch's commits into the push, and the
# push is refused. The range is judged commit by commit: a merge commit or a root commit hides its paths from diff-tree,
# so either one in the range is refused. Most lane branches are cut from the tip, so their handoff is the only change.
# Section 40806 runs after the LOG_CHECKS join at section 40805, so its log check joins LOG_CHECKS directly.

HANDOFF_DIR = os.path.join(ROOT, "handoff")
LONG_SLUG = "lane-handoff-" + "x" * 19  # 32 characters, the slug limit of a record
HANDOFF_PUSH = VCS + " push origin HEAD:roadmap"
LANE = LANE_TRANSCRIPT
TRIAGE = TRIAGE_TRANSCRIPT
TIP_FILES = {
    "base.txt": "base\n",
    "roadmap/data/steps/base.json": "{}\n",
    "roadmap/outbox/outbox-a-handoff.md": "a old\n",  # the lane's own handoff, already on the record
    "roadmap/outbox/outbox-b-handoff.md": "b old\n",  # another lane's handoff
}


def _handoff_commit(where, ops):
    """Apply one commit's ops in `where` and commit them. An op is ("put", path, text), ("rm", path) or
    ("mv", old, new)."""
    for op in ops:
        if op[0] == "put":
            write(os.path.join(where, op[1]), op[2])
        elif op[0] == "rm":
            os.remove(os.path.join(where, op[1]))
        else:
            os.makedirs(os.path.dirname(os.path.join(where, op[2])), exist_ok=True)
            os.rename(os.path.join(where, op[1]), os.path.join(where, op[2]))
    run_vcs(where, "add", "-A")
    done = run_vcs(where, *IDENT, "commit", "-q", "-m", "handoff case")
    if done.returncode != 0:
        sys.exit("fixture setup failed in _apply: the commit in %r failed. stderr: %s" % (where, done.stderr.strip()))


def _handoff_repo(name, branch, commits=(), local_roadmap=False, broken_tip=False, no_tip=False, detached=False,
                  orphan_root=False, merged_tip=False):
    """A checkout on `branch`, cut from the record tip. origin/roadmap is that tip, a ref the guard reads with no fetch.
    `commits` is a list of commits, each a list of ops. local_roadmap adds a local roadmap branch one commit past the
    tip, and cuts the lane from it, so origin/roadmap..HEAD carries that unpushed commit. broken_tip points
    origin/roadmap at a commit the object store lacks, so the changed paths cannot be read. no_tip leaves
    origin/roadmap unset, as a single-branch clone does. detached leaves HEAD on no branch after the commits.
    orphan_root starts the lane from a root commit that adds docs/root.md, so the range holds a root commit. merged_tip
    moves origin/roadmap one commit past the tip after the commits, then merges that newer tip into the lane, so the
    range holds a merge commit. Built on first use."""
    where = os.path.join(HANDOFF_DIR, name)

    def build():
        make_repo(where, TIP_FILES)
        if run_vcs(where, "remote", "add", "origin", PUSHREMOTE).returncode != 0:
            sys.exit("fixture setup failed in _handoff_repo: origin add in %r failed" % where)
        if not no_tip and run_vcs(where, "update-ref", "refs/remotes/origin/roadmap", "HEAD").returncode != 0:
            sys.exit("fixture setup failed in _handoff_repo: the origin tip in %r failed" % where)
        if local_roadmap:
            if run_vcs(where, "checkout", "-q", "-b", "roadmap").returncode != 0:
                sys.exit("fixture setup failed in _handoff_repo: local roadmap in %r failed" % where)
            _handoff_commit(where, [("put", "docs/extra.md", "local only\n")])
        if orphan_root:
            if run_vcs(where, "checkout", "-q", "--orphan", branch).returncode != 0:
                sys.exit("fixture setup failed in _handoff_repo: orphan branch %r in %r failed" % (branch, where))
            _handoff_commit(where, [("put", "docs/root.md", "root\n")])
        elif run_vcs(where, "checkout", "-q", "-b", branch).returncode != 0:
            sys.exit("fixture setup failed in _handoff_repo: branch %r in %r failed" % (branch, where))
        for ops in commits:
            _handoff_commit(where, ops)
        if merged_tip:
            if run_vcs(where, "checkout", "-q", "-b", "newer-tip", "refs/remotes/origin/roadmap").returncode != 0:
                sys.exit("fixture setup failed in _handoff_repo: newer tip in %r failed" % where)
            _handoff_commit(where, [("put", "roadmap/data/steps/newer.json", "{}\n")])
            if run_vcs(where, "update-ref", "refs/remotes/origin/roadmap", "HEAD").returncode != 0:
                sys.exit("fixture setup failed in _handoff_repo: the moved origin tip in %r failed" % where)
            if run_vcs(where, "checkout", "-q", branch).returncode != 0:
                sys.exit("fixture setup failed in _handoff_repo: back to branch %r in %r failed" % (branch, where))
            merged = run_vcs(where, *IDENT, "merge", "--no-ff", "-m", "merge the newer record tip", "newer-tip")
            if merged.returncode != 0:
                sys.exit("fixture setup failed in _handoff_repo: the merge in %r failed: %s"
                         % (where, merged.stderr.strip()))
        if detached and run_vcs(where, "checkout", "-q", "--detach").returncode != 0:
            sys.exit("fixture setup failed in _handoff_repo: detaching %r failed" % where)
        head = run_vcs(where, "symbolic-ref", "-q", "HEAD").stdout.strip()
        if head != ("" if detached else "refs/heads/" + branch):
            sys.exit("fixture setup failed in _handoff_repo: %r sits on %r, want %r" % (where, head, branch))
        if broken_tip:
            write(os.path.join(where, ".git", "refs", "remotes", "origin", "roadmap"), "1" * 40 + "\n")
        reads = run_vcs(where, "diff", "--name-status", "refs/remotes/origin/roadmap", "HEAD")
        unread = broken_tip or no_tip
        if unread and reads.returncode == 0:
            sys.exit("fixture setup failed in _handoff_repo: the tip-less checkout %r still reads" % where)
        if not unread and reads.returncode != 0:
            sys.exit("fixture setup failed in _handoff_repo: the changed paths in %r do not read: %s"
                     % (where, reads.stderr.strip()))
    lazy_fixture([where], build)
    return where


HANDOFF_REPO = {
    # The lane's own handoff, already on the record, changed in place: the allow.
    "modify-own": _handoff_repo("modify-own", "lane/outbox-a",
                                [[("put", "roadmap/outbox/outbox-a-handoff.md", "a new\n")]]),
    "add-own": _handoff_repo("add-own", "lane/outbox-c",
                             [[("put", "roadmap/outbox/outbox-c-handoff.md", "c new\n")]]),
    "add-e": _handoff_repo("add-e", "lane/outbox-a",
                           [[("put", "roadmap/outbox/outbox-e-handoff.md", "e new\n")]]),
    "add-other": _handoff_repo("add-other", "lane/outbox-a",
                               [[("put", "roadmap/outbox/outbox-d-handoff.md", "d new\n")]]),
    "two-files": _handoff_repo("two-files", "lane/outbox-a",
                               [[("put", "roadmap/outbox/outbox-a-handoff.md", "a new\n"),
                                 ("put", "roadmap/outbox/outbox-a-extra.md", "x\n")]]),
    "under-roadmap": _handoff_repo("under-roadmap", "lane/outbox-a",
                                   [[("put", "roadmap/data/steps/outbox-a.json", "{}\n")]]),
    "outside-roadmap": _handoff_repo("outside-roadmap", "lane/outbox-a",
                                     [[("put", "docs/outbox-a-handoff.md", "a\n")]]),
    "delete-own": _handoff_repo("delete-own", "lane/outbox-a",
                                [[("rm", "roadmap/outbox/outbox-a-handoff.md")]]),
    "delete-other": _handoff_repo("delete-other", "lane/outbox-a",
                                  [[("rm", "roadmap/outbox/outbox-b-handoff.md")]]),
    "rename-into-own": _handoff_repo("rename-into-own", "lane/outbox-c",
                                     [[("mv", "roadmap/data/steps/base.json", "roadmap/outbox/outbox-c-handoff.md")]]),
    "slash-branch": _handoff_repo("slash-branch", "lane/a/b",
                                  [[("put", "roadmap/outbox/a/b-handoff.md", "ab\n")]]),
    "slash-tag": _handoff_repo("slash-tag", "lane/outbox-a",
                               [[("put", "roadmap/outbox/a/b-handoff.md", "ab\n")]]),
    "dotdot-tag": _handoff_repo("dotdot-tag", "lane/outbox-a",
                                [[("put", "roadmap/outbox/..-handoff.md", "dd\n")]]),
    "empty-tag": _handoff_repo("empty-tag", "lane/outbox-a",
                               [[("put", "roadmap/outbox/-handoff.md", "e\n")]]),
    "long-slug": _handoff_repo("long-slug", "lane/" + LONG_SLUG,
                               [[("put", "roadmap/outbox/%s-handoff.md" % LONG_SLUG, "l\n")]]),
    # The empty state: a push whose commit changes no path.
    "no-diff": _handoff_repo("no-diff", "lane/outbox-a"),
    # The last commit is the handoff alone; the commit before it changes a file outside it.
    "earlier-commit": _handoff_repo("earlier-commit", "lane/outbox-a",
                                    [[("put", "docs/notes.md", "n\n")],
                                     [("put", "roadmap/outbox/outbox-a-handoff.md", "a new\n")]]),
    "local-roadmap": _handoff_repo("local-roadmap", "lane/outbox-a",
                                   [[("put", "roadmap/outbox/outbox-a-handoff.md", "a new\n")]],
                                   local_roadmap=True),
    # The lane merged a newer record tip into its branch: the range holds the merge, whose paths diff-tree hides.
    "merged-tip": _handoff_repo("merged-tip", "lane/outbox-a",
                                [[("put", "roadmap/outbox/outbox-a-handoff.md", "a new\n")]], merged_tip=True),
    # The lane starts from a root commit: the range holds it, and diff-tree hides a root commit's paths.
    "root-commit": _handoff_repo("root-commit", "lane/outbox-a",
                                 [[("put", "roadmap/outbox/outbox-a-handoff.md", "a new\n")]], orphan_root=True),
    "broken-tip": _handoff_repo("broken-tip", "lane/outbox-a",
                                [[("put", "roadmap/outbox/outbox-a-handoff.md", "a new\n")]], broken_tip=True),
    # An earlier commit adds a file outside the handoff and a later one removes it: the tree diff against the tip
    # shows the handoff alone, so only the commits in the range show the file.
    "history-gap": _handoff_repo("history-gap", "lane/outbox-a",
                                  [[("put", "docs/secret.md", "s\n")],
                                   [("rm", "docs/secret.md")],
                                   [("put", "roadmap/outbox/outbox-a-handoff.md", "a new\n")]]),
    # The own handoff pushed from a detached HEAD: the cs-step tag names the slug, and no branch does.
    "detached-own": _handoff_repo("detached-own", "lane/outbox-a",
                                  [[("put", "roadmap/outbox/outbox-a-handoff.md", "a new\n")]], detached=True),
    # A single-branch clone: origin has no roadmap ref to read the changed paths against.
    "no-tip": _handoff_repo("no-tip", "lane/outbox-a",
                            [[("put", "roadmap/outbox/outbox-a-handoff.md", "a new\n")]], no_tip=True),
}

# The lane records these cases name. A record's slug comes from its own cs-step tags, so each tag set is its own record.
HAND_LINES = {
    "hand-two": role_call("g1", ["cs-build:lane", "cs-step:outbox-a", "cs-step:outbox-e", "cs-repo:o/r"]),
    "hand-long": role_call("g1", ["cs-build:lane", "cs-step:" + LONG_SLUG, "cs-repo:o/r"]),
    "hand-slash": role_call("g1", ["cs-build:lane", "cs-step:a/b", "cs-repo:o/r"]),
    "hand-dotdot": role_call("g1", ["cs-build:lane", "cs-step:..", "cs-repo:o/r"]),
    "hand-empty": role_call("g1", ["cs-build:lane", "cs-step:", "cs-repo:o/r"]),
    "hand-untagged": role_call("g1", ["cs-repo:o/r"]),
    "hand-title": role_call("g1", ["cs-repo:o/r"], title="handed to cs-build:lane"),
    "hand-other": role_call("g1", LANE_TAGS, session=ROLE_OTHER),
    "hand-tagged-after": role_call("g1", LANE_TAGS) + role_tag_call("t1"),
}
_CLASH = sorted(set(HAND_LINES) & set(ROLE_LINES))
if _CLASH:
    sys.exit("fixture setup failed: handoff transcripts %s name ROLE_LINES entries" % _CLASH)
ROLE_LINES.update(HAND_LINES)
lazy_fixture([role_path(name) for name in HAND_LINES], write_role_transcripts)


# The new allow. Red on the code that refuses every push a lane makes to the record branch.
record_allow("roadmap-one-writer handoff: a lane's own handoff, pushed as HEAD:roadmap, is allowed",
             HANDOFF_PUSH, LANE, cwd=HANDOFF_REPO["modify-own"])
record_allow("roadmap-one-writer handoff: a lane's own handoff, pushed by its source name, is allowed",
             VCS + " push origin lane/outbox-a:roadmap", LANE, cwd=HANDOFF_REPO["modify-own"])
record_allow("roadmap-one-writer handoff: a lane's own new handoff file is allowed",
             HANDOFF_PUSH, LANE, cwd=HANDOFF_REPO["add-own"])
record_allow("roadmap-one-writer handoff: a handoff for a lane's second cs-step slug is allowed",
             HANDOFF_PUSH, role_path("hand-two"), cwd=HANDOFF_REPO["add-e"])
record_allow("roadmap-one-writer handoff: a handoff for a 32-character slug is allowed",
             HANDOFF_PUSH, role_path("hand-long"), cwd=HANDOFF_REPO["long-slug"])
# Triage keeps its full allow: none of these is read as a lane's handoff.
record_allow("roadmap-one-writer handoff: triage's push of two files is allowed",
             HANDOFF_PUSH, TRIAGE, cwd=HANDOFF_REPO["two-files"])
record_allow("roadmap-one-writer handoff: triage's push of a delete is allowed",
             HANDOFF_PUSH, TRIAGE, cwd=HANDOFF_REPO["delete-own"])
record_allow("roadmap-one-writer handoff: triage's push of a file outside roadmap/ is allowed",
             HANDOFF_PUSH, TRIAGE, cwd=HANDOFF_REPO["outside-roadmap"])

# Everything else stays denied. Each refusal sits beside the allow above that it must not reach.
record_refuse("roadmap-one-writer handoff: another lane's slug is refused",
              HANDOFF_PUSH, LANE, cwd=HANDOFF_REPO["add-other"])
record_refuse("roadmap-one-writer handoff: the own handoff with a second file under roadmap/outbox is refused",
              HANDOFF_PUSH, LANE, cwd=HANDOFF_REPO["two-files"])
record_refuse("roadmap-one-writer handoff: a file under roadmap/ that is no handoff is refused",
              HANDOFF_PUSH, LANE, cwd=HANDOFF_REPO["under-roadmap"])
record_refuse("roadmap-one-writer handoff: a file outside roadmap/, named as a handoff, is refused",
              HANDOFF_PUSH, LANE, cwd=HANDOFF_REPO["outside-roadmap"])
record_refuse("roadmap-one-writer handoff: a delete of the own handoff is refused",
              HANDOFF_PUSH, LANE, cwd=HANDOFF_REPO["delete-own"])
record_refuse("roadmap-one-writer handoff: a delete of another lane's handoff is refused",
              HANDOFF_PUSH, LANE, cwd=HANDOFF_REPO["delete-other"])
record_refuse("roadmap-one-writer handoff: a rename into the own handoff path is refused",
              HANDOFF_PUSH, LANE, cwd=HANDOFF_REPO["rename-into-own"])
record_refuse("roadmap-one-writer handoff: a slug with / from the branch is refused",
              HANDOFF_PUSH, LANE, cwd=HANDOFF_REPO["slash-branch"])
record_refuse("roadmap-one-writer handoff: a slug with / from a cs-step tag is refused",
              HANDOFF_PUSH, role_path("hand-slash"), cwd=HANDOFF_REPO["slash-tag"])
record_refuse("roadmap-one-writer handoff: a slug with .. from a cs-step tag is refused",
              HANDOFF_PUSH, role_path("hand-dotdot"), cwd=HANDOFF_REPO["dotdot-tag"])
record_refuse("roadmap-one-writer handoff: an empty slug from a cs-step tag is refused",
              HANDOFF_PUSH, role_path("hand-empty"), cwd=HANDOFF_REPO["empty-tag"])
record_refuse("roadmap-one-writer handoff: a push with no changed paths is refused",
              HANDOFF_PUSH, LANE, cwd=HANDOFF_REPO["no-diff"])
record_refuse("roadmap-one-writer handoff: an earlier commit with a file outside the handoff is refused, "
              "though the last commit is the handoff alone",
              HANDOFF_PUSH, LANE, cwd=HANDOFF_REPO["earlier-commit"])
# A lane cut from an unpushed local roadmap: its commit is in origin/roadmap..HEAD, so the push would carry it.
record_refuse("roadmap-one-writer handoff: a lane cut from an unpushed local roadmap is refused, since the range "
              "from origin/roadmap carries the local commit",
              HANDOFF_PUSH, LANE, cwd=HANDOFF_REPO["local-roadmap"])
# A range with a merge commit: the merge's paths hide from diff-tree, so the push is refused, not read as the handoff.
record_refuse("roadmap-one-writer handoff: a lane that merged a newer record tip into its branch is refused",
              HANDOFF_PUSH, LANE, cwd=HANDOFF_REPO["merged-tip"])
record_refuse("roadmap-one-writer handoff: a lane's refused merge says to rebase the commits onto the record tip",
              HANDOFF_PUSH, LANE, cwd=HANDOFF_REPO["merged-tip"], carries="rebase")
record_refuse("roadmap-one-writer handoff: a lane's refused merge says no merge commit",
              HANDOFF_PUSH, LANE, cwd=HANDOFF_REPO["merged-tip"], carries="no merge commit")
# A range with a root commit: the root's paths hide from diff-tree, so the push is refused.
record_refuse("roadmap-one-writer handoff: a lane whose range starts at a root commit is refused",
              HANDOFF_PUSH, LANE, cwd=HANDOFF_REPO["root-commit"])
# The range is read before a commit made in the same call exists, so the chain is refused: the remedy says so.
record_refuse("roadmap-one-writer handoff: a commit and a push in one call is refused, and the remedy says to commit "
              "in its own call first",
              VCS + " add roadmap/outbox/outbox-a-handoff.md && " + VCS + " commit -m handoff && " + HANDOFF_PUSH,
              LANE, cwd=HANDOFF_REPO["no-diff"], carries="commit in its own call first")
sh("roadmap-one-writer handoff: a forced push of the own handoff is refused, by force-push",
   VCS + " push --force origin HEAD:roadmap", "deny", transcript=LANE, env=ROLE_ENV, cwd=HANDOFF_REPO["modify-own"])
record_refuse("roadmap-one-writer handoff: a coordinator's push of a handoff is refused",
              HANDOFF_PUSH, role_path("coordinator"), cwd=HANDOFF_REPO["modify-own"])
record_refuse("roadmap-one-writer handoff: a session with no cs-build tag is refused a handoff push",
              HANDOFF_PUSH, role_path("hand-untagged"), cwd=HANDOFF_REPO["modify-own"])
record_refuse("roadmap-one-writer handoff: a lane record with a set_session_tags call after it is refused",
              HANDOFF_PUSH, role_path("hand-tagged-after"), cwd=HANDOFF_REPO["modify-own"])
record_refuse("roadmap-one-writer handoff: a lane tag in a record's title is not a proof",
              HANDOFF_PUSH, role_path("hand-title"), cwd=HANDOFF_REPO["modify-own"])
record_refuse("roadmap-one-writer handoff: another session's lane record is not a proof",
              HANDOFF_PUSH, role_path("hand-other"), cwd=HANDOFF_REPO["modify-own"])
record_refuse("roadmap-one-writer handoff: a session with no get_session record is refused a handoff push",
              HANDOFF_PUSH, role_path("no-record"), cwd=HANDOFF_REPO["modify-own"])
record_refuse("roadmap-one-writer handoff: a lane's handoff with an unreadable transcript is refused",
              HANDOFF_PUSH, role_path("unreadable"), cwd=HANDOFF_REPO["modify-own"])
record_refuse("roadmap-one-writer handoff: a lane's handoff with no transcript is refused",
              HANDOFF_PUSH, None, cwd=HANDOFF_REPO["modify-own"])
record_refuse("roadmap-one-writer handoff: a lane's push whose changed paths cannot be read is refused",
              HANDOFF_PUSH, LANE, cwd=HANDOFF_REPO["broken-tip"])

# The forms a lane types for its own handoff. Each is allowed, so the allow stays as wide as the lane needs.
record_allow("roadmap-one-writer handoff: a lane's own handoff pushed with -u is allowed",
             VCS + " push -u origin HEAD:roadmap", LANE, cwd=HANDOFF_REPO["modify-own"])
record_allow("roadmap-one-writer handoff: a lane's own handoff pushed with --set-upstream is allowed",
             VCS + " push --set-upstream origin HEAD:roadmap", LANE, cwd=HANDOFF_REPO["modify-own"])
record_allow("roadmap-one-writer handoff: a lane's own handoff pushed to HEAD:refs/heads/roadmap is allowed",
             VCS + " push origin HEAD:refs/heads/roadmap", LANE, cwd=HANDOFF_REPO["modify-own"])
record_allow("roadmap-one-writer handoff: the own handoff pushed from a detached HEAD, with a cs-step tag naming "
             "its slug, is allowed", HANDOFF_PUSH, role_path("hand-two"), cwd=HANDOFF_REPO["detached-own"])

# Pushes the handoff allow must not reach: a range that hides a file in an earlier commit, tags, and a lease, pinned
# to a sha or with --force-if-includes.
PINNED_LEASE = "a" * 40  # a sha the lease names; the guard reads the pin, never the object
record_refuse("roadmap-one-writer handoff: an earlier commit that adds then removes a file outside the handoff is "
              "refused, though the tree diff shows the handoff alone",
              HANDOFF_PUSH, LANE, cwd=HANDOFF_REPO["history-gap"])
record_refuse("roadmap-one-writer handoff: --tags on the own handoff push is refused",
              VCS + " push --tags origin HEAD:roadmap", LANE, cwd=HANDOFF_REPO["modify-own"])
record_refuse("roadmap-one-writer handoff: --follow-tags on the own handoff push is refused",
              VCS + " push --follow-tags origin HEAD:roadmap", LANE, cwd=HANDOFF_REPO["modify-own"])
record_refuse("roadmap-one-writer handoff: a sha-pinned lease on the own handoff push is refused",
              VCS + " push --force-with-lease=roadmap:" + PINNED_LEASE + " origin HEAD:roadmap", LANE,
              cwd=HANDOFF_REPO["modify-own"])
record_refuse("roadmap-one-writer handoff: --force-if-includes on the own handoff push is refused",
              VCS + " push --force-with-lease --force-if-includes origin HEAD:roadmap", LANE,
              cwd=HANDOFF_REPO["modify-own"])

# A single-branch clone has no origin/roadmap to read. The refusal tells the lane to fetch and retry. A refusal never
# names the record branch in a command (the remedy rule), so the text is held to RECORD_LACKS like the others above.
record_refuse("roadmap-one-writer handoff: a lane's own handoff push with no origin/roadmap is refused, and the "
              "refusal names the fetch and the retry",
              HANDOFF_PUSH, LANE, cwd=HANDOFF_REPO["no-tip"], carries=("fetch", "retry the handoff push"))


# The handoff check's own git spawns, matched by the argv the check builds: the range read, the path read and the
# branch read. Another rule spawns the same verbs for its own reads (octopus-push reads a pushed range), so a spawn is
# counted by these argv prefixes, never by the verb alone. Each push is judged with a stand-in git on PATH, which logs
# every spawn.
HANDOFF_SPAWNS = ("rev-list --parents refs/remotes/", "diff-tree --stdin", "symbolic-ref -q --short HEAD")
HANDOFF_COST_LABEL = ("roadmap-one-writer: a lane's handoff push spawns the range read and the path read, and the "
                      "branch read only when no cs-step tag names its slug; a push by another session or to another "
                      "branch spawns none of the three")


def _spawn_argv(line):
    """A logged git spawn's argv as one string, without the -C and -c pairs that lead it."""
    words = line.split()
    while len(words) >= 2 and words[0] in ("-C", "-c"):
        words = words[2:]
    return " ".join(words)


def _handoff_spawns(log):
    """The count of each HANDOFF_SPAWNS argv in the log, in the same order."""
    lines = open(log, encoding="utf-8").read().splitlines() if os.path.exists(log) else []
    argvs = [_spawn_argv(line) for line in lines]
    return tuple(sum(1 for argv in argvs if argv.startswith(prefix)) for prefix in HANDOFF_SPAWNS)


def handoff_push_cost_case():
    """A lane's push that reaches the record branch spawns the range read and the path read, and the branch read when
    no cs-step tag names its slug, allowed or refused, since the paths decide it. A push by triage, by another session
    or to another branch spawns none of the three. Why: decision session-tiers, the roadmap-one-writer cost line."""
    if os.name == "nt":
        return SKIP, "skipped: a stand-in git is not reached through CreateProcess"
    log, path = _stand_in_git("handoffcost")
    if path is None:
        return False, "no git on PATH"

    def judge(command, cwd, transcript):
        if os.path.exists(log):
            os.remove(log)
        got, _reason = decide({"raw": None, "tool": "Bash", "cwd": cwd, "session": None, "env_path": path,
                               "config": None, "agent_id": None, "tool_input": {"command": command},
                               "transcript": transcript, "env": ROLE_ENV})
        return got, _handoff_spawns(log)

    # label, command, transcript, checkout, the verdict, and the counts of HANDOFF_SPAWNS the check must spawn.
    rows = (
        ("a lane's handoff", HANDOFF_PUSH, LANE, HANDOFF_REPO["modify-own"], "allow", (1, 1, 1)),
        ("a lane's handoff named by a cs-step tag", HANDOFF_PUSH, role_path("hand-two"), HANDOFF_REPO["add-e"],
         "allow", (1, 1, 0)),
        ("a lane's handoff for another lane's slug", HANDOFF_PUSH, LANE, HANDOFF_REPO["add-other"], "deny", (1, 1, 1)),
        ("a lane's push to lane/foo", VCS + " push origin lane/foo", LANE, HANDOFF_REPO["modify-own"], "allow",
         (0, 0, 0)),
        ("a triage push to roadmap", HANDOFF_PUSH, TRIAGE, HANDOFF_REPO["modify-own"], "allow", (0, 0, 0)),
        ("a coordinator's push to roadmap", HANDOFF_PUSH, role_path("coordinator"), HANDOFF_REPO["modify-own"],
         "deny", (0, 0, 0)),
        ("another session's lane record", HANDOFF_PUSH, role_path("hand-other"), HANDOFF_REPO["modify-own"],
         "deny", (0, 0, 0)),
    )
    problems = []
    for label, command, transcript, cwd, want, counts in rows:
        got, spawned = judge(command, cwd, transcript)
        if got != want:
            problems.append("%s: verdict %s, want %s" % (label, got, want))
        if spawned != counts:
            problems.append("%s: range, path and branch spawns %s, want %s" % (label, spawned, counts))
    if problems:
        return False, "; ".join(problems)
    return True, "a lane's push spawns the range read and the path read, and the branch read without a cs-step tag; " \
                 "triage, another session and another branch spawn none"


LOG_FAMILY[HANDOFF_COST_LABEL] = FAMILY
LOG_CHECKS = LOG_CHECKS + ((HANDOFF_COST_LABEL, handoff_push_cost_case),)


# _lane_handoff_holds alone, in a child Python, so the guard's module state stays out of this process. The
# whole-suite run hands a forced push to the force-push rule first, so only this call shows that the handoff check
# refuses a force, a + refspec, a delete and a mirror on its own.
HANDOFF_HOLDS_PROBE = r'''
import json, sys
sys.path.insert(0, sys.argv[1])
import guard_merge
where = sys.argv[2]
for args in json.loads(sys.argv[3]):
    print(json.dumps(bool(guard_merge._lane_handoff_holds(args, where, None, where, "roadmap", []))))
'''
HANDOFF_HOLDS_ROWS = (  # the argument list, and the verdict _lane_handoff_holds must give
    (["origin", "HEAD:roadmap"], True),  # the control: the plain push is held, so a refuse-all probe fails here
    (["--force", "origin", "HEAD:roadmap"], False),
    (["origin", "+HEAD:roadmap"], False),
    (["--delete", "origin", "roadmap"], False),
    (["--mirror", "origin"], False),
)
HANDOFF_HOLDS_LABEL = ("roadmap-one-writer: _lane_handoff_holds holds a lane's plain push of its own handoff, and "
                       "refuses a forced, a + refspec, a deleting and a mirror push")


def handoff_holds_unit_case():
    """_lane_handoff_holds, called alone on the own handoff checkout: the plain push is held (the scope), and the
    forced, `+`, deleting and mirror pushes are not (the subject). The scope comes first, so a probe that cannot read
    the diff fails on the control, not on a refusal it never reached. Why: a force dropped from the handoff check
    must fail a named case, since no other case reaches the check past the force-push rule."""
    materialize(HANDOFF_REPO["modify-own"])
    done = subprocess.run(
        [sys.executable, "-c", HANDOFF_HOLDS_PROBE, os.path.dirname(GUARD), HANDOFF_REPO["modify-own"],
         json.dumps([args for args, _want in HANDOFF_HOLDS_ROWS])],
        capture_output=True, text=True, timeout=120)
    printed = done.stdout.split()
    if done.returncode != 0 or len(printed) != len(HANDOFF_HOLDS_ROWS):
        return False, "the probe printed %d verdicts, want %d: exit %d, error %r" % (
            len(printed), len(HANDOFF_HOLDS_ROWS), done.returncode, done.stderr.strip()[-200:])
    verdicts = [json.loads(line) for line in printed]
    if verdicts[0] is not True:
        return False, "the plain push control: _lane_handoff_holds said %s, want True" % verdicts[0]
    problems = ["%s: _lane_handoff_holds said %s, want %s" % (" ".join(args), verdict, want)
                for (args, want), verdict in zip(HANDOFF_HOLDS_ROWS[1:], verdicts[1:]) if verdict != want]
    if problems:
        return False, "; ".join(problems)
    return True, "the plain push is held, and the forced, + refspec, deleting and mirror pushes are refused"


LOG_FAMILY[HANDOFF_HOLDS_LABEL] = FAMILY
LOG_CHECKS = LOG_CHECKS + ((HANDOFF_HOLDS_LABEL, handoff_holds_unit_case),)
