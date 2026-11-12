# section 29942
FAMILY = "merge"  # a merge rule: GUARD_FAMILY=merge selects this section's cases
REPO_RULE = "merge-confirm-repo"
REPO_A = os.path.join(ROOT, "repo-o-a")       # origin github.com/o/a
REPO_B = os.path.join(ROOT, "repo-o-b")       # origin github.com/o/b
REPO_HASH = os.path.join(ROOT, "repo#a")      # origin github.com/o/a, a path that holds a `#`
MERGE_ORIGINS = {REPO_A: "https://github.com/o/a", REPO_B: "https://github.com/o/b", REPO_HASH: "https://github.com/o/a"}


def _build_merge_origins():
    """The three checkouts of the merge-confirm-repo cases: see MERGE_ORIGINS."""
    _build_origins(MERGE_ORIGINS)


lazy_fixture(list(MERGE_ORIGINS), _build_merge_origins)
CLOUD_ENV = {**ROLE_ENV, "CLAUDE_CODE_REMOTE": "true"}  # decide() drops CLAUDE_CODE_REMOTE, then applies a case's env
TX_A = role_path("repo-o-a")             # a lane whose record names cs-repo:o/a
TX_RUNNER = role_path("repo-runner-claude-settings")
TX_CHILDREN = role_path("repo-runner-children")
TX_EMPTY = role_path("repo-empty-tags")
TX_NONE = role_path("no-record")
TX_BAD = role_path("not-json")
TX_FOLDER = role_path("unreadable")
NO_CHECKOUT = os.path.join(ROOT, "no-such-checkout")


def repo_case(name, expected, command, cwd, transcript, env=CLOUD_ENV):
    """One case: `command` runs in `cwd` with the transcript and env given. A deny must name REPO_RULE."""
    sh("merge-confirm-repo: " + name, command, expected, rule=REPO_RULE if expected == "deny" else None,
       cwd=cwd, transcript=transcript, env=env)


# A cloud merge is denied when the checkout it names is not the repo the own record proves.
repo_case("--repo-dir names another checkout is denied", "deny", f"{MERGE_SHIM} --repo-dir '{REPO_B}' 5 --confirm", REPO_A, TX_A)
repo_case("--repo-dir= names another checkout is denied", "deny", f"{MERGE_SHIM} --repo-dir='{REPO_B}' 5 --confirm", REPO_A, TX_A)
repo_case("-C names another checkout is denied", "deny", f"{MERGE_SHIM} -C '{REPO_B}' 5 --confirm", REPO_A, TX_A)
repo_case("-C glued to its value names another checkout and is denied", "deny", f"{MERGE_SHIM} -C'{REPO_B}' 5 --confirm", REPO_A, TX_A)
repo_case("a flag after the PR number is judged and denied", "deny", f"{MERGE_SHIM} 5 --confirm --repo-dir '{REPO_B}'", REPO_A, TX_A)
repo_case("the last of two flags names another checkout and is denied", "deny",
          f"{MERGE_SHIM} --repo-dir '{REPO_A}' -C '{REPO_B}' 5 --confirm", REPO_A, TX_A)
repo_case("a cd into another checkout, then a merge, is denied", "deny", f"cd '{REPO_B}' && {MERGE_SHIM} 5 --confirm", REPO_A, TX_A)
repo_case("no flag and a working directory of another checkout is denied", "deny", f"{MERGE_SHIM} 5 --confirm", REPO_B, TX_A)
repo_case("a lone quote before a merge of another checkout is denied", "deny",
          f"echo it's && {MERGE_SHIM} --repo-dir {REPO_B} 5 --confirm", REPO_A, TX_A)
# A flag whose value cannot be read is a denial: no checkout, no git checkout, no value, an empty value, or an option where the value goes.
repo_case("a flag naming no checkout is denied", "deny", f"{MERGE_SHIM} --repo-dir '{NO_CHECKOUT}' 5 --confirm", REPO_A, TX_A)
repo_case("a flag naming a folder that is no git checkout is denied", "deny", f"{MERGE_SHIM} --repo-dir '{NOGIT}' 5 --confirm", REPO_A, TX_A)
repo_case("a flag with no value is denied", "deny", f"{MERGE_SHIM} 5 --confirm --repo-dir", REPO_A, TX_A)
repo_case("a flag with an empty value is denied", "deny", f"{MERGE_SHIM} --repo-dir= 5 --confirm", REPO_A, TX_A)
repo_case("-C followed by an option, with no value, is denied", "deny", f"{MERGE_SHIM} 5 -C --confirm", REPO_A, TX_A)
# A record that cannot prove a repo denies the merge: no tags, no get_session record, a record that is not JSON, a folder in its place, no transcript.
repo_case("a record with no tags denies the merge", "deny", f"{MERGE_SHIM} --repo-dir '{REPO_A}' 5 --confirm", REPO_A, TX_EMPTY)
repo_case("no get_session record denies the merge", "deny", f"{MERGE_SHIM} --repo-dir '{REPO_A}' 5 --confirm", REPO_A, TX_NONE)
repo_case("a record that is not JSON denies the merge", "deny", f"{MERGE_SHIM} --repo-dir '{REPO_A}' 5 --confirm", REPO_A, TX_BAD)
repo_case("a transcript that cannot be read denies the merge", "deny", f"{MERGE_SHIM} --repo-dir '{REPO_A}' 5 --confirm", REPO_A, TX_FOLDER)
repo_case("no transcript denies the merge", "deny", f"{MERGE_SHIM} --repo-dir '{REPO_A}' 5 --confirm", REPO_A, None)
# A runner whose only repo is a child's may not merge claude-settings, with or without the flag.
repo_case("a runner with only a child repo tag is denied a claude-settings merge", "deny", f"{MERGE_SHIM} 5 --confirm",
          LANE_REPO, TX_CHILDREN)
repo_case("a runner with only a child repo tag is denied a claude-settings merge named by flag", "deny",
          f"{MERGE_SHIM} --repo-dir '{LANE_REPO}' 5 --confirm", REPO_A, TX_CHILDREN)
# The same merge is allowed when the own record names the checkout's repo: a flag names it, a cd names it, a working directory names it,
# a path with a hash is read whole, and the proxy's origin names the same repo.
repo_case("--repo-dir naming this checkout is allowed from another directory", "allow",
          f"{MERGE_SHIM} --repo-dir '{REPO_A}' 5 --confirm", REPO_B, TX_A)
repo_case("a cd into this checkout is allowed from another directory", "allow", f"cd '{REPO_A}' && {MERGE_SHIM} 5 --confirm", REPO_B, TX_A)
repo_case("no flag and this working directory is allowed", "allow", f"{MERGE_SHIM} 5 --confirm", REPO_A, TX_A)
# gh-write-cloud: the merge tool is no gh write, so a cloud merge it runs is allowed. merge-confirm-repo also judges it, so these run in
# REPO_A with the lane record that names its repo: the allow is then gh-write-cloud's own, not a refusal of a missing record.
for _command in ("merge 12 --confirm", MERGE_SHIM + " 12 --confirm"):
    sh("gh-write-cloud: %s is allowed in a cloud session" % _command, _command, "allow", cwd=REPO_A, env=CLOUD_ENV, transcript=TX_A)
# A redirect or pipe on the merge belongs to the shell, not to the merge tool's arguments. The control above has none.
repo_case("a merge piped to tee with 2>&1 is allowed", "allow", f"{MERGE_SHIM} 5 --confirm 2>&1 | tee run.out", REPO_A, TX_A)
repo_case("a merge with a > file and 2>&1 is allowed", "allow", f"{MERGE_SHIM} 5 --confirm > run.log 2>&1", REPO_A, TX_A)
repo_case("a merge with a > file and 2>&1 that names another checkout is denied", "deny",
          f"{MERGE_SHIM} -C '{REPO_B}' 5 --confirm > run.log 2>&1", REPO_A, TX_A)
# A reason flag's quoted value may hold `>` or `<`. The shell reads it as text, not as a redirect, so the merge is judged on its
# arguments: the arrow or the `<` in the reason is allowed, and a -C naming another checkout beside it is still denied.
repo_case("a quoted --base-red-ok reason with -> is allowed", "allow",
          f'{MERGE_SHIM} 185 --confirm --base-red-ok "fix -> lane"', REPO_A, TX_A)
repo_case("a --base-red-ok=value with -> in its quotes is allowed", "allow",
          f'{MERGE_SHIM} 185 --confirm --base-red-ok="x -> y"', REPO_A, TX_A)
repo_case("a single-quoted --base-red-ok reason with < is allowed", "allow",
          "merge 185 --confirm --base-red-ok 'a < b'", REPO_A, TX_A)
repo_case("a quoted --base-red-ok reason with -> beside -C another checkout is denied", "deny",
          f'{MERGE_SHIM} -C \'{REPO_B}\' 185 --confirm --base-red-ok "fix -> lane"', REPO_A, TX_A)
repo_case("a --base-red-ok=value with -> beside -C another checkout is denied", "deny",
          f'{MERGE_SHIM} -C \'{REPO_B}\' 185 --confirm --base-red-ok="x -> y"', REPO_A, TX_A)
repo_case("a single-quoted --base-red-ok reason with < beside -C another checkout is denied", "deny",
          f"merge -C '{REPO_B}' 185 --confirm --base-red-ok 'a < b'", REPO_A, TX_A)
# A -C after a quoted reason is still read: a fix that cut the command at the first quote would allow this one.
repo_case("a -C after a quoted reason with -> names another checkout and is denied", "deny",
          f'{MERGE_SHIM} --base-red-ok "a -> b" -C \'{REPO_B}\' 185 --confirm', REPO_A, TX_A)
repo_case("an unquoted reason with a > file and 2>&1 is allowed", "allow",
          f"{MERGE_SHIM} 185 --confirm --base-red-ok fixlane > run.log 2>&1", REPO_A, TX_A)
repo_case("an unquoted reason with a > file and 2>&1 beside -C another checkout is denied", "deny",
          f"{MERGE_SHIM} -C '{REPO_B}' 185 --confirm --base-red-ok fixlane > run.log 2>&1", REPO_A, TX_A)
# Each backslash escape is one step of the quote walk but two characters, and strip_redirections indexes the walk's marks by
# character. An escape therefore shifts every later mark: a legitimate merge is denied, and a -C naming another checkout beside it is allowed.
# The raw strings keep each backslash. The quoted-reason cases above, with no escape, are the green controls.
repo_case("a reason with an escaped quote in double quotes is allowed", "allow",
          r'merge 185 --confirm --base-red-ok "fix \"x\" red"', REPO_A, TX_A)
repo_case("a reason with an escaped dollar is allowed", "allow", r"merge 185 --confirm --base-red-ok \$X", REPO_A, TX_A)
repo_case("a reason with an escaped space is allowed", "allow", r"merge 185 --confirm --base-red-ok a\ b", REPO_A, TX_A)
repo_case("a > file named with an escaped space is allowed", "allow", r"merge 185 --confirm > a\ b", REPO_A, TX_A)
repo_case("a reason with an escaped space beside a &> file and -C another checkout is denied", "deny",
          rf"merge 5 --confirm --base-red-ok a\ b &> o -C '{REPO_B}' 2>&1", REPO_A, TX_A)
repo_case("a path with a hash names its checkout whole and is allowed", "allow", f"{MERGE_SHIM} --repo-dir '{REPO_HASH}' 5 --confirm",
          REPO_B, TX_A)
repo_case("a runner that names claude-settings is allowed through the proxy's origin", "allow", f"{MERGE_SHIM} 5 --confirm", LANE_PROXY,
          TX_RUNNER)
repo_case("a runner that names claude-settings by flag is allowed", "allow", f"{MERGE_SHIM} --repo-dir '{LANE_REPO}' 5 --confirm",
          REPO_A, TX_RUNNER)
# The checkout a merge acts in is the one in force where the merge's own segment runs: a `cd` before it in the same clause, else the
# working directory. A `cd` after the merge, a `git -C` on another segment and a later `cd` do not move that checkout.
repo_case("a cd into another checkout before a merge, then a cd back after it, is denied", "deny",
          f"cd '{REPO_B}' && {MERGE_SHIM} 5 --confirm; cd '{REPO_A}'", REPO_A, TX_A)
repo_case("a cd into another checkout before a merge, then a cd back chained after it, is denied", "deny",
          f"cd '{REPO_B}' && {MERGE_SHIM} 5 --confirm && cd '{REPO_A}'", REPO_A, TX_A)
repo_case("a git -C of this checkout, then a cd into another checkout and a merge, is denied", "deny",
          f"git -C '{REPO_A}' status && cd '{REPO_B}' && {MERGE_SHIM} 5 --confirm", REPO_A, TX_A)
repo_case("a merge before a cd into another checkout is allowed", "allow", f"{MERGE_SHIM} 5 --confirm; cd '{REPO_B}'", REPO_A, TX_A)
repo_case("a git -C of another checkout before a merge does not move the shell, so it is allowed", "allow",
          f"git -C '{REPO_B}' fetch && {MERGE_SHIM} 5 --confirm", REPO_A, TX_A)
# A cd the guard cannot follow (a variable, a missing folder) leaves no checkout, so the merge is denied. A fallback to the working
# directory would allow it. The -C cases read the value against the folder the cd leaves.
repo_case("a cd to a variable, then a merge, is denied", "deny", f"cd $X && {MERGE_SHIM} 5 --confirm", REPO_A, TX_A)
repo_case("a cd to a missing folder, then a merge, is denied", "deny", f"cd '{NO_CHECKOUT}' && {MERGE_SHIM} 5 --confirm", REPO_A, TX_A)
repo_case("a cd to the parent of this checkout, then -C naming this checkout, is allowed from another checkout", "allow",
          f"cd '{os.path.dirname(REPO_A)}' && {MERGE_SHIM} -C '{os.path.basename(REPO_A)}' 5 --confirm", REPO_B, TX_A)
repo_case("a cd to the parent of this checkout, then -C naming another checkout, is denied from this one", "deny",
          f"cd '{os.path.dirname(REPO_A)}' && {MERGE_SHIM} -C '{os.path.basename(REPO_B)}' 5 --confirm", REPO_A, TX_A)
# A merge inside a subshell or a bash -c string takes the checkout its own segment names, as a bare one does. The record is
# claude-settings's (TX_RUNNER), the tagged checkout is LANE_REPO, and REPO_B is the other checkout.
repo_case("a cd into another checkout in a subshell, then a merge, is denied", "deny",
          f"(cd '{REPO_B}' && {MERGE_SHIM} 5 --confirm)", LANE_REPO, TX_RUNNER)
repo_case("a cd into another checkout inside bash -c, then a merge, is denied", "deny",
          f"bash -c 'cd {REPO_B} && {MERGE_SHIM} 5 --confirm'", LANE_REPO, TX_RUNNER)
repo_case("a -C naming another checkout inside bash -c is denied", "deny",
          f"bash -c '{MERGE_SHIM} -C {REPO_B} 5 --confirm'", LANE_REPO, TX_RUNNER)
repo_case("a merge in a subshell inside the tagged checkout is allowed", "allow",
          f"({MERGE_SHIM} 5 --confirm)", LANE_REPO, TX_RUNNER)
# A lane the owner started (G2, owner 2026-11-10 14:23 CST; G10, 14:33 CST) merges only in the repo its own record's sources name:
# claude-settings. The repo gate reads the cs-repo tags, and a lane can tag itself, so the scope is judged on the sources as well:
# a merge in another repo is denied even when a tag names that repo. No refusal wording is pinned here.
LONE_CS = role_path("lone-lane-repo")          # sources and cs-repo tag name claude-settings
LONE_O_A = role_path("lone-repo-o-a")          # sources name claude-settings, the cs-repo tag names o/a
LONE_OTHER = role_path("lone-other-sources")   # sources name shivinate7/mailaudit, the cs-repo tag names o/a
LONE_NO_SOURCES = role_path("lone-no-sources")  # no sources, the cs-repo tag names o/a
LONE_UNTAGGED = role_path("lone-untagged")     # sources name claude-settings, no tags at all
LONE_SELF_READ = role_path("lone-self-tag-then-read")
LONE_SELF_STALE = role_path("lone-self-tag-no-reread")


def scope_case(name, expected, command, cwd, transcript, env=CLOUD_ENV):
    """One case of a lane the owner started. No rule name is pinned, so a refusal of any rule passes."""
    sh("lone-lane scope: " + name, command, expected, cwd=cwd, transcript=transcript, env=env)


scope_case("a lane the owner started whose sources name claude-settings is denied a merge in o/a, though its tag names o/a",
           "deny", f"{MERGE_SHIM} 5 --confirm", REPO_A, LONE_O_A)
scope_case("a lane the owner started whose sources name claude-settings is denied a merge in o/a named by flag",
           "deny", f"{MERGE_SHIM} --repo-dir '{REPO_A}' 5 --confirm", REPO_A, LONE_O_A)
scope_case("a lane the owner started whose sources name another repo is denied a merge in o/a, though its tag names o/a",
           "deny", f"{MERGE_SHIM} 5 --confirm", REPO_A, LONE_OTHER)
scope_case("a lane the owner started whose record names no source is denied a merge in o/a, though its tag names o/a",
           "deny", f"{MERGE_SHIM} 5 --confirm", REPO_A, LONE_NO_SOURCES)
scope_case("a lane the owner started whose sources name claude-settings is allowed a merge in claude-settings",
           "allow", f"{MERGE_SHIM} 5 --confirm", LANE_PROXY, LONE_CS)
scope_case("a lane the owner started whose sources name claude-settings is allowed a merge in claude-settings named by flag",
           "allow", f"{MERGE_SHIM} --repo-dir '{LANE_REPO}' 5 --confirm", REPO_A, LONE_CS)
scope_case("a lane the owner started that tags itself and reads its record again is allowed a merge in claude-settings",
           "allow", f"{MERGE_SHIM} 5 --confirm", LANE_PROXY, LONE_SELF_READ)
scope_case("a lane the owner started that tags itself and does not read its record again is denied a merge in claude-settings",
           "deny", f"{MERGE_SHIM} 5 --confirm", LANE_PROXY, LONE_SELF_STALE)
# No cs-repo tag at all: merge-confirm-repo denies it, and the remedy names the owner-started lane and the runner it asks (G2, G10).
sh("merge-confirm-repo: a lane the owner started with no cs-repo tag is denied, and its remedy names the owner-started lane",
   f"{MERGE_SHIM} 5 --confirm", "deny", rule=REPO_RULE, cwd=LANE_PROXY, transcript=LONE_UNTAGGED, env=CLOUD_ENV,
   carries=OWNER_LANE_ASK)

# The head check of a lane the owner started. Its confirm must name, with --head, a head that is the tip of a branch in the checkout the
# merge acts in: the head it built and pushed. The merge tool requires --head for the batch-runner role and compares it with the PR's live
# head, so the two checks together put the PR's head in this checkout. The batch runner is not subject to it: its record carries
# cs-build:batch-runner. Fixed commit objects (the empty tree, one identity, one date) give the same shas on every run.
import hashlib  # noqa: E402  the fixed commit shas below; the section runs in the guard test's globals
LANE_TIP = os.path.join(ROOT, "lanetip")  # a checkout whose origin is claude-settings, with one branch: lane-tip
TIP_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"  # git's empty tree, in every repo


def _commit_body(parent, message):
    """The text of a commit object: the empty tree, one identity, one date, and the parent when there is one."""
    lines = ["tree " + TIP_TREE] + (["parent " + parent] if parent else [])
    lines += ["author lane <lane@example.com> 1794528000 +0000", "committer lane <lane@example.com> 1794528000 +0000", "", message]
    return "\n".join(lines) + "\n"


def _commit_sha(body):
    """The sha git gives the commit object with this text."""
    raw = body.encode()
    return hashlib.sha1(b"commit %d\x00" % len(raw) + raw).hexdigest()


PR_HEAD_BODY = _commit_body(None, "the head the pull request had")
PR_HEAD = _commit_sha(PR_HEAD_BODY)                      # the head the PR had, now behind the local tip
TIP_BODY = _commit_body(PR_HEAD, "the local tip, one commit past the pull request head")
TIP = _commit_sha(TIP_BODY)                              # the tip of lane-tip in LANE_TIP
OTHER_PR_HEAD = _commit_sha(_commit_body(None, "another pull request's head, not in this checkout"))


def _build_lane_tip():
    """LANE_TIP: a checkout with origin claude-settings, the two commits, and the branch lane-tip at the newer one."""
    make_repo(LANE_TIP, {"README.md": "# lane\n"})
    run_vcs(LANE_TIP, "remote", "add", "origin", "https://github.com/" + ARCH_REPO_SETTINGS)
    for body, sha in ((PR_HEAD_BODY, PR_HEAD), (TIP_BODY, TIP)):
        written = subprocess.run([VCS, "hash-object", "-t", "commit", "-w", "--stdin"], input=body, cwd=LANE_TIP,
                                 capture_output=True, text=True)
        if written.returncode != 0 or written.stdout.strip() != sha:
            sys.exit("fixture setup failed in build_fixtures: git did not write the commit %s in %r. stderr: %s"
                     % (sha, LANE_TIP, written.stderr.strip()))
    run_vcs(LANE_TIP, "update-ref", "refs/heads/lane-tip", TIP)


lazy_fixture([LANE_TIP], _build_lane_tip)


def head_case(name, expected, head, transcript):
    """One merge confirm in LANE_TIP that names `head` with --head. A deny must name REPO_RULE."""
    sh("merge-confirm-repo: " + name, f"{MERGE_SHIM} 5 --confirm --head {head}", expected,
       rule=REPO_RULE if expected == "deny" else None, cwd=LANE_TIP, transcript=transcript, env=CLOUD_ENV)


head_case("a lane the owner started whose confirm names its own branch tip is allowed", "allow", TIP, LONE_CS)
head_case("a lane the owner started whose confirm names another pull request's head is denied", "deny", OTHER_PR_HEAD, LONE_CS)
head_case("a lane the owner started whose confirm names a head its branch has moved past is denied", "deny", PR_HEAD, LONE_CS)
head_case("a batch runner whose confirm names a head outside this checkout is not judged and is allowed", "allow", OTHER_PR_HEAD,
          TX_RUNNER)
# Not judged: a merge named in quoted text, --lane-lint (no lock, no merge), and any session outside the cloud.
repo_case("a merge named in a quoted echo is not judged", "allow", f"echo '{MERGE_SHIM} --repo-dir {REPO_B} 5 --confirm'", REPO_A, TX_A)
repo_case("--lane-lint is not judged, whatever the record", "allow", f"{MERGE_SHIM} --lane-lint --repo-dir '{REPO_B}' 5", REPO_A, TX_NONE)
repo_case("--lane-lint naming no git checkout is not judged", "allow", f"{MERGE_SHIM} --lane-lint --repo-dir '{NOGIT}' 5", REPO_A, TX_NONE)
repo_case("outside the cloud a merge is not judged", "allow", f"{MERGE_SHIM} --repo-dir '{REPO_B}' 5 --confirm", REPO_A, TX_A,
          env=ROLE_ENV)


# strip_redirections, read directly: each input has one escape, or none as a control. The quoted text must survive whole and the
# redirect target must be cut, so the strip keeps a reason's text and drops only the unquoted redirect. A raised error fails its
# check; it does not crash the run.
STRIP_REDIRECT_CASES = (
    (r'merge 185 --confirm --base-red-ok "fix \"x\" red" > run.log', r'"fix \"x\" red"', "run.log"),
    (r"merge 185 --confirm --base-red-ok a\ b > run.log", r"a\ b", "run.log"),
    (r"merge 185 --confirm --base-red-ok $'it\'s > x' > run.log", r"$'it\'s > x'", "run.log"),
    (r"merge 185 --confirm --base-red-ok \$X > run.log", r"\$X", "run.log"),
    (r"merge 5 --confirm --base-red-ok a\ b &> o", r"a\ b", "o"),
    (r'echo "a # b" > run.log', r'"a # b"', "run.log"),   # control: quoted text with no escape
    (r"echo don't > run.log", "don't", "run.log"),          # control: a contraction is text, not a quote
)


def strip_redirections_case():
    """strip_redirections keeps the quoted text of each input and cuts only its unquoted redirect.

    _load_guard_module() reloads guard_core, so sys.modules["guard_core"] is the copy beside the file under test.
    """
    _load_guard_module()
    core = sys.modules["guard_core"]
    problems = []
    for command, quoted, target in STRIP_REDIRECT_CASES:
        try:
            got = core.strip_redirections(command)
        except Exception as error:   # a misaligned walk raises here: a named failure of this check
            problems.append("%r: strip_redirections raised %s" % (command, type(error).__name__))
            continue
        if quoted not in got:
            problems.append("%r: quoted text %r is not kept, got %r" % (command, quoted, got))
        if target in got.split():
            problems.append("%r: redirect target %r is not cut, got %r" % (command, target, got))
    if problems:
        return False, "; ".join(problems)
    return True, "strip_redirections keeps quoted text and cuts only the unquoted redirect"


LOG_CHECKS_EXTRA.append(("merge-confirm-repo: strip_redirections keeps quoted text and cuts only the unquoted redirect",
                         strip_redirections_case))
