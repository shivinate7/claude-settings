#!/usr/bin/env python3
"""Fails when a change closes a debt without proof that its Retire step holds. Stdlib and git only.

    python3 lint/check_debt_retire.py [--upstream origin/main] [--head HEAD] [--strict]

A debt is closed when its file is deleted, or renamed out of the debts folder (lint/layout.py, kind debts). The
check reads that debt's Retire paragraph from the base and runs what it names, on the head:

  runnable  a backticked span that is a test file the head tracks (test_*.py, *_test.py, *.test.mjs, test_*.mjs,
            test_*.sh) runs as one argv, with no shell, from the head folder, under a timeout. Non-zero is red.
            A missing interpreter, a failed start, or a timeout is unknown.
  prose     a Retire that names no runnable check holds the close, unless the PR body cites a run:
            `Retire-run: <slug> -- <run URL>`, read as the Drops-lines line of check_silent_undo is. The run must be
            green and on the PR head or a commit above it. A cite also clears a check that could not run here (unknown);
            a red check is never cleared by a cite.

A runnable suite that a step of the head's `.github/workflows/checks.yml` runs is judged from that step in the PR's own CI run instead,
once, in CI (a caller that gives check() a ci_steps reader): every such step must be success on a run of the head or a commit above it.
A draft has no run yet, so its close is deferred, neither passed nor refused. A skipped step falls back to the local run above.

Exit 1 on any finding. Design: decision debt-close-runs-retire.
"""
import argparse
import contextlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_record_slugs as records  # noqa: E402  the one home of the record markers and the changed-files read
import check_silent_undo as undo  # noqa: E402  the one home of the PR body's key-line reading
import layout  # noqa: E402  the one home of where the debts folder is
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py; check_record_slugs puts hooks on the path)

Unknown = records.Unknown  # a git read failed, so the closes are not known
CITE = "Retire-run"
TIMEOUT = 1800  # per suite; interim stopgap (owner 12:11 CST Nov 10, decision ci-job-caps; ends with step time-pinned-tests-go)
# Each runnable suffix with the argv that starts it. The check never runs anything else.
INTERPRETERS = {".py": ["python3"], ".mjs": ["node", "--test"], ".sh": ["bash"]}
TEST_NAME = re.compile(r"^(?:test_[^/]+\.(?:py|mjs|sh)|[^/]+_test\.py|[^/]+\.test\.mjs)$")
SPAN = re.compile(r"`([^`\s]+)`")  # no space inside: a lone backtick in prose never swallows the real span after it
CITE_LINE = re.compile(r"\s*(\S+)\s+--\s+(\S+)\s*$")
CI_WORKFLOW = ".github/workflows/checks.yml"  # the one workflow whose steps prove a suite; the merge tool reads its run by name (merge.py CI_RUN_NAME)
CI_RED = ("failure", "timed_out")  # a step that ended another way than these or success is no verdict on the suite


class Finding:
    def __init__(self, slug, kind, text):
        self.slug, self.kind, self.text = slug, kind, text

    def __repr__(self):
        return "Finding(%r, %r)" % (self.slug, self.kind)


def retire_text(lines):
    """The Retire paragraph of a debt: its marker line and the lines after it, up to a blank line or the next marker."""
    retire, any_marker = records.marker("Retire"), records.marker()
    out = []
    for line in lines:
        if out and (not line.strip() or any_marker.match(line)):
            break
        if out or retire.match(line):
            out.append(line)
    return " ".join(" ".join(out).split())


def spans(text, tracked):
    """The backticked test files of `text` that the head tracks, in order, each once."""
    found = []
    for s in SPAN.findall(text):
        s = s[2:] if s.startswith("./") else s
        if s in tracked and TEST_NAME.match(os.path.basename(s)) and os.path.splitext(s)[1] in INTERPRETERS and s not in found:
            found.append(s)
    return found


@contextlib.contextmanager
def scratch(wt, head):
    """A detached worktree of `head` under the temp dir, removed after: what a Retire test writes stays there and never reaches `wt`, except through a linked `node_modules`, which is the install itself (see link_packages).
    A tree that cannot be made yields None, and the test is unknown."""
    tmp = tempfile.mkdtemp(prefix="debt-retire-")
    tree = os.path.join(tmp, "tree")
    try:
        made = _nowindow.run(["git", "-C", wt, "worktree", "add", "-q", "--detach", tree, head], capture_output=True).returncode == 0
        if made:
            link_packages(wt, tree)
        yield tree if made else None
    finally:
        _nowindow.run(["git", "-C", wt, "worktree", "remove", "--force", tree], capture_output=True)
        shutil.rmtree(tmp, ignore_errors=True)


def link_packages(wt, tree):
    """Link the installed `node_modules` into the scratch tree, at the root and beside each package.json the tree holds.
    A fresh worktree has none, so a test that imports a package would exit "module not found" and read red (decision debt-close-runs-retire).
    Each folder comes from `wt` when `wt` has it, else from the main checkout of `wt`'s repository: the merge tool's `wt` is itself a
    fresh worktree, and the install lives in the checkout it was made from. No other place is read.
    The link is that install's own folder, so a Retire test that writes or deletes inside `node_modules` changes it (repaired by an install;
    decision debt-close-runs-retire). It reads the installed packages, never head's lockfile.
    A folder neither place has is not linked, so a test that needs it still fails. Best effort: a link that cannot be made leaves the test to run without it."""
    homes = [os.path.abspath(wt)]  # absolute: a relative link target would resolve inside the scratch tree, to itself
    main = installed_checkout(wt)
    if main and main not in homes:
        homes.append(main)
    listed = _nowindow.run(["git", "-C", tree, "ls-files", "-z", "--", "package.json", "*/package.json"], capture_output=True, encoding="utf-8", errors="replace")
    for pkg in listed.stdout.split("\0"):
        rel = os.path.join(os.path.dirname(pkg), "node_modules")
        dst = os.path.join(tree, rel)
        src = next((s for s in (os.path.join(h, rel) for h in homes) if os.path.isdir(s)), None)
        if pkg and src and not os.path.lexists(dst):
            try:
                os.symlink(src, dst, target_is_directory=True)
            except OSError:
                pass


def installed_checkout(wt):
    """The absolute path of the main checkout of `wt`'s repository: the folder that holds its `.git`, from git's common dir.
    None when git cannot say, or when the repository is bare (its common dir is not a `.git` folder), so no path is guessed."""
    got = _nowindow.run(["git", "-C", wt, "rev-parse", "--git-common-dir"], capture_output=True, encoding="utf-8", errors="replace")
    common = got.stdout.strip()
    if got.returncode or not common:
        return None
    common = os.path.abspath(os.path.join(wt, common))  # a relative answer is relative to `wt`
    return os.path.dirname(common) if os.path.basename(common) == ".git" else None


def run_span(wt, span, timeout):
    """(kind, text) for one test: red on a non-zero exit, unknown when it could not run, else None."""
    argv = list(INTERPRETERS[os.path.splitext(span)[1]])
    exe = shutil.which(argv[0])
    if not exe:
        return "unknown", "%s is not on PATH, so %s did not run" % (argv[0], span)
    try:
        r = _nowindow.run([exe, *argv[1:], span], cwd=wt, capture_output=True, encoding="utf-8", errors="replace",
                                  timeout=timeout, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    except subprocess.TimeoutExpired:
        return "unknown", "%s ran past %d s" % (span, timeout)
    except OSError as e:
        return "unknown", "%s did not start: %s" % (span, e)
    if r.returncode:
        tail = " | ".join((r.stdout + r.stderr).strip().splitlines()[-5:])
        return "red", "%s exited %d%s" % (span, r.returncode, ": " + tail[:400] if tail else "")
    return None


def cites(pr_body):
    """{debt slug: run URL} from the `Retire-run: <slug> -- <url>` lines of the PR body's last paragraph. The last cite of a slug wins."""
    res = {}
    for line in re.findall(r"^" + CITE + r":(.*)$", undo.last_paragraph(pr_body), re.I | re.M | re.ASCII):
        m = CITE_LINE.match(line)
        if m:
            res[m.group(1)] = m.group(2)
    return res


def covers(wt, head, sha):
    """True when `sha` is `head` or a commit above it, False when it is not, None when this checkout cannot say."""
    rc = _nowindow.run(["git", "-C", wt, "merge-base", "--is-ancestor", head, str(sha)], capture_output=True).returncode
    return True if rc == 0 else False if rc == 1 else None


def judge_run(wt, head, url, run_state):
    """(kind, text) for a cited run, or None when it is green on the head or a commit above it."""
    if run_state is None:
        return "unknown", "no reader for the cited run %s" % url
    try:
        conclusion, sha = run_state(url)
    except Exception as e:  # any failed read: the run is unknown, never clear
        return "unknown", "the cited run %s could not be read: %s" % (url, " ".join(str(e).split()))
    if conclusion != "success":
        return "red", "the cited run %s ended %s, not success" % (url, conclusion)
    held = covers(wt, head, sha)
    if held:
        return None
    if held is False:
        return "red", "the cited run %s is on %s, not on the PR head %s or a commit above it" % (url, str(sha)[:9], head[:9])
    return "unknown", "the cited run %s is on %s, which this checkout does not hold" % (url, str(sha)[:9])


BLOCK = re.compile(r"[|>][+-]?\d?\s*(?:#.*)?$")
KEY = re.compile(r"(?P<key>[\w.-]+|'[^']*'|\"[^\"]*\")\s*:(?:\s+(?P<val>.*))?$")


def scalar(value):
    """The value of a YAML `key: value` line: a quoted string without its quotes, an unquoted one up to a ` #` comment. A quote inside an unquoted value is text."""
    value = value.strip()
    if value[:1] not in ("'", '"'):
        return re.split(r"(?:^|\s)#", value, maxsplit=1)[0].strip()
    q, i = value[0], 1
    while i < len(value):
        if value[i] == "\\" and q == '"':
            i += 2
        elif value[i] == q and q == "'" and value[i + 1:i + 2] == q:
            i += 2
        elif value[i] == q:
            return value[1:i]
        else:
            i += 1
    return value[1:]


def entries(text):
    """[(indent, key column, dashed, key, value)] of the content lines of a YAML file: no blank or comment line, and the lines of a block scalar folded into its value.
    A line that is not `key: value` has key None."""
    lines, out, i = text.splitlines(), [], 0
    while i < len(lines):
        raw, i = lines[i], i + 1
        body = raw.strip()
        if not body or body.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        dash = re.match(r"(?:-\s+)+", body)
        rest = body[dash.end():] if dash else body
        column = indent + (dash.end() if dash else 0)
        m = KEY.match(rest)
        key, val = (m.group("key").strip("'\""), m.group("val") or "") if m else (None, rest)
        if m and BLOCK.match(val):
            block = []
            while i < len(lines) and (not lines[i].strip() or len(lines[i]) - len(lines[i].lstrip(" ")) > column):
                block.append(lines[i].strip())
                i += 1
            val = "\n".join(block).strip()
        elif m:
            val = scalar(val)
        out.append((indent, column, bool(dash), key, val))
    return out


def ci_jobs(text):
    """[(job id, job name, [(step name, run text)])] of a workflow file, read by indentation. A job's name is its `name:`, else its id; a step's, its `name:`, else GitHub's `Run <first line>`.
    A shape this scan does not read (a flow-style `jobs:`) gives no job, so no suite counts as run by CI."""
    rows = entries(text)
    start = next((n for n, r in enumerate(rows) if r[0] == 0 and r[3] == "jobs" and not r[4]), None)
    if start is None:
        return []
    body = []
    for r in rows[start + 1:]:
        if r[0] == 0:
            break
        body.append(r)
    jobs, job = [], None
    for indent, column, dash, key, val in body:
        if indent == body[0][0] and not dash and key and not val:
            job = {"id": key, "name": key, "key": None, "dash": None, "step": None, "steps": []}  # dash: the steps list's dash column, -1 until the first item
            jobs.append(job)
            continue
        if job is None:
            continue
        if job["key"] is None:
            job["key"] = indent
        if job["dash"] is not None and job["dash"] >= 0 and not (indent > job["dash"] or (indent == job["dash"] and dash)):
            job["dash"] = None  # a job key after the list ends it
        if job["dash"] is None:
            if indent == job["key"] and not dash and key == "name" and val:
                job["name"] = val
            elif indent == job["key"] and not dash and key == "steps" and not val:
                job["dash"] = -1
            continue
        if job["dash"] == -1:
            if not dash:
                job["dash"] = None
                continue
            job["dash"] = indent
        if dash and indent == job["dash"]:
            job["step"] = {"name": None, "run": "", "column": column}
            job["steps"].append(job["step"])
        step = job["step"]
        if step and column == step["column"] and key in ("name", "run"):
            step[key] = val
    return [(j["id"], j["name"], [(s["name"] or "Run " + (s["run"].splitlines() or [""])[0], s["run"]) for s in j["steps"]]) for j in jobs]


def runs_suite(run, span):
    """True when the shell text `run` names the test file `span` as a word of its own: not a longer path, not a longer name."""
    return bool(re.search(r"(?<![\w./-])(?:\./)?" + re.escape(span) + r"(?![\w./-])", run))


LOCAL = object()  # the CI judgment gives no verdict: run the suite here


class Deferred:
    """A draft's close whose suite a CI step runs: no run exists yet, so it neither passes nor refuses."""

    def __init__(self, slug):
        self.slug = slug


class CiJudge:
    """The CI-step judgment of one check: the head's workflow and the PR head's CI steps, each read once, on first use.
    reader(sha) -> [{job, name, conclusion, status, run_sha}], one row per step of the PR's checks run (a job that lists no steps, as a skipped one, is one row with name None), or raises."""

    def __init__(self, reader, draft=False):
        self.reader, self.draft, self.flow, self.rows = reader, draft, None, None

    def named(self, wt, head, tracked, span):
        """[(job id, job name, step name)] of each step of the head's workflow whose `run:` names `span`. Empty when CI is not read or the head has no workflow."""
        if self.reader is None or CI_WORKFLOW not in tracked:
            return []
        if self.flow is None:
            try:
                self.flow = ci_jobs("\n".join(records.show(wt, head, CI_WORKFLOW)))
            except Unknown:
                self.flow = []
        return [(jid, jname, step) for jid, jname, steps in self.flow for step, run in steps if runs_suite(run, span)]

    def read(self, head):
        """The step rows of the PR head's run, or the (kind, text) pair when they could not be read."""
        if self.rows is None:
            try:
                got = self.reader(head)
                ok = isinstance(got, (list, tuple)) and all(isinstance(r, dict) and {"job", "conclusion", "status", "run_sha"} <= set(r) for r in got)
                self.rows = list(got) if ok else ("unknown", "the CI steps of the PR head were not given as a list of steps")
            except Exception as e:  # any failed read: unknown, never clear
                self.rows = ("unknown", "the CI steps of the PR head could not be read: %s" % " ".join(str(e).split()))
        return self.rows

    def judge(self, wt, head, span, named):
        """(kind, text) for `span` from its CI steps, None when each is success on a run of the head or above, LOCAL when one was skipped and none is red or unknown.
        A red step outranks an unknown one, which outranks a skipped one. A run of another head says nothing about this one: unknown, never red."""
        rows = self.read(head)
        if isinstance(rows, tuple):
            return rows
        red = unknown = None
        skipped = False
        for jid, jname, step in named:
            hits = [r for r in rows if r["job"] in (jname, jid) or str(r["job"]).startswith((jname + " (", jid + " ("))]  # a matrix job is "name (value)"
            mine = [r for r in hits if r.get("name") == step] or [r for r in hits if r.get("name") is None]
            if not mine:
                unknown = unknown or ("unknown", "%s: the PR head's checks run has no step %r of job %r" % (span, step, jname))
            for r in mine:
                where = "step %r of job %r" % (step, r["job"])
                held = covers(wt, head, r["run_sha"]) if r["run_sha"] else False
                if not held:
                    why = "not on the PR head %s or a commit above it" % head[:9] if held is False else "a commit this checkout does not hold"
                    unknown = unknown or ("unknown", "%s: %s ran on %s, %s" % (span, where, str(r["run_sha"])[:9], why))
                elif r["status"] != "completed" or not r["conclusion"]:
                    unknown = unknown or ("unknown", "%s: %s has not finished in CI" % (span, where))
                elif r["conclusion"] in CI_RED:
                    red = red or ("red", "%s is red in CI: %s ended %s" % (span, where, r["conclusion"]))
                elif r["conclusion"] == "skipped":
                    skipped = True
                elif r["conclusion"] != "success":
                    unknown = unknown or ("unknown", "%s: %s ended %s in CI, which is no verdict" % (span, where, r["conclusion"]))
        return red or unknown or (LOCAL if skipped else None)


SKIP = object()  # a rename inside the debts folder with its Retire unchanged: not a close


def closes(wt, base_ref, head):
    """(debt, closed, head sha, merge base, tracked files) for the debts `head` closes against `base_ref`, or None when it closes none. Raises Unknown."""
    try:
        debt = records.debt_file(wt)
    except layout.LayoutError as e:
        raise Unknown("the debts folder is not known: %s" % e)
    # A rename inside the folder is a close only when its Retire changed (decided in judge_close, once the texts are read).
    closed = [(old, new) for status, old, new in records.changes(wt, base_ref, head)[1]
              if debt(old) and (status == "D" or (status == "R" and (not debt(new) or new != old)))]
    if not closed:
        return None
    head = records.git_names(wt, "rev-parse", head + "^{commit}")[0].strip()
    mb = records.git_names(wt, "merge-base", base_ref, head)[0].strip()
    tracked = set(records.git_names(wt, "ls-tree", "-r", "-z", "--name-only", head))
    return debt, closed, head, mb, tracked


def judge_close(wt, base_ref, head, mb, tracked, debt, old, new, cited, run_state, isolate, timeout, ci=None):
    """The one judgment of a closed debt: a Finding, None when its Retire holds, Deferred when only a draft's CI-run suite is left unjudged, or SKIP when the rename is no close."""
    slug = os.path.basename(old)[:-3]
    try:
        lines = records.show(wt, base_ref, old)  # the base tip's Retire, the one the base holds now
    except Unknown:
        lines = records.show(wt, mb, old)  # the base tip no longer holds the file: the fork point's
    text = retire_text(lines)
    if new != old and debt(new) and text == retire_text(records.show(wt, head, new)):
        return SKIP
    todo = spans(text, tracked)
    if todo:
        got, deferring = None, False
        for span in todo:
            named = ci.named(wt, head, tracked, span) if ci else []
            if named and ci.draft:  # a draft has no CI run yet, and the suite is not run a second time here
                deferring = True
                continue
            one = ci.judge(wt, head, span, named) if named else LOCAL
            if one is LOCAL:
                with scratch(wt, head) if isolate else contextlib.nullcontext(wt) as tree:
                    one = run_span(tree, span, timeout) if tree else ("unknown", "no scratch worktree for %s" % span)
            if one and one[0] == "red":
                got = one
                break
            got = got or one  # an unknown sticks: only a red outranks it, whatever the order
        if got and got[0] == "unknown" and slug in cited:  # a check this machine cannot run: a green cited run proves it ran
            if (cite := judge_run(wt, head, cited[slug], run_state)) is None:
                return None if not deferring else Deferred(slug)
            got = cite
        if got:
            return Finding(slug, got[0], "debt %s: its Retire check %s. Retire: %s" % (slug, got[1], text))
        return Deferred(slug) if deferring else None
    got = judge_run(wt, head, cited[slug], run_state) if slug in cited else ("prose", None)
    if got is None:
        return None
    if got[0] == "prose":
        got = "prose", ("debt %s closes with a Retire that names no runnable check. Retire: %s\n"
                        "Name a test file in backticks in the Retire line, or cite a passing run in the PR body: `%s: %s -- <run URL>`."
                        % (slug, text or "(no Retire line)", CITE, slug))
    else:
        got = got[0], "debt %s: %s" % (slug, got[1])
    return Finding(slug, *got)


def check(wt, base_ref, head="HEAD", timeout=TIMEOUT, pr_body="", run_state=None, isolate=False, ci_steps=None, draft=False, deferred=None):
    """[Finding] for each debt that `head` closes against `base_ref` and whose Retire step does not hold. Raises Unknown.
    run_state(url) -> (conclusion, head sha) of a workflow run, or raises.
    ci_steps(sha) -> the step rows of the PR's checks run on `sha` (CiJudge): with it, a suite that a step of the head's workflow runs is judged from those steps and never run here.
    Without it, every suite runs here. draft: the PR has no run yet, so such a close is deferred: its slug is appended to `deferred` and it gives no Finding.
    A draft with no `deferred` list to hold it gives an unknown Finding, never a silent pass.
    isolate: run each test in its own scratch worktree of `head` (the merge tool and the CLI do), so nothing it writes reaches `wt` or its main checkout but through a linked `node_modules` (link_packages);
    off, a test runs in `wt` itself."""
    got = closes(wt, base_ref, head)
    if not got:
        return []
    debt, closed, head, mb, tracked = got
    cited, ci = cites(pr_body), CiJudge(ci_steps, draft)
    found = []
    for old, new in closed:
        one = judge_close(wt, base_ref, head, mb, tracked, debt, old, new, cited, run_state, isolate, timeout, ci)
        if isinstance(one, Deferred):
            if deferred is None:
                one = Finding(one.slug, "unknown", "debt %s: its Retire suite is run by CI, which has no run on a draft yet, and this check has no list to defer it to" % one.slug)
            else:
                deferred.append(one.slug)
        if isinstance(one, Finding):
            found.append(one)
    return found


def retired(wt, base_ref, head="HEAD", pr_body="", run_state=None, isolate=False, timeout=TIMEOUT, paths=None, ci_steps=None, draft=False):
    """{debt path at base: reason} for each deleted debt whose slug the PR body cites and whose judgment gives no Finding (the
    silent-undo check excuses that path's delete). A rename out of the folder is no delete: the file's lines live on at the new
    path. paths, when given, limits the judged closes: an unflagged or uncited close is never judged, so its run is never read.
    A deferred close (a draft's CI-run suite) is no judgment, so it excuses nothing. Raises Unknown."""
    cited, ci = cites(pr_body), CiJudge(ci_steps, draft)
    got = closes(wt, base_ref, head) if cited else None
    if not got:
        return {}
    debt, closed, head, mb, tracked = got
    res = {}
    for old, new in closed:
        slug = os.path.basename(old)[:-3]
        if new == old and slug in cited and (paths is None or old in paths) and judge_close(wt, base_ref, head, mb, tracked, debt, old, new, cited, run_state, isolate, timeout, ci) is None:
            res[old] = "%s: %s -- %s, the debt-close check holds" % (CITE, slug, cited[slug])
    return res


def say(line):
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    print(line.encode(enc, "backslashreplace").decode(enc))


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--upstream", default="origin/main")
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--strict", action="store_true", help="unknown exits 1 (also when env CI is set)")
    ap.add_argument("--repo", default=os.getcwd())
    a = ap.parse_args(argv)
    try:
        found = check(a.repo, a.upstream, a.head, isolate=True)
    except Unknown as e:
        say("debt-retire: UNKNOWN: %s" % e)
        return 1 if (a.strict or os.environ.get("CI")) else 0
    for f in found:
        say("debt-retire: FAIL (%s): %s" % (f.kind, f.text))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
