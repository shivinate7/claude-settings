# section 30131
# A send_message to another session names only refs that exist (decision send-message-refs-resolve). A ref is a commit
# sha (the token rule of agent-report-shas-resolve), a pull request (PR #N, PRs #N and #M, a pull URL) or a PR comment
# link, and each resolves in the owner/repo of the cwd checkout's origin. The reads go to a local bare repo through
# insteadOf, and a fake gh comes first on PATH, so no case reaches the network. This section sits after the
# sections that define _stand_in_git (30130) and decide (27664), and before the LOG_CHECKS_EXTRA join (40805).
FAMILY = "message-ref-missing"
MRF_RULE = "message-ref-missing"
MRF_ORIGIN = "https://github.com/o/r"
MRF_DIR = os.path.join(ROOT, "mrf")
MRF_BARE = os.path.join(MRF_DIR, "bare.git")          # the origin of MRF_REPO, through insteadOf
MRF_REPO = os.path.join(MRF_DIR, "repo")              # origin is MRF_ORIGIN, and refs/pull/7/head exists
MRF_NOORIGIN = os.path.join(MRF_DIR, "noorigin")      # a repo with no origin at all
MRF_BADREMOTE = os.path.join(MRF_DIR, "badremote")    # origin routed to a bare path that is not there
MRF_NOREPO = os.path.join(MRF_DIR, "norepo")          # a plain folder, no git repo at all
MRF_GH_BIN = os.path.join(MRF_DIR, "gh-bin")          # a folder that holds the fake gh
MRF_GH_LOG = os.path.join(MRF_DIR, "gh-calls.log")    # one line per call the fake gh receives
MRF_PATH = MRF_GH_BIN + os.pathsep + os.environ.get("PATH", "")
MRF_EXISTING_PRS = list(range(10, 31))                # 21 pull requests the bare repo holds beyond #7; #8 and #9 stay missing
MRF_DEEP_SRC = os.path.join(MRF_DIR, "deep-src")      # two commits, so a depth-1 clone of it is shallow
MRF_SHALLOW = os.path.join(MRF_DIR, "shallow-clone")  # a depth-1 clone of MRF_DEEP_SRC, its sha lookups fail
# The fake gh. Comment 111 exists; any other comment is a 404. FAKE_GH_MODE=error is a 500, the non-404 failure.
# FAKE_GH_MODE=url404 is a 500 whose URL holds /404/, so it is not a 404 answer. FAKE_GH_MODE=all200 answers
# every comment as existing.
MRF_FAKE_GH = """#!/bin/sh
[ -n "$FAKE_GH_LOG" ] && printf '%s\\n' "$*" >> "$FAKE_GH_LOG"
if [ "$FAKE_GH_MODE" = error ]; then
  echo "gh: HTTP 500: Internal Server Error" >&2
  exit 1
fi
if [ "$FAKE_GH_MODE" = url404 ]; then
  echo "gh: HTTP 500: Internal Server Error (https://api.github.com/repos/o/r/issues/comments/404/)" >&2
  exit 1
fi
if [ "$FAKE_GH_MODE" = all200 ]; then
  for arg in "$@"; do
    case "$arg" in
      repos/o/r/issues/comments/*) printf '{"id":%s}\\n' "${arg##*/}"; exit 0 ;;
    esac
  done
fi
case " $* " in
  *" repos/o/r/issues/comments/111 "*) printf '%s\\n' '{"id":111}'; exit 0 ;;
esac
echo "gh: Not Found (HTTP 404)" >&2
exit 1
"""


def _mrf_probe(where, *args, env=None):
    """(return code, stdout, stderr) of one command run in `where`, for the scope checks of mrf_build."""
    done = subprocess.run(list(args), cwd=where, capture_output=True, text=True, env=env)
    return done.returncode, done.stdout.strip(), done.stderr.strip()


def mrf_build():
    """The message-ref fixtures, built on first use: a repo whose origin routes to a bare repo holding
    refs/pull/7/head, a repo with no origin, a repo whose origin routes to a missing path, and the fake gh."""
    os.makedirs(MRF_DIR, exist_ok=True)
    os.makedirs(MRF_NOREPO, exist_ok=True)
    _rsha_git(MRF_DIR, "init", "-q", "--bare", MRF_BARE)
    for where in (MRF_REPO, MRF_NOORIGIN, MRF_BADREMOTE):
        os.makedirs(where, exist_ok=True)
        _rsha_git(where, "init", "-q", "-b", "main", ".")
        write(os.path.join(where, "src", "app.py"), "x = 1\n")
        _rsha_git(where, "add", "-A")
        _rsha_git(where, *IDENT, "commit", "-q", "-m", "base", date=RSHA_DATE)
    _rsha_git(MRF_REPO, "remote", "add", "origin", MRF_ORIGIN)
    _rsha_git(MRF_REPO, "config", "url.%s.insteadOf" % MRF_BARE, MRF_ORIGIN)
    _rsha_git(MRF_REPO, "push", "-q", "origin", "HEAD:refs/heads/main")
    head = _rsha_git(MRF_REPO, "rev-parse", "HEAD")
    _rsha_git(MRF_BARE, "update-ref", "refs/pull/7/head", head)
    for number in MRF_EXISTING_PRS:
        _rsha_git(MRF_BARE, "update-ref", "refs/pull/%d/head" % number, head)
    os.makedirs(MRF_DEEP_SRC, exist_ok=True)
    _rsha_git(MRF_DEEP_SRC, "init", "-q", "-b", "main", ".")
    for text, message in (("x = 1\n", "first"), ("x = 2\n", "second")):
        write(os.path.join(MRF_DEEP_SRC, "src", "app.py"), text)
        _rsha_git(MRF_DEEP_SRC, "add", "-A")
        _rsha_git(MRF_DEEP_SRC, *IDENT, "commit", "-q", "-m", message, date=RSHA_DATE)
    _rsha_git(MRF_DIR, "clone", "-q", "--depth", "1", "file://" + slash(MRF_DEEP_SRC), MRF_SHALLOW)
    if _rsha_git(MRF_SHALLOW, "rev-parse", "--is-shallow-repository") != "true":
        sys.exit("fixture setup failed in mrf_build: MRF_SHALLOW is not a shallow clone")
    _rsha_git(MRF_BADREMOTE, "remote", "add", "origin", MRF_ORIGIN)
    _rsha_git(MRF_BADREMOTE, "config", "url.%s.insteadOf" % os.path.join(MRF_DIR, "missing.git"), MRF_ORIGIN)
    os.makedirs(MRF_GH_BIN, exist_ok=True)
    gh = os.path.join(MRF_GH_BIN, "gh")
    write(gh, MRF_FAKE_GH)
    os.chmod(gh, 0o755)
    # The scope every case relies on, read before any case does (P7). A fault here names itself, not a red case.
    rc, listed, _ = _mrf_probe(MRF_REPO, VCS, "ls-remote", "origin")
    if rc != 0 or "refs/pull/7/head" not in listed or "refs/pull/8/head" in listed:
        sys.exit("fixture setup failed in mrf_build: origin of MRF_REPO does not reach the bare repo "
                 "(git exit %d)" % rc)
    rc, _, _ = _mrf_probe(MRF_BADREMOTE, VCS, "ls-remote", "origin")
    if rc == 0:
        sys.exit("fixture setup failed in mrf_build: origin of MRF_BADREMOTE reads, so it does not fail")
    rc, remotes, _ = _mrf_probe(MRF_NOORIGIN, VCS, "remote")
    if rc != 0 or remotes:
        sys.exit("fixture setup failed in mrf_build: MRF_NOORIGIN has a remote")
    rc, _, _ = _mrf_probe(MRF_NOREPO, VCS, "config", "--local", "--get", "remote.origin.url")
    if rc != 128:
        sys.exit("fixture setup failed in mrf_build: MRF_NOREPO is inside a git repo (git config exit %d)" % rc)
    gh_env = dict(os.environ, PATH=MRF_PATH)
    rc, _, _ = _mrf_probe(MRF_REPO, "gh", "api", "repos/o/r/issues/comments/111", env=gh_env)
    if rc != 0:
        sys.exit("fixture setup failed in mrf_build: the fake gh does not allow comment 111 (exit %d)" % rc)
    rc, _, err = _mrf_probe(MRF_REPO, "gh", "api", "repos/o/r/issues/comments/222", env=gh_env)
    if rc == 0 or "404" not in err:
        sys.exit("fixture setup failed in mrf_build: the fake gh does not 404 comment 222")
    rc, _, err = _mrf_probe(MRF_REPO, "gh", "api", "repos/o/r/issues/comments/222",
                            env=dict(gh_env, FAKE_GH_MODE="error"))
    if rc == 0 or "404" in err:
        sys.exit("fixture setup failed in mrf_build: the fake gh error mode is not a non-404 failure")


lazy_fixture([MRF_REPO, MRF_NOORIGIN, MRF_NOREPO, MRF_BADREMOTE, MRF_GH_BIN, MRF_SHALLOW, MRF_DEEP_SRC], mrf_build)


def mrf_judge(cwd, message, agent=None, env_path=None, mode=None):
    """(decision, reason) for one send_message from `cwd`, with an agent_id when `agent` is given."""
    env = {"FAKE_GH_LOG": MRF_GH_LOG}
    if mode:
        env["FAKE_GH_MODE"] = mode
    return decide({
        "raw": None, "tool": SEND_MESSAGE, "cwd": cwd, "session": None,
        "env_path": env_path or MRF_PATH, "config": None,
        "agent_id": agent, "agent_type": "builder" if agent else None,
        "tool_input": {"message": message}, "transcript": None, "event": None,
        "stop_active": False, "env": env, "no_root": False, "guard": None,
        "temp": None, "max_seconds": None,
    })


def mrf_case(name, expected, message, cwd=MRF_REPO, carries=(), mode=None, context=False, lacks=()):
    """One send_message case from the main session. An agent's send never reaches this check: the agent-remote-tools
    rule (agent-no-remote-tools) refuses it first, so an agent variant could only ever read that refusal.
    `context` asks for an allow whose output holds additionalContext and no permissionDecision key. `lacks` names
    fragments the printed reason must not hold."""
    env = {"FAKE_GH_LOG": MRF_GH_LOG}
    if mode:
        env["FAKE_GH_MODE"] = mode
    add("message-ref-missing: %s, main session" % name, expected, MRF_RULE if expected == "deny" else None,
        tool=SEND_MESSAGE, cwd=cwd, env_path=MRF_PATH, env=env, carries=carries, lacks=lacks,
        no_permission_key=context, message=message)


mrf_case("a made-up commit sha is refused", "deny", "Record link: commit 8c1f0e2a7 has the fix.",
         carries=("8c1f0e2a7",))
mrf_case("PR #8, which the repo does not have, is refused and named", "deny", "PR #8 has the fix.",
         carries=("#8",))
mrf_case("a pull URL of this repo for PR 9 is refused and named", "deny",
         "See https://github.com/o/r/pull/9 for it.", carries=(("#9", "pull/9"),))
mrf_case("a comment link to comment 222, which does not exist, is refused and named", "deny",
         "See https://github.com/o/r/pull/7#issuecomment-222 for the reply.", carries=("222",))
mrf_case("PR #7, which the repo has, is allowed", "allow", "PR #7 has the fix.")
mrf_case("a comment link to comment 111, which exists, is allowed", "allow",
         "See https://github.com/o/r/pull/7#issuecomment-111 for the reply.")
mrf_case("a bare #8 with no PR word is not judged", "allow", "Item #8 is open.")
mrf_case("a pull URL of another repo is not judged", "allow",
         "See https://github.com/x/y/pull/8 for the upstream change.")
mrf_case("a sha on a line that names x/y@<sha> on main is not judged", "allow", "x/y@8c1f0e2a7 on main.")
mrf_case("a PR in a repo with no origin is not judged", "allow", "PR #8 has the fix.", cwd=MRF_NOORIGIN)
# A folder that is no git repo: its PR and comment links are neither judged nor named, and its sha is named unchecked.
mrf_case("a PR, a comment link and a made-up sha in a folder that is no git repo: the sha is named, the PR and comment are not",
         "allow", "See https://github.com/o/r/pull/7#issuecomment-222 and PR #8 for it, at 8c1f0e2a7.",
         cwd=MRF_NOREPO, carries=("8c1f0e2a7",), lacks=("#8", "222"), context=True)
mrf_case("a message with no ref is allowed", "allow", "Verdict: pass, nothing to name.")
# Fail open: the call is allowed, and the output names each ref it could not check in additionalContext,
# with no permissionDecision key, so the sender sees the note and no permission prompt is skipped.
mrf_case("a gh error on comment 222 is allowed, and the output names 222", "allow",
         "See https://github.com/o/r/pull/7#issuecomment-222 for the reply.", carries=("222",), mode="error",
         context=True)
mrf_case("an ls-remote that fails is allowed, and the output names PR #7", "allow", "PR #7 has the fix.",
         cwd=MRF_BADREMOTE, carries=("#7",), context=True)
# The forms a sha, a pull request and a commit link take in running text, each judged by the ref it names.
mrf_case("a made-up sha after Head, on a branch name, is refused", "deny",
         "Head 8c1f0e2a7 on lane/env-file-scope", carries=("8c1f0e2a7",))
mrf_case("a made-up sha after Rebased on origin/main at is refused", "deny",
         "Rebased on origin/main at 8c1f0e2a7.", carries=("8c1f0e2a7",))
mrf_case("pull request #8, which the repo does not have, is refused and named", "deny",
         "pull request #8 has the fix.", carries=("#8",))
mrf_case("#8 (PR), which the repo does not have, is refused and named", "deny",
         "#8 (PR) has the fix.", carries=("#8",))
mrf_case("pr #8, which the repo does not have, is refused and named", "deny",
         "pr #8 has the fix.", carries=("#8",))
mrf_case("a pull URL with no scheme for PR 8 is refused and named", "deny",
         "See github.com/o/r/pull/8 for it.", carries=("#8",))
mrf_case("a pull URL with a /files tail for PR 8 is refused and named", "deny",
         "See https://github.com/o/r/pull/8/files for it.", carries=("#8",))
mrf_case("PRs 7 and 8, with 8 missing, is refused and names 8", "deny",
         "PRs 7 and 8 are open.", carries=("#8",))
mrf_case("a commit link of this repo for a made-up sha is refused", "deny",
         "See https://github.com/o/r/commit/8c1f0e2a7 for it.", carries=("8c1f0e2a7",))
# The refusal of a missing sha names the route to it: `git fetch origin`, the route the report-sha refusal names.
mrf_case("a made-up sha is refused, and the refusal names git fetch origin", "deny",
         "Record link: commit 8c1f0e2a7 has the fix.", carries=("8c1f0e2a7", "git fetch origin"))
mrf_case("a made-up commit link is refused, and the refusal names git fetch origin", "deny",
         "See https://github.com/o/r/commit/8c1f0e2a7 for it.", carries=("8c1f0e2a7", "git fetch origin"))
# Fail open: a gh 500 whose URL holds /404/ is not a 404, so the link is left unchecked and named.
mrf_case("a gh 500 whose URL holds /404/ leaves comment 333 unchecked, and the output names it", "allow",
         "See https://github.com/o/r/pull/7#issuecomment-333 for the reply.", carries=("333",), mode="url404",
         context=True)
# Controls: a ref of another repo, written with a mark, is not judged.
mrf_case("acme/widgets: PR #8 names another repo and is not judged", "allow", "acme/widgets: PR #8 has the fix.")
mrf_case("acme/widgets#8 names another repo and is not judged", "allow", "See acme/widgets#8 for it.")
mrf_case("x/y@<sha> alone is not judged", "allow", "x/y@8c1f0e2a7")
mrf_case("a bare PR #7 is allowed", "allow", "PR #7")


def mrf_lines(path):
    return open(path, encoding="utf-8").read().splitlines() if os.path.exists(path) else []


def mrf_cost_run(message):
    """(problem, (git lines, gh lines)) for one send_message from MRF_REPO, through the stand-in git and the fake gh.
    A stand-in that sees no call makes the counts meaningless, so that is the problem instead."""
    materialize(MRF_REPO)
    log, path = _stand_in_git("mrf_cost")
    if not path:
        return "no git on PATH, so the stand-in cannot count", None
    if not rsha_stand_in_sees(log, path, cwd=MRF_REPO):
        return "the stand-in git saw no call, so the counts prove nothing", None
    for name in (log, MRF_GH_LOG):
        if os.path.exists(name):
            os.remove(name)
    mrf_judge(MRF_REPO, message, env_path=MRF_GH_BIN + os.pathsep + path)
    return "", (mrf_lines(log), mrf_lines(MRF_GH_LOG))


def mrf_no_ref_cost_case():
    """A message with no ref starts no git process and no gh call."""
    if os.name == "nt":
        return SKIP, "skipped: a stand-in git and a shell fake gh are not reached through CreateProcess"
    problem, runs = mrf_cost_run("Verdict: pass, nothing to name.")
    if problem:
        return False, problem
    gits, gh = runs
    if gits or gh:
        return False, "a message with no ref started %d git and %d gh process(es), want none: %r" % (
            len(gits), len(gh), (gits + gh)[:2])
    return True, "a message with no ref starts no git or gh process"


def mrf_pr_once_cost_case():
    """PRs #7 and #8 together start exactly one git ls-remote."""
    if os.name == "nt":
        return SKIP, "skipped: a stand-in git is not reached through CreateProcess"
    problem, runs = mrf_cost_run("PRs #7 and #8 are open.")
    if problem:
        return False, problem
    remotes = [line for line in runs[0] if "ls-remote" in line]
    if len(remotes) != 1:
        return False, "%d ls-remote call(s) for PRs #7 and #8, want exactly one: %r" % (len(remotes), remotes[:2])
    return True, "PRs #7 and #8 start exactly one ls-remote"


LOG_CHECKS_EXTRA.append(("message-ref-missing: a message with no ref starts no git or gh process",
                         mrf_no_ref_cost_case))
LOG_CHECKS_EXTRA.append(("message-ref-missing: PRs #7 and #8 start exactly one git ls-remote", mrf_pr_once_cost_case))
FIXTURELESS_CHECKS.update((mrf_no_ref_cost_case, mrf_pr_once_cost_case))

SIX_LINKS = " ".join("https://github.com/o/r/pull/7#issuecomment-%d" % n for n in range(201, 207))


def mrf_six_links_case():
    """Six comment links make at most five gh calls, and the sixth is named as unchecked
    (decision send-message-refs-resolve)."""
    if os.name == "nt":
        return SKIP, "skipped: the fake gh is a POSIX shell script"
    materialize(MRF_REPO)
    if os.path.exists(MRF_GH_LOG):
        os.remove(MRF_GH_LOG)
    decision, reason = mrf_judge(MRF_REPO, "Links: " + SIX_LINKS + ".", mode="all200")
    calls = mrf_lines(MRF_GH_LOG)
    if len(calls) != 5:
        return False, "%d gh call(s) for six comment links, want 5" % len(calls)
    if "206" not in reason:
        return False, "the sixth link, comment 206, is not named as unchecked: %r" % reason[:160]
    if decision != "allow":
        return False, "%s, want allow for a link left unchecked" % decision
    return True, "six comment links make five gh calls, and the sixth is named unchecked"


LOG_CHECKS_EXTRA.append(("message-ref-missing: six comment links make five gh calls, and the sixth is named unchecked",
                         mrf_six_links_case))
FIXTURELESS_CHECKS.add(mrf_six_links_case)

# Pins of built behaviour for the guard lines that decide a ref's repo or the PR list. Each is green on the built code.
# hooks/mutate_guard.py has one mutant for this rule, on its deny line, so these pins have none.
mrf_case("o/r: PR #8 names this repo, so PR 8 is judged and refused", "deny",
         "o/r: PR #8 has the fix.", carries=("#8",))
mrf_case("PR #7, 12 files: a singular PR reads one number, so 12 is not judged", "allow",
         "PR #7, 12 files are open.")
mrf_case("origin/main: PR #8 names no other repo, so PR 8 is judged and refused", "deny",
         "origin/main: PR #8 has the fix.", carries=("#8",))
mrf_case("hooks/guard.py:100 PR #8 names no repo, so PR 8 is judged and refused", "deny",
         "hooks/guard.py:100 PR #8 has the fix.", carries=("#8",))

# Marks and forms, in running text. The first group's labels are not repo marks, so the made-up PR and sha on each line are judged.
mrf_case("CI/CD: PR #8 is green is refused", "deny", "CI/CD: PR #8 is green.", carries=("#8",))
mrf_case("Done/Next: PR #8 open is refused", "deny", "Done/Next: PR #8 open.", carries=("#8",))
mrf_case("Batch 2/3: PR #8 merged is refused", "deny", "Batch 2/3: PR #8 merged.", carries=("#8",))
mrf_case("Done/Next: head 8c1f0e2a7 is refused", "deny", "Done/Next: head 8c1f0e2a7", carries=("8c1f0e2a7",))
mrf_case("PR: #8 is refused and named", "deny", "PR: #8", carries=("#8",))
mrf_case("PR (#8) is refused and named", "deny", "PR (#8)", carries=("#8",))
mrf_case("**PR** #8 is refused and named", "deny", "**PR** #8", carries=("#8",))
mrf_case("PR `#8` is refused and named", "deny", "PR `#8`", carries=("#8",))
mrf_case("PR number 8 is refused and named", "deny", "PR number 8", carries=("#8",))
mrf_case("PRs #7 #8 names 8 and is refused", "deny", "PRs #7 #8", carries=("#8",))
mrf_case("PRs #7 or #8 names 8 and is refused", "deny", "PRs #7 or #8", carries=("#8",))
mrf_case("PRs #7 + #8 names 8 and is refused", "deny", "PRs #7 + #8", carries=("#8",))
# Fail open: a shallow clone and a repo with no origin name what they could not check, with no permissionDecision.
mrf_case("a made-up sha in a shallow clone is allowed, and the output names the sha", "allow",
         "Rebased on 8c1f0e2a7.", cwd=MRF_SHALLOW, carries=("8c1f0e2a7",), context=True)
mrf_case("PR #8 in a repo with no origin is allowed, and the output names #8", "allow",
         "PR #8 has the fix.", cwd=MRF_NOORIGIN, carries=("#8",), context=True)
# Another repo's PR, written with a mark, is not judged.
mrf_case("acme/widgets PR #9 is another repo and is allowed", "allow", "acme/widgets PR #9 is ready.")
# Twenty-one PRs that exist: the first twenty resolve, and the twenty-first is named as unchecked, not dropped.
MRF_TWENTY_ONE = "PRs " + ", ".join("#%d" % number for number in MRF_EXISTING_PRS) + " are open."
mrf_case("21 existing PRs are allowed, and the output names the 21st, #30", "allow", MRF_TWENTY_ONE,
         carries=("#30",), context=True)
# A capitalised repo with a colon mark is not a mark, so its PR is judged against this repo.
mrf_case("Acme/Widgets: PR #8 is judged against this repo and refused", "deny", "Acme/Widgets: PR #8 has the fix.",
         carries=("#8",))


# Which repo (decision send-message-refs-resolve, "Which repo"): a branch with this repo's own prefix (lane/, archive/,
# claude/, handoff/) is not another repo, so a PR number or a sha on its line is judged here. The green controls are the
# `PR: #8` case and the `acme/widgets PR #9 is ready.` case above.
mrf_case("a lane/ branch names PR #8, which the repo does not have, and is refused", "deny",
         "lane/send-message-refs-resolve PR #8 is open.", carries=("#8",))
mrf_case("an archive/ branch with a colon names PR #8 and is refused", "deny",
         "archive/send-message-refs: PR #8 pushed.", carries=("#8",))
mrf_case("a claude/ branch with a colon names PR #8 and is refused", "deny",
         "claude/fix-foo: PR #8 is open.", carries=("#8",))
mrf_case("a handoff/ branch names PR #8 and is refused", "deny", "handoff/x PR #8 ready.", carries=("#8",))
mrf_case("an archive/ branch with a colon names sha 8c1f0e2a7 and is refused", "deny",
         "archive/send-message-refs: pushed 8c1f0e2a7", carries=("8c1f0e2a7",))
# What is judged (decision send-message-refs-resolve, "What is judged"): a number after PR with no # is no PR.
mrf_case("PR: 2500 lines changed, with no #, is no PR and is allowed", "allow", "PR: 2500 lines changed.")
mrf_case("PR (2500 lines) is big, with no #, is no PR and is allowed", "allow", "PR (2500 lines) is big.")
# A PR or pull word judges the first #N after it when other words or marks stand between them (decision
# send-message-refs-resolve, "What is judged"). A bare #N with no PR word is not judged; the controls keep that line.
mrf_case("PR opened: #8 is refused and names 8", "deny", "PR opened: #8", carries=("#8",))
mrf_case("PR is #8 is refused and names 8", "deny", "PR is #8", carries=("#8",))
mrf_case("PR - #8 is refused and names 8", "deny", "PR - #8", carries=("#8",))
mrf_case("PR, #8 is open is refused and names 8", "deny", "PR, #8 is open", carries=("#8",))
mrf_case("Opened the PR as #8 is refused and names 8", "deny", "Opened the PR as #8", carries=("#8",))
mrf_case("the PR for this lane is #8 is refused and names 8", "deny", "the PR for this lane is #8", carries=("#8",))
mrf_case("pull #8 is open is refused and names 8", "deny", "pull #8 is open", carries=("#8",))
mrf_case("PR [#8] is open is refused and names 8", "deny", "PR [#8] is open", carries=("#8",))
mrf_case("this repo's owner/repo#8 is open is refused and names 8", "deny", "o/r#8 is open", carries=("#8",))
mrf_case("Issue #8 is open. is allowed, with no PR word", "allow", "Issue #8 is open.")
mrf_case("PR #7 is open. is allowed", "allow", "PR #7 is open.")
mrf_case("acme/widgets#8 is open. names another repo and is allowed", "allow", "acme/widgets#8 is open.")
mrf_case("PR #7, 12 files is allowed, and 12 is not judged", "allow", "PR #7, 12 files")
# Each #N after a PR word is judged, so the second number of `PR #7 is #8` is refused. A PR word inside a name, a
# `pull` not right before its number, a closing or issue word between the word and the number, and an issue's
# owner/repo#N are no PR.
mrf_case("PR #7 is #8, the second number after a found PR, is refused and names 8", "deny", "PR #7 is #8.",
         carries=("#8",))
mrf_case("a PR word inside branch msg-ref-pr-forms is no PR word, so #8 is allowed", "allow",
         "branch msg-ref-pr-forms, see #8")
mrf_case("pull with words before its number is no PR, so #8 is allowed", "allow", "pull the list at #8")
mrf_case("an issue's owner/repo#8 is no PR, so it is allowed", "allow", "Issue o/r#8 is open.")
mrf_case("PR closes #8 is no PR, so #8 is allowed", "allow", "This PR closes #8.")
mrf_case("PR fixes #8 is no PR, so #8 is allowed", "allow", "The PR fixes #8.")
# A pull request word still judges its number, and a digit, an issue word or a gap of more than six words keeps a
# number unjudged.
mrf_case("the pull request for this lane is #8 is refused and names 8", "deny",
         "the pull request for this lane is #8", carries=("#8",))
mrf_case("PR for step 2 is #8 is allowed, a digit in the gap", "allow", "PR for step 2 is #8")
mrf_case("PR for this bug is #8 is allowed, an issue word in the gap", "allow", "PR for this bug is #8")
mrf_case("PR for the lock in the cache today is #8 is allowed, more than six words in the gap", "allow",
         "PR for the lock in the cache today is #8")
# A hex colour after a PR word is a colour, not a PR number, so its digits are not judged.
mrf_case("PR #7 sets the background to #0b0f14 is allowed", "allow", "PR #7 sets the background to #0b0f14.")
mrf_case("The PR changes the border to #000000 is allowed", "allow", "The PR changes the border to #000000.")
# Fail open (decision send-message-refs-resolve, "Fail open"): twenty-one made-up shas in a shallow clone, where none
# resolves, so each is unchecked. The twenty-first is named by the twenty-sha cap, not dropped.
MRF_TWENTY_ONE_SHAS = "Shas: " + " ".join("d1e%04x" % number for number in range(1, 22))
mrf_case("21 made-up shas are allowed, and the output names the 21st, d1e0015", "allow", MRF_TWENTY_ONE_SHAS,
         cwd=MRF_SHALLOW, carries=("d1e0015",), context=True)
# Text that names another repo, or a quoted line, is not this repo's ref (decision send-message-refs-resolve, "Which
# repo"; the quote rule of decision agent-report-shas-resolve, which a sha already follows). A PR label that links to
# another repo's pull is that repo's PR, and a `> ` line or a double-quoted span is quoted text, which may come from
# another repo. The controls: a bare PR and this repo's own link to the same PR are still refused.
mrf_case("a PR label that links another repo's pull is not judged", "allow",
         "Upstream fix: [PR #8](https://github.com/facebook/react/pull/8) merged.")
mrf_case("a PR on a `> ` quoted line is not judged", "allow", "> lane says PR #8 merged")
mrf_case("a PR in a double-quoted span is not judged", "allow",
         'The other lane wrote "PR #8 is green" in its report.')
mrf_case("PR #8 merged, bare, is refused and named", "deny", "PR #8 merged.", carries=("#8",))
mrf_case("this repo's link to PR #8 merged is refused and named", "deny",
         "[PR #8](https://github.com/o/r/pull/8) merged.", carries=("#8",))
# A sha written as the text of a link to another repo's commit names that repo's commit, so it is not judged, as a PR
# in the same link form is not. Its control is the same shape with this repo's origin, which is refused. The quote
# rule blanks each `"..."` span on a line, and a `>` after the span must not make the rest of the line a quote line.
mrf_case("a made-up sha as the link text of another repo's commit is not judged", "allow",
         "Upstream fix: [0123abc](https://github.com/acme/widgets/commit/0123abc) merged.")
mrf_case("a made-up sha as the link text of this repo's commit is refused", "deny",
         "Upstream fix: [0123abc](https://github.com/o/r/commit/0123abc) merged.", carries=("0123abc",))
mrf_case("a made-up sha after a closed double-quoted span and a > mark is refused", "deny",
         '"x" > landed as 0123abc', carries=("0123abc",))
mrf_case("a made-up sha after x and a > mark is refused", "deny", "x > landed as 0123abc", carries=("0123abc",))
