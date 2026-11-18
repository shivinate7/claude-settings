# section 442
# --------------------------------------------------------------------------- the fixtures
#
# Every path a case names lives under one temporary root, so no case can reach the real
# configuration, the real log or a real repository.

# test-temp-standard (decisions/test-temp-standard.md): this run's folder is `<pid>-<UUID>` under one
# temp root for this repo. The first request of a run sweeps the sibling run folders older than one
# day; newer ones belong to parallel runs and stay. run_cases removes this run folder at teardown.
TEMP_ROOT = os.path.join(tempfile.gettempdir(), "claude-settings-test-temp")
RUN_FOLDER_RE = re.compile(r"[0-9]+-[0-9a-f]{32}")
RUN_FOLDER_MAX_AGE = 24 * 60 * 60


def sweep_run_folders(temp_root, own, now=None):
    """Remove each sibling run folder under `temp_root` whose mtime is over a day old. `own` stays."""
    now = time.time() if now is None else now
    try:
        names = os.listdir(temp_root)
    except OSError:
        return
    for name in names:
        path = os.path.join(temp_root, name)
        if path == own or not RUN_FOLDER_RE.fullmatch(name) or not os.path.isdir(path):
            continue
        if now - os.path.getmtime(path) > RUN_FOLDER_MAX_AGE:
            shutil.rmtree(path, ignore_errors=True)


os.makedirs(TEMP_ROOT, exist_ok=True)
ROOT = os.path.join(TEMP_ROOT, "%d-%s" % (os.getpid(), uuid.uuid4().hex))
os.makedirs(ROOT)
sweep_run_folders(TEMP_ROOT, ROOT)
CFG = os.path.join(ROOT, "cfg")            # stands in for the config directory
LOGDIR = os.path.join(ROOT, "logcfg")      # a second config directory, for the log case
PROJ = os.path.join(ROOT, "proj")          # an ordinary project with its own .claude folder
CLONE = os.path.join(ROOT, "clone")        # the clone of claude-settings, which is NOT frozen
NOGIT = os.path.join(ROOT, "nogit")        # a directory that is not a git tree
GITMAIN = os.path.join(ROOT, "repo")       # an ordinary checkout, shared with other sessions
GITWT = os.path.join(ROOT, "lane")         # a linked worktree of that checkout
# D2026-10-03 (owner ruling): a linked worktree under <repo>/.claude/worktrees/ is AGENT-OWNED,
# and a discard there is allowed and noted instead of asked. AGENTWT is the real thing. FARWT,
# DOTDOTWT and SYMWT are near misses that must NOT count as agent-owned: a sibling path that
# merely contains the word "worktrees", a textual ".claude/worktrees/.." that resolves back
# outside, and (where the platform allows it) a symlink doing the same. DECOYMAIN is the MAIN
# checkout, whose own folder happens to be nested under a path spelled like the agent layout.
AGENTWT = os.path.join(GITMAIN, ".claude", "worktrees", "agent-x")
FARWT = os.path.join(ROOT, "worktrees", "stray")
SYMWT = os.path.join(GITMAIN, ".claude", "worktrees", "linked-agent")
DECOYMAIN = os.path.join(ROOT, "decoyhost", ".claude", "worktrees", "decoy")
CONFLICT = os.path.join(ROOT, "conflict")  # a real checkout with an unresolved merge conflict
SUBJCLEAN = os.path.join(ROOT, "subjclean")  # a real checkout with a clean tree and no stash
SUBJCLEANWT = os.path.join(ROOT, "subjcleanlane")  # a real, clean linked worktree of that one
SUBJDIRTY = os.path.join(ROOT, "subjdirty")  # a real checkout with real uncommitted work
SUBJSTASH = os.path.join(ROOT, "subjstash")  # a clean tree carrying one real stash entry
SUBJSTASHWT = os.path.join(ROOT, "subjstashlane")  # a linked worktree of it: same stack
SUBJSTASHDIRTY = os.path.join(ROOT, "subjstashdirty")  # a dirty checkout carrying one real stash entry
SUBJSTAGED = os.path.join(ROOT, "subjstaged")  # a real checkout: a staged edit, a staged new file
GITBLIND = os.path.join(ROOT, "gitblind")  # a git that answers the repo test and no status read
NOGIT_PATH = os.path.join(ROOT, "nogitpath")  # an empty folder on PATH: no git runs at all
# A repository under a scratchpad named after one session. ROOT already sits under the system
# temporary directory, which is the other half of the path test.
FAKE_SESSION = "5b9f6a3d-0000-4000-8000-000000000000"
OTHER_SESSION = "0000ffff-0000-4000-8000-000000000000"
PRIVREPO = os.path.join(ROOT, FAKE_SESSION, "scratchpad", "priv")
GHMAIN = os.path.join(ROOT, "ghmain")      # a fake command line tool answering "main"
GHDEV = os.path.join(ROOT, "ghdev")        # the same, answering "dev"
GHPEND = os.path.join(ROOT, "ghpend")      # green base main, but one check is pending
GHRED = os.path.join(ROOT, "ghred")        # one check failed
GHRUNPEND = os.path.join(ROOT, "ghrunpend")  # every check passed, one workflow run is not done
GHBROKEN = os.path.join(ROOT, "ghbroken")  # answers every call with text that is not JSON
GHNEED = os.path.join(ROOT, "ghneed")      # green, but only for a call that names pull request 12 and y/x
GHEMPTY = os.path.join(ROOT, "ghempty")    # no check and no workflow run reported yet
GHCWD = os.path.join(ROOT, "ghcwd")        # green, but only for a call run inside the folder `ctxrepo`
WFREPO = os.path.join(ROOT, "wfrepo")      # a folder that holds one workflow file
GHSLOW = os.path.join(ROOT, "ghslow")      # green, but every call takes longer than the guard waits
HANG_MARGIN_S = 3      # what a read may run past MERGE_READ_TIMEOUT: process start and the kill landing
HANG_CEILING_S = 45    # the most MERGE_READ_TIMEOUT plus its margin may be: well inside the hook's 60s
HOOK_BUDGET_S = 60     # the hook's own time budget
GHWARM = os.path.join(ROOT, "ghwarm")      # green, each call as slow as a real gh measured locally
GHHANG = os.path.join(ROOT, "ghhang")      # green, but every call never answers at all
GHBLANK = os.path.join(ROOT, "ghblank")    # green checks, a base that reads as empty
GHSTATPEND = os.path.join(ROOT, "ghstatpend")  # a green check run, and one commit status still pending
GHSTATRED = os.path.join(ROOT, "ghstatred")    # a green check run, and one commit status failed
GHBATCH = os.path.join(ROOT, "ghbatch")        # merging pull request 1 while pull request 2, also ready on main, has its required check pending
GHBATCHDONE = os.path.join(ROOT, "ghbatchdone")  # the same, with pull request 2's required check passed
GHBATCHRED = os.path.join(ROOT, "ghbatchred")    # the same, with pull request 2's required check failed
GHBATCHCONTAIN = os.path.join(ROOT, "ghbatchcontain")  # the same as GHBATCH, but pull request 2's head holds pull request 1's head (compare "ahead")
GHBATCHDIVERGED = os.path.join(ROOT, "ghbatchdiverged")  # the same as GHBATCH, and pull request 2's head does not hold pull request 1's (compare "diverged")
GHBATCHBEHIND = os.path.join(ROOT, "ghbatchbehind")  # the same as GHBATCHCONTAIN, but pull request 1's head is behind main (compare "main...<head>" "behind")
GHPINNED = os.path.join(ROOT, "ghpinned")        # the same, with the protection naming `gate`: STAMPREPO pins `checks`, and only the pin counts
GHNOPROT = os.path.join(ROOT, "ghnoprot")        # no branch protection: pull request 2's pending check counts, whatever its name
GHNOPROTDONE = os.path.join(ROOT, "ghnoprotdone")  # the same, with pull request 2's check passed
GHPROT500 = os.path.join(ROOT, "ghprot500")      # the protection read fails with a server error, and pull request 2's check passed
GHPROTNET = os.path.join(ROOT, "ghprotnet")      # the protection read fails on the network, and pull request 2's check passed
GHRUNBLOCK = os.path.join(ROOT, "ghrunblock")    # pull request 2's workflow `ci-checks` runs, and only its non-required scope job has a row
GHRUNNONE = os.path.join(ROOT, "ghrunnone")      # pull request 2's workflow `ci-checks` is queued, and it has no check rows at all
GHRUNDONE = os.path.join(ROOT, "ghrundone")      # pull request 2's workflow finished, and its required check passed
GHRUNIGNORED = os.path.join(ROOT, "ghrunignored")  # pull request 2's only running workflow is `sync`, which STAMPIGNORE ignores


def batch_other(*checks, runs=None):
    """Pull request 2 on main, ready, with (name, bucket) check rows and workflow runs on its head: the other half of the batch brake."""
    return [{"number": 2, "head": "pr-two-head", "draft": False,
             "checks": [{"name": name, "bucket": bucket, "link": "https://github.com/y/x/actions/runs/88"} for name, bucket in checks],
             "runs": list(runs or [])}]
GHPAGE2 = os.path.join(ROOT, "ghpage2")        # the failed check run is on the second page of the check runs
CURREPO = os.path.join(ROOT, "currepo")        # a checkout on the branch `feat`, the head of the one pull request the fake gh lists
CTXREPO = os.path.join(ROOT, "ctxrepo")      # a checkout on main with one merged branch, `done`
MSG_BAD = os.path.join(ROOT, "msg_bad.txt")  # a message file that cites a record by path
MSG_OK = os.path.join(ROOT, "msg_ok.txt")    # a message file that cites a record by id
MSG_LANE = os.path.join(ROOT, "msg_lane.txt")  # a message file that names a lane by session number
MSG_FENCE = os.path.join(ROOT, "msg_fence.txt")  # a message file that names a lane only in a fence
# Message files in a session's scratchpad (scratchpad-message). The scratchpad is shared by the agents of
# one session, so a file there may hold another agent's message. Each path names its own folder.
MSG_NOGIT = os.path.join(NOGIT, "msg_nogit.txt")  # a clean message file outside every scratchpad
SCRATCH_MSG = os.path.join(ROOT, FAKE_SESSION, "scratchpad", "probe", "commit_msg.txt")  # a clean one, this session's
SCRATCH_EMPTY = os.path.join(ROOT, FAKE_SESSION, "scratchpad", "probe", "empty_msg.txt")  # an empty one, this session's
SCRATCH_OTHER_MSG = os.path.join(ROOT, OTHER_SESSION, "scratchpad", "probe", "commit_msg.txt")  # a clean one, another session's
TILDE_DIR = os.path.join(ROOT, "tilde~dir")   # a folder whose name holds ~: a variable naming it is no literal to the guard
TILDE_MSG = os.path.join(TILDE_DIR, "commit_msg.txt")  # a clean message file in it, outside every scratchpad
SCRATCH_LINK_IN = os.path.join(NOGIT, "link_into_scratch.txt")  # a link outside every scratchpad, to SCRATCH_MSG
SCRATCH_LINK_OUT = os.path.join(ROOT, FAKE_SESSION, "scratchpad", "probe", "link_out.txt")  # a link in the scratchpad, to MSG_NOGIT
PATHSPEC_LIST = os.path.join(ROOT, "pathspec_list.txt")  # a pathspec file naming f.txt, for --pathspec-from-file
MERGECFG = os.path.join(ROOT, "mergecfg")  # a config directory whose rules file points at this repo
GHNONE = os.path.join(ROOT, "ghnone")      # an empty directory, so the tool is missing
# The WHOLE PATH of every "gh missing" case: GHNONE and nothing else, never PY_PATH beside it.
# MEASURED on WSL Ubuntu: with the interpreter at /usr/bin/python3, PY_PATH is /usr/bin, which also
# holds apt's real, logged-in /usr/bin/gh, so the "missing" case made a live GitHub call and read a
# real pull request. That masked a "gh missing" mutant in
# 3 of 3 runs. CI's setup-python folder holds no gh, so CI cannot see it. The guard needs nothing
# else on PATH to run: the GITBLIND cases run it on a one-folder PATH too. build_fixtures fails
# setup if gh resolves here.
GHNONE_PATH = GHNONE
# lane-closes-after-records: the step slug a lane's cs-step tag carries, and the head its pull request names.
ARCHIVE_SLUG = "lane-closes-after-records"
# A lane's own pull request has a head ref equal to its step slug, exactly (the roadmap ruling: a step is live when
# an open pull request's branch equals the step id). Near misses that only contain the slug or a lane's id do not count.
ARCHIVE_HEAD = ARCHIVE_SLUG
ARCHOPEN = os.path.join(ROOT, "archopen")      # the slug's pull request is open: the refusal
ARCHCLOSED = os.path.join(ROOT, "archclosed")  # the slug's pull request was closed as replaced
ARCHMERGED = os.path.join(ROOT, "archmerged")  # the slug's pull request was merged
ARCHPAGE = os.path.join(ROOT, "archpage")      # the slug's pull request is on page two of the open list
ARCHNEAR_C10 = os.path.join(ROOT, "archnear-c10")      # an open head `c10`: contains the lane id `c1`, is not it
ARCHNEAR_C10X = os.path.join(ROOT, "archnear-c10x")    # an open head `claude/c10-x1`: contains `c1`, is not it
ARCHNEAR_CI = os.path.join(ROOT, "archnear-ci")        # an open head `claude/fix-ci-retry-x1`: contains `ci`, is not it
ARCHOPEN_LANE = os.path.join(ROOT, "archopen-lane")    # the slug's pull request is open on the `lane/<slug>` head form
ARCH_AGENT_SLUG = "lane-agent-own-step"                # the step an agent's own record names, a second step in the same repo
ARCHOPEN_AGENT = os.path.join(ROOT, "archopen-agent-step")  # the agent record's step's pull request is open; the main step's is not
# The containment read of an open lane pull request's head against main, by its status. Each fake holds one open
# pull request on the slug, its head the slug's head sha; the read's answer is what the name says.
ARCHDRAFT_BEHIND = os.path.join(ROOT, "archdraft-behind")      # an open draft, head behind main: its commits landed
ARCHDRAFT_IDENT = os.path.join(ROOT, "archdraft-identical")    # an open draft, head identical to main: its commits landed
ARCHDRAFT_AHEAD = os.path.join(ROOT, "archdraft-ahead")        # an open draft, head ahead of main: not landed
ARCHDRAFT_DIVERGED = os.path.join(ROOT, "archdraft-diverged")  # an open draft, head diverged from main: not landed
ARCHREADY_BEHIND = os.path.join(ROOT, "archready-behind")      # an open ready (not draft) pull request, head behind main
ARCHDRAFT_READFAIL = os.path.join(ROOT, "archdraft-readfail")  # an open draft whose containment read fails
ARCHDRAFT_INTEG = os.path.join(ROOT, "archdraft-integ")        # an open draft based on integration/b1, not the default branch
ARCHDRAFT_LANE_BEHIND = os.path.join(ROOT, "archdraft-lane-behind")  # an open draft on the lane/<slug> head, head behind main
# The branch read (lane-closes-after-records). The incident: a lane tagged for claude-settings and q_max, its branch pushed
# to q_max alone. Its fakes name both repos (make_fake_gh's `repos`), and each repo answers for itself.
ARCH_REPO_SETTINGS = "shivinate7/claude-settings"
ARCH_REPO_QMAX = "shivinate7/q_max"
ARCH_BRANCH = "claude/qmax-hosted-db-gate-notes"  # ahead of main in q_max, on no pull request
ARCH_BRANCH_OTHER = "claude/other-y1"             # another branch of q_max, on an open pull request
ARCHINC_NOPR = os.path.join(ROOT, "archinc-nopr")              # the branch is ahead in q_max, on no pull request
ARCHINC_OTHERPR = os.path.join(ROOT, "archinc-otherpr")        # q_max's open pull request is on another branch
ARCHINC_MERGED = os.path.join(ROOT, "archinc-merged")          # the branch's pull request was merged (a squash: still ahead)
ARCHINC_CLOSED = os.path.join(ROOT, "archinc-closed")          # the branch's pull request was closed as replaced
ARCHINC_OPEN = os.path.join(ROOT, "archinc-open")              # the branch's pull request is open
ARCHINC_BEHIND = os.path.join(ROOT, "archinc-behind")          # the branch is behind main in q_max
ARCHINC_IDENT = os.path.join(ROOT, "archinc-identical")        # the branch is identical to main in q_max
ARCHINC_DEFAULT = os.path.join(ROOT, "archinc-default")        # the branch is main, the default of both repos
ARCHINC_ARCHIVE = os.path.join(ROOT, "archinc-archive")        # the branch is archive/..., ahead in both repos
ARCHINC_404ALL = os.path.join(ROOT, "archinc-404-all")         # the branch is in neither repo: a 404 in each
ARCHINC_COMPARE500 = os.path.join(ROOT, "archinc-compare-500") # the compare of the branch in q_max is a server error
ARCHINC_NETWORK = os.path.join(ROOT, "archinc-network")        # the compare of the branch in q_max is a refused connection
ARCHINC_PULLS500 = os.path.join(ROOT, "archinc-pulls-500")     # the pull request list of the branch in q_max is a server error
ARCHINC_PULLSJUNK = os.path.join(ROOT, "archinc-pulls-junk")   # the pull request list of the branch in q_max is not JSON
ARCHINC_REPO500 = os.path.join(ROOT, "archinc-repo-500")       # q_max's own read, its default branch, is a server error
ARCHINC_TRUNK = os.path.join(ROOT, "archinc-trunk")            # q_max's default branch is trunk: the branch is ahead of trunk
ARCHINC_DIVERGED = os.path.join(ROOT, "archinc-diverged")      # the branch diverged from main in q_max, on no pull request
ARCHINC_REPO404 = os.path.join(ROOT, "archinc-repo-404")       # q_max is named only by a source; its own read answers 404
ARCHINC_OPENLIST_QMAX = os.path.join(ROOT, "archinc-openlist-qmax")          # q_max's open pull request list is a server error; claude-settings' answers
ARCHINC_OPENLIST_SETTINGS = os.path.join(ROOT, "archinc-openlist-settings")  # claude-settings' open pull request list is a server error; q_max's answers
ARCHINC_OPENLIST403_QMAX = os.path.join(ROOT, "archinc-openlist-403-qmax")  # q_max's open pull request list answers 403; claude-settings' answers
ARCHINC_OPENLIST_RATELIMIT_QMAX = os.path.join(ROOT, "archinc-openlist-ratelimit-qmax")  # q_max's open pull request list answers a rate-limit 403; claude-settings' answers
ARCHINC_OPENLIST404_SETTINGS = os.path.join(ROOT, "archinc-openlist-404-settings")  # claude-settings' open pull request list answers 404; q_max's answers
ARCHINC_PULLS403 = os.path.join(ROOT, "archinc-pulls-403")  # the pull request list of the branch in q_max answers 403
ARCHINC_PULLS404 = os.path.join(ROOT, "archinc-pulls-404")  # the pull request list of the branch in q_max answers 404
ARCHINC_REPO403 = os.path.join(ROOT, "archinc-repo-403")  # q_max's own read, its default branch, answers 403
ARCHINC_COMPARE403 = os.path.join(ROOT, "archinc-compare-403")  # the compare of the branch in q_max answers 403
ARCHINC_SLOW = os.path.join(ROOT, "archinc-slow")              # two branches of q_max, behind main; each compare of q_max sleeps
ARCHDRAFT_SLOW = os.path.join(ROOT, "archdraft-slow")          # an open draft of the slug in q_max, behind main, and a branch ahead there; each compare of q_max sleeps
ARCHINC_CLOSEDALONE = os.path.join(ROOT, "archinc-closed-alone")  # the branch's pull request was closed, and no pull request replaced it
ARCHINC_MERGEDMOVED = os.path.join(ROOT, "archinc-merged-moved")  # the branch's pull request merged at one head, and a commit sits on the branch after it
ARCHLEFT_NOPR = os.path.join(ROOT, "archleft-nopr")              # a left branch under the lane's slug form is ahead of main, on no pull request
ARCHLEFT_PR = os.path.join(ROOT, "archleft-pr")                  # the same left branch, on an open pull request
ARCHLEFT_NEAR = os.path.join(ROOT, "archleft-near")              # a branch named <slug>x, ahead, on no pull request: no slug form, so no read of it
ARCHLEFT_REPLACED = os.path.join(ROOT, "archleft-replaced")      # lane/<slug> closed unmerged, replaced by a merged pull request on lane/<slug>-r2 that holds its tip
ARCHLEFT_REPLACED_AHEAD = os.path.join(ROOT, "archleft-replaced-ahead")  # the same, but the replacing head is ahead of the tip: the tip is not contained
REPLACED_TIP = "%040d" % 21       # the branch tip, which the replacing pull request's head contains
REPLACING_HEAD = "%040d" % 24     # the head of the merged pull request that replaced the closed one
NEW_TIP = "%040d" % 99            # the branch tip after a new commit, past the head of its merged pull request
ARCH_SLOW_A = "claude/slow-behind-a"                           # the first slow branch: behind main in q_max
ARCH_SLOW_B = "claude/slow-behind-b"                           # the second slow branch: behind main in q_max
ARCH_COPY_BRANCH = "claude/x"                                  # a lane's branch in o/r, ahead of main, on no pull request
ARCH_COPY_REF = "archive/" + ARCH_COPY_BRANCH                  # the copy the guard lists under the branch's archive/ name
ARCH_COPY_TIP = "%040d" % 31                                   # that branch's tip: each copy's compare is keyed by this sha
ARCHCOPY_IDENT = os.path.join(ROOT, "archcopy-identical")      # the branch's archive/ copy holds its tip
ARCHCOPY_AHEAD = os.path.join(ROOT, "archcopy-ahead")          # the branch's archive/ copy is at an older tip: the tip is ahead of it
ARCHCOPY_MISSING = os.path.join(ROOT, "archcopy-missing")      # the branch has no archive/ copy: the listing is empty
# Copies under other names. The listing returns each ref under the prefix, and the guard counts only the exact name and `-<digits>`.
ARCHCOPY_NUMBERED = os.path.join(ROOT, "archcopy-numbered")    # archive/<branch> at a diverged tip; archive/<branch>-2 holds the tip
ARCHCOPY_NUMBERED_NONE = os.path.join(ROOT, "archcopy-numbered-none")  # archive/<branch> diverged; archive/<branch>-2 ahead: none holds the tip
ARCHCOPY_LOOKALIKE = os.path.join(ROOT, "archcopy-lookalike")  # archive/<branch>y holds the tip: neither the exact name nor -<digits>
ARCHCOPY_SUFFIX_R2 = os.path.join(ROOT, "archcopy-suffix-r2")  # archive/<branch>-r2 holds the tip: a suffix that is not digits


def arch_pair(qmax=None, settings=None):
    """The incident's two repos, as make_fake_gh's `repos` takes them. claude-settings does not hold the branch (its compare is a
    404); q_max holds it, ahead of main. A scope given here replaces the default keys of its repo."""
    return {
        ARCH_REPO_SETTINGS: dict({"compares": {"main..." + ARCH_BRANCH: "missing"}}, **(settings or {})),
        ARCH_REPO_QMAX: dict({"compares": {"main..." + ARCH_BRANCH: "ahead"}}, **(qmax or {})),
    }


def arch_row(ref, number, state="open", merged=False):
    """A pull request row for an arch fixture: its head ref, its number and its state. Its head sha is the number, padded to forty."""
    return {"number": number, "head": "%040d" % number, "ref": ref, "state": state, "merged": merged}


def arch_replaced(containment):
    """The repo of a lane whose branch lane/<slug> is closed unmerged, replaced by a merged pull request on lane/<slug>-r2.
    The -r2 branch's tip is that merged head. The compare of the merged head with the lane branch's tip reads `containment`:
    "behind" when the merged head holds the tip, "ahead" when it does not. Both lane branches read ahead of main."""
    slug = ARCHIVE_SLUG
    return {
        "others": [arch_row("lane/" + slug, 23, state="closed"),
                   arch_row("lane/" + slug + "-r2", 24, state="closed", merged=True)],
        "refs": ["lane/" + slug, "lane/" + slug + "-r2"],
        "tips": {"lane/" + slug: REPLACED_TIP, "lane/" + slug + "-r2": REPLACING_HEAD},
        "compares": {"main...lane/" + slug: "ahead", "main...lane/" + slug + "-r2": "ahead",
                     REPLACING_HEAD + "..." + REPLACED_TIP: containment},
    }


def arch_copies(answers, others=()):
    """The repo of a lane whose branch ARCH_COPY_BRANCH is ahead of main on no pull request, or on the rows given. Its tip is
    ARCH_COPY_TIP. `answers` maps each archive/ ref the listing holds (its full name) to the status of that ref's compare with
    the tip, so a listed copy and its compare are one answer. The compare key names the tip by sha, never by the branch."""
    compares = {"main..." + ARCH_COPY_BRANCH: "ahead"}
    compares.update({name + "..." + ARCH_COPY_TIP: status for name, status in answers.items()})
    return {
        "tips": {ARCH_COPY_BRANCH: ARCH_COPY_TIP},
        "refs": list(answers),
        "compares": compares,
        "others": list(others),
    }


def arch_copy(archive, others=()):
    """The repo of a lane whose branch ARCH_COPY_BRANCH is ahead of main on no pull request, with its archive/<branch> copy
    answering `archive`: "identical" when the copy holds the tip, "ahead" when it is older, "missing" when there is no copy.
    A "missing" copy is not listed, so the listing answers []. Its compare still answers 404 for a direct read of the copy, so
    a guard that compared the copy without the listing would read it as unreadable, and fail the case that names it."""
    if archive == "missing":
        copy = arch_copies({}, others)
        copy["compares"][ARCH_COPY_REF + "..." + ARCH_COPY_TIP] = "missing"
        return copy
    return arch_copies({ARCH_COPY_REF: archive}, others)


# THE POINTER CHECKOUT. `PTRCFG` is a config directory whose global rules file points at
# `PTRMAIN`, which stands in for the machine's primary checkout: the one every session runs its
# hooks and its lint from. `PTRWT` is a real linked worktree of it, which must stay allowed.
# `PTRBADCFG` and `PTRGONECFG` are the two fail-open shapes, and `PTRNOCFG` holds no rules file.
PTRCFG = os.path.join(ROOT, "ptrcfg")
PTRMAIN = os.path.join(ROOT, "ptrmain")
PTRWT = os.path.join(ROOT, "ptrlane")
# A linked worktree NESTED under the pointer checkout, at the harness's `.claude/worktrees/<name>` shape.
PTRNEST = os.path.join(PTRMAIN, ".claude", "worktrees", "ptrnest")
PTRBADCFG = os.path.join(ROOT, "ptrbadcfg")
PTRGONECFG = os.path.join(ROOT, "ptrgonecfg")
PTRNOCFG = os.path.join(ROOT, "ptrnocfg")
# A pointer checkout that is OFF main: HEAD is on `feat`. The recovery cases run here, because a move back
# to main is only a repair when HEAD is not already on it.
PTROFFCFG = os.path.join(ROOT, "ptroffcfg")
PTROFF = os.path.join(ROOT, "ptroffmain")
# The reset of main onto origin/main is judged against origin/main, so each pointer checkout states
# its own. PTRMAIN and PTROFF have local main equal to origin/main (an ancestor: the reset passes).
# PTRAHEAD has one local commit that origin/main lacks. PTRNOORIGIN has no origin/main at all.
PTRAHEADCFG = os.path.join(ROOT, "ptraheadcfg")
PTRAHEAD = os.path.join(ROOT, "ptraheadmain")
PTRNOORIGINCFG = os.path.join(ROOT, "ptrnoorigincfg")
PTRNOORIGIN = os.path.join(ROOT, "ptrnooriginmain")

# --------------------------------------------------------------- branch delete / worktree fixtures
#
# BRANCHREMOTE stands in for a remote: a bare clone BRANCHREPO pushes to, so `git for-each-ref
# --contains` has a real remote-tracking ref to answer against. BRANCHREPO carries a real
# `origin/HEAD`, so its cases prove the FIRST base in the resolve order. BRANCHFALLBACKMAIN and
# BRANCHFALLBACKMASTER carry no remote at all, so their one case each proves the second and third
# steps of that same order. BRANCHNOBASE answers none of the three, so its case proves the
# unreadable arm.
BRANCHREMOTE = os.path.join(ROOT, "branchremote.git")
BRANCHREPO = os.path.join(ROOT, "branchrepo")
BRANCHFALLBACKMAIN = os.path.join(ROOT, "branchfallbackmain")
BRANCHFALLBACKMASTER = os.path.join(ROOT, "branchfallbackmaster")
BRANCHNOBASE = os.path.join(ROOT, "branchnobase")

# The push cases. Each is a real checkout, so the default branch is read from git and never
# guessed. PUSHFEAT sits on `feat` with origin/HEAD naming main, PUSHMAIN sits on main, PUSHTRUNK
# sits on `feat` with origin/HEAD naming trunk (so main is an ordinary branch there), PUSHNOHEAD
# has no origin/HEAD at all (the main/master fallback), PUSHDETACHED has no current branch.
# PUSHDANGLING sits on `feat`; its origin/HEAD names origin/gone, a ref that does not exist, and
# origin/main does exist (owner's read order 2026-10-16: origin/HEAD when it resolves, then origin/main).
PUSHFEAT = os.path.join(ROOT, "pushfeat")
PUSHMAIN = os.path.join(ROOT, "pushmain")
PUSHTRUNK = os.path.join(ROOT, "pushtrunk")
# PUSHTRUNKLOCAL is PUSHTRUNK plus a LOCAL branch named origin/trunk. There `git symbolic-ref --short`
# prints the ambiguous `remotes/origin/trunk`, which once blanked the default branch's name.
PUSHTRUNKLOCAL = os.path.join(ROOT, "pushtrunklocal")
PUSHNOHEAD = os.path.join(ROOT, "pushnohead")
PUSHDETACHED = os.path.join(ROOT, "pushdetached")
# PUSHSAMETAG sits on main and holds a TAG named main. There the short symbolic-ref read of HEAD
# prints the ambiguous `heads/main`, which once hid the default branch from a lease push of HEAD.
PUSHSAMETAG = os.path.join(ROOT, "pushsametag")
PUSHDANGLING = os.path.join(ROOT, "pushdangling")
# Where origin/HEAD does not name the branch, main AND master stay protected. PUSHNOHEADMAIN has
# origin/main and no origin/HEAD. PUSHONLYMASTER has origin/master and no origin/HEAD (local main
# exists, as in any checkout). PUSHUPSTREAM has two remotes: origin/HEAD names develop,
# upstream/HEAD names main, and `feat` tracks upstream/main with push.default upstream. A push
# reads the PUSHED remote's default branch, never origin's.
PUSHNOHEADMAIN = os.path.join(ROOT, "pushnoheadmain")
PUSHONLYMASTER = os.path.join(ROOT, "pushonlymaster")
PUSHUPSTREAM = os.path.join(ROOT, "pushupstream")
# push.default fixtures, each on `feat`: UP follows an upstream named main, UPSELF an upstream
# named feat, NOUP has push.default upstream and no upstream, MATCH has push.default matching.
PUSHUP = os.path.join(ROOT, "pushup")
PUSHUPSELF = os.path.join(ROOT, "pushupself")
PUSHNOUP = os.path.join(ROOT, "pushnoup")
PUSHMATCH = os.path.join(ROOT, "pushmatch")
# Owner rulings 206 a and 207 a. PUSHSTRAY sits on `mylocal`, which tracks
# origin/lane/x, with a `fork` remote the upstream does not name and push.default simple. PUSHLANE and
# PUSHLANEMASTER sit on lanes cut from origin/main and origin/master: their upstreams are inherited, so
# the stray-branch rule stays silent there. PUSHSELF sits on `feat`, which tracks origin/feat.
PUSHSTRAY = os.path.join(ROOT, "pushstray")
PUSHLANE = os.path.join(ROOT, "pushlane")
PUSHLANEMASTER = os.path.join(ROOT, "pushlanemaster")
PUSHSELF = os.path.join(ROOT, "pushself")
PUSHMAINUP = os.path.join(ROOT, "pushmainup")  # main itself, tracking origin/main
PUSHSTACK = os.path.join(ROOT, "pushstack")    # lane/fix cut from origin/lane/base: its upstream is another lane
# PUSHOWNREF is `lane-x`, tracking origin/batch-1, and origin/lane-x exists too. The stray rule
# reads that ref as a destination already on the remote, so an implied push to its own name is silent there.
PUSHOWNREF = os.path.join(ROOT, "pushownref")
# Rule push-main reads the remote a push names (ruling 207 a, judged on its URL). Every push fixture's origin is
# PUSHREMOTE, a network URL the guard never contacts, so the existing push-main asks keep their meaning.
# PUSHLOCAL has a local origin (a bare path), PUSHSSH an scp-form origin, and PUSHNOREMOTE no remote at all.
# PUSHLOCALSTRAY has the same local origin, and its branch `feat` tracks origin/other, so an implied destination
# on it is a stray push. PUSHLOCAL's `feat` has no upstream.
PUSHREMOTE = "https://example.invalid/repo.git"
PUSHSSHURL = "git@github.com:o/r.git"
PUSHLOCAL = os.path.join(ROOT, "pushlocal")
PUSHLOCALSTRAY = os.path.join(ROOT, "pushlocalstray")
# PUSHLOCALMAIN is main with the same local origin and tracks origin/main, as PUSHMAINUP does with an https origin.
# It is the local-origin twin of PUSHMAINUP: the two differ only in the origin's kind.
PUSHLOCALMAIN = os.path.join(ROOT, "pushlocalmain")
PUSHSSH = os.path.join(ROOT, "pushssh")
PUSHNOREMOTE = os.path.join(ROOT, "pushnoremote")
# Agent-worktree branch names (rule push-agent-branch). A branch is named by HEAD, so each name has its own
# checkout. PUSHAGENT holds the name that a stray push sent to origin, with no upstream. The other shapes and
# the near misses sit beside it.
PUSHAGENT = os.path.join(ROOT, "pushagent")            # claude/agent-<hex>
PUSHAGENTWT = os.path.join(ROOT, "pushagentwt")        # worktree-agent-<hex>
PUSHAGENTBARE = os.path.join(ROOT, "pushagentbare")    # agent-<hex>
PUSHAGENTNOTES = os.path.join(ROOT, "pushagentnotes")  # agent-notes: a prefix with no hex after it
PUSHAGENTMYABC = os.path.join(ROOT, "pushagentmyabc")  # my-agent-abc: a prefix, too short to hold hex
PUSHAGENTMYHEX = os.path.join(ROOT, "pushagentmyhex")  # my-agent-<hex>: hex behind a prefix, not the shape
PUSHAGENTSHORT = os.path.join(ROOT, "pushagentshort")  # agent-<7 hex>: a hex tail one character short of the shape
PUSHAGENTEIGHT = os.path.join(ROOT, "pushagenteight")  # agent-<8 hex>: the exact shape, at its lower bound
PUSHAGENTCFG = os.path.join(ROOT, "pushagentcfg")      # claude/agent-<hex> with push.autoSetupRemote in its own config
# --all and --branches fixtures. PUSHAHEAD, PUSHAHEADLANE, PUSHAHEADDET and PUSHAHEADAGENT hold a local
# main one commit ahead of origin/main, from a main, lane, detached and agent checkout. PUSHNOTRACK has no origin/main
# ref. PUSHBEHIND has origin/main one commit ahead of local main. PUSHMASTERAHEAD has master, not main, one commit ahead
# of origin/master. PUSHNOMAIN has neither main nor master. PUSHLOCALAHEAD is PUSHAHEAD with a local-path origin.
PUSHAHEAD = os.path.join(ROOT, "pushahead")              # main checkout, local main ahead of origin/main
PUSHAHEADLANE = os.path.join(ROOT, "pushaheadlane")      # lane checkout (feat), local main ahead
PUSHAHEADDET = os.path.join(ROOT, "pushaheaddet")        # detached checkout, local main ahead
PUSHAHEADAGENT = os.path.join(ROOT, "pushaheadagent")    # agent checkout (claude/agent-<hex>), local main ahead
PUSHNOTRACK = os.path.join(ROOT, "pushnotrack")          # lane checkout, local main, no origin/main ref
PUSHBEHIND = os.path.join(ROOT, "pushbehind")            # main checkout, origin/main ahead of local main
PUSHMASTERAHEAD = os.path.join(ROOT, "pushmasterahead")  # master checkout, local master ahead; no local main
PUSHNOMAIN = os.path.join(ROOT, "pushnomain")            # lane checkout; local trunk and feat, no main or master
PUSHLOCALAHEAD = os.path.join(ROOT, "pushlocalahead")    # PUSHAHEAD's state, with a local-path origin
# Every-branch fixtures (rule push-all-main): main equal to its tracking ref on a network origin. PUSHALLNOAGENT holds
# no agent-named local branch; each of the other three adds one, and differs from PUSHALLNOAGENT only in that branch.
PUSHALLNOAGENT = os.path.join(ROOT, "pushallnoagent")          # main only
PUSHALLAGENT = os.path.join(ROOT, "pushallagent")              # plus agent-<hex suffix>
PUSHALLAGENTWT = os.path.join(ROOT, "pushallagentwt")          # plus worktree-agent-<hex suffix>
PUSHALLAGENTCLAUDE = os.path.join(ROOT, "pushallagentclaude")  # plus claude/agent-<hex suffix>
PUSHALLAGENTAHEAD = os.path.join(ROOT, "pushallagentahead")    # plus agent-<hex suffix>; local main one commit ahead
PUSHALLBROKEN = os.path.join(ROOT, "pushallbroken")            # PUSHALLAGENT, whose listing of refs/heads/ fails
# The rule ids the push asks name. Each is the one home for its id in this file.
PUSH_STRAY_RULE = "push-stray-branch"   # ruling 206 a: a push with an implied destination off its upstream
PUSH_MAIN_RULE = "push-main"            # ruling 207 a: a non-forced push whose destination is main or master
PUSH_AGENT_RULE = "push-agent-branch"   # a non-forced push whose destination is an agent-worktree branch name
# The remedy a push-agent-branch refusal prints: the lane's own branch, by name. It never names the agent's
# branch (rule git-remedy-never-names-target). A deny has no approval prompt, so its reason never offers one.
PUSH_AGENT_REMEDY = "git push origin HEAD:<lane-branch>"
PUSH_AGENT_LACKS = ("Approving the prompt", "push origin claude/agent-", "push origin worktree-agent-",
                    "HEAD:claude/agent-", "HEAD:worktree-agent-")
# --all and --branches never ask. They are refused when the push would update main or master on the remote, and
# allowed when it would not. A refusal's remedy never names main or master as a target.
PUSH_ALL_RULE = "push-all-main"
PUSH_ALL_LACKS = ("Approving the prompt", "push origin main", "push origin master", "HEAD:main", "HEAD:master")
# A refusal for an agent-named branch names no agent branch in its remedy (rule git-remedy-never-names-target).
PUSH_ALL_AGENT_LACKS = ("push origin agent-", "HEAD:agent-", "push origin claude/agent-", "HEAD:claude/agent-",
                        "push origin worktree-agent-", "HEAD:worktree-agent-")
# roadmap-one-writer fixtures. RECROADMAP sits on the record branch, `roadmap`. RECFORK sits on `roadmap-fork`,
# and its extras file names that branch as the record branch, so `roadmap` is not its record.
RECROADMAP = os.path.join(ROOT, "recroadmap")
RECFORK = os.path.join(ROOT, "recfork")

# WTMAIN is the primary checkout of its own small repository. Every linked worktree below is a
# real one, because the rule reads `git worktree list --porcelain` and `git status --porcelain`
# with git itself, never a guess from a path. WTPRUNE is a SEPARATE repository, so pruning it
# never touches WTMAIN's own registrations.
WTMAIN = os.path.join(ROOT, "wtmain")
WTCLEAN = os.path.join(ROOT, "wtclean")
WTDIRTY = os.path.join(ROOT, "wtdirtylane")
WTLOCKED = os.path.join(ROOT, "wtlocked")
WTLIVE = os.path.join(ROOT, "wtlive")
WTDEADSESSION = os.path.join(ROOT, "wtdeadsession")
WTSTALESTART = os.path.join(ROOT, "wtstalestart")
WTPRUNE = os.path.join(ROOT, "wtprune")
WTPRUNESTALE = os.path.join(ROOT, "wtprunestale")

# Each of these is a config directory whose `sessions/` folder holds one record, read through
# `CLAUDE_CONFIG_DIR` exactly as the live sessions folder would be. A record is built against a
# REAL process (this test runner's own pid), read back with `ps` the same way the guard itself
# reads it, so the fixture cannot drift from what the guard actually measures.
WTLIVECFG = os.path.join(ROOT, "wtlivecfg")
WTDEADCFG = os.path.join(ROOT, "wtdeadcfg")
WTSTALESTARTCFG = os.path.join(ROOT, "wtstalestartcfg")

# BASE COPIES (the base-copies incident, Nov 1 22:41 CST). A worktree whose staged files are byte-equal to
# its branch base, with no unpushed commit, must remove. BCINC is that state: its branch moved onto P1 with
# `update-ref`, so its index holds the base P0, an ancestor of HEAD. Each other tree breaks one condition
# of BCINC. BCORIGIN is a bare origin. BCMAIN and BCSECOND are clones of it: BCMAIN is the primary every
# tree hangs from, and BCSECOND is the other tree that pushes P1.
BCORIGIN = os.path.join(ROOT, "bc-origin.git")
BCSEED = os.path.join(ROOT, "bc-seed")
BCMAIN = os.path.join(ROOT, "bc-main")
BCSECOND = os.path.join(ROOT, "bc-second")
BCINC = os.path.join(ROOT, "bc-inc")                # case 1: the incident state, no other condition
BCUNIQUE = os.path.join(ROOT, "bc-unique")          # case 2: a worktree edit whose content is in no commit
BCUNTRACKED = os.path.join(ROOT, "bc-untracked")    # case 3: an untracked file beside the incident
BCUNPUSHED = os.path.join(ROOT, "bc-unpushed")      # case 4: an unpushed commit on HEAD beside the incident
BCBYPASS = os.path.join(ROOT, "bc-bypass")          # case 5: a staged blob held only by an unpushed commit
BCCLEAN = os.path.join(ROOT, "bc-clean")            # case 6: a clean tree on a pushed branch
BCLOCKED = os.path.join(ROOT, "bc-locked")          # the incident tree, locked
BCLIVE = os.path.join(ROOT, "bc-live")              # the incident tree, with a live session standing in it
BCLIVECFG = os.path.join(ROOT, "bc-livecfg")        # the config folder holding that session's record
BCEXEC = os.path.join(ROOT, "bc-exec")              # the incident tree, f.txt at mode 100755 in the base

# SYMLINK WORKTREES (the feed-build incident). An agent linked
# `app/node_modules` to another worktree's packages. Git lists an untracked symlink as a FILE
# (`?? app/node_modules`), and removing the link deletes only the link, never its target. So an
# untracked entry that is a symlink is not work. LINKMAIN is its own repository with NO
# .gitignore, so a real `node_modules` directory is listed as untracked, not hidden.
LINKMAIN = os.path.join(ROOT, "linkmain")
LINKOUT = os.path.join(ROOT, "linkoutside")          # a real directory OUTSIDE every worktree
WTLINKDIR = os.path.join(ROOT, "wtlinkdir")          # detached; its only untracked entry links to LINKOUT
WTLINKFILE = os.path.join(ROOT, "wtlinkfile")        # detached; its only untracked entry links to a file in the tree
WTCTRLFILE = os.path.join(ROOT, "wtctrlfile")        # a link, plus an untracked real file
WTCTRLTRACKED = os.path.join(ROOT, "wtctrltracked")  # a link, plus a change to a tracked file
WTCTRLDIR = os.path.join(ROOT, "wtctrldir")          # a real untracked node_modules directory with a file
WTCTRLNESTED = os.path.join(ROOT, "wtctrlnested")    # a link inside an untracked real directory
# two-worktrees-one-branch (section 1a below). TWBASE is the checkout on main, TWHOLD a linked
# worktree on branch x, and TWACT the linked worktree that acts, on its own branch. TWLOGSHIM and
# TWFAILSHIM are git stand-ins put on PATH: one logs each call it gets, the other fails the worktree
# list read. Each name is a distinct folder, never a substring of another fixture's path.
TWBASE = os.path.join(ROOT, "twobr-base")
TWHOLD = os.path.join(ROOT, "twobr-holder")
TWACT = os.path.join(ROOT, "twobr-actor")
TWLOGSHIM = os.path.join(ROOT, "twobr-logshim")
TWFAILSHIM = os.path.join(ROOT, "twobr-failshim")


def slash(path):
    return path.replace("\\", "/")


def long_name(path):
    """The long-name form of `path` on Windows, where a temp folder may be the 8.3 short name `RUNNER~1`.
    os.path.realpath returns the final path there (ntpath, through _getfinalpathname), which expands a
    short name, and it falls back to the existing prefix for a tail that does not exist yet. The guard's
    in_any_session_scratchpad compares by realpath too, so this is the form it matches. Other hosts keep
    the path as it is."""
    return os.path.realpath(path) if os.name == "nt" else path


def copy_guard_family(dest):
    """Every module in GUARD's folder (mutate_shared.module_files) into `dest`: guard.py, its guard_*
    siblings, and each module they may import, so a new shared module cannot crash the copy on import.
    git_reads.py is copied by name, so a folder that lacks it stops the fixture instead of building a
    guard that cannot load."""
    source = os.path.dirname(GUARD)
    for path in mutate_shared.module_files(source):
        shutil.copy(path, dest)
    shutil.copy(os.path.join(source, "git_reads.py"), dest)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def run_vcs(cwd, *args):
    return subprocess.run([VCS, *args], cwd=cwd, capture_output=True, text=True)


def _require_conflict(where, path):
    """Stop the suite unless `where` really holds an unresolved conflict on `path`.

    A fixture whose setup silently fails proves nothing: it can pass for the wrong reason on
    one machine and fail on another. This reads the tree with git itself, the same two checks
    the guard's own `conflict_in_progress` makes, so a broken build step is caught here rather
    than showing up later as a wrong PASS or a confusing FAIL far from its cause.
    """
    verify = run_vcs(where, "rev-parse", "--verify", "-q", "MERGE_HEAD")
    if verify.returncode != 0:
        sys.exit(
            "fixture setup failed in build_fixtures: MERGE_HEAD does not resolve in %r. "
            "The conflict-repo merge did not run, or it did not conflict. "
            "stderr: %s" % (where, verify.stderr.strip())
        )
    status = run_vcs(where, "status", "--porcelain")
    lines = [line for line in status.stdout.splitlines() if path in line]
    if not any(line[:2] in ("UU", "AA") for line in lines):
        sys.exit(
            "fixture setup failed in build_fixtures: %r is not left in an unresolved "
            "conflict state in %r. git status --porcelain shows: %r" % (path, where, lines)
        )


IDENT = ["-c", "user.email=cases@example.invalid", "-c", "user.name=cases"]


def _porcelain(where):
    """Return the lines of `git status --porcelain`, the same read the guard makes."""
    status = run_vcs(where, "status", "--porcelain")
    if status.returncode != 0:
        sys.exit(
            "fixture setup failed in build_fixtures: git status --porcelain failed in %r. "
            "stderr: %s" % (where, status.stderr.strip())
        )
    return [line for line in status.stdout.splitlines() if line.strip()]


def _require_clean(where):
    """Stop the suite unless `where` really has an empty working-tree subject.

    The empty-subject cases below prove that an empty subject PASSES. A fixture that is quietly
    dirty would pass them for the wrong reason, the PR #30 defect: a fixture whose setup never
    ran and whose case therefore proved nothing.
    """
    lines = _porcelain(where)
    if lines:
        sys.exit(
            "fixture setup failed in build_fixtures: %r was built to be clean, and git status "
            "--porcelain shows: %r" % (where, lines)
        )


def _require_dirty(where, tracked, untracked, clean_path):
    """Stop the suite unless `where` really holds a modified tracked file, a real untracked file,
    and one tracked path that is NOT in the status output.

    The non-empty cases below prove that a non-empty subject is still refused, and the per-path
    cases prove that a clean path inside a dirty tree passes. Both need each of the three to be
    real, so each one is read back with git itself.
    """
    lines = _porcelain(where)
    if not any(line[1:].strip().endswith(tracked) and line[:2].strip() == "M" for line in lines):
        sys.exit(
            "fixture setup failed in build_fixtures: %r is not modified in %r. git status "
            "--porcelain shows: %r" % (tracked, where, lines)
        )
    if not any(line[:2] == "??" and line[3:].strip().endswith(untracked) for line in lines):
        sys.exit(
            "fixture setup failed in build_fixtures: %r is not untracked in %r. git status "
            "--porcelain shows: %r" % (untracked, where, lines)
        )
    if any(clean_path in line for line in lines):
        sys.exit(
            "fixture setup failed in build_fixtures: %r was built to be clean inside %r, and "
            "git status --porcelain shows it: %r" % (clean_path, where, lines)
        )
    scoped = run_vcs(where, "status", "--porcelain", "--", clean_path)
    if scoped.returncode != 0 or scoped.stdout.strip():
        sys.exit(
            "fixture setup failed in build_fixtures: the path-scoped read of %r in %r is not "
            "empty: exit %d, %r" % (clean_path, where, scoped.returncode, scoped.stdout)
        )


def _require_status(where, expected):
    """Stop the suite unless `git status --porcelain` in `where` lists exactly `expected`.

    The symlink cases below prove only what their fixture is. Each fixture is read back with git
    itself, so a link that git lists differently (a directory, or nothing) stops the run here.
    """
    lines = sorted(_porcelain(where))
    if lines != sorted(expected):
        sys.exit(
            "fixture setup failed in build_fixtures: %r should list %r. git status --porcelain "
            "shows: %r" % (where, sorted(expected), lines)
        )


def _require_stash(where, count):
    """Stop the suite unless `where`'s stash stack really holds `count` entries.

    A fixture that says it has a one-entry stack and holds none would make the `stash drop` case pass
    for the wrong reason. MEASURED lesson from CI: `git stash push` writes a commit, so it needs
    a git identity, and a runner has none unless the call carries one.
    """
    listing = run_vcs(where, "stash", "list")
    if listing.returncode != 0:
        sys.exit(
            "fixture setup failed in build_fixtures: git stash list failed in %r. stderr: %s"
            % (where, listing.stderr.strip())
        )
    lines = [line for line in listing.stdout.splitlines() if line.strip()]
    if len(lines) != count:
        sys.exit(
            "fixture setup failed in build_fixtures: %r was built with %d stash entries, and "
            "git stash list shows %d: %r" % (where, count, len(lines), lines)
        )


def _require_pointer_branch(where, branch):
    """Stop the suite unless `where` is really checked out on `branch`.

    The allowed case below is a move TO `main`, and the refused cases are moves away from it. A
    fixture sitting on some other branch would answer the same decisions for a reason the cases
    were not built to prove, so the branch is read back with git itself.
    """
    head = run_vcs(where, "rev-parse", "--abbrev-ref", "HEAD")
    if head.returncode != 0 or head.stdout.strip() != branch:
        sys.exit(
            "fixture setup failed in build_fixtures: %r was built on %r, and git answers %r. "
            "stderr: %s" % (where, branch, head.stdout.strip(), head.stderr.strip())
        )


def _real_process_start_ms(pid):
    """Return `pid`'s real start time in epoch milliseconds, read apart from the guard's own parse.

    POSIX: `ps -o etime=` gives elapsed run time with no clock or zone, subtracted from now. The
    guard parses `ps -o lstart=` instead, so a zone defect there cannot also sit here and agree
    with it. Windows: copies `_process_start_ms_windows`, not a call into it, for the same reason.
    """
    if sys.platform.startswith("win"):
        import ctypes
        import ctypes.wintypes

        kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            sys.exit(
                "fixture setup failed in build_fixtures: OpenProcess(%d) answered no handle. "
                "GetLastError: %d" % (pid, ctypes.GetLastError())
            )
        try:
            creation = ctypes.wintypes.FILETIME()
            exit_time = ctypes.wintypes.FILETIME()
            kernel_time = ctypes.wintypes.FILETIME()
            user_time = ctypes.wintypes.FILETIME()
            ok = kernel32.GetProcessTimes(
                handle, ctypes.byref(creation), ctypes.byref(exit_time),
                ctypes.byref(kernel_time), ctypes.byref(user_time),
            )
            if not ok:
                sys.exit(
                    "fixture setup failed in build_fixtures: GetProcessTimes(%d) failed." % pid
                )
            value = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
            return value // 10000 - 11644473600000
        finally:
            kernel32.CloseHandle(handle)
    now_ms = time.time() * 1000  # ps latency inflates etime, so this reads early by that latency
    result = subprocess.run(["ps", "-o", "etime=", "-p", str(pid)],
                             capture_output=True, text=True, timeout=5)
    text = result.stdout.strip()
    if result.returncode != 0 or not text:
        sys.exit(
            "fixture setup failed in build_fixtures: `ps -o etime= -p %d` answered nothing. "
            "stderr: %s" % (pid, result.stderr.strip())
        )
    # [[dd-]hh:]mm:ss, the form both procps and macOS BSD ps print
    days, _, clock = text.rpartition("-")
    parts = [int(part) for part in clock.split(":")]
    parts = [0] * (3 - len(parts)) + parts
    elapsed = int(days or 0) * 86400 + parts[0] * 3600 + parts[1] * 60 + parts[2]
    return int(now_ms - elapsed * 1000)


def _require_staged(where, tracked, untracked):
    """Stop the suite unless `where` holds a STAGED edit to `tracked` (index column M, worktree
    column clean) and a STAGED new file `untracked` (index column A).

    The `--merge` cases that use SUBJSTAGED depend on exactly this state: git reverts the staged
    edit and deletes the staged new file. Unstaged work would pass them for the wrong reason, so
    both are read back with git itself.
    """
    lines = _porcelain(where)
    if not any(line[:2] == "M " and line[3:].strip() == tracked for line in lines):
        sys.exit(
            "fixture setup failed in _build_subject: %r is not staged as modified in %r. git "
            "status --porcelain shows: %r" % (tracked, where, lines)
        )
    if not any(line[:2] == "A " and line[3:].strip() == untracked for line in lines):
        sys.exit(
            "fixture setup failed in _build_subject: %r is not staged as new in %r. git status "
            "--porcelain shows: %r" % (untracked, where, lines)
        )


def make_repo(where, files):
    """Build a real checkout holding `files`, committed, with an explicit identity."""
    os.makedirs(where, exist_ok=True)
    run_vcs(where, "init", "-q", "-b", "main", ".")
    for name, text in files.items():
        write(os.path.join(where, name), text)
    run_vcs(where, "add", "-A")
    commit = run_vcs(where, *IDENT, "commit", "-q", "-m", "first")
    if commit.returncode != 0:
        sys.exit(
            "fixture setup failed in build_fixtures: the first commit in %r failed. stderr: %s"
            % (where, commit.stderr.strip())
        )


def make_blind_git(folder):
    """Put a `git` on PATH that answers the repository test and NO status read.

    The unreadable-subject arm needs git to fail to ANSWER, which is not the same as a directory
    that is no git tree. A real repository is still the cwd; only the program answering is blind,
    so the case drives the guard's own "I could not read this" path rather than a mock of it.

    MEASURED on Windows 2026-09-16: a call through
    CreateProcess appends `.exe` and never reads PATHEXT, so a `git.cmd` stand-in would be
    skipped there and the case would answer for the wrong reason. The unreadable-subject cases
    are therefore SKIPPED on Windows rather than run against a stand-in that never answers.
    """
    os.makedirs(folder, exist_ok=True)
    script = os.path.join(folder, "git")
    write(script, "#!/bin/sh\n"
                  "for arg in \"$@\"; do\n"
                  "  if [ \"$arg\" = \"--is-inside-work-tree\" ]; then echo true; exit 0; fi\n"
                  "done\n"
                  "echo 'blind git: no answer' >&2\n"
                  "exit 128\n")
    os.chmod(script, 0o755)


FAKE_GH_PY = r'''import io, json, os, re, sys, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", newline="")  # the bytes go out as written: a text-mode stdout on Windows turns each \n into \r\n, which real gh never does
state = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")))
if state.get("count_file"):  # a test that counts the calls names the file: one line per call, its argv
    with open(state["count_file"], "a", encoding="utf-8") as handle:
        handle.write(json.dumps(sys.argv[1:]) + "\n")
if state.get("delay_s"):
    time.sleep(state["delay_s"])
args = sys.argv[1:]
REPO_ID = 424242424  # the numeric id GitHub names in a Link header; the cloud agent proxy refuses paths that carry it
GRAPHQL = "HTTP 403: GitHub GraphQL is not available from Claude Code sessions; use the REST API (https://api.github.com/graphql)"
if state["cwd_name"] and os.path.basename(os.getcwd()) != state["cwd_name"]:
    state["broken"] = True


def parse(argv):
    """The args after `gh api` -> (path, fields, flags). Query values in the path become fields, as gh sends them."""
    path, fields, flags, i = "", {}, set(), 0
    argv = [part for x in argv for part in (x.split("=", 1) if x.startswith("--") and "=" in x else [x])]
    while i < len(argv):
        a = argv[i]
        if a in ("-X", "--method", "-H", "--header", "-q", "--jq"):
            i += 2
        elif a in ("-f", "-F", "--field", "--raw-field"):
            k, _, v = argv[i + 1].partition("="); fields[k] = v; i += 2
        elif a.startswith("-"):
            flags.add(a); i += 1
        else:
            path = a; i += 1
    path, _, query = path.partition("?")
    for pair in filter(None, query.split("&")):
        k, _, v = pair.partition("="); fields.setdefault(k, v)
    return path, fields, flags


ACCESS_403 = "GitHub access to this repository is not enabled for this session. Use add_repo to request access."  # the 403 an unattached repo answers, as measured
RATE_403 = "API rate limit exceeded for user ID 1."  # the 403 gh prints when the rate limit is spent: no answer about the repo
def api_error(code, message):
    if "-i" in flags:  # gh api -i prints the reply's status line and headers before the body: the status line ends \n, the headers and the blank line \r\n
        sys.stdout.write("HTTP/1.1 %d %s\nContent-Type: application/json\r\n\r\n" % (code, {403: "Forbidden", 404: "Not Found"}.get(code, "Internal Server Error")))
    print(json.dumps({"message": message, "status": str(code)}, separators=(",", ":")) + "gh: %s (HTTP %d)" % (message, code))
    sys.exit(1)


def listing(items, key, fields, flags, top=None, rel=""):
    """What gh prints for a list read: one page unless --paginate; array pages joined; object pages back to back; --slurp one array of pages.
    With -i the status line and headers come first, and a page that more pages follow carries the Link header GitHub sends, on the numeric route."""
    size = max(1, min(int(fields.get("per_page", 30)), state["page_cap"]))
    pages = [items[i:i + size] for i in range(0, len(items), size)] or [[]]
    asked = max(1, int(fields.get("page", 1)))
    chosen = pages if "--paginate" in flags else [pages[asked - 1] if asked <= len(pages) else []]
    bodies = [c if key is None else dict(top or {}, **{key: c}) for c in chosen]
    if "--slurp" in flags:
        body = json.dumps(bodies)
    else:
        body = json.dumps([x for c in chosen for x in c]) if key is None else "".join(json.dumps(b) for b in bodies)
    if "-i" not in flags:
        return body
    link = None
    if "--paginate" not in flags and asked < len(pages):
        def url(page):
            parts = ["%s=%s" % kv for kv in fields.items() if kv[0] != "page"] + ["page=%d" % page]
            return "<https://api.github.com/repositories/%d/%s?%s>" % (REPO_ID, rel, "&".join(parts))
        link = '%s; rel="next", %s; rel="last"' % (url(asked + 1), url(len(pages)))
    return "HTTP/1.1 200 OK\nContent-Type: application/json\r\n%s\r\n%s" % ("Link: %s\r\n" % link if link else "", body)


RUN_OF = {"pass": ("completed", "success"), "fail": ("completed", "failure"), "pending": ("in_progress", None),
          "skipping": ("completed", "skipped"), "cancel": ("completed", "cancelled")}
STATUS_OF = {"pass": "success", "fail": "failure", "pending": "pending", "error": "error"}

path, fields, flags = parse(args[1:]) if args[:1] == ["api"] else ("", {}, set())
if any("&" in a for a in args):  # the Windows .cmd form of this fake lets cmd.exe split the command at '&': send query values with -f
    print("fake gh: an argument holds '&'"); sys.exit(1)
if path:
    # Every REST call names the repo it was asked for (repos/y/x/...), and the pull request read names the number (.../pulls/12).
    for word in state["need"]:
        if ("/" in word and "repos/" + word + "/" not in path) or ("/" not in word and "/pulls/" in path and "/pulls/" + word not in path):
            state["broken"] = True
    if state.get("repos") is not None:  # per-repo answers: a call to a repo the fixture does not name is a broken tool
        named = re.match(r"^repos/([^/{}]+/[^/{}]+)(?:/|$)", path)
        scope = state["repos"].get(named.group(1)) if named else None
        if scope is None:
            state["broken"] = True
        else:
            state.update(repo_mode=True, others=scope.get("others", []), compares=scope.get("compares", {}),
                         default_branch=scope.get("default_branch", "main"), repo_error=scope.get("repo_error"),
                         pulls_error=scope.get("pulls_error"), compare_delay_s=scope.get("compare_delay_s", 0),
                         refs=scope.get("refs", []), tips=scope.get("tips", {}))
while "-R" in args:
    i = args.index("-R")
    del args[i:i + 2]
if state["broken"]:
    print("boom")
    sys.exit(1)
if not args:
    print(json.dumps({"base": state["pr"]["base"]["ref"]}))
elif args[:2] == ["run", "list"]:
    commit = args[args.index("--commit") + 1] if "--commit" in args else ""
    others_runs = {o["head"]: o.get("runs", []) for o in state["others"]}  # another open pull request's runs; the head's are state["runs"]
    print(json.dumps(others_runs[commit] if commit in others_runs else state["runs"]))
elif args[:1] != ["api"]:
    print(GRAPHQL)  # gh pr ..., gh repo view: GraphQL, which a Claude Code cloud session refuses
    sys.exit(1)
else:
    m = re.match(r"^repos/(?:\{owner\}/\{repo\}|[^/{}]+/[^/{}]+)/(.*)$", path)
    rel = m.group(1) if m else ""
    head = state["pr"]["head"]["sha"]
    rows_of = {head: (state["checks"], state["statuses"])}  # the head's own rows; each other open pull request's head has its own
    rows_of.update({o["head"]: (o.get("checks", []), o.get("statuses", [])) for o in state["others"]})
    if state.get("repo_mode") and re.fullmatch(r"repos/[^/{}]+/[^/{}]+", path):  # the repo's own read: its default branch
        if state["repo_error"] == "server":
            api_error(500, "repo read broke")
        if state["repo_error"] == "forbidden":  # the repo is not attached to this session: its own read answers 403
            api_error(403, ACCESS_403)
        if state["repo_error"] == "missing":  # the repo is not on GitHub: its own read answers 404
            api_error(404, "Not Found")
        print(json.dumps({"full_name": path[len("repos/"):], "default_branch": state["default_branch"]}))
    elif re.fullmatch(r"pulls/\d+", rel):
        print(json.dumps(dict(state["pr"], number=int(rel.split("/")[1]))))
    elif rel == "pulls":
        if state.get("pulls_error") and fields.get("state") == state["pulls_error"][0]:  # a list read of that state fails
            if state["pulls_error"][1] == "server":
                api_error(500, "pulls read broke")
            if state["pulls_error"][1] == "forbidden":
                api_error(403, ACCESS_403)
            if state["pulls_error"][1] == "ratelimit":  # a 403 with gh's rate-limit text: the rate limit, not the repo's access
                api_error(403, RATE_403)
            if state["pulls_error"][1] == "missing":
                api_error(404, "Not Found")
            print("<html>a page that is not JSON</html>")
            sys.exit(0)
        others = [dict(state["pr"], number=o["number"], draft=o.get("draft", False), head={"ref": o.get("ref", "feat%d" % o["number"]), "sha": o["head"]},
                       base={"ref": o.get("base", "main"), "repo": {"default_branch": o.get("default_branch", "main")}},
                       state=o.get("state", "open"), merged=o.get("merged", False)) for o in state["others"]]
        rows = ([] if state.get("repo_mode") else [dict(state["pr"], number=state["number"])]) + others  # a repo scope holds its own rows only
        if fields.get("state") == "open":  # GitHub lists a closed or merged pull request only when the read asks for it
            rows = [row for row in rows if row["state"] == "open"]
        if "head" in fields:  # GitHub filters a list read by `head=<owner>:<branch>`: the owner is the repo's, so a bare branch matches none
            owner, _, branch = fields["head"].partition(":")
            rows = [row for row in rows if owner == path.split("/")[1] and row["head"]["ref"] == branch]
        print(listing(rows, None, fields, flags, rel=rel))
    elif re.fullmatch(r"commits/([^/]+)/(check-runs|status)", rel) and rel.split("/")[1] in rows_of:
        checks, statuses = rows_of[rel.split("/")[1]]
        if rel.endswith("check-runs"):
            runs = [{"id": i, "name": c["name"], "status": RUN_OF.get(c["bucket"], ("completed", c["bucket"]))[0],
                     "conclusion": RUN_OF.get(c["bucket"], ("completed", c["bucket"]))[1], "details_url": c["link"] or None,
                     "started_at": None, "completed_at": None} for i, c in enumerate(checks)]
            print(listing(runs, "check_runs", fields, flags, {"total_count": len(runs)}, rel=rel))
        else:
            sts = [{"id": 50 + i, "context": c["name"], "state": STATUS_OF.get(c["bucket"], c["bucket"]), "target_url": c["link"] or None}
                   for i, c in enumerate(statuses)]
            states = {s["state"] for s in sts}
            combined = "failure" if states & {"failure", "error"} else "pending" if (not states or "pending" in states) else "success"
            print(listing(sts, "statuses", fields, flags, {"state": combined, "sha": rel.split("/")[1], "total_count": len(sts)}, rel=rel))
    elif re.fullmatch(r"branches/[^/]+/protection/required_status_checks", rel):
        if state["protection"] == "absent":
            api_error(404, "Branch not protected")
        if state["protection"] == "server":
            api_error(500, "protection read broke")
        if state["protection"] == "network":
            print('Get "https://api.github.com/repos/y/x/branches/main/protection/required_status_checks": dial tcp 140.82.112.6:443: connect: connection refused')
            sys.exit(1)
        print(json.dumps(state["required"]))  # the `--jq .contexts` of the protection read: a JSON array of the required names
    elif re.fullmatch(r"rules/branches/[^/]+", rel):  # the rules that apply to the base: GitHub answers 200 [] when no ruleset applies
        print("[]")
    elif re.fullmatch(r"compare/.+", rel):  # the containment read of "<base>...<head sha>" (a base may hold a slash): a pair not listed is diverged
        if state.get("compare_delay_s"):  # a repo's compare reads each sleep first: one budget shared across them runs out
            time.sleep(state["compare_delay_s"])
        status = state.get("compares", {}).get(rel[len("compare/"):], "diverged")
        if status == "server":  # the read fails, as a server error: the guard cannot tell whether the commits landed
            api_error(500, "compare read broke")
        if status == "forbidden":  # the repo is not attached to this session: the compare answers 403
            api_error(403, ACCESS_403)
        if status == "missing":  # the branch is not in this repo: GitHub answers 404
            api_error(404, "Not Found")
        if status == "network":  # no HTTP status at all: a refused connection
            print('Get "https://api.github.com/' + rel + '": dial tcp 140.82.112.6:443: connect: connection refused')
            sys.exit(1)
        print(json.dumps({"status": status}))
    elif rel.startswith("git/matching-refs/heads/"):  # the refs whose name starts with the prefix, as GitHub's prefix match answers
        prefix = rel[len("git/matching-refs/heads/"):]
        print(json.dumps([{"ref": "refs/heads/" + name, "object": {"sha": state["tips"].get(name, "f" * 40), "type": "commit"}}
                          for name in state["refs"] if name.startswith(prefix)]))
    elif re.fullmatch(r"branches/.+", rel):  # a branch's tip: its commit sha, at f * 40 unless the fixture names one
        name = rel[len("branches/"):]
        print(json.dumps({"name": name, "commit": {"sha": state["tips"].get(name, "f" * 40)}}))
    else:
        api_error(404, "Not Found")
'''


def make_fake_gh(folder, base, delay=0, delay_s=0, checks=None, runs=None, broken=False, need=(),
                 cwd_name="", statuses=None, page_cap=100, others=(), required=("checks",), protection=None,
                 count_file=None, compares=None, repos=None, refs=(), tips=None, head_sha=None, head_ref=None,
                 draft=False):
    """Put a stand-in for the pull request tool in its own folder on PATH.

    `count_file`, when given, is a path the stand-in appends one line to per call (the call's argv as
    JSON), before it answers. Only a case that counts calls names one; every other fake writes nothing.

    `repos`, when given, maps each repo name ("owner/name") to that repo's own answers, for a case whose
    lane spans repos: `compares` (its containment reads; "server" is a 500, "forbidden" a 403, "missing" a 404, "network" a refused
    connection), `others` (its pull requests, rows as `others` takes them), `default_branch` (what its
    own read names; main when unset), `repo_error` ("server": its own read fails with 500; "forbidden": with 403; "missing": with 404), `compare_delay_s` (seconds each of its
    compare reads sleeps before it answers) and `pulls_error`
    ([state, "server", "forbidden", "ratelimit", "missing" or "junk"]: a list read of that state fails with that answer; "ratelimit" is a 403 with gh's rate-limit text). A repo's answers replace the
    top-level ones for the calls that name it. A call to a repo the map does not name is a broken tool.

    MEASURED on Windows 2026-09-16: a call of "gh" through CreateProcess appends `.exe` and never
    reads PATHEXT, so a `gh.cmd` earlier on PATH was skipped and the real `gh.exe` further along
    answered instead. The guard resolves the program with shutil.which for that reason, and this
    stand-in is a `.cmd` file to keep the case honest on this machine.

    The stand-in speaks the REST API the way `gh api` does (c53: a Claude Code cloud session answers
    GraphQL with HTTP 403, and so does this stand-in): the pull request, the open pull requests, the
    check runs of its head and the commit statuses of its head. `statuses` are commit statuses in
    the check-row form; a head with none has the combined state "pending" on GitHub, as here.
    `page_cap` is the page size GitHub gives: a list read takes one page unless it asks for all.

    `delay_s` is a plain float number of seconds, slept inside the fake's own Python process
    before it answers. It needs no external `sleep`/`ping` and so has none of the whole-second or
    PATH-resolution limits `delay` carries below; use it for a measured, fractional or very long
    wait (a realistic `gh` latency, or a stand-in for a `gh` that never answers at all).

    `delay` whole seconds run before the answer. The merge guard's real subprocess.run carries a real
    timeout (MERGE_READ_TIMEOUT). A mutant that shrinks it would race an instant answer instead of
    losing to it: Python's timeout
    clock starts only once communicate() itself runs, and a busy runner can delay THAT call long
    enough for an already-finished child to be read back with no TimeoutExpired at all, whatever
    the nominal timeout was. That is why the mutant SURVIVED on a loaded shared runner (CI run
    35883652442) though the fixture suite was green an hour earlier: the kill depended on wall-clock
    luck, not on the mutant's own defect. A deliberate delay, far past the mutant's 0.0001s and far
    under the real 10s, removes the race instead of hoping the real timeout stays small enough to
    lose it every time.

    The delay tool (`sleep` or `ping`) is resolved to an ABSOLUTE PATH here, with shutil.which on
    this test process's own full PATH, and that absolute path is written into the fake's body. The
    fake itself runs under a narrow PATH the guard builds (its own folder, then only the Python
    interpreter's folder — see PY_PATH), and calling the tool by bare name there is a silent
    no-op on machines where that narrow PATH has no `sleep`/`ping` of its own: on Linux CI
    setup-python's toolcache folder has no `sleep`, and on Windows
    `C:\\Python314` has no `ping`. Both print a "not found" line to stderr and return instantly, so
    the delay never runs and the race make_fake_gh exists to remove comes right back. A missing
    tool is a raise, not a silent skip: a delay fixture that cannot delay is a defect in the
    fixture, not a fact to route around.
    """
    os.makedirs(folder, exist_ok=True)
    # The answers live in a state file, and `ghfake.py` serves them the way the real tool does: `pulls/<n>`
    # the pull request, `pulls` the open ones, `commits/<sha>/check-runs` and `commits/<sha>/status` the
    # checks of its head, `run list` the workflow runs. No argument at all answers the base alone, which is
    # what _verify_fake_gh_delay reads. `broken` answers every call with text that is not JSON.
    state = {
        "pr": {"state": "open", "merged": False, "draft": False, "body": None, "mergeable": True, "mergeable_state": "clean",
               "merge_commit_sha": "e" * 40, "head": {"ref": "feat", "sha": "abc1234"}, "base": {"ref": base}},
        "number": 12,
        "checks": checks if checks is not None else [{"name": "checks", "bucket": "pass", "link": ""}],
        "statuses": statuses if statuses is not None else [],
        "page_cap": page_cap,
        "others": [dict(o) for o in others],  # more pull requests on the base, each {number, head, draft, checks, ref, state, merged}: the batch brake and the archive guard read them; ref defaults to feat<number>, state to open
        "required": list(required),  # the names the base's protection requires
        "protection": protection,  # None: the read answers `required`; "absent": 404; "server": 500; "network": a refused connection
        "compares": dict(compares or {}),  # "<base sha>...<head sha>" -> the status of the containment read; a pair not listed is "diverged"
        "runs": runs if runs is not None else [
            {"status": "completed", "conclusion": "success", "name": "checks"}],
        "broken": broken,
        "cwd_name": cwd_name,   # the folder name a call must run in, or it answers as a broken tool
        "need": list(need),   # words every call must carry, or it answers as a broken tool does
        "delay_s": delay_s,   # seconds to sleep in-process before answering; see the delay_s note above
        "count_file": count_file,  # None: no call log; a path: one line per call (see the docstring)
        "repos": None if repos is None else dict(repos),  # None: one repo, the top-level answers; a map: see the docstring
        "refs": list(refs),  # branch names the repo holds: the matching-refs read answers the ones under its prefix
        "tips": dict(tips or {}),  # branch name -> the sha of its tip; a branch not listed is at f * 40
    }
    if head_sha:  # the pull request's own head, when a case names a real commit (records-page-ready); its draft flag too
        state["pr"]["head"] = {"ref": head_ref or "feat", "sha": head_sha}
        state["pr"]["draft"] = draft
    write(os.path.join(folder, "state.json"), json.dumps(state))
    write(os.path.join(folder, "ghfake.py"), FAKE_GH_PY)
    fake_py = os.path.join(folder, "ghfake.py")
    if os.name == "nt":
        tool = shutil.which("ping", path=os.environ.get("PATH")) if delay else None
        if delay and not tool:
            raise RuntimeError(
                "make_fake_gh: delay=%d requested but 'ping' is not on this process's PATH" % delay
            )
        # Both streams to nul, not stdout alone: cmd.exe redirects only what it is told to, so an
        # unredirected stderr handle stays inherited into `ping` and keeps the REAL captured pipe
        # open for ping's whole run. MEASURED: with stdout alone redirected, a delay far past
        # SH_TIMEOUT (GHHANG, 30s wait vs. a 3s kill) left communicate() blocked on that still-open
        # handle for the ping's full duration, not the ~3s the kill should have bounded it to.
        wait = ('"%s" -n %d 127.0.0.1 >nul 2>&1\r\n' % (tool, delay + 1)) if delay else ""
        write(os.path.join(folder, "gh.cmd"), "@echo off\r\n" + wait
              + '"%s" "%s" %%*\r\n' % (sys.executable, fake_py))
    else:
        script = os.path.join(folder, "gh")
        tool = shutil.which("sleep", path=os.environ.get("PATH")) if delay else None
        if delay and not tool:
            raise RuntimeError(
                "make_fake_gh: delay=%d requested but 'sleep' is not on this process's PATH" % delay
            )
        wait = ("%s %d\n" % (tool, delay)) if delay else ""
        write(script, "#!/bin/sh\n" + wait + 'exec "%s" "%s" "$@"\n' % (sys.executable, fake_py))
        os.chmod(script, 0o755)


def _verify_fake_gh_delay(ghdir, delay):
    """Fail fixture setup if the delayed gh fake in `ghdir` does not actually delay.

    Runs the fake under the exact PATH the guard itself gets when it is asked about that base
    (`ghdir` first, then only the Python interpreter's own folder: see PY_PATH). This is the
    check that goes red on the defect make_fake_gh's absolute-path fix
    repairs: a delay tool resolved by bare name can silently vanish on that narrow PATH, and the
    fake then answers instantly with an error on stderr instead of raising or waiting.
    """
    py_path = os.path.dirname(sys.executable)
    env = dict(os.environ)
    env["PATH"] = ghdir + os.pathsep + py_path
    program = shutil.which("gh", path=env["PATH"])
    if not program:
        sys.exit(
            "fixture check failed in _verify_fake_gh_delay: no 'gh' fake resolvable on "
            "PATH=%r" % env["PATH"]
        )
    started = time.time()
    result = subprocess.run([program], capture_output=True, text=True, env=env, timeout=60)
    elapsed = time.time() - started
    if result.stderr.strip():
        sys.exit(
            "fixture check failed in _verify_fake_gh_delay: the delayed gh fake in %r wrote to "
            "stderr instead of delaying %ds (PATH=%r): %r"
            % (ghdir, delay, env["PATH"], result.stderr.strip())
        )
    if elapsed < delay:
        sys.exit(
            "fixture check failed in _verify_fake_gh_delay: the delayed gh fake in %r answered "
            "in %.3fs, under its %ds delay (PATH=%r) -- the delay tool resolved to nothing "
            "real on this PATH" % (ghdir, elapsed, delay, env["PATH"])
        )


UNDERTESTS = os.path.join(ROOT, "tests", "clone")   # a repo whose own folder sits under `tests`


LINKS_MADE = False  # set by build_fixtures; True only where os.symlink works


# Lazy fixtures. A block that runs git or builds a repo is a builder, run the first time a case
# names one of its paths (`materialize_for`, from decide). A path is matched as text, after slash(),
# in the fields the guard reads: cwd, env_path, config, transcript, raw and the tool_input values.
# A log check builds its own fixtures in its own code, so `materialize_all` runs before the logs.
# A builder's paths are every path it creates. Keep the list whole, or a case reads a missing folder.
LAZY = {}  # slash(path) -> the once() that builds its builder


def lazy_fixture(paths, build):
    """Register `build` (run once, the first time a case names one of `paths`) for every path."""
    done = []

    def once():
        if not done:
            done.append(1)
            beat("fixture %s, before it builds" % build.__name__)
            _timed(build.__name__, build)
            beat("fixture %s, after it built" % build.__name__)
    for path in paths:
        LAZY[slash(path)] = once


def materialize(path):
    once = LAZY.get(slash(path)) if path else None
    if once:
        once()


def materialize_for(case):
    """Build every lazy fixture that a case's own fields name, before the case runs."""
    fields = [case.get(k) for k in ("cwd", "env_path", "config", "transcript", "raw", "guard")]
    fields += list(case.get("tool_input", {}).values())
    text = slash(" ".join(str(f) for f in fields if f is not None))
    for key, once in list(LAZY.items()):
        if key in text:
            once()


def materialize_all():
    """Build every lazy fixture except the diff repos and the conflict-markers repos. A log check builds
    its own diff repos (see diff_repo), so the run loop need not build all ~170 of them for any log check.
    No log check reads a conflict-markers repo: a case builds one through materialize_for, when it names it."""
    for key, once in list(LAZY.items()):
        if slash(DIFFROOT) not in key and not key.startswith(slash(CMKROOT) + "/"):
            once()


def build_fixtures():
    """The EAGER fixtures: config folders, fake gh files, message files and the link probe. Each git
    repo is a builder below, and it is built on first use."""
    global LINKS_MADE, SYMWT_MADE
    for folder in (CFG, LOGDIR, PROJ, CLONE, NOGIT, os.path.join(UNDERTESTS, ".git"),
                   os.path.join(ROOT, "tmp")):   # the temp folder the silent-write cases read
        os.makedirs(folder, exist_ok=True)
    write(os.path.join(CFG, "settings.json"), "{}\n")
    write(os.path.join(CFG, "CLAUDE.md"), "rules\n")
    write(os.path.join(CFG, "hooks", "guard.py"), "# hook\n")
    write(os.path.join(CFG, "lint", "prose.py"), "# lint\n")
    write(os.path.join(CFG, "agents", "builder.md"), "builder\n")
    write(os.path.join(PROJ, ".claude", "settings.json"), "{}\n")
    write(os.path.join(PROJ, ".claude", "settings.local.json"), "{}\n")
    write(os.path.join(PROJ, ".claude", "hooks", "g.py"), "# hook\n")
    write(os.path.join(PROJ, "src", "app.py"), "print(1)\n")
    # The clone of claude-settings. Its own settings.json is the SOURCE the install script copies,
    # so it must stay editable. The marker files tell the clone from a config folder, and the install
    # script is the one that makes the pin, so a folder beside a clone that holds it is a pin.
    write(os.path.join(CLONE, "settings.json"), "{}\n")
    write(os.path.join(CLONE, "install.ps1"), "# install\n")
    write(os.path.join(CLONE, "merge", "install_from_main.sh"), "# install\n")
    make_fake_gh(GHMAIN, "main")
    write(MSG_BAD, "title\n\ncites decisions/one-shared-record-stamp.md\n")
    write(MSG_OK, "title\n\ncites D12, short titles for records\n")
    write(MSG_LANE, "title\n\nLane N20 lands the guard.\n")
    write(MSG_FENCE, "title\n\n```\nLane N20 lands the guard.\n```\n")
    write(MSG_NOGIT, "title\n\nclean body\n")
    write(SCRATCH_MSG, "title\n\nthe message another agent wrote\n")
    write(SCRATCH_EMPTY, "")
    write(SCRATCH_OTHER_MSG, "title\n\nthe message of another session\n")
    write(TILDE_MSG, "title\n\nthe message the agent wrote\n")
    write(PATHSPEC_LIST, "f.txt\n")
    make_fake_gh(GHPEND, "main", checks=[{"name": "checks", "bucket": "pending", "link": ""}])
    make_fake_gh(GHRED, "main", checks=[{"name": "checks", "bucket": "fail", "link": ""}])
    make_fake_gh(GHRUNPEND, "main",
                 runs=[{"status": "in_progress", "conclusion": "", "name": "checks"}])
    make_fake_gh(GHBROKEN, "main", broken=True)
    make_fake_gh(GHBLANK, "", )
    make_fake_gh(GHNEED, "main", need=["12", "y/x"])
    make_fake_gh(GHBATCH, "main", others=batch_other(("checks", "pending")))
    make_fake_gh(GHBATCHDONE, "main", others=batch_other(("checks", "pass")))
    make_fake_gh(GHBATCHRED, "main", others=batch_other(("checks", "fail")))
    # Pull request 1's head is the fake's default head. The base read, "main...<that head>", is ahead when that head holds main's tip, behind when it does not.
    make_fake_gh(GHBATCHCONTAIN, "main", others=batch_other(("checks", "pending")),
                 compares={"abc1234...pr-two-head": "ahead", "main...abc1234": "ahead"})
    make_fake_gh(GHBATCHDIVERGED, "main", others=batch_other(("checks", "pending")), compares={"abc1234...pr-two-head": "diverged"})
    make_fake_gh(GHBATCHBEHIND, "main", others=batch_other(("checks", "pending")),
                 compares={"abc1234...pr-two-head": "ahead", "main...abc1234": "behind"})
    # the guard's required names: a pinned list, or the branch protection (none, failed, or a list that is not pinned)
    make_fake_gh(GHPINNED, "main", others=batch_other(("checks", "pass"), ("gate", "pending")), required=["gate"])
    make_fake_gh(GHNOPROT, "main", others=batch_other(("sync", "pending")), protection="absent")
    make_fake_gh(GHNOPROTDONE, "main", others=batch_other(("sync", "pass")), protection="absent")
    make_fake_gh(GHPROT500, "main", others=batch_other(("checks", "pass")), protection="server")
    make_fake_gh(GHPROTNET, "main", others=batch_other(("checks", "pass")), protection="network")
    make_fake_gh(GHRUNBLOCK, "main", others=batch_other(("scope", "pending"), runs=[{"name": "ci-checks", "status": "in_progress", "conclusion": None}]))
    make_fake_gh(GHRUNNONE, "main", others=batch_other(runs=[{"name": "ci-checks", "status": "queued", "conclusion": None}]))
    make_fake_gh(GHRUNDONE, "main", others=batch_other(("checks", "pass"), runs=[{"name": "ci-checks", "status": "completed", "conclusion": "success"}]))
    make_fake_gh(GHRUNIGNORED, "main", others=batch_other(("checks", "pass"), runs=[{"name": "sync", "status": "in_progress", "conclusion": None}]))
    # merge.py's shared_deadline splits one budget across the read's calls (c53: four on REST: the pull request, the check
    # runs, the commit statuses, the workflow runs), so a delay only a little past the per-call figure that used to be the
    # cutoff no longer exhausts it. 20s per call outruns the whole shared budget on its own, whichever call absorbs the
    # time: keep it above MERGE_READ_TIMEOUT.
    make_fake_gh(GHSLOW, "main", delay=20)
    # 3.5s per call stands in for real gh latency (3.0-3.9s, measured on Windows for gh's GraphQL calls): nowhere near a hang.
    # c53: the read makes four REST calls, 4 * 3.5s = 14s, which fits the 25s MERGE_READ_TIMEOUT (the slowest measured call, 3.9s,
    # makes 15.6s). The latency of a REST call is unmeasured, so the figure stays the measured one.
    make_fake_gh(GHWARM, "main", delay_s=3.5)
    # A `gh` that never answers at all. MEASURED on Windows: this fake is a `.cmd`, so the
    # process subprocess.run actually kills on timeout is cmd.exe, never the ping (or python)
    # it spawned for the wait -- Windows hands that child a full set of inherited handles
    # REGARDLESS of its own `>nul 2>&1` redirection, so the real captured pipe stays open and
    # communicate() blocks for the WHOLE configured wait, not just until the kill. One gh call
    # is all head_read ever attempts before an exception ends the read (see merge_hang_timeout_case
    # below), so 10s bounds the real wait on this fixture's worst case here, and bounds it far
    # more tightly still on a platform (POSIX CI) where the kill lands cleanly.
    make_fake_gh(GHHANG, "main", delay=10)
    make_fake_gh(GHEMPTY, "main", checks=[], runs=[])
    make_fake_gh(GHCWD, "main", cwd_name="ctxrepo")
    make_fake_gh(GHSTATPEND, "main", statuses=[{"name": "deploy", "bucket": "pending", "link": ""}])
    make_fake_gh(GHSTATRED, "main", statuses=[{"name": "deploy", "bucket": "fail", "link": ""}])
    make_fake_gh(GHPAGE2, "main", page_cap=2, checks=[{"name": "lint", "bucket": "pass", "link": ""},
                                                      {"name": "unit", "bucket": "pass", "link": ""},
                                                      {"name": "checks", "bucket": "fail", "link": ""}])
    write(os.path.join(WFREPO, ".github", "workflows", "checks.yml"), "name: checks\n")
    # The guard finds the merge tool beside its own real path, or in the clone the global rules
    # file points at. A mutant copy of the guard sits in a temp folder and takes the second way.
    write(os.path.join(MERGECFG, "CLAUDE.md"), "@" + slash(REPO) + "/CLAUDE.md\n")
    # GHDEV alone gets the delay: it is the one base whose logged/not-logged answer the timeout
    # mutant can flip (GHMAIN and GHNONE both expect "logged" either way), so it is the one fixture
    # whose instant reply could race that mutant's shrunk timeout. See make_fake_gh's docstring.
    make_fake_gh(GHDEV, "dev", delay=1)
    # lane-closes-after-records. `need` pins the repo the guard reads: from the lane's cs-repo tag, as `repos/o/r/...`.
    # A call that names another repo, or `{owner}/{repo}`, answers as a broken tool.
    slug_head = {"number": 13, "head": "d" * 40, "ref": ARCHIVE_HEAD}
    make_fake_gh(ARCHOPEN, "main", need=["o/r"], others=[slug_head])
    make_fake_gh(ARCHCLOSED, "main", need=["o/r"], others=[dict(slug_head, state="closed")])
    make_fake_gh(ARCHMERGED, "main", need=["o/r"], others=[dict(slug_head, state="closed", merged=True)])
    # The same lane's pull request on the `lane/<slug>` head form (decision session-tiers names both forms).
    make_fake_gh(ARCHOPEN_LANE, "main", need=["o/r"], others=[dict(slug_head, ref="lane/" + ARCHIVE_SLUG)])
    # The agent record's step has the open pull request, and the main record's step has none (see the agent cases).
    make_fake_gh(ARCHOPEN_AGENT, "main", need=["o/r"], others=[dict(slug_head, ref=ARCH_AGENT_SLUG)])
    # Page two of the open list (two rows a page): the slug's pull request is the third row, so only a read of
    # every page sees it. The two rows before it name other lanes.
    make_fake_gh(ARCHPAGE, "main", need=["o/r"], page_cap=2, others=[
        {"number": 13, "head": "1" * 40, "ref": "claude/other-lane-x1"},
        {"number": 14, "head": "2" * 40, "ref": "claude/other-lane-x2"},
        dict(slug_head, number=15, head="3" * 40)])
    # Open pull requests on a near-miss head, one per fake. Each holds a lane's id or slug as a substring only: an
    # exact read of the open list allows an archive of the lane named in the case beside it.
    make_fake_gh(ARCHNEAR_C10, "main", need=["o/r"], others=[dict(slug_head, number=13, ref="c10")])
    make_fake_gh(ARCHNEAR_C10X, "main", need=["o/r"], others=[dict(slug_head, number=13, ref="claude/c10-x1")])
    make_fake_gh(ARCHNEAR_CI, "main", need=["o/r"], others=[dict(slug_head, number=13, ref="claude/fix-ci-retry-x1")])
    # The containment read is keyed "main...<head sha>" (the base's name, then the head's sha, as the compare API takes them).
    draft_pair = "main..." + slug_head["head"]
    draft_rows = [dict(slug_head, draft=True)]
    make_fake_gh(ARCHDRAFT_BEHIND, "main", need=["o/r"], others=draft_rows, compares={draft_pair: "behind"})
    make_fake_gh(ARCHDRAFT_IDENT, "main", need=["o/r"], others=draft_rows, compares={draft_pair: "identical"})
    make_fake_gh(ARCHDRAFT_AHEAD, "main", need=["o/r"], others=draft_rows, compares={draft_pair: "ahead"})
    make_fake_gh(ARCHDRAFT_DIVERGED, "main", need=["o/r"], others=draft_rows, compares={draft_pair: "diverged"})
    # A ready pull request, not a draft: its head behind main does not release it, so the refusal stands.
    make_fake_gh(ARCHREADY_BEHIND, "main", need=["o/r"], others=[dict(slug_head)], compares={draft_pair: "behind"})
    make_fake_gh(ARCHDRAFT_READFAIL, "main", need=["o/r"], others=draft_rows, compares={draft_pair: "server"})
    # A draft based on integration/b1, whose head is behind both main and integration/b1. The rule refuses it, because
    # its base is not the repo's default branch. A guard that compares against the base's name would release it here.
    make_fake_gh(ARCHDRAFT_INTEG, "main", need=["o/r"], others=[dict(slug_head, draft=True, base="integration/b1")],
                 compares={draft_pair: "behind", "integration/b1..." + slug_head["head"]: "behind"})
    # An open draft on the `lane/<slug>` head form, its head behind main: released as the bare-slug draft is.
    make_fake_gh(ARCHDRAFT_LANE_BEHIND, "main", need=["o/r"],
                 others=[dict(slug_head, draft=True, ref="lane/" + ARCHIVE_SLUG)], compares={draft_pair: "behind"})
    # The branch read: each fake names both repos of the incident (`repos`), so no call may name another.
    make_fake_gh(ARCHINC_NOPR, "main", repos=arch_pair())
    make_fake_gh(ARCHINC_OTHERPR, "main", repos=arch_pair(qmax={"others": [arch_row(ARCH_BRANCH_OTHER, 21)]}))
    # A merged pull request whose head is the branch tip: the squash left the branch at that head, so it is covered.
    make_fake_gh(ARCHINC_MERGED, "main", repos=arch_pair(qmax={
        "others": [arch_row(ARCH_BRANCH, 22, state="closed", merged=True)], "tips": {ARCH_BRANCH: "%040d" % 22}}))
    # The same merged pull request, and a commit after it: the tip is past the head, so the merged pull request does not cover it.
    make_fake_gh(ARCHINC_MERGEDMOVED, "main", repos=arch_pair(qmax={
        "others": [arch_row(ARCH_BRANCH, 22, state="closed", merged=True)], "tips": {ARCH_BRANCH: NEW_TIP}}))
    # A closed pull request with no replacement: nothing open or merged holds the branch's work, so it is not covered.
    make_fake_gh(ARCHINC_CLOSEDALONE, "main", repos=arch_pair(qmax={"others": [arch_row(ARCH_BRANCH, 23, state="closed")]}))
    # A closed pull request, replaced by a merged one whose head contains the tip: the one compare of the replacing head with
    # the tip reads behind (the tip is an ancestor of it), so the closed pull request covers the branch.
    make_fake_gh(ARCHINC_CLOSED, "main", repos=arch_pair(qmax={
        "others": [arch_row(ARCH_BRANCH, 23, state="closed"), arch_row(ARCH_BRANCH, 24, state="closed", merged=True)],
        "tips": {ARCH_BRANCH: REPLACED_TIP},
        "compares": {"main..." + ARCH_BRANCH: "ahead", REPLACING_HEAD + "..." + REPLACED_TIP: "behind"}}))
    # A left branch under the lane's slug forms: the bare slug's `-r2` variant and the `lane/` form, ahead of main.
    # Each left-branch fake names its repo (`repos`), as the multi-read fixtures do: the repo read answers its default branch.
    make_fake_gh(ARCHLEFT_NOPR, "main", repos={"o/r": {"refs": ["lane/" + ARCHIVE_SLUG + "-r2"],
                 "compares": {"main...lane/" + ARCHIVE_SLUG + "-r2": "ahead"}}})
    make_fake_gh(ARCHLEFT_PR, "main", repos={"o/r": {"refs": ["lane/" + ARCHIVE_SLUG + "-r2"],
                 "compares": {"main...lane/" + ARCHIVE_SLUG + "-r2": "ahead"},
                 "others": [{"number": 40, "head": "%040d" % 40, "ref": "lane/" + ARCHIVE_SLUG + "-r2"}]}})
    # A ref that starts with the slug but is no `-*` variant of it: the prefix read returns it, the form match drops it.
    make_fake_gh(ARCHLEFT_NEAR, "main", repos={"o/r": {"refs": [ARCHIVE_SLUG + "x"],
                 "compares": {"main..." + ARCHIVE_SLUG + "x": "ahead"}}})
    # A closed pull request on lane/<slug>, replaced by a merged one on lane/<slug>-r2: contained in the replacing head, or not.
    make_fake_gh(ARCHLEFT_REPLACED, "main", repos={"o/r": arch_replaced("behind")})
    make_fake_gh(ARCHLEFT_REPLACED_AHEAD, "main", repos={"o/r": arch_replaced("ahead")})
    # A lane branch ahead of main on no pull request, whose archive/ copy holds its tip (identical) or is older (ahead).
    make_fake_gh(ARCHCOPY_IDENT, "main", repos={"o/r": arch_copy("identical")})
    make_fake_gh(ARCHCOPY_AHEAD, "main", repos={"o/r": arch_copy("ahead")})
    make_fake_gh(ARCHCOPY_MISSING, "main", repos={"o/r": arch_copy("missing")})
    make_fake_gh(ARCHCOPY_NUMBERED, "main", repos={"o/r": arch_copies({ARCH_COPY_REF: "diverged",
                                                                       ARCH_COPY_REF + "-2": "identical"})})
    make_fake_gh(ARCHCOPY_NUMBERED_NONE, "main", repos={"o/r": arch_copies({ARCH_COPY_REF: "diverged",
                                                                            ARCH_COPY_REF + "-2": "ahead"})})
    make_fake_gh(ARCHCOPY_LOOKALIKE, "main", repos={"o/r": arch_copies({ARCH_COPY_REF + "y": "identical"})})
    make_fake_gh(ARCHCOPY_SUFFIX_R2, "main", repos={"o/r": arch_copies({ARCH_COPY_REF + "-r2": "identical"})})
    make_fake_gh(ARCHINC_OPEN, "main", repos=arch_pair(qmax={"others": [arch_row(ARCH_BRANCH, 24)]}))
    make_fake_gh(ARCHINC_BEHIND, "main", repos=arch_pair(qmax={"compares": {"main..." + ARCH_BRANCH: "behind"}}))
    make_fake_gh(ARCHINC_IDENT, "main", repos=arch_pair(qmax={"compares": {"main..." + ARCH_BRANCH: "identical"}}))
    # The default branch is judged by no compare: an unlisted pair is diverged (ahead), so a guard that judged it would refuse.
    make_fake_gh(ARCHINC_DEFAULT, "main", repos=arch_pair(qmax={"compares": {}}, settings={"compares": {}}))
    make_fake_gh(ARCHINC_ARCHIVE, "main", repos=arch_pair(qmax={"compares": {"main...archive/claude/x": "ahead"}}))
    make_fake_gh(ARCHINC_404ALL, "main", repos=arch_pair(qmax={"compares": {"main..." + ARCH_BRANCH: "missing"}}))
    make_fake_gh(ARCHINC_COMPARE500, "main", repos=arch_pair(qmax={"compares": {"main..." + ARCH_BRANCH: "server"}}))
    make_fake_gh(ARCHINC_NETWORK, "main", repos=arch_pair(qmax={"compares": {"main..." + ARCH_BRANCH: "network"}}))
    make_fake_gh(ARCHINC_PULLS500, "main", repos=arch_pair(qmax={"pulls_error": ["all", "server"]}))
    make_fake_gh(ARCHINC_PULLSJUNK, "main", repos=arch_pair(qmax={"pulls_error": ["all", "junk"]}))
    make_fake_gh(ARCHINC_REPO500, "main", repos=arch_pair(qmax={"repo_error": "server"}))
    make_fake_gh(ARCHINC_TRUNK, "main", repos=arch_pair(qmax={"default_branch": "trunk",
                                                             "compares": {"main..." + ARCH_BRANCH: "behind",
                                                                          "trunk..." + ARCH_BRANCH: "ahead"}}))
    make_fake_gh(ARCHINC_DIVERGED, "main", repos=arch_pair(qmax={"compares": {"main..." + ARCH_BRANCH: "diverged"}}))
    # q_max's own read answers 404: the repo is named only through a source, and it is not on GitHub.
    make_fake_gh(ARCHINC_REPO404, "main", repos=arch_pair(qmax={"repo_error": "missing"}))
    # The open pull request list of one repo fails and the other's answers, so the archive's first read that fails names its repo.
    make_fake_gh(ARCHINC_OPENLIST_QMAX, "main", repos=arch_pair(qmax={"pulls_error": ["open", "server"]}))
    make_fake_gh(ARCHINC_OPENLIST_SETTINGS, "main", repos=arch_pair(settings={"pulls_error": ["open", "server"]}))
    # An unattached repo answers 403 (measured), and a repo gh cannot find answers 404. Each one fails its own read only.
    make_fake_gh(ARCHINC_OPENLIST403_QMAX, "main", repos=arch_pair(qmax={"pulls_error": ["open", "forbidden"]}))
    make_fake_gh(ARCHINC_OPENLIST_RATELIMIT_QMAX, "main", repos=arch_pair(qmax={"pulls_error": ["open", "ratelimit"]}))
    make_fake_gh(ARCHINC_OPENLIST404_SETTINGS, "main", repos=arch_pair(settings={"pulls_error": ["open", "missing"]}))
    make_fake_gh(ARCHINC_PULLS403, "main", repos=arch_pair(qmax={"pulls_error": ["all", "forbidden"]}))
    make_fake_gh(ARCHINC_PULLS404, "main", repos=arch_pair(qmax={"pulls_error": ["all", "missing"]}))
    make_fake_gh(ARCHINC_REPO403, "main", repos=arch_pair(qmax={"repo_error": "forbidden"}))
    make_fake_gh(ARCHINC_COMPARE403, "main", repos=arch_pair(qmax={"compares": {"main..." + ARCH_BRANCH: "forbidden"}}))
    # Each compare of q_max sleeps 13s, under MERGE_READ_TIMEOUT (25s) alone. The two branches are behind main, so a
    # read that runs both sums past one budget. A delay on every call would stretch the run past a minute.
    make_fake_gh(ARCHINC_SLOW, "main", repos=arch_pair(qmax={
        "compares": {"main..." + ARCH_SLOW_A: "behind", "main..." + ARCH_SLOW_B: "behind"}, "compare_delay_s": 13}))
    # One read budget runs across the slug draft's containment read and the branch read after it. Each compare of q_max
    # sleeps 13s, under MERGE_READ_TIMEOUT (25s) alone. The draft's head is behind main, so only the branch read can refuse.
    make_fake_gh(ARCHDRAFT_SLOW, "main", repos=arch_pair(qmax={
        "others": [dict(slug_head, draft=True)],
        "compares": {"main..." + slug_head["head"]: "behind", "main..." + ARCH_BRANCH: "ahead"}, "compare_delay_s": 13}))
    os.makedirs(GHNONE, exist_ok=True)
    found = shutil.which("gh", path=GHNONE_PATH)
    if found:
        sys.exit("fixture check failed: the 'gh missing' PATH %r resolves a real gh at %r"
                 % (GHNONE_PATH, found))
    # The link probe, read at import: registration reads LINKS_MADE and SYMWT_MADE, and the link
    # fixtures themselves are built lazily. One link in ROOT asks the same privilege they need.
    try:
        os.symlink(ROOT, os.path.join(ROOT, "linkprobe"), target_is_directory=True)
        LINKS_MADE = SYMWT_MADE = True
    except Exception:  # no symlink privilege: the link cases skip, as they did before
        LINKS_MADE = SYMWT_MADE = False
    if LINKS_MADE:   # the scratchpad links (scratchpad-message), made only where the probe above made one
        os.symlink(SCRATCH_MSG, SCRATCH_LINK_IN)
        os.symlink(MSG_NOGIT, SCRATCH_LINK_OUT)


def _build_currepo():
    """CURREPO: a repo on the branch `feat`. The fake gh lists one open pull request whose head is `feat`, so a merge named by no number reads that one."""
    os.makedirs(CURREPO, exist_ok=True)
    run_vcs(CURREPO, "init", "-q", "-b", "feat", ".")
    run_vcs(CURREPO, *IDENT, "commit", "-q", "--allow-empty", "-m", "first")


def _build_ctxrepo():
    """CTXREPO: a repo on main with one branch, `done`. GHCWD's fake gh checks it by folder name."""
    os.makedirs(CTXREPO, exist_ok=True)
    run_vcs(CTXREPO, "init", "-q", "-b", "main", ".")
    run_vcs(CTXREPO, *IDENT, "commit", "-q", "--allow-empty", "-m", "first")
    run_vcs(CTXREPO, "branch", "done")


GHDEV_CHECK = {}  # the delay check's thread, and the error it raised, if it raised one


def _run_ghdev_check():
    try:
        _verify_fake_gh_delay(GHDEV, delay=1)
    except BaseException as exc:  # _build_ghdev raises it, on the thread that needs the answer
        GHDEV_CHECK["error"] = exc


def _start_ghdev_check():
    """Run the delay check on a daemon thread. Called once, after build_fixtures has written GHDEV's fake."""
    thread = threading.Thread(target=_run_ghdev_check, name="ghdev-delay-check", daemon=True)
    GHDEV_CHECK["thread"] = thread
    thread.start()


def _build_ghdev():
    # Trust this delay only once it is proven, not assumed: the check runs under the guard's own
    # narrow PATH and fails fixture setup outright if it does not really delay. See
    # _verify_fake_gh_delay's docstring for the defect this catches. It takes about a second and starts
    # with the fixtures, so this waits only for what is left of it, and a run that never names
    # GHDEV never waits.
    GHDEV_CHECK["thread"].join()
    if "error" in GHDEV_CHECK:
        raise GHDEV_CHECK["error"]


def _build_gitmain():
    """GITMAIN, its linked worktrees, and DECOYMAIN. The DOTDOTWT and SYMWT checks ride on it."""
    os.makedirs(GITMAIN, exist_ok=True)
    # A real checkout and a real linked worktree of it. The shared-tree rule asks git which is
    # which, so no fake will do.
    #
    # BOTH TREES CARRY REAL UNCOMMITTED WORK. The four worktree cases below are about the
    # deny-or-ask SPLIT, and the rule reads the subject first, so a clean tree there would
    # pass on the empty subject and prove nothing about the split.
    run_vcs(GITMAIN, "init", "-q", "-b", "main", ".")
    run_vcs(GITMAIN, *IDENT, "commit", "-q", "--allow-empty", "-m", "first")
    write(os.path.join(GITMAIN, "docs", "DEBTS.md"), "base\n")
    write(os.path.join(GITMAIN, "f.txt"), "base\n")
    write(os.path.join(GITMAIN, "keep.txt"), "base\n")
    # The per-file cases name these three: two JSON fixtures a lane regenerates, and a source file
    # for the folder case. All three are tracked, so each one is a real subject once modified.
    write(os.path.join(GITMAIN, "fixtures", "a.json"), "base\n")
    write(os.path.join(GITMAIN, "fixtures", "media-players.json"), "base\n")
    write(os.path.join(GITMAIN, "src", "app.py"), "base\n")
    # The per-file allow cases also name two root files, a.txt and b.txt, and a folder, hooks/. A
    # bare `checkout hooks` must read as a folder: the folder is tracked and each tree modifies it.
    write(os.path.join(GITMAIN, "a.txt"), "base\n")
    write(os.path.join(GITMAIN, "b.txt"), "base\n")
    write(os.path.join(GITMAIN, "hooks", "guard.py"), "base\n")
    # The last-bullets cases name README.md as a restore operand. It is tracked and modified in
    # every tree, so each one is a real subject.
    write(os.path.join(GITMAIN, "README.md"), "base\n")
    # The bare-checkout cases name an extensionless root file, Makefile, and one under a folder,
    # tools/runner. LICENSE is never modified: it is the clean-path control.
    write(os.path.join(GITMAIN, "Makefile"), "base\n")
    write(os.path.join(GITMAIN, "tools", "runner"), "base\n")
    write(os.path.join(GITMAIN, "LICENSE"), "base\n")
    # The gate rows below name two more root files, both extensionless: hotfix, which is also a
    # branch, and staged-note, which is staged in the shared checkout only.
    write(os.path.join(GITMAIN, "hotfix"), "base\n")
    write(os.path.join(GITMAIN, "staged-note"), "base\n")
    run_vcs(GITMAIN, "add", "-A")
    run_vcs(GITMAIN, *IDENT, "commit", "-q", "-m", "files")
    run_vcs(GITMAIN, "branch", "hotfix")
    run_vcs(GITMAIN, "worktree", "add", "-q", GITWT, "-b", "lane")
    # AGENTWT: a real linked worktree whose path sits under GITMAIN's own .claude/worktrees/.
    # FARWT: a real linked worktree elsewhere, at a path that merely contains the word
    # "worktrees" (mimics an unrelated /tmp/worktrees/x), so the agent-owned check must read the
    # path's PREFIX, not just test for the substring.
    run_vcs(GITMAIN, "worktree", "add", "-q", AGENTWT, "-b", "agent-x-branch")
    run_vcs(GITMAIN, "worktree", "add", "-q", FARWT, "-b", "stray-branch")
    for _tree in (GITMAIN, GITWT, AGENTWT, FARWT):
        write(os.path.join(_tree, "docs", "DEBTS.md"), "uncommitted\n")
        write(os.path.join(_tree, "f.txt"), "uncommitted\n")
        write(os.path.join(_tree, "new.txt"), "untracked\n")
        write(os.path.join(_tree, "fixtures", "a.json"), "uncommitted\n")
        write(os.path.join(_tree, "fixtures", "media-players.json"), "uncommitted\n")
        write(os.path.join(_tree, "src", "app.py"), "uncommitted\n")
        write(os.path.join(_tree, "a.txt"), "uncommitted\n")
        write(os.path.join(_tree, "b.txt"), "uncommitted\n")
        write(os.path.join(_tree, "hooks", "guard.py"), "uncommitted\n")
        write(os.path.join(_tree, "README.md"), "uncommitted\n")
        write(os.path.join(_tree, "Makefile"), "uncommitted\n")
        write(os.path.join(_tree, "tools", "runner"), "uncommitted\n")
        _require_dirty(_tree, "f.txt", "new.txt", "keep.txt")
        _require_dirty(_tree, "Makefile", "new.txt", "LICENSE")
        for _name in ("fixtures/a.json", "fixtures/media-players.json", "src/app.py",
                      "a.txt", "b.txt", "hooks/guard.py", "README.md", "Makefile",
                      "tools/runner"):
            if not any(line[:2].strip() == "M" and line[3:].strip() == _name
                       for line in _porcelain(_tree)):
                sys.exit("fixture setup failed in build_fixtures: %r is not modified in %r"
                         % (_name, _tree))
    # The gate rows, in the shared checkout only. hotfix is a dirty tracked file that is also a
    # branch. staged-note is staged, and the tree holds the same text, so no change is left
    # unstaged. scratch is an untracked file with no extension, so it is no tracked change.
    write(os.path.join(GITMAIN, "hotfix"), "uncommitted\n")
    write(os.path.join(GITMAIN, "staged-note"), "staged\n")
    run_vcs(GITMAIN, "add", "staged-note")
    write(os.path.join(GITMAIN, "scratch"), "untracked\n")
    # DECOYMAIN: an ordinary MAIN checkout whose own folder happens to be nested under a path
    # spelled ".claude/worktrees/<name>". It is not a linked worktree of anything, so the
    # coincidence in its path must not earn it the agent-owned allowance.
    make_repo(DECOYMAIN, {"f.txt": "base\n", "keep.txt": "base\n"})
    write(os.path.join(DECOYMAIN, "f.txt"), "uncommitted\n")
    write(os.path.join(DECOYMAIN, "new.txt"), "untracked\n")
    _require_dirty(DECOYMAIN, "f.txt", "new.txt", "keep.txt")

    # DOTDOTWT, checked on the real tree: a path through .claude/worktrees/ that climbs back out
    # with ".." must resolve to GITWT itself. SYMWT is a real link to GITWT, when the account may
    # make one (SYMWT_MADE, from the probe in build_fixtures).
    if os.path.normcase(os.path.realpath(DOTDOTWT)) != os.path.normcase(os.path.realpath(GITWT)):
        sys.exit("fixture setup failed: DOTDOTWT does not resolve to GITWT. realpath is %r"
                 % os.path.realpath(DOTDOTWT))
    if SYMWT_MADE:
        os.symlink(GITWT, SYMWT, target_is_directory=True)


def _build_subject():
    """The subject-read repos: SUBJCLEAN, SUBJCLEANWT, SUBJDIRTY, SUBJSTASH, SUBJSTASHWT,
    SUBJSTASHDIRTY and SUBJSTAGED."""
    # THE SUBJECT READ. Each arm gets both sides, built with real state: a real clean tree, a
    # real uncommitted edit, a real untracked file, a real one-entry stash stack.
    make_repo(SUBJCLEAN, {"f.txt": "base\n", "keep.txt": "base\n"})
    _require_clean(SUBJCLEAN)
    _require_stash(SUBJCLEAN, 0)
    # A CLEAN worktree of that clean checkout. The narrowed `reset --hard` arm keeps the
    # deny-or-ask split for a named commit, and the ask half of that split can only be shown in a
    # real linked worktree whose tree is also clean.
    run_vcs(SUBJCLEAN, "worktree", "add", "-q", SUBJCLEANWT, "-b", "subjlane")
    _require_clean(SUBJCLEANWT)

    make_repo(SUBJDIRTY, {"f.txt": "base\n", "keep.txt": "base\n"})
    write(os.path.join(SUBJDIRTY, "f.txt"), "uncommitted\n")
    write(os.path.join(SUBJDIRTY, "new.txt"), "untracked\n")
    _require_dirty(SUBJDIRTY, "f.txt", "new.txt", "keep.txt")
    _require_stash(SUBJDIRTY, 0)

    # One real stash entry over a CLEAN tree, so the `stash drop` cases prove the guard reads the
    # STACK and not the tree. The push carries the identity, because a stash writes a commit.
    make_repo(SUBJSTASH, {"f.txt": "base\n"})
    write(os.path.join(SUBJSTASH, "f.txt"), "to be stashed\n")
    run_vcs(SUBJSTASH, *IDENT, "stash", "push", "-m", "cases")
    _require_stash(SUBJSTASH, 1)
    _require_clean(SUBJSTASH)
    # A linked worktree of that checkout. `refs/stash` lives in the common git directory, so the
    # worktree sees the same one-entry stack, and a drop there destroys the primary's entry.
    run_vcs(SUBJSTASH, "worktree", "add", "-q", SUBJSTASHWT, "-b", "stashlane")
    _require_stash(SUBJSTASHWT, 1)

    # A DIRTY checkout that also carries one real stash entry, so `stash create` is judged where
    # local edits and a stack entry exist together. Its untracked file is made after the push.
    make_repo(SUBJSTASHDIRTY, {"f.txt": "base\n", "keep.txt": "base\n"})
    write(os.path.join(SUBJSTASHDIRTY, "f.txt"), "to be stashed\n")
    run_vcs(SUBJSTASHDIRTY, *IDENT, "stash", "push", "-m", "cases")
    _require_stash(SUBJSTASHDIRTY, 1)
    write(os.path.join(SUBJSTASHDIRTY, "f.txt"), "uncommitted\n")
    write(os.path.join(SUBJSTASHDIRTY, "new.txt"), "untracked\n")
    _require_dirty(SUBJSTASHDIRTY, "f.txt", "new.txt", "keep.txt")

    # A STAGED edit to a tracked file and a STAGED new file: the state `reset --merge HEAD` reverts
    # and deletes. The tree is dirty, and its work is all in the index.
    make_repo(SUBJSTAGED, {"f.txt": "base\n", "keep.txt": "base\n"})
    write(os.path.join(SUBJSTAGED, "f.txt"), "staged\n")
    write(os.path.join(SUBJSTAGED, "new.txt"), "staged new\n")
    run_vcs(SUBJSTAGED, "add", "f.txt", "new.txt")
    _require_staged(SUBJSTAGED, "f.txt", "new.txt")

def _build_privrepo():
    """PRIVREPO: a dirty repository under a scratchpad named after one session."""
    # A dirty repository under a scratchpad named after one session.
    make_repo(PRIVREPO, {"f.txt": "base\n", "keep.txt": "base\n"})
    write(os.path.join(PRIVREPO, "f.txt"), "uncommitted\n")
    write(os.path.join(PRIVREPO, "new.txt"), "untracked\n")
    _require_dirty(PRIVREPO, "f.txt", "new.txt", "keep.txt")

def _set_origin_main(where, rev):
    """Point refs/remotes/origin/main at `rev` in `where`. The guard reads that ref, and no remote is needed."""
    result = run_vcs(where, "update-ref", "refs/remotes/origin/main", rev)
    if result.returncode != 0:
        sys.exit("fixture setup failed: origin/main in %r. stderr: %s" % (where, result.stderr.strip()))


def _build_pointer():
    """The pointer checkout (PTRMAIN, PTRWT), its config folders, and the blind git."""
    # THE POINTER CHECKOUT, built with git itself. The rule compares TOP LEVELS read from git, so
    # no fake directory will do, and the worktree that must stay allowed has to be a real one.
    #
    # PTRMAIN CARRIES REAL UNCOMMITTED WORK on `f.txt`, and `keep.txt` is really clean inside it.
    # The path-operation cases are what prove rule 1 still governs `checkout -- <path>` in this
    # checkout, unchanged, and both of rule 1's answers need real state to come out of.
    # `docs/note.md` exists so that the subdirectory case below runs in a real directory. A `cd`
    # into a directory that is not there would answer "allow" for the wrong reason.
    make_repo(PTRMAIN, {"f.txt": "base\n", "keep.txt": "base\n", "docs/note.md": "base\n"})
    write(os.path.join(PTRMAIN, "f.txt"), "uncommitted\n")
    write(os.path.join(PTRMAIN, "new.txt"), "untracked\n")
    _require_dirty(PTRMAIN, "f.txt", "new.txt", "keep.txt")
    run_vcs(PTRMAIN, "worktree", "add", "-q", PTRWT, "-b", "ptrlane")
    _require_clean(PTRWT)
    _require_pointer_branch(PTRMAIN, "main")
    # A linked worktree NESTED under the pointer, made the way the harness makes a lane's. It has its
    # own git directory, so a write into it is a worktree's write and not the pointer's own. The
    # scope check stops the suite if git gave it the pointer's git directory instead.
    nested = run_vcs(PTRMAIN, "worktree", "add", "-q", PTRNEST, "-b", "ptrnest")
    if nested.returncode != 0:
        sys.exit("fixture setup failed: the nested worktree at %r: %s" % (PTRNEST, nested.stderr.strip()))
    gitdir = run_vcs(PTRNEST, "rev-parse", "--absolute-git-dir")
    if gitdir.returncode != 0 or os.path.normcase(os.path.realpath(gitdir.stdout.strip())) == (
            os.path.normcase(os.path.realpath(os.path.join(PTRMAIN, ".git")))):
        sys.exit("fixture setup failed: the nested worktree at %r does not hold its own git directory: %r"
                 % (PTRNEST, gitdir.stdout.strip()))
    _require_clean(PTRNEST)
    _set_origin_main(PTRMAIN, "HEAD")
    # The pointer line has the same shape the installer writes and the shell readers parse.
    write(os.path.join(PTRCFG, "CLAUDE.md"), "@" + slash(PTRMAIN) + "/CLAUDE.md\n")
    # The off-main pointer checkout: a second repository whose HEAD is on `feat`.
    make_repo(PTROFF, {"f.txt": "base\n"})
    run_vcs(PTROFF, "checkout", "-b", "feat")
    _require_pointer_branch(PTROFF, "feat")
    _set_origin_main(PTROFF, "main")
    write(os.path.join(PTROFFCFG, "CLAUDE.md"), "@" + slash(PTROFF) + "/CLAUDE.md\n")
    # Local main one commit ahead of origin/main: a reset of main onto origin/main would drop that commit.
    make_repo(PTRAHEAD, {"f.txt": "base\n"})
    _set_origin_main(PTRAHEAD, "main")
    write(os.path.join(PTRAHEAD, "f.txt"), "local only\n")
    run_vcs(PTRAHEAD, "add", "-A")
    ahead = run_vcs(PTRAHEAD, *IDENT, "commit", "-q", "-m", "local only")
    if ahead.returncode != 0:
        sys.exit("fixture setup failed: the local commit in PTRAHEAD. stderr: %s" % ahead.stderr.strip())
    _require_pointer_branch(PTRAHEAD, "main")
    write(os.path.join(PTRAHEADCFG, "CLAUDE.md"), "@" + slash(PTRAHEAD) + "/CLAUDE.md\n")
    # No origin/main at all: the pointer checkout on main, with no remote-tracking ref.
    make_repo(PTRNOORIGIN, {"f.txt": "base\n"})
    _require_pointer_branch(PTRNOORIGIN, "main")
    write(os.path.join(PTRNOORIGINCFG, "CLAUDE.md"), "@" + slash(PTRNOORIGIN) + "/CLAUDE.md\n")
    write(os.path.join(PTRBADCFG, "CLAUDE.md"), "rules with no pointer line\n")
    write(os.path.join(PTRGONECFG, "CLAUDE.md"),
          "@" + slash(os.path.join(ROOT, "nosuchcheckout")) + "/CLAUDE.md\n")
    # Scope before subject: the stand-down cases need the directory PTRGONECFG names to be absent.
    if os.path.exists(os.path.join(ROOT, "nosuchcheckout")):
        sys.exit("fixture setup failed: the directory the gone-pointer rules name exists: %r"
                 % os.path.join(ROOT, "nosuchcheckout"))
    os.makedirs(PTRNOCFG, exist_ok=True)

    make_blind_git(GITBLIND)

def _build_conflict():
    """CONFLICT: a real checkout with one unresolved merge conflict."""
    # A real checkout with a real, unresolved merge conflict, built with git itself rather than
    # mocked. Two branches each change the same file, and merging one into the other leaves
    # MERGE_HEAD set and the file in the conflicted "AA" state, which git will not let a commit
    # leave silently.
    os.makedirs(CONFLICT, exist_ok=True)
    run_vcs(CONFLICT, "init", "-q", "-b", "main", ".")
    ident = ["-c", "user.email=cases@example.invalid", "-c", "user.name=cases"]
    write(os.path.join(CONFLICT, "docs", "DEBTS.md"), "base\n")
    run_vcs(CONFLICT, "add", "docs/DEBTS.md")
    run_vcs(CONFLICT, *ident, "commit", "-q", "-m", "base")
    run_vcs(CONFLICT, "checkout", "-q", "-b", "feature")
    write(os.path.join(CONFLICT, "docs", "DEBTS.md"), "feature change\n")
    run_vcs(CONFLICT, "add", "docs/DEBTS.md")
    run_vcs(CONFLICT, *ident, "commit", "-q", "-m", "feature change")
    run_vcs(CONFLICT, "checkout", "-q", "main")
    write(os.path.join(CONFLICT, "docs", "DEBTS.md"), "main change\n")
    run_vcs(CONFLICT, "add", "docs/DEBTS.md")
    run_vcs(CONFLICT, *ident, "commit", "-q", "-m", "main change")
    # MEASURED on CI (run 35182973995): this call ran with no `ident`, so on a runner with no
    # global git identity the merge refused before it ever touched the tree ("Committer identity
    # unknown", exit 128), MERGE_HEAD was never set, and the conflict-resolve fixtures below were
    # silently testing a CLEAN tree. It passed here only because this machine's own ~/.gitconfig
    # supplied an identity the fixture never asked for.
    run_vcs(CONFLICT, *ident, "merge", "feature")  # conflicts and leaves MERGE_HEAD set
    _require_conflict(CONFLICT, "docs/DEBTS.md")

def _build_branch():
    """The branch-delete repos: a bare remote, the base fallbacks and the unmerged branches."""
    # ----------------------------------------------------------------- branch delete fixtures
    #
    # BRANCHREPO pushes to a real bare remote, so `git cherry` and `git for-each-ref --contains`
    # both read REAL history, never a guess. The shape below builds four branches off one
    # history so each of the rule's three tests gets a branch only IT would pass:
    #
    #   ancestor-work   never moves past the first commit: trivially an ancestor of `origin/main`.
    #   rebased-work    carries a commit whose PATCH main also carries, under a different commit
    #                   id, so only `git cherry` (not ancestry) proves it is redundant.
    #   unmerged-work   carries a commit found nowhere else at all: the only-copy case.
    #   pushed-work     carries a commit AS unique as unmerged-work's, but pushed to the remote,
    #                   so only the remote-contains test proves it is safe to delete.
    os.makedirs(BRANCHREMOTE, exist_ok=True)
    run_vcs(BRANCHREMOTE, "init", "-q", "--bare")
    make_repo(BRANCHREPO, {"base.txt": "base\n"})
    run_vcs(BRANCHREPO, "remote", "add", "origin", slash(BRANCHREMOTE))
    push = run_vcs(BRANCHREPO, "push", "-q", "origin", "main")
    if push.returncode != 0:
        sys.exit("fixture setup failed in build_fixtures: pushing BRANCHREPO's main failed. "
                  "stderr: %s" % push.stderr.strip())
    run_vcs(BRANCHREPO, "remote", "set-head", "origin", "main")
    run_vcs(BRANCHREPO, "checkout", "-q", "-b", "ancestor-work")
    run_vcs(BRANCHREPO, "checkout", "-q", "main")
    run_vcs(BRANCHREPO, "checkout", "-q", "-b", "rebased-work")
    write(os.path.join(BRANCHREPO, "r.txt"), "same patch\n")
    run_vcs(BRANCHREPO, "add", "r.txt")
    run_vcs(BRANCHREPO, *IDENT, "commit", "-q", "-m", "add r.txt on rebased-work")
    run_vcs(BRANCHREPO, "checkout", "-q", "main")
    write(os.path.join(BRANCHREPO, "r.txt"), "same patch\n")  # identical content, own commit
    run_vcs(BRANCHREPO, "add", "r.txt")
    run_vcs(BRANCHREPO, *IDENT, "commit", "-q", "-m", "add r.txt directly on main")
    run_vcs(BRANCHREPO, "checkout", "-q", "-b", "unmerged-work")
    write(os.path.join(BRANCHREPO, "u.txt"), "found nowhere else\n")
    run_vcs(BRANCHREPO, "add", "u.txt")
    run_vcs(BRANCHREPO, *IDENT, "commit", "-q", "-m", "unmerged-work's only copy")
    run_vcs(BRANCHREPO, "checkout", "-q", "main")
    run_vcs(BRANCHREPO, "checkout", "-q", "-b", "pushed-work")
    write(os.path.join(BRANCHREPO, "p.txt"), "pushed to the remote\n")
    run_vcs(BRANCHREPO, "add", "p.txt")
    run_vcs(BRANCHREPO, *IDENT, "commit", "-q", "-m", "pushed-work's commit")
    pushb = run_vcs(BRANCHREPO, "push", "-q", "origin", "pushed-work")
    if pushb.returncode != 0:
        sys.exit("fixture setup failed in build_fixtures: pushing pushed-work failed. "
                  "stderr: %s" % pushb.stderr.strip())
    run_vcs(BRANCHREPO, "checkout", "-q", "main")
    # archived-work is as unique as unmerged-work, then gets the refusal's own handed remedy: its
    # push step, read from the printed reason with the placeholder filled, run for real. The
    # delete case below proves that the remedy, once run, makes the rule allow the delete.
    run_vcs(BRANCHREPO, "checkout", "-q", "-b", "archived-work")
    write(os.path.join(BRANCHREPO, "a.txt"), "archived by the handed remedy\n")
    run_vcs(BRANCHREPO, "add", "a.txt")
    run_vcs(BRANCHREPO, *IDENT, "commit", "-q", "-m", "archived-work's commit")
    run_vcs(BRANCHREPO, "checkout", "-q", "main")
    # No handed push step leaves the branch the only copy, so that case goes red, not the suite.
    _, refusal = decide({"raw": None, "tool": "Bash", "cwd": BRANCHREPO, "session": None,
                         "env_path": None,
                         "tool_input": {"command": VCS + " branch -D archived-work"}})
    handed = re.search(r"`git (push [^`]*)`", refusal or "")
    if handed:
        archive = run_vcs(BRANCHREPO, *handed.group(1).replace("<branch>", "archived-work").split())
        if archive.returncode != 0:
            sys.exit("fixture setup failed in build_fixtures: the branch-delete refusal's handed "
                     "push failed. stderr: %s" % archive.stderr.strip())
    pushm = run_vcs(BRANCHREPO, "push", "-q", "origin", "main")
    if pushm.returncode != 0:
        sys.exit("fixture setup failed in build_fixtures: re-pushing main failed. "
                  "stderr: %s" % pushm.stderr.strip())
    fetch = run_vcs(BRANCHREPO, "fetch", "-q", "origin")
    if fetch.returncode != 0:
        sys.exit("fixture setup failed in build_fixtures: fetching origin failed. "
                  "stderr: %s" % fetch.stderr.strip())
    base_check = run_vcs(BRANCHREPO, "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD")
    if base_check.returncode != 0 or base_check.stdout.strip() != "origin/main":
        sys.exit(
            "fixture setup failed in build_fixtures: origin/HEAD in BRANCHREPO does not resolve "
            "to origin/main. git answers: %r, stderr: %s"
            % (base_check.stdout.strip(), base_check.stderr.strip())
        )
    cherry_check = run_vcs(BRANCHREPO, "cherry", "origin/main", "rebased-work")
    if any(line.startswith("+") for line in cherry_check.stdout.splitlines()):
        sys.exit(
            "fixture setup failed in build_fixtures: rebased-work still carries a `+` against "
            "origin/main, so it does not prove the patch-id test. git cherry says: %r"
            % cherry_check.stdout
        )

    # A fallback base with no remote at all: only local `main` answers, proving the SECOND step
    # of the resolve order (`origin/HEAD`, then local `main`, then local `master`).
    make_repo(BRANCHFALLBACKMAIN, {"base.txt": "base\n"})
    run_vcs(BRANCHFALLBACKMAIN, "checkout", "-q", "-b", "ancestor-fallback")
    run_vcs(BRANCHFALLBACKMAIN, "checkout", "-q", "main")
    # A branch that only a REAL fallback to local `main` can deny: if the fallback silently gave
    # up instead, the base would read as unreadable and this branch would wrongly pass.
    run_vcs(BRANCHFALLBACKMAIN, "checkout", "-q", "-b", "unmerged-fallback")
    write(os.path.join(BRANCHFALLBACKMAIN, "uf.txt"), "found nowhere else, no remote at all\n")
    run_vcs(BRANCHFALLBACKMAIN, "add", "uf.txt")
    run_vcs(BRANCHFALLBACKMAIN, *IDENT, "commit", "-q", "-m", "unmerged-fallback's only copy")
    run_vcs(BRANCHFALLBACKMAIN, "checkout", "-q", "main")

    # A fallback base with only local `master`, no `main` and no remote, proving the THIRD step.
    os.makedirs(BRANCHFALLBACKMASTER, exist_ok=True)
    run_vcs(BRANCHFALLBACKMASTER, "init", "-q", "-b", "master", ".")
    write(os.path.join(BRANCHFALLBACKMASTER, "base.txt"), "base\n")
    run_vcs(BRANCHFALLBACKMASTER, "add", "-A")
    run_vcs(BRANCHFALLBACKMASTER, *IDENT, "commit", "-q", "-m", "first")
    run_vcs(BRANCHFALLBACKMASTER, "checkout", "-q", "-b", "ancestor-fallback-master")
    run_vcs(BRANCHFALLBACKMASTER, "checkout", "-q", "master")
    run_vcs(BRANCHFALLBACKMASTER, "checkout", "-q", "-b", "unmerged-fallback-master")
    write(os.path.join(BRANCHFALLBACKMASTER, "uf.txt"), "found nowhere else, no remote at all\n")
    run_vcs(BRANCHFALLBACKMASTER, "add", "uf.txt")
    run_vcs(BRANCHFALLBACKMASTER, *IDENT, "commit", "-q", "-m",
            "unmerged-fallback-master's only copy")
    run_vcs(BRANCHFALLBACKMASTER, "checkout", "-q", "master")

    # No `origin/HEAD`, no local `main`, no local `master`: none of the three steps answers, so
    # the base is UNREADABLE and the delete must be allowed and logged, never denied and never
    # silently passed.
    os.makedirs(BRANCHNOBASE, exist_ok=True)
    run_vcs(BRANCHNOBASE, "init", "-q", "-b", "trunk", ".")
    write(os.path.join(BRANCHNOBASE, "base.txt"), "base\n")
    run_vcs(BRANCHNOBASE, "add", "-A")
    run_vcs(BRANCHNOBASE, *IDENT, "commit", "-q", "-m", "first")
    run_vcs(BRANCHNOBASE, "checkout", "-q", "-b", "orphan-work")
    write(os.path.join(BRANCHNOBASE, "o.txt"), "irrelevant to the unreadable case\n")
    run_vcs(BRANCHNOBASE, "add", "o.txt")
    run_vcs(BRANCHNOBASE, *IDENT, "commit", "-q", "-m", "orphan-work's commit")
    run_vcs(BRANCHNOBASE, "checkout", "-q", "trunk")
    base_check2 = run_vcs(BRANCHNOBASE, "rev-parse", "--verify", "-q", "refs/heads/main")
    if base_check2.returncode == 0:
        sys.exit("fixture setup failed in build_fixtures: BRANCHNOBASE unexpectedly has a "
                  "local main")

# The bad packed-refs record: its name sorts before every ref the every-branch fixtures hold.
BROKEN_REF = b"refs/heads/aaa-broken"


def _break_branch_listing(where):
    """Make `where`, an every-branch fixture, a repo whose listing of refs/heads/ fails while its tracking read answers.

    Git reads packed-refs from the first name a read seeks to onward, so one bad record fails every read that reaches
    it. The tracking read's first name is refs/heads/main, and it seeks there, so a record sorted before that name is
    not reached. The listing of refs/heads/ seeks to a prefix that sorts first, so it reaches the record and fails.
    Every probe runs git itself, never the guard, so a mutant of the guard cannot break the build.
    """
    packed = run_vcs(where, "pack-refs", "--all")
    path = os.path.join(where, ".git", "packed-refs")
    if (packed.returncode != 0 or not os.path.isfile(path)
            or os.path.exists(os.path.join(where, ".git", "refs", "heads", "main"))):
        sys.exit("fixture setup failed in build_fixtures: pack-refs --all in %r did not move the refs into "
                 "packed-refs. stderr: %s" % (where, packed.stderr.strip()))
    with open(path, "rb") as handle:
        header, *records = handle.read().split(b"\n")
    records = [line for line in records if line]
    # The junk sha has the width of a real one, so the file keeps its fixed-width records. It is not hex.
    width = len(records[0].split(b" ", 1)[0])
    index = next((i for i, line in enumerate(records) if line.split(b" ", 1)[1] > BROKEN_REF), len(records))
    records.insert(index, b"g" * width + b" " + BROKEN_REF)
    # Binary mode keeps LF line endings on Windows, which git reads as record ends.
    with open(path, "wb") as handle:
        handle.write(b"\n".join([header] + records) + b"\n")
    listing = run_vcs(where, "for-each-ref", "--format=%(refname)", "refs/heads/")
    if listing.returncode == 0 or "packed-refs" not in listing.stderr:
        sys.exit("fixture setup failed in build_fixtures: the listing of refs/heads/ in %r should fail on packed-refs, "
                 "got exit %d, stderr: %s" % (where, listing.returncode, listing.stderr.strip()))
    tracking = run_vcs(where, "for-each-ref", "--format=%(refname) %(objectname)",
                       "refs/heads/main", "refs/heads/master", "refs/remotes/origin/main", "refs/remotes/origin/master")
    shas = {}
    for line in tracking.stdout.splitlines():
        ref, _, sha = line.partition(" ")
        shas[ref] = sha
    if tracking.returncode != 0 or not shas.get("refs/heads/main") or shas["refs/heads/main"] != shas.get(
            "refs/remotes/origin/main"):
        sys.exit("fixture setup failed in build_fixtures: the tracking read of %r should answer with main equal to "
                 "origin/main, got exit %d, stdout: %r" % (where, tracking.returncode, tracking.stdout))
    head = run_vcs(where, "symbolic-ref", "-q", "HEAD")
    if head.stdout.strip() != "refs/heads/main":
        sys.exit("fixture setup failed in build_fixtures: %r should sit on refs/heads/main, symbolic-ref reads %r"
                 % (where, head.stdout.strip()))


def _build_push():
    """The push destinations: the feat, main, trunk and upstream repos and their remotes."""
    materialize(BRANCHREMOTE)  # PUSHLOCAL's origin is this bare remote, a local path
    # ----------------------------------------------------------------- push destinations
    for where, head, branch in ((PUSHFEAT, "main", "feat"), (PUSHMAIN, "main", "main"),
                                (PUSHTRUNK, "trunk", "feat"), (PUSHTRUNKLOCAL, "trunk", "feat"),
                                (PUSHNOHEAD, None, "feat"), (PUSHDETACHED, "main", None),
                                (PUSHSAMETAG, "main", "main"), (RECROADMAP, "main", "roadmap"),
                                (RECFORK, "main", "roadmap-fork"),
                                (PUSHLOCAL, "main", "feat"), (PUSHLOCALSTRAY, "main", "feat"),
                                (PUSHLOCALMAIN, "main", "main"),
                                (PUSHSSH, "main", "feat"), (PUSHNOREMOTE, None, "feat")):
        make_repo(where, {"base.txt": "base\n"})
        if head:
            origin = {PUSHLOCAL: slash(BRANCHREMOTE), PUSHLOCALSTRAY: slash(BRANCHREMOTE),
                      PUSHLOCALMAIN: slash(BRANCHREMOTE), PUSHSSH: PUSHSSHURL}.get(where, PUSHREMOTE)
            run_vcs(where, "remote", "add", "origin", origin)
            run_vcs(where, "update-ref", "refs/remotes/origin/" + head, "HEAD")
            run_vcs(where, "symbolic-ref", "refs/remotes/origin/HEAD",
                    "refs/remotes/origin/" + head)
        if branch and branch != "main":
            run_vcs(where, "checkout", "-q", "-b", branch)
        if branch is None:
            run_vcs(where, "checkout", "-q", "--detach")
        if (head and run_vcs(where, "symbolic-ref", "refs/remotes/origin/HEAD").returncode != 0):
            sys.exit("fixture setup failed in build_fixtures: origin/HEAD in %r unreadable" % where)

    # Each remote fixture reads back the origin it was given (P7), so a case never judges a remote the build did
    # not set. PUSHNOREMOTE must have no remote at all.
    for where, want in ((PUSHLOCAL, slash(BRANCHREMOTE)), (PUSHLOCALSTRAY, slash(BRANCHREMOTE)),
                        (PUSHLOCALMAIN, slash(BRANCHREMOTE)), (PUSHSSH, PUSHSSHURL)):
        if run_vcs(where, "config", "--get", "remote.origin.url").stdout.strip() != want:
            sys.exit("fixture setup failed in build_fixtures: %r needs origin %s" % (where, want))
    if run_vcs(PUSHNOREMOTE, "remote").stdout.strip():
        sys.exit("fixture setup failed in build_fixtures: PUSHNOREMOTE must have no remote")

    # PUSHLOCALSTRAY's upstream is set by git (--set-upstream-to), then read back, so a case never judges a
    # fixture without it.
    run_vcs(PUSHLOCALSTRAY, "update-ref", "refs/remotes/origin/other", "HEAD")
    run_vcs(PUSHLOCALSTRAY, "branch", "--set-upstream-to=origin/other", "feat")
    if run_vcs(PUSHLOCALSTRAY, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}").stdout.strip() \
            != "origin/other":
        sys.exit("fixture setup failed in build_fixtures: PUSHLOCALSTRAY needs upstream origin/other")

    # PUSHLOCALMAIN tracks origin/main, set by git and read back, the same as PUSHMAINUP. Its checkout is main.
    run_vcs(PUSHLOCALMAIN, "branch", "--set-upstream-to=origin/main", "main")
    if run_vcs(PUSHLOCALMAIN, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}").stdout.strip() \
            != "origin/main":
        sys.exit("fixture setup failed in build_fixtures: PUSHLOCALMAIN needs upstream origin/main")
    if run_vcs(PUSHLOCALMAIN, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() != "main":
        sys.exit("fixture setup failed in build_fixtures: PUSHLOCALMAIN must sit on main")

    # The feat destination holds the remote-tracking refs that the push cost case's forms read: feat for
    # a HEAD or bare push, lane/foo for a refspec push or HEAD:lane/foo. A local lane/foo is the source.
    for args in (("update-ref", "refs/remotes/origin/feat", "HEAD"),
                 ("update-ref", "refs/remotes/origin/lane/foo", "HEAD"), ("branch", "lane/foo")):
        if run_vcs(PUSHFEAT, *args).returncode != 0:
            sys.exit("fixture setup failed in build_fixtures: PUSHFEAT needs git %s" % " ".join(args))

    # The fork names its record branch in the extras file, as lint/layout.py reads it (key record-branch).
    write(os.path.join(RECFORK, ".claude", "layout-extras.json"),
          json.dumps({"kinds": {}, "record-branch": "roadmap-fork"}) + "\n")

    run_vcs(PUSHSAMETAG, "tag", "main")
    if run_vcs(PUSHSAMETAG, "symbolic-ref", "-q", "--short", "HEAD").stdout.strip() != "heads/main":
        sys.exit("fixture setup failed in build_fixtures: PUSHSAMETAG needs a tag named main that "
                 "makes the short read of HEAD print an ambiguous name")

    run_vcs(PUSHTRUNKLOCAL, "branch", "origin/trunk")
    if (run_vcs(PUSHTRUNKLOCAL, "rev-parse", "--verify", "-q", "refs/heads/origin/trunk").returncode != 0
            or run_vcs(PUSHTRUNKLOCAL, "symbolic-ref", "-q", "--short",
                       "refs/remotes/origin/HEAD").stdout.strip() == "origin/trunk"):
        sys.exit("fixture setup failed in build_fixtures: PUSHTRUNKLOCAL needs a local branch "
                 "origin/trunk that makes `symbolic-ref --short` print an ambiguous name")

    # A dangling origin/HEAD: it names origin/gone, which is missing. origin/main exists, so the read
    # order gives main as the default branch.
    make_repo(PUSHDANGLING, {"base.txt": "base\n"})
    run_vcs(PUSHDANGLING, "remote", "add", "origin", PUSHREMOTE)
    run_vcs(PUSHDANGLING, "update-ref", "refs/remotes/origin/main", "HEAD")
    run_vcs(PUSHDANGLING, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/gone")
    run_vcs(PUSHDANGLING, "checkout", "-q", "-b", "feat")
    if (run_vcs(PUSHDANGLING, "symbolic-ref", "refs/remotes/origin/HEAD").returncode != 0
            or run_vcs(PUSHDANGLING, "rev-parse", "--verify", "-q",
                       "refs/remotes/origin/HEAD^{commit}").returncode == 0
            or run_vcs(PUSHDANGLING, "rev-parse", "--verify", "-q",
                       "refs/remotes/origin/main^{commit}").returncode != 0):
        sys.exit("fixture setup failed in build_fixtures: PUSHDANGLING needs a dangling origin/HEAD "
                 "and a live origin/main")

    # origin/HEAD unset, one remote branch: origin/main (PUSHNOHEADMAIN) or origin/master (PUSHONLYMASTER).
    for where, remote_branch, absent in ((PUSHNOHEADMAIN, "main", "master"),
                                         (PUSHONLYMASTER, "master", "main")):
        make_repo(where, {"base.txt": "base\n"})
        run_vcs(where, "remote", "add", "origin", PUSHREMOTE)
        run_vcs(where, "update-ref", "refs/remotes/origin/" + remote_branch, "HEAD")
        run_vcs(where, "checkout", "-q", "-b", "feat")
        if (run_vcs(where, "symbolic-ref", "-q", "refs/remotes/origin/HEAD").returncode == 0
                or run_vcs(where, "rev-parse", "--verify", "-q",
                           "refs/remotes/origin/" + remote_branch + "^{commit}").returncode != 0
                or run_vcs(where, "rev-parse", "--verify", "-q",
                           "refs/remotes/origin/" + absent + "^{commit}").returncode == 0):
            sys.exit("fixture setup failed in build_fixtures: %r needs origin/%s, no origin/%s and "
                     "no origin/HEAD" % (where, remote_branch, absent))

    # Two remotes with two default branches. `feat` tracks upstream/main, so a bare push goes there.
    make_repo(PUSHUPSTREAM, {"base.txt": "base\n"})
    for remote, default in (("origin", "develop"), ("upstream", "main")):
        run_vcs(PUSHUPSTREAM, "remote", "add", remote, PUSHREMOTE)
        run_vcs(PUSHUPSTREAM, "update-ref", "refs/remotes/%s/%s" % (remote, default), "HEAD")
        run_vcs(PUSHUPSTREAM, "symbolic-ref", "refs/remotes/%s/HEAD" % remote,
                "refs/remotes/%s/%s" % (remote, default))
    run_vcs(PUSHUPSTREAM, "checkout", "-q", "-b", "feat")
    run_vcs(PUSHUPSTREAM, "config", "push.default", "upstream")
    run_vcs(PUSHUPSTREAM, "config", "branch.feat.remote", "upstream")
    run_vcs(PUSHUPSTREAM, "config", "branch.feat.merge", "refs/heads/main")
    if (run_vcs(PUSHUPSTREAM, "symbolic-ref", "refs/remotes/origin/HEAD").stdout.strip()
            != "refs/remotes/origin/develop"
            or run_vcs(PUSHUPSTREAM, "symbolic-ref", "refs/remotes/upstream/HEAD").stdout.strip()
            != "refs/remotes/upstream/main"
            or run_vcs(PUSHUPSTREAM, "config", "--get", "branch.feat.remote").stdout.strip() != "upstream"):
        sys.exit("fixture setup failed in build_fixtures: PUSHUPSTREAM needs origin/HEAD -> develop, "
                 "upstream/HEAD -> main and feat tracking upstream")
    # The second remote's main is read back before a case names it: local main equals upstream/main, and origin
    # has no main at all, so a push that reads the wrong remote's tracking refs changes its verdict.
    local_main = run_vcs(PUSHUPSTREAM, "rev-parse", "-q", "--verify", "refs/heads/main").stdout.strip()
    if (not local_main
            or local_main != run_vcs(PUSHUPSTREAM, "rev-parse", "-q", "--verify",
                                     "refs/remotes/upstream/main").stdout.strip()
            or run_vcs(PUSHUPSTREAM, "rev-parse", "-q", "--verify", "refs/remotes/origin/main").returncode == 0):
        sys.exit("fixture setup failed in build_fixtures: PUSHUPSTREAM needs local main equal to upstream/main "
                 "and no origin/main")

    for where, mode, merge in ((PUSHUP, "upstream", "main"), (PUSHUPSELF, "upstream", "feat"),
                               (PUSHNOUP, "upstream", None), (PUSHMATCH, "matching", None)):
        make_repo(where, {"base.txt": "base\n"})
        run_vcs(where, "remote", "add", "origin", PUSHREMOTE)
        run_vcs(where, "update-ref", "refs/remotes/origin/main", "HEAD")
        run_vcs(where, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        run_vcs(where, "checkout", "-q", "-b", "feat")
        run_vcs(where, "config", "push.default", mode)
        if merge:
            run_vcs(where, "config", "branch.feat.remote", "origin")
            run_vcs(where, "config", "branch.feat.merge", "refs/heads/" + merge)
        if run_vcs(where, "config", "--get", "push.default").stdout.strip() != mode:
            sys.exit("fixture setup failed in build_fixtures: push.default in %r" % where)

    # The upstream shapes of rulings 206 a and 207 a. Each upstream is set by git itself (--track and
    # --set-upstream-to), then read back, so a case never judges a fixture that lacks its upstream.
    make_repo(PUSHSTRAY, {"base.txt": "base\n"})
    run_vcs(PUSHSTRAY, "remote", "add", "origin", PUSHREMOTE)
    run_vcs(PUSHSTRAY, "remote", "add", "fork", PUSHREMOTE)
    run_vcs(PUSHSTRAY, "update-ref", "refs/remotes/origin/lane/x", "HEAD")
    run_vcs(PUSHSTRAY, "checkout", "-q", "-b", "mylocal")
    run_vcs(PUSHSTRAY, "branch", "--set-upstream-to=origin/lane/x", "mylocal")
    run_vcs(PUSHSTRAY, "config", "push.default", "simple")

    make_repo(PUSHSELF, {"base.txt": "base\n"})
    run_vcs(PUSHSELF, "remote", "add", "origin", PUSHREMOTE)
    run_vcs(PUSHSELF, "update-ref", "refs/remotes/origin/feat", "HEAD")
    run_vcs(PUSHSELF, "checkout", "-q", "--track", "-b", "feat", "origin/feat")

    for where, lane, base in ((PUSHLANE, "lane/foo", "main"), (PUSHLANEMASTER, "lane/bar", "master")):
        make_repo(where, {"base.txt": "base\n"})
        run_vcs(where, "remote", "add", "origin", PUSHREMOTE)
        run_vcs(where, "update-ref", "refs/remotes/origin/" + base, "HEAD")
        run_vcs(where, "checkout", "-q", "--track", "-b", lane, "origin/" + base)

    make_repo(PUSHSTACK, {"base.txt": "base\n"})
    run_vcs(PUSHSTACK, "remote", "add", "origin", PUSHREMOTE)
    run_vcs(PUSHSTACK, "update-ref", "refs/remotes/origin/lane/base", "HEAD")
    run_vcs(PUSHSTACK, "checkout", "-q", "--track", "-b", "lane/fix", "origin/lane/base")

    make_repo(PUSHMAINUP, {"base.txt": "base\n"})
    run_vcs(PUSHMAINUP, "remote", "add", "origin", PUSHREMOTE)
    run_vcs(PUSHMAINUP, "update-ref", "refs/remotes/origin/main", "HEAD")
    run_vcs(PUSHMAINUP, "branch", "--set-upstream-to=origin/main", "main")

    # Its own name is on origin, so the implied pushes to it are silent. Built by git itself.
    make_repo(PUSHOWNREF, {"base.txt": "base\n"})
    run_vcs(PUSHOWNREF, "remote", "add", "origin", PUSHREMOTE)
    run_vcs(PUSHOWNREF, "update-ref", "refs/remotes/origin/batch-1", "HEAD")
    run_vcs(PUSHOWNREF, "update-ref", "refs/remotes/origin/lane-x", "HEAD")
    run_vcs(PUSHOWNREF, "checkout", "-q", "-b", "lane-x")
    run_vcs(PUSHOWNREF, "branch", "--set-upstream-to=origin/batch-1", "lane-x")

    for where, upstream in ((PUSHSTRAY, "origin/lane/x"), (PUSHSELF, "origin/feat"),
                            (PUSHLANE, "origin/main"), (PUSHLANEMASTER, "origin/master"),
                            (PUSHSTACK, "origin/lane/base"), (PUSHMAINUP, "origin/main"),
                            (PUSHOWNREF, "origin/batch-1")):
        got = run_vcs(where, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}").stdout.strip()
        if got != upstream:
            sys.exit("fixture setup failed in build_fixtures: %r needs upstream %s, reads %r"
                     % (where, upstream, got))
    # The no-upstream cases ride on these two checkouts, so each must read back with no upstream.
    for where in (PUSHFEAT, PUSHMAIN):
        if run_vcs(where, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}").returncode == 0:
            sys.exit("fixture setup failed in build_fixtures: %r must have no upstream" % where)
    if (sorted(run_vcs(PUSHSTRAY, "remote").stdout.split()) != ["fork", "origin"]
            or run_vcs(PUSHSTRAY, "config", "--get", "push.default").stdout.strip() != "simple"):
        sys.exit("fixture setup failed in build_fixtures: PUSHSTRAY needs remotes fork and origin "
                 "and push.default simple")
    # Scope before subject (P7). The stray controls need origin/mylocal absent in PUSHSTRAY, and the ruling 432 a
    # red rows need origin/lane-x present in PUSHOWNREF. Each is read back, so no case judges a fixture without it.
    for where, ref, present in ((PUSHSTRAY, "refs/remotes/origin/mylocal", False),
                                (PUSHOWNREF, "refs/remotes/origin/lane-x", True)):
        if (run_vcs(where, "rev-parse", "-q", "--verify", ref).returncode == 0) != present:
            sys.exit("fixture setup failed in build_fixtures: %r needs %s %s"
                     % (where, ref, "present" if present else "absent"))

    # The agent-worktree names and their near misses (rule push-agent-branch). Each reads back its own name
    # in HEAD and no upstream, so a case judges the name it names and nothing inherited.
    for where, branch in ((PUSHAGENT, "claude/agent-a22bb0ed47825117b"),
                          (PUSHAGENTWT, "worktree-agent-a22bb0ed47825117b"),
                          (PUSHAGENTBARE, "agent-a22bb0ed47825117b"),
                          (PUSHAGENTNOTES, "agent-notes"),
                          (PUSHAGENTMYABC, "my-agent-abc"),
                          (PUSHAGENTMYHEX, "my-agent-a22bb0ed47825117b"),
                          (PUSHAGENTSHORT, "agent-1234567"),
                          (PUSHAGENTEIGHT, "agent-12345678")):
        make_repo(where, {"base.txt": "base\n"})
        run_vcs(where, "remote", "add", "origin", PUSHREMOTE)
        run_vcs(where, "update-ref", "refs/remotes/origin/main", "HEAD")
        run_vcs(where, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        run_vcs(where, "checkout", "-q", "-b", branch)
        if run_vcs(where, "symbolic-ref", "-q", "HEAD").stdout.strip() != "refs/heads/" + branch:
            sys.exit("fixture setup failed in build_fixtures: %r must be on branch %s" % (where, branch))
        if run_vcs(where, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}").returncode == 0:
            sys.exit("fixture setup failed in build_fixtures: %r must have no upstream" % where)
    # The config-file autoSetupRemote (rule push-agent-branch). The key is written to this repo's own config,
    # so a bare push reads it there, not from a `-c` override on the call.
    make_repo(PUSHAGENTCFG, {"base.txt": "base\n"})
    run_vcs(PUSHAGENTCFG, "remote", "add", "origin", PUSHREMOTE)
    run_vcs(PUSHAGENTCFG, "update-ref", "refs/remotes/origin/main", "HEAD")
    run_vcs(PUSHAGENTCFG, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
    run_vcs(PUSHAGENTCFG, "checkout", "-q", "-b", "claude/agent-0c1d2e3f4a5b6c7d")
    run_vcs(PUSHAGENTCFG, "config", "push.autoSetupRemote", "true")
    if run_vcs(PUSHAGENTCFG, "config", "--get", "push.autoSetupRemote").stdout.strip() != "true":
        sys.exit("fixture setup failed in build_fixtures: %r must set push.autoSetupRemote in its config" % PUSHAGENTCFG)
    if run_vcs(PUSHAGENTCFG, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}").returncode == 0:
        sys.exit("fixture setup failed in build_fixtures: %r must have no upstream" % PUSHAGENTCFG)

    # --all and --branches. Each fixture is read back before a case judges it: the local branch,
    # the remote-tracking ref it is compared with, and the checkout the case names.
    def _ref(where, ref):
        return run_vcs(where, "rev-parse", "-q", "--verify", ref).stdout.strip()

    def _head(where):
        return run_vcs(where, "symbolic-ref", "-q", "HEAD").stdout.strip()

    def _work_commit(where):
        write(os.path.join(where, "local.txt"), "a commit only this checkout has\n")
        run_vcs(where, "add", "-A")
        run_vcs(where, *IDENT, "commit", "-q", "-m", "work")

    for where, checkout, head in ((PUSHAHEAD, None, "refs/heads/main"),
                                  (PUSHAHEADLANE, "feat", "refs/heads/feat"),
                                  (PUSHAHEADDET, "--detach", ""),
                                  (PUSHAHEADAGENT, "claude/agent-a22bb0ed47825117b",
                                   "refs/heads/claude/agent-a22bb0ed47825117b")):
        make_repo(where, {"base.txt": "base\n"})
        run_vcs(where, "remote", "add", "origin", PUSHREMOTE)
        run_vcs(where, "update-ref", "refs/remotes/origin/main", "HEAD")
        run_vcs(where, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        _work_commit(where)
        if checkout == "--detach":
            run_vcs(where, "checkout", "-q", "--detach")
        elif checkout:
            run_vcs(where, "checkout", "-q", "-b", checkout)
        if (_head(where) != head or not _ref(where, "refs/heads/main")
                or _ref(where, "refs/heads/main") == _ref(where, "refs/remotes/origin/main")):
            sys.exit("fixture setup failed in build_fixtures: %r needs local main ahead of origin/main, on %r"
                     % (where, head or "a detached HEAD"))

    make_repo(PUSHNOTRACK, {"base.txt": "base\n"})
    run_vcs(PUSHNOTRACK, "remote", "add", "origin", PUSHREMOTE)
    run_vcs(PUSHNOTRACK, "checkout", "-q", "-b", "feat")
    if (_ref(PUSHNOTRACK, "refs/remotes/origin/main") or not _ref(PUSHNOTRACK, "refs/heads/main")
            or _head(PUSHNOTRACK) != "refs/heads/feat"):
        sys.exit("fixture setup failed in build_fixtures: PUSHNOTRACK needs local main and no origin/main ref")

    make_repo(PUSHBEHIND, {"base.txt": "base\n"})
    run_vcs(PUSHBEHIND, "remote", "add", "origin", PUSHREMOTE)
    run_vcs(PUSHBEHIND, "checkout", "-q", "-b", "side")
    _work_commit(PUSHBEHIND)
    run_vcs(PUSHBEHIND, "update-ref", "refs/remotes/origin/main", "HEAD")
    run_vcs(PUSHBEHIND, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
    run_vcs(PUSHBEHIND, "checkout", "-q", "main")
    if (_head(PUSHBEHIND) != "refs/heads/main" or not _ref(PUSHBEHIND, "refs/remotes/origin/main")
            or _ref(PUSHBEHIND, "refs/heads/main") == _ref(PUSHBEHIND, "refs/remotes/origin/main")):
        sys.exit("fixture setup failed in build_fixtures: PUSHBEHIND needs origin/main ahead of local main")

    make_repo(PUSHMASTERAHEAD, {"base.txt": "base\n"})
    run_vcs(PUSHMASTERAHEAD, "branch", "-m", "main", "master")
    run_vcs(PUSHMASTERAHEAD, "remote", "add", "origin", PUSHREMOTE)
    run_vcs(PUSHMASTERAHEAD, "update-ref", "refs/remotes/origin/master", "HEAD")
    run_vcs(PUSHMASTERAHEAD, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/master")
    _work_commit(PUSHMASTERAHEAD)
    if (_head(PUSHMASTERAHEAD) != "refs/heads/master" or _ref(PUSHMASTERAHEAD, "refs/heads/main")
            or _ref(PUSHMASTERAHEAD, "refs/heads/master") == _ref(PUSHMASTERAHEAD, "refs/remotes/origin/master")):
        sys.exit("fixture setup failed in build_fixtures: PUSHMASTERAHEAD needs local master ahead, no local main")

    make_repo(PUSHNOMAIN, {"base.txt": "base\n"})
    run_vcs(PUSHNOMAIN, "branch", "-m", "main", "trunk")
    run_vcs(PUSHNOMAIN, "remote", "add", "origin", PUSHREMOTE)
    run_vcs(PUSHNOMAIN, "update-ref", "refs/remotes/origin/trunk", "HEAD")
    run_vcs(PUSHNOMAIN, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/trunk")
    run_vcs(PUSHNOMAIN, "checkout", "-q", "-b", "feat")
    if (_ref(PUSHNOMAIN, "refs/heads/main") or _ref(PUSHNOMAIN, "refs/heads/master")
            or _head(PUSHNOMAIN) != "refs/heads/feat"):
        sys.exit("fixture setup failed in build_fixtures: PUSHNOMAIN must hold no local main or master")

    make_repo(PUSHLOCALAHEAD, {"base.txt": "base\n"})
    run_vcs(PUSHLOCALAHEAD, "remote", "add", "origin", slash(BRANCHREMOTE))
    run_vcs(PUSHLOCALAHEAD, "update-ref", "refs/remotes/origin/main", "HEAD")
    run_vcs(PUSHLOCALAHEAD, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
    _work_commit(PUSHLOCALAHEAD)
    if (run_vcs(PUSHLOCALAHEAD, "config", "--get", "remote.origin.url").stdout.strip() != slash(BRANCHREMOTE)
            or _ref(PUSHLOCALAHEAD, "refs/heads/main") == _ref(PUSHLOCALAHEAD, "refs/remotes/origin/main")):
        sys.exit("fixture setup failed in build_fixtures: PUSHLOCALAHEAD needs a local-path origin, "
                 "and local main ahead")

    # The every-branch fixtures (rule push-all-main). Scope before subject: each reads back that the checkout is main,
    # that main equals its tracking ref (one commit ahead of it for PUSHALLAGENTAHEAD), and that its local branches are
    # exactly main and the one agent-named branch the fixture names (or main alone), so no case judges a fixture that
    # holds a branch it does not name.
    for where, branch, ahead in ((PUSHALLNOAGENT, None, False), (PUSHALLAGENT, "agent-0123456789abcdef", False),
                                 (PUSHALLAGENTWT, "worktree-agent-0123456789abcdef", False),
                                 (PUSHALLAGENTCLAUDE, "claude/agent-0123456789abcdef", False),
                                 (PUSHALLAGENTAHEAD, "agent-0123456789abcdef", True),
                                 (PUSHALLBROKEN, "agent-0123456789abcdef", False)):
        make_repo(where, {"base.txt": "base\n"})
        run_vcs(where, "remote", "add", "origin", PUSHREMOTE)
        run_vcs(where, "update-ref", "refs/remotes/origin/main", "HEAD")
        run_vcs(where, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        if ahead:
            _work_commit(where)
        if branch:
            run_vcs(where, "branch", branch)
        heads = sorted(run_vcs(where, "for-each-ref", "--format=%(refname)", "refs/heads/").stdout.split())
        want = sorted(["refs/heads/main"] + (["refs/heads/" + branch] if branch else []))
        main_equal = _ref(where, "refs/heads/main") == _ref(where, "refs/remotes/origin/main")
        main_ok = bool(_ref(where, "refs/heads/main")) and main_equal == (not ahead)
        if _head(where) != "refs/heads/main" or not main_ok or heads != want:
            sys.exit("fixture setup failed in build_fixtures: %r needs main equal to origin/main and local branches "
                     "%s, got %s" % (where, want, heads))
    _break_branch_listing(PUSHALLBROKEN)


def _build_worktrees():
    """The worktree remove and prune repos: locked, live, dead, stale and clean linked trees."""
    # ----------------------------------------------------------------- worktree remove/prune
    #
    # WTMAIN carries real tracked files, the same `keep.txt`/`f.txt` shape SUBJDIRTY uses above,
    # so `_require_dirty` can prove WTDIRTY really is dirty and `keep.txt` really is clean.
    make_repo(WTMAIN, {"f.txt": "base\n", "keep.txt": "base\n"})
    run_vcs(WTMAIN, "worktree", "add", "-q", WTCLEAN, "-b", "wtclean-branch")
    _require_clean(WTCLEAN)
    run_vcs(WTMAIN, "worktree", "add", "-q", WTDIRTY, "-b", "wtdirty-branch")
    write(os.path.join(WTDIRTY, "f.txt"), "uncommitted\n")
    write(os.path.join(WTDIRTY, "new.txt"), "untracked\n")
    _require_dirty(WTDIRTY, "f.txt", "new.txt", "keep.txt")
    run_vcs(WTMAIN, "worktree", "add", "-q", WTLOCKED, "-b", "wtlocked-branch")
    _require_clean(WTLOCKED)
    lock = run_vcs(WTMAIN, "worktree", "lock", WTLOCKED, "--reason", "fixture")
    if lock.returncode != 0:
        sys.exit("fixture setup failed in build_fixtures: locking WTLOCKED failed. stderr: %s"
                  % lock.stderr.strip())
    lock_check = run_vcs(WTMAIN, "worktree", "list", "--porcelain")
    locked_ok = False
    for block in lock_check.stdout.split("\n\n"):
        lines = block.splitlines()
        if not lines or not lines[0].startswith("worktree "):
            continue
        path = lines[0][len("worktree "):].strip()
        if os.path.realpath(path) != os.path.realpath(WTLOCKED):
            continue
        locked_ok = any(line == "locked" or line.startswith("locked ") for line in lines[1:])
        break
    if not locked_ok:
        sys.exit(
            "fixture setup failed in build_fixtures: WTLOCKED is not registered as locked. "
            "git worktree list --porcelain says: %r" % lock_check.stdout
        )
    run_vcs(WTMAIN, "worktree", "add", "-q", WTLIVE, "-b", "wtlive-branch")
    _require_clean(WTLIVE)
    run_vcs(WTMAIN, "worktree", "add", "-q", WTDEADSESSION, "-b", "wtdead-branch")
    _require_clean(WTDEADSESSION)
    run_vcs(WTMAIN, "worktree", "add", "-q", WTSTALESTART, "-b", "wtstalestart-branch")
    _require_clean(WTSTALESTART)

    # A live session record, built against THIS TEST RUNNER'S OWN pid, which stays alive for the
    # whole run. `startedAt` is read with `_real_process_start_ms`, a zone-free `ps -o etime=`
    # read, not the guard's `lstart=` parse, so the fixture cannot share a zone defect with the
    # code it proves.
    self_pid = os.getpid()
    self_start_ms = _real_process_start_ms(self_pid)
    os.makedirs(os.path.join(WTLIVECFG, "sessions"), exist_ok=True)
    write(
        os.path.join(WTLIVECFG, "sessions", "%d.json" % self_pid),
        json.dumps({"pid": self_pid, "cwd": slash(WTLIVE), "startedAt": self_start_ms}),
    )

    # A DEAD pid: a real short-lived process, started and waited on here, so its pid is not
    # running by the time any case reads it. The record still names the RIGHT start time for
    # that pid; only the process itself is gone, which is the exact case the plan names: "the
    # id is alive AND its recorded start time still matches".
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead_pid = dead.pid
    dead.wait(timeout=10)
    os.makedirs(os.path.join(WTDEADCFG, "sessions"), exist_ok=True)
    write(
        os.path.join(WTDEADCFG, "sessions", "%d.json" % dead_pid),
        json.dumps({"pid": dead_pid, "cwd": slash(WTDEADSESSION), "startedAt": 0}),
    )

    # A RECYCLED-PID shape: the pid IS alive (this runner, again) and the cwd sits inside the
    # target tree, but the recorded start time does not match the live process's real start
    # time. A pid can be reused by an unrelated process after the session that recorded it
    # exited, and this is exactly the statement that must not read as live.
    os.makedirs(os.path.join(WTSTALESTARTCFG, "sessions"), exist_ok=True)
    write(
        os.path.join(WTSTALESTARTCFG, "sessions", "%d.json" % self_pid),
        json.dumps({
            "pid": self_pid, "cwd": slash(WTSTALESTART), "startedAt": self_start_ms - 999999999,
        }),
    )

    # WTPRUNE is its own repository, so pruning it can never touch WTMAIN's own worktrees.
    # WTPRUNESTALE is added and then its directory is removed out from under git, the same shape
    # `is_worktree`'s own comment measures elsewhere in this file: a stale administrative record
    # with no directory behind it.
    make_repo(WTPRUNE, {"base.txt": "base\n"})
    run_vcs(WTPRUNE, "worktree", "add", "-q", WTPRUNESTALE, "-b", "wtprune-branch")
    shutil.rmtree(WTPRUNESTALE)
    prune_check = run_vcs(WTPRUNE, "worktree", "prune", "-n")
    if not (prune_check.stdout.strip() or prune_check.stderr.strip()):
        sys.exit(
            "fixture setup failed in build_fixtures: WTPRUNE has nothing to prune after "
            "WTPRUNESTALE's directory was removed. git answers stdout=%r stderr=%r"
            % (prune_check.stdout, prune_check.stderr)
        )
    prune_clean_check = run_vcs(WTMAIN, "worktree", "prune", "-n")
    if prune_clean_check.stdout.strip() or prune_clean_check.stderr.strip():
        sys.exit(
            "fixture setup failed in build_fixtures: WTMAIN unexpectedly has something to "
            "prune. git answers stdout=%r stderr=%r"
            % (prune_clean_check.stdout, prune_clean_check.stderr)
        )

# The status lines of the incident state: f.txt staged as its base copy, and g.txt staged as a deletion.
BC_INCIDENT = ["M  f.txt", "D  g.txt"]


def _base_git(where, *args):
    """One git call for the base-copy fixture. A failed call stops the suite, as the other builders do."""
    done = run_vcs(where, *args)
    if done.returncode != 0:
        sys.exit("fixture setup failed in build_fixtures: git %s failed in %r. stderr: %s"
                 % (" ".join(args), where, done.stderr.strip()))
    return done


def _base_copy_tree(where, branch, moved=True, executable=False):
    """Build one base-copy tree at `where`: a linked worktree of BCMAIN on `branch`, pushed at the base P0.
    When `executable`, P0 is a commit that sets f.txt to mode 100755, so the base carries the exec bit.
    When `moved`, BCSECOND pushes P1 (a change to f.txt, and a new g.txt) to that branch. BCMAIN then fetches
    it and moves the branch onto P1 with `update-ref`, which leaves the worktree's index on P0."""
    _base_git(BCMAIN, "worktree", "add", "-q", where, "-b", branch)
    if executable:
        _base_git(where, "update-index", "--chmod=+x", "f.txt")
        _base_git(where, *IDENT, "commit", "-q", "-m", "make f.txt executable on " + branch)
    _base_git(where, "push", "-q", "origin", branch)
    if not moved:
        return
    _base_git(BCSECOND, "fetch", "-q", "origin")
    _base_git(BCSECOND, "checkout", "-q", "-B", branch, "origin/" + branch)
    write(os.path.join(BCSECOND, "f.txt"), "changed on %s\n" % branch)
    write(os.path.join(BCSECOND, "g.txt"), "new on %s\n" % branch)
    _base_git(BCSECOND, "add", "-A")
    _base_git(BCSECOND, *IDENT, "commit", "-q", "-m", "change " + branch)
    _base_git(BCSECOND, "push", "-q", "origin", branch)
    _base_git(BCMAIN, "fetch", "-q", "origin")
    _base_git(BCMAIN, "update-ref", "refs/heads/" + branch, "refs/remotes/origin/" + branch)


def _require_base_copy(where, status, unpushed, staged_ancestor=True):
    """Stop the suite unless `where` really shows the status lines named, `unpushed` commits of HEAD on no
    remote-tracking ref, and, for the incident shape, a staged f.txt that equals the base copy and not HEAD.
    A case refused for the wrong reason would pass unnoticed otherwise, so each shape is read back with git."""
    lines = sorted(_porcelain(where))
    if lines != sorted(status):
        sys.exit("fixture setup failed in build_fixtures: %r git status --porcelain is %r, want %r"
                 % (where, lines, sorted(status)))
    missing = run_vcs(where, "rev-list", "HEAD", "--not", "--remotes").stdout.split()
    if len(missing) != unpushed:
        sys.exit("fixture setup failed in build_fixtures: %r has %d commits of HEAD on no remote-tracking "
                 "ref, want %d" % (where, len(missing), unpushed))
    if staged_ancestor:
        index = run_vcs(where, "rev-parse", ":f.txt").stdout.strip()
        base = run_vcs(where, "rev-parse", "origin/main:f.txt").stdout.strip()
        head = run_vcs(where, "rev-parse", "HEAD:f.txt").stdout.strip()
        if not index or index != base or index == head:
            sys.exit("fixture setup failed in build_fixtures: %r staged f.txt is not the base copy: "
                     "index %r, base %r, HEAD %r" % (where, index, base, head))


def _build_base_copies():
    """The base-copy trees. BCINC is the incident state, and each other tree breaks one condition of it.
    Built once, on the first case that names one of them."""
    _base_git(ROOT, "init", "-q", "--bare", BCORIGIN)
    _base_git(BCORIGIN, "symbolic-ref", "HEAD", "refs/heads/main")
    make_repo(BCSEED, {"f.txt": "base\n", "k.txt": "k base\n"})
    _base_git(BCSEED, "remote", "add", "origin", BCORIGIN)
    _base_git(BCSEED, "push", "-q", "origin", "main")
    _base_git(ROOT, "clone", "-q", BCORIGIN, BCMAIN)
    _base_git(ROOT, "clone", "-q", BCORIGIN, BCSECOND)

    # Case 1: the incident. Nothing else is wrong with this tree.
    _base_copy_tree(BCINC, "bc-inc")
    _require_base_copy(BCINC, BC_INCIDENT, 0)

    # Case 2: one worktree edit whose content is in no commit. Its index blob is still the base copy.
    _base_copy_tree(BCUNIQUE, "bc-unique")
    write(os.path.join(BCUNIQUE, "k.txt"), "unique text, in no commit\n")
    _require_base_copy(BCUNIQUE, BC_INCIDENT + [" M k.txt"], 0)

    # Case 3: an untracked file beside the incident.
    _base_copy_tree(BCUNTRACKED, "bc-untracked")
    write(os.path.join(BCUNTRACKED, "new.txt"), "untracked\n")
    _require_base_copy(BCUNTRACKED, BC_INCIDENT + ["?? new.txt"], 0)

    # Case 4: one unpushed commit on HEAD, beside the incident. The commit is limited to u.txt, so the
    # staged base copies stay staged and the tree stays dirty, as in case 1.
    _base_copy_tree(BCUNPUSHED, "bc-unpushed")
    write(os.path.join(BCUNPUSHED, "u.txt"), "local only\n")
    _base_git(BCUNPUSHED, "add", "u.txt")
    _base_git(BCUNPUSHED, *IDENT, "commit", "-q", "-m", "local only", "--", "u.txt")
    _require_base_copy(BCUNPUSHED, BC_INCIDENT, 1)

    # Case 5: the staged f.txt is the blob of one unpushed commit X, which only HEAD's reflog keeps. HEAD is
    # then moved back to the pushed tip with `update-ref`, so the index keeps X and HEAD is fully pushed.
    _base_copy_tree(BCBYPASS, "bc-bypass", moved=False)
    write(os.path.join(BCBYPASS, "f.txt"), "unpushed text, in one local commit\n")
    _base_git(BCBYPASS, "add", "f.txt")
    _base_git(BCBYPASS, *IDENT, "commit", "-q", "-m", "local only")
    local_commit = _base_git(BCBYPASS, "rev-parse", "HEAD").stdout.strip()
    _base_git(BCBYPASS, "update-ref", "refs/heads/bc-bypass", "refs/remotes/origin/bc-bypass")
    _require_base_copy(BCBYPASS, ["M  f.txt"], 0, staged_ancestor=False)
    staged = _base_git(BCBYPASS, "rev-parse", ":f.txt").stdout.strip()
    committed = _base_git(BCBYPASS, "rev-parse", local_commit + ":f.txt").stdout.strip()
    reflog = _base_git(BCBYPASS, "log", "-g", "--format=%H", "HEAD").stdout.split()
    on_remote = _base_git(BCBYPASS, "branch", "-r", "--contains", local_commit).stdout.strip()
    if staged != committed or local_commit not in reflog or on_remote:
        sys.exit("fixture setup failed in build_fixtures: the bypass tree does not hold the unpushed blob in "
                 "HEAD's reflog only: staged %r, committed %r, in reflog %r, on a remote %r"
                 % (staged, committed, local_commit in reflog, on_remote))

    # Case 6: a clean tree on a pushed branch, with no condition broken.
    _base_copy_tree(BCCLEAN, "bc-clean", moved=False)
    _require_base_copy(BCCLEAN, [], 0, staged_ancestor=False)

    # Locked: the incident tree, locked. The lock is the only condition that refuses it.
    _base_copy_tree(BCLOCKED, "bc-locked")
    _base_git(BCMAIN, "worktree", "lock", BCLOCKED, "--reason", "fixture")
    _require_base_copy(BCLOCKED, BC_INCIDENT, 0)

    # Live session: the incident tree, with one record whose cwd is the tree and whose pid is this run's own.
    _base_copy_tree(BCLIVE, "bc-live")
    self_pid = os.getpid()
    os.makedirs(os.path.join(BCLIVECFG, "sessions"), exist_ok=True)
    write(
        os.path.join(BCLIVECFG, "sessions", "%d.json" % self_pid),
        json.dumps({"pid": self_pid, "cwd": slash(BCLIVE), "startedAt": _real_process_start_ms(self_pid)}),
    )
    _require_base_copy(BCLIVE, BC_INCIDENT, 0)

    # Exec bit: the incident tree, with f.txt at mode 100755 in its base. The worktree copy is chmod 0655.
    # git reads that as 100644 (it tests the owner bit only), so f.txt is dirty in its mode alone.
    if os.name != "nt":  # Windows git ignores the exec bit, so this tree could not be built there
        _base_copy_tree(BCEXEC, "bc-exec", executable=True)
        os.chmod(os.path.join(BCEXEC, "f.txt"), 0o655)
        _require_base_copy(BCEXEC, ["MM f.txt", "D  g.txt"], 0)


lazy_fixture([BCMAIN, BCINC, BCUNIQUE, BCUNTRACKED, BCUNPUSHED, BCBYPASS, BCCLEAN, BCLOCKED, BCLIVE,
              BCLIVECFG, BCEXEC], _build_base_copies)


def _build_links():
    """The symlink worktrees: a link to a folder outside, a link to a tracked file, and controls."""
    # ----------------------------------------------------------------- symlink worktrees
    # Every tree below is DETACHED, so none of them takes a branch name. `app/package.json` is
    # tracked, which keeps `app/` a tracked directory and makes the link its own status line.
    make_repo(LINKMAIN, {"app/package.json": "{}\n", "config.json": "{}\n"})
    os.makedirs(LINKOUT, exist_ok=True)
    write(os.path.join(LINKOUT, "pkg.js"), "module.exports = {};\n")
    for where in (WTLINKDIR, WTLINKFILE, WTCTRLFILE, WTCTRLTRACKED, WTCTRLDIR, WTCTRLNESTED):
        added = run_vcs(LINKMAIN, "worktree", "add", "-q", "--detach", where)
        if added.returncode != 0:
            sys.exit("fixture setup failed in build_fixtures: worktree add %r failed. stderr: %s"
                     % (where, added.stderr.strip()))
    # A real untracked node_modules directory needs no link, so its control always runs.
    write(os.path.join(WTCTRLDIR, "app", "node_modules", "index.js"), "module.exports = {};\n")
    _require_status(WTCTRLDIR, ["?? app/node_modules/"])
    # Case 1 and the link-only controls: the only untracked entry is one symlink. Without symlink
    # privilege (MEASURED: this box raises OSError: a required privilege is not held by the client)
    # LINKS_MADE is False, from the probe, and the link cases skip, as before.
    if not LINKS_MADE:
        return
    os.symlink(LINKOUT, os.path.join(WTLINKDIR, "app", "node_modules"))
    _require_status(WTLINKDIR, ["?? app/node_modules"])
    # Case 2: the link targets a tracked file inside the same tree.
    os.symlink(os.path.join("..", "config.json"), os.path.join(WTLINKFILE, "app", "node_modules"))
    _require_status(WTLINKFILE, ["?? app/node_modules"])
    # Control: the same link, next to an untracked real file.
    os.symlink(LINKOUT, os.path.join(WTCTRLFILE, "app", "node_modules"))
    write(os.path.join(WTCTRLFILE, "notes.txt"), "untracked\n")
    _require_status(WTCTRLFILE, ["?? app/node_modules", "?? notes.txt"])
    # Control: the same link, next to a change to a tracked file.
    os.symlink(LINKOUT, os.path.join(WTCTRLTRACKED, "app", "node_modules"))
    write(os.path.join(WTCTRLTRACKED, "app", "package.json"), '{"changed": true}\n')
    _require_status(WTCTRLTRACKED, [" M app/package.json", "?? app/node_modules"])
    # Control, case 4: a link inside an untracked real directory. Git lists the directory only.
    os.makedirs(os.path.join(WTCTRLNESTED, "vendor"))
    os.symlink(LINKOUT, os.path.join(WTCTRLNESTED, "vendor", "link"))
    _require_status(WTCTRLNESTED, ["?? vendor/"])


build_fixtures()
_start_ghdev_check()
_mark("build_fixtures: eager config, fake gh writes, GHNONE and the link probe")
beat("eager fixtures at import")

# Each builder runs the first time a case names one of its paths (see lazy_fixture). A builder's
# list is every path it creates, and the config folders that point into a repo are listed with it,
# so a case that names only PTRCFG still gets PTRMAIN built.
lazy_fixture([CTXREPO], _build_ctxrepo)
lazy_fixture([CURREPO], _build_currepo)
lazy_fixture([GHDEV], _build_ghdev)
lazy_fixture([GITMAIN, GITWT, AGENTWT, FARWT, SYMWT, DECOYMAIN], _build_gitmain)
lazy_fixture([SUBJCLEAN, SUBJCLEANWT, SUBJDIRTY, SUBJSTASH, SUBJSTASHWT, SUBJSTASHDIRTY,
              SUBJSTAGED], _build_subject)
lazy_fixture([PRIVREPO], _build_privrepo)
lazy_fixture([PTRMAIN, PTRWT, PTRCFG, PTROFF, PTROFFCFG, PTRAHEAD, PTRAHEADCFG, PTRNOORIGIN,
              PTRNOORIGINCFG, PTRBADCFG, PTRGONECFG, PTRNOCFG, GITBLIND], _build_pointer)
lazy_fixture([CONFLICT], _build_conflict)
lazy_fixture([BRANCHREMOTE, BRANCHREPO, BRANCHFALLBACKMAIN, BRANCHFALLBACKMASTER, BRANCHNOBASE],
             _build_branch)
lazy_fixture([PUSHFEAT, PUSHMAIN, PUSHTRUNK, PUSHTRUNKLOCAL, PUSHNOHEAD, PUSHDETACHED, PUSHSAMETAG, PUSHDANGLING, PUSHNOHEADMAIN,
              PUSHONLYMASTER, PUSHUPSTREAM, PUSHUP, PUSHUPSELF, PUSHNOUP, PUSHMATCH, RECROADMAP, RECFORK,
              PUSHSTRAY, PUSHLANE, PUSHLANEMASTER, PUSHSELF, PUSHMAINUP, PUSHSTACK, PUSHOWNREF,
              PUSHLOCAL, PUSHLOCALSTRAY, PUSHLOCALMAIN, PUSHSSH, PUSHNOREMOTE,
              PUSHAGENT, PUSHAGENTWT, PUSHAGENTBARE, PUSHAGENTNOTES, PUSHAGENTMYABC, PUSHAGENTMYHEX,
              PUSHAGENTSHORT, PUSHAGENTEIGHT, PUSHAGENTCFG,
              PUSHAHEAD, PUSHAHEADLANE, PUSHAHEADDET, PUSHAHEADAGENT, PUSHNOTRACK, PUSHBEHIND,
              PUSHMASTERAHEAD, PUSHNOMAIN, PUSHLOCALAHEAD,
              PUSHALLNOAGENT, PUSHALLAGENT, PUSHALLAGENTWT, PUSHALLAGENTCLAUDE, PUSHALLAGENTAHEAD, PUSHALLBROKEN],
             _build_push)
lazy_fixture([WTMAIN, WTCLEAN, WTDIRTY, WTLOCKED, WTLIVE, WTDEADSESSION, WTSTALESTART, WTPRUNE,
              WTPRUNESTALE, WTLIVECFG, WTDEADCFG, WTSTALESTARTCFG], _build_worktrees)
lazy_fixture([LINKMAIN, LINKOUT, WTLINKDIR, WTLINKFILE, WTCTRLFILE, WTCTRLTRACKED, WTCTRLDIR,
              WTCTRLNESTED], _build_links)

# DOTDOTWT: a path spelled through GITMAIN's .claude/worktrees/ that climbs back out with "..",
# resolving to GITWT itself (a linked worktree OUTSIDE .claude/worktrees). It must be judged on
# where it really is, not on the ".claude/worktrees" segment in its spelling. Checked in _build_gitmain.
DOTDOTWT = os.path.join(GITMAIN, ".claude", "worktrees", "..", "..", "..", "lane")

# --------------------------------------------------------------- the ported shell traps
