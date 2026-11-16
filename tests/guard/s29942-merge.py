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
# `merge <pr> --ready` pushes the records page to the pull request's branch, from the checkout it acts in, as --confirm's draft step does. It takes
# the same repo proof as --confirm: the checkout must be the repo the own record names, and a flag, a cd or the working directory decides which.
repo_case("--ready from another checkout's repo is denied", "deny", f"{MERGE_SHIM} 5 --ready", REPO_B, TX_A)
repo_case("--ready with --repo-dir naming another checkout is denied", "deny", f"{MERGE_SHIM} --repo-dir '{REPO_B}' 5 --ready", REPO_A, TX_A)
repo_case("--ready with -C naming another checkout is denied", "deny", f"{MERGE_SHIM} -C '{REPO_B}' 5 --ready", REPO_A, TX_A)
repo_case("--ready after a cd into another checkout is denied", "deny", f"cd '{REPO_B}' && {MERGE_SHIM} 5 --ready", REPO_A, TX_A)
repo_case("--ready with a record that proves no repo is denied", "deny", f"{MERGE_SHIM} 5 --ready", REPO_A, TX_NONE)
# Controls: a lane marks its own draft ready once, from its own repo, and the proof passes, as --confirm's does.
repo_case("--ready from this checkout's repo is allowed", "allow", f"{MERGE_SHIM} 5 --ready", REPO_A, TX_A)
repo_case("--ready with --repo-dir naming this checkout is allowed from another directory", "allow",
          f"{MERGE_SHIM} --repo-dir '{REPO_A}' 5 --ready", REPO_B, TX_A)
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
# Not judged: a merge named in quoted text, --lane-lint (no lock, no merge), and any session outside the cloud.
repo_case("a merge named in a quoted echo is not judged", "allow", f"echo '{MERGE_SHIM} --repo-dir {REPO_B} 5 --confirm'", REPO_A, TX_A)
# The two lane-lint rows run in the background under the lane lint's time limit, so check-timeout passes them.
# They pin this rule, not the limit.
add("merge-confirm-repo: --lane-lint is not judged, whatever the record", "allow", cwd=REPO_A,
    transcript=TX_NONE, env=CLOUD_ENV,
    run_in_background=True, timeout=CHECK_TIMEOUT_MS, description=TAIL_BG_UNTIL,
    command=f"{MERGE_SHIM} --lane-lint --repo-dir '{REPO_B}' 5")
add("merge-confirm-repo: --lane-lint naming no git checkout is not judged", "allow", cwd=REPO_A,
    transcript=TX_NONE, env=CLOUD_ENV,
    run_in_background=True, timeout=CHECK_TIMEOUT_MS, description=TAIL_BG_UNTIL,
    command=f"{MERGE_SHIM} --lane-lint --repo-dir '{NOGIT}' 5")
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
