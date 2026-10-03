"""Runs the ste-lint step script on a fixture repo. `python3 actions/ste-lint/test_action.py`.
Asserts the gated finding reaches the job log and the ::error annotation, both exit codes,
the changed-lines scope, the diff range, the exclude split, and annotation escaping."""
import os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
# Stdlib only: the step's `run: |` block is the lines after "      run: |", indented 8 spaces.
text = open(os.path.join(HERE, "action.yml")).read()
block = text.split("      run: |\n", 1)[1]
script = "\n".join(re.sub(r"^ {8}", "", l) for l in block.split("\n")).replace("${{ github.action_path }}", HERE)

# /bin/bash is 3.2 on macOS: the script must survive empty arrays under set -u there.
BASH = "/bin/bash" if os.path.exists("/bin/bash") else "bash"
LONG = " ".join(["word"] * 40) + " end."
BASE_FILES = {"a.md": "# T\n\nShort line.\n"}


def git(cwd, *a):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=cwd, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def write(work, name, content, mode="w"):
    open(os.path.join(work, name), mode).write(content)


def default_change(work):
    write(work, "a.md", "\n" + LONG + "\n", "a")
    git(work, "commit", "-qam", "long")


def run(scope, fail="true", base=BASE_FILES, change=default_change, on_main=False, **over):
    """Build a bare remote, commit `base` on main, branch to topic (or stay on main when
    on_main), apply `change(work)`, then run the step script. `over` overrides env vars."""
    with tempfile.TemporaryDirectory() as d:
        remote, work = os.path.join(d, "r.git"), os.path.join(d, "w")
        git(d, "init", "-q", "--bare", "-b", "main", remote)
        git(d, "clone", "-q", remote, work)
        for name, content in base.items():
            write(work, name, content)
        git(work, "add", "."); git(work, "commit", "-qm", "base"); git(work, "push", "-q", "origin", "main")
        if not on_main:
            git(work, "checkout", "-q", "-b", "topic")
        change(work)
        git(work, "fetch", "-q", "origin")
        env = dict(os.environ, EVENT_NAME="pull_request", BASE_REF="main", DEFAULT_BRANCH="main",
                   REF_NAME="topic", SCOPE=scope, FAIL=fail, PATHS_GLOB="**/*.md", EXCLUDE="",
                   CHANGED_PATHS_GLOB="*.md", DECISIONS_DIR="", GITHUB_STEP_SUMMARY=os.path.join(d, "sum"))
        env.update(over)
        p = subprocess.run([BASH, "-c", script], cwd=work, env=env, capture_output=True, text=True)
        return p.returncode, p.stdout + p.stderr


failed = 0


def check(name, ok, out):
    global failed
    print(("ok - " if ok else "FAIL - ") + name)
    if not ok:
        failed += 1
        print(out)


rc, out = run("changed")
check("changed: exit 1", rc == 1, out)
check("changed: log line", "a.md:5: STE001 " in out, out)
check("changed: ::error annotation", "::error file=a.md,line=5::STE001 " in out, out)
check("changed: verdict", "ste-lint: FAIL, 1 error(s)" in out, out)
rc, out = run("changed", "false")
check("fail=false: exit 0, PASS verdict, finding logged", rc == 0 and "ste-lint: PASS" in out and "a.md:5: STE001" in out, out)
rc, out = run("all")
check("all: exit 0, finding logged", rc == 0 and "a.md:5: STE001" in out and "::error file=a.md,line=5::" in out, out)


# Gate only the lines the diff added: a long line already on main is not gated (the job summary lists it).
def touch_elsewhere(work):
    write(work, "a.md", "# T\n\n" + LONG + "\n\nAnother short line.\n")
    git(work, "commit", "-qam", "touch")


rc, out = run("changed", base={"a.md": "# T\n\n" + LONG + "\n"}, change=touch_elsewhere)
check("unchanged line: a finding there never fails the gate",
      rc == 0 and "ste-lint: PASS, 0 error(s)" in out and "STE001" not in out, out)


# A one-line hunk prints "+3" with no ",1" count. It must still count as one added line.
def replace_line(work):
    write(work, "a.md", "# T\n\n" + LONG + "\n")
    git(work, "commit", "-qam", "replace")


rc, out = run("changed", change=replace_line)
check("one-line hunk with no count: linted", rc == 1 and "a.md:3: STE001" in out, out)


# A pull request diffs origin/base...HEAD, wider than the last commit: an earlier commit's
# finding must fail the gate.
def two_commits(work):
    default_change(work)
    write(work, "a.md", "\nTiny.\n", "a")
    git(work, "commit", "-qam", "tiny")


rc, out = run("changed", change=two_commits)
check("pull request: an earlier commit of the branch is linted", rc == 1 and "a.md:5: STE001" in out, out)
# A push to the default branch has no other side: HEAD~1..HEAD only, so the earlier commit is skipped.
rc, out = run("changed", change=two_commits, on_main=True, BASE_REF="", REF_NAME="main", EVENT_NAME="push")
check("push to default branch: only the last commit is linted", rc == 0 and "STE001" not in out, out)


# EXCLUDE is comma- or newline-separated: every listed pattern drops its file.
def three_files(work):
    write(work, "a.md", "# A\n\nShort line.\n")
    write(work, "b.md", "# B\n\n" + LONG + "\n")
    write(work, "c.md", "# C\n\n" + LONG + "\n")
    git(work, "add", "."); git(work, "commit", "-qm", "three")


rc, out = run("changed", base={"a.md": "# A\n"}, change=three_files, EXCLUDE="b.md,c.md")
check("exclude: comma-separated patterns each drop their file",
      rc == 0 and "1 file(s) in scope, 2 excluded" in out and "STE001" not in out, out)


# '%' in an annotation property is escaped as %25, or the runner decodes the path wrongly.
def pct_file(work):
    write(work, "50%.md", "# T\n\n" + LONG + "\n")
    git(work, "add", "."); git(work, "commit", "-qm", "pct")


rc, out = run("changed", change=pct_file)
check("annotation escapes % in the file property", "::error file=50%25.md,line=3::STE001 " in out, out)
sys.exit(1 if failed else 0)
