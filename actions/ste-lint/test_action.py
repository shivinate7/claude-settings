"""Runs the ste-lint step script on a fixture repo. `python3 actions/ste-lint/test_action.py`.
Asserts the gated finding reaches the job log and the ::error annotation, both exit codes."""
import os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
# Stdlib only: the step's `run: |` block is the lines after "      run: |", indented 8 spaces.
text = open(os.path.join(HERE, "action.yml")).read()
block = text.split("      run: |\n", 1)[1]
script = "\n".join(re.sub(r"^ {8}", "", l) for l in block.split("\n")).replace("${{ github.action_path }}", HERE)

# /bin/bash is 3.2 on macOS: the script must survive empty arrays under set -u there.
BASH = "/bin/bash" if os.path.exists("/bin/bash") else "bash"
LONG = " ".join(["word"] * 40) + " end."


def git(cwd, *a):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=cwd, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def run(scope, fail="true"):
    with tempfile.TemporaryDirectory() as d:
        remote, work = os.path.join(d, "r.git"), os.path.join(d, "w")
        git(d, "init", "-q", "--bare", "-b", "main", remote)
        git(d, "clone", "-q", remote, work)
        open(os.path.join(work, "a.md"), "w").write("# T\n\nShort line.\n")
        git(work, "add", "."); git(work, "commit", "-qm", "base"); git(work, "push", "-q", "origin", "main")
        git(work, "checkout", "-q", "-b", "topic")
        open(os.path.join(work, "a.md"), "a").write("\n" + LONG + "\n")
        git(work, "commit", "-qam", "long"); git(work, "fetch", "-q", "origin")
        env = dict(os.environ, EVENT_NAME="pull_request", BASE_REF="main", DEFAULT_BRANCH="main",
                   REF_NAME="topic", SCOPE=scope, FAIL=fail, PATHS_GLOB="**/*.md", EXCLUDE="",
                   CHANGED_PATHS_GLOB="*.md", DECISIONS_DIR="", GITHUB_STEP_SUMMARY=os.path.join(d, "sum"))
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
sys.exit(1 if failed else 0)
