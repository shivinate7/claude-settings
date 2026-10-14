"""Runs the ste-lint step script on a fixture repo. `python3 actions/ste-lint/test_action.py`.
Asserts the gated finding reaches the job log and the ::error annotation, both exit codes,
the changed-lines scope, the diff range, the exclude split, and annotation escaping.
Also asserts bin/ste-changed matches the step on the same diff: scope, findings, verdict, exit code."""
import os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
CMD = os.path.join(ROOT, "bin", "ste-changed")
GATES = os.path.join(ROOT, ".github", "workflows", "gates.yml")
# Stdlib only: the step's `run: |` block is the lines after "      run: |", indented 8 spaces.
text = open(os.path.join(HERE, "action.yml")).read()
block = text.split("      run: |\n", 1)[1]
script = "\n".join(re.sub(r"^ {8}", "", l) for l in block.split("\n")).replace("${{ github.action_path }}", HERE)

# /bin/bash is 3.2 on macOS: the script must survive empty arrays under set -u there.
# Windows: a bare "bash" can resolve to WSL's System32 copy, which cannot run this script.
BASH = "/bin/bash" if os.path.exists("/bin/bash") else (
    r"C:\Program Files\Git\bin\bash.exe" if os.path.exists(r"C:\Program Files\Git\bin\bash.exe") else "bash")
LONG = " ".join(["word"] * 40) + " end."
BASE_FILES = {"a.md": "# T\n\nShort line.\n"}
STEP_ENV = ("EVENT_NAME", "BASE_REF", "DEFAULT_BRANCH", "REF_NAME", "SCOPE", "FAIL", "PATHS_GLOB",
            "EXCLUDE", "CHANGED_PATHS_GLOB", "DECISIONS_DIR")
FINDING = re.compile(r"^\S.*:\d+: [A-Z]+\d+ ")


def git(cwd, *a):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=cwd, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def write(work, name, content, mode="w"):
    path = os.path.join(work, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, mode, newline="\n") as f:
        f.write(content)


def default_change(work):
    write(work, "a.md", "\n" + LONG + "\n", "a")
    git(work, "commit", "-qam", "long")


def ci_exclude():
    """The exclude the gates job passes to this action, read from that job's `with:` block."""
    block = re.split(r"uses:.*actions/ste-lint", open(GATES).read(), maxsplit=1)[1].split("- name:", 1)[0]
    return re.search(r"^\s*exclude:[ \t]*(\S+)", block, re.M).group(1)


def changed_paths_default():
    """The changed_paths default the step uses when the caller omits it, read from action.yml."""
    return re.search(r"changed_paths:.*?\n    default: \"([^\"]*)\"", text, re.S).group(1)


def make_repo(d, base, change, on_main=False):
    """Bare remote, `base` committed on main and pushed, a topic branch (unless on_main), then `change(work)`."""
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
    return work


def run_step(d, work, env):
    """Run the step script from a file, not `bash -c`: Windows argv quoting mangles its heredocs."""
    path = os.path.join(d, "step.sh")
    with open(path, "w", newline="\n") as f:
        f.write(script)
    p = subprocess.run([BASH, path.replace("\\", "/")], cwd=work, env=env, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def run(scope, fail="true", base=BASE_FILES, change=default_change, on_main=False, **over):
    """Build a bare remote, commit `base` on main, branch to topic (or stay on main when
    on_main), apply `change(work)`, then run the step script. `over` overrides env vars."""
    with tempfile.TemporaryDirectory() as d:
        work = make_repo(d, base, change, on_main)
        env = dict(os.environ, EVENT_NAME="pull_request", BASE_REF="main", DEFAULT_BRANCH="main",
                   REF_NAME="topic", SCOPE=scope, FAIL=fail, PATHS_GLOB="**/*.md", EXCLUDE="",
                   CHANGED_PATHS_GLOB="*.md", DECISIONS_DIR="", GITHUB_STEP_SUMMARY=os.path.join(d, "sum"))
        env.update(over)
        return run_step(d, work, env)


def run_command(work):
    """bin/ste-changed main in the scratch repo, with the step's variables stripped: it finds its own config."""
    if not os.path.exists(CMD):
        return 127, "bin/ste-changed is missing: %s" % CMD
    env = {k: v for k, v in os.environ.items() if k not in STEP_ENV}
    p = subprocess.run([sys.executable, CMD, "main"], cwd=work, env=env, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def run_pair(change, base=BASE_FILES):
    """One diff, two runs: the step with CI's exclude and changed_paths, then bin/ste-changed."""
    with tempfile.TemporaryDirectory() as d:
        work = make_repo(d, base, change)
        env = dict(os.environ, EVENT_NAME="pull_request", BASE_REF="main", DEFAULT_BRANCH="main",
                   REF_NAME="topic", SCOPE="changed", FAIL="true", PATHS_GLOB="**/*.md",
                   EXCLUDE=ci_exclude(), CHANGED_PATHS_GLOB=changed_paths_default(), DECISIONS_DIR="",
                   GITHUB_STEP_SUMMARY=os.path.join(d, "sum"))
        return run_step(d, work, env), run_command(work)


def parts(out):
    """What a job log shows about scope: the header, the scoped files, the gated findings, the verdict."""
    lines = out.splitlines()
    head = next((l for l in lines if " file(s) in scope," in l or l == "ste-lint: no markdown changed"), "")
    files = []
    if head:
        for l in lines[lines.index(head) + 1:]:
            if not l.startswith("  "):
                break
            files.append(l[2:])
    return {"head": head, "files": files,
            "findings": sorted(l for l in lines if FINDING.match(l)),
            "verdict": next((l for l in lines if l.startswith(("ste-lint: PASS", "ste-lint: FAIL"))), "")}


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


# bin/ste-changed <base> lints the files the gates job lints for the same diff, and gives the same
# header, files, findings, verdict and exit code. Each case runs the step and the command on one repo,
# so the expected scope is the step's own output, never a copy of its rules.
def skill_change(work):
    write(work, ".claude/skills/x/SKILL.md", "\n" + LONG + "\n", "a")
    git(work, "commit", "-qam", "skill")


(s_rc, s_out), (c_rc, c_out) = run_pair(skill_change, base={".claude/skills/x/SKILL.md": "# Skill\n"})
s, c = parts(s_out), parts(c_out)
check("skill: the step lints a changed SKILL.md and fails",
      s_rc == 1 and bool(s["findings"]) and s["findings"][0].startswith(".claude/skills/x/SKILL.md:"), s_out)
check("skill: the command lints the same SKILL.md, exits 1, reports the same finding",
      c_rc == 1 and c["files"] == s["files"] and c["findings"] == s["findings"] and c["verdict"] == s["verdict"], c_out)


# A file with a long line that the diff does not touch is never linted. A clean changed file keeps
# the scope non-empty, so an empty scope cannot pass this case.
def clean_change(work):
    write(work, ".claude/skills/x/SKILL.md", "# Skill\n\nShort line.\n", "w")
    git(work, "commit", "-qam", "clean")


(s_rc, s_out), (c_rc, c_out) = run_pair(clean_change, base={
    "old.md": "# Old\n\n" + LONG + "\n",
    ".claude/skills/y/SKILL.md": "# Y\n\n" + LONG + "\n",
    ".claude/skills/x/SKILL.md": "# Skill\n"})
s, c = parts(s_out), parts(c_out)
check("unchanged: the step lints only the changed clean file, exit 0",
      s_rc == 0 and s["files"] == [".claude/skills/x/SKILL.md"], s_out)
check("unchanged: the command lints only that file, exit 0, reports nothing",
      c_rc == 0 and c["files"] == s["files"] and c["findings"] == [] and c["head"] == s["head"], c_out)


# Files the step skips, pinned to the step's own skips: the gates job's exclude (its path read from
# the CI config, so the case follows a change to it), a non-Markdown file, and a deleted Markdown file.
EXCLUDED = ci_exclude().replace("**", "probe.md")


def skipped_change(work):
    write(work, EXCLUDED, "# P\n\n" + LONG + "\n", "w")
    write(work, "notes.txt", LONG + "\n", "w")
    write(work, ".claude/skills/x/SKILL.md", "# Skill\n\n" + LONG + "\n", "w")
    os.remove(os.path.join(work, "gone.md"))
    git(work, "add", "-A"); git(work, "commit", "-qm", "mixed")


(s_rc, s_out), (c_rc, c_out) = run_pair(skipped_change, base={
    "gone.md": "# G\n", EXCLUDED: "# P\n", "notes.txt": "x\n", ".claude/skills/x/SKILL.md": "# Skill\n"})
s, c = parts(s_out), parts(c_out)
check("skipped: the step skips the excluded, non-Markdown and deleted files",
      s["files"] == [".claude/skills/x/SKILL.md"] and s["head"].endswith("1 excluded"), s_out)
check("skipped: the command skips them too, with the same header, files, findings, verdict and exit code",
      c_rc == s_rc and c["head"] == s["head"] and c["files"] == s["files"]
      and c["findings"] == s["findings"] and c["verdict"] == s["verdict"], c_out)


# Exit-code parity on three diffs: a gated finding, a finding only on an unchanged line, no change.
for label, change, base, want in [
        ("a finding on a changed line", default_change, BASE_FILES, 1),
        ("a finding only on an unchanged line", touch_elsewhere, {"a.md": "# T\n\n" + LONG + "\n"}, 0),
        ("nothing changed", lambda work: None, BASE_FILES, 0)]:
    (s_rc, s_out), (c_rc, c_out) = run_pair(change, base=base)
    check("exit parity, %s: both exit %d" % (label, want),
          s_rc == want and c_rc == want and parts(s_out) == parts(c_out),
          s_out + "\n--- command ---\n" + c_out)
sys.exit(1 if failed else 0)
