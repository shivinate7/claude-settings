"""Runs the ste-lint step script on a fixture repo. `python3 actions/ste-lint/test_action.py`.
Asserts the failing finding reaches the job log and the ::error annotation, both exit codes,
that an advisory finding is a ::warning that never fails the step, the changed-lines scope, the diff range, the exclude split, and annotation escaping.
Also asserts bin/ste-changed matches the step on the same diff: scope, findings, verdict, exit code.
Excludes are the target repo's own .ste-lint-exclude plus the action's `exclude` input, never this repo's file.
Also asserts the file's last line counts with no final newline, '**' matches at the root, and a run from a subdirectory.
Also asserts a planted json.py, json/ package or ste_emit.py in the linted repo never runs on import, and the summary still prints.
Also asserts the command's pin check: a CI pin whose lint differs exits 3 and names the pin and the remedy,
an unrelated commit is no drift, an unknown pin changes no exit code, a shallow clone that cuts the history above a pin
says unknown and never "not on main", and LINT_FILES holds every file the step runs.
Also asserts a zizmor pin, `claude-settings/actions/zizmor@<sha>`, is read with the same verdict lines, compared on
actions/zizmor/run.sh, one line per action, and that a workflow pinning both actions at one commit keeps both lines.
Also asserts the installed copy: install.sh run into a temp HOME, in cloud (copy) mode and in local (symlink) mode, lands
bin/ste-changed where its own folder holds no actions/. The command still finds the claude-settings checkout the global
CLAUDE.md names, reads the pin check from it, and with no checkout prints one line, never a traceback.
Also asserts the tree-cites input: off by default, passed to the step as TREE_CITES, and on, the step checks the whole tree.
Also asserts an uncommitted or untracked markdown file is linted or fails bin/ste-changed, never a plain PASS, a file .gitignore
matches is not linted, and a clean tree still passes. A non-ASCII untracked name is linted by its own name, a run with no merge
base names it, and an uncommitted removal that a tracked doc cites fails bin/ste-changed as the committed removal fails the step.
Also asserts a push whose HEAD is a root commit exits 0 with an unknown stale-cites line, a Markdown file that is untracked and cites
an uncommitted removal is named unknown and never PASS, a held .git/index.lock prints one ste-lint unknown line that names the lock,
a name with a space is linted, and a run with no merge base writes unknown to the step summary, not "No markdown changed".
Also asserts a stat-only change (a touched tracked file, the same bytes) still fails on a committed STE001, and an untracked
markdown file that .ste-lint-exclude matches is not named unknown. A dirty tree whose snapshot fails is named unknown, never
PASS, and a clean tree with a held index lock lints as main does, touched or not.
Also asserts a root push's missing HEAD~1 is named by an ste-lint unknown line, not "no markdown changed"; a .ste-lint-exclude
line git rejects as a pathspec is unknown, never "no markdown changed"; and a .git/index that is gone or a directory is one
ste-lint unknown line, exit 0, and no PASS.
Also asserts the pin note (STE_CHANGED_PIN_NOTE=1, set by ci-job on a step that runs the local copy): a drifted pin with a
passing lint exits 0 with the drift on stderr, a failing lint still exits 1. R67: ci-job runs the pinned ste-lint under
--lint and --step from a tree with no .git, so the log reads the pin as unknown (not drift), the step reads PASS with no pin note, and no exit 3."""
import ast, atexit, contextlib, os, re, shutil, subprocess, sys, tempfile, time, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lint"))
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
CMD = os.path.join(ROOT, "bin", "ste-changed")
EXCLUDE_FILE = os.path.join(ROOT, ".ste-lint-exclude")
EXCLUDE_TEXT = open(EXCLUDE_FILE, encoding="utf-8").read()  # run_pair writes this as the target's file
sys.path.append(os.path.join(ROOT, "hooks"))  # append: the pin note's names (hooks/pin_note.py)
from pin_note import ENV as PIN_NOTE_ENV, MARKER as PIN_NOTE_MARKER  # noqa: E402  the one home of the pin note's names (hooks/pin_note.py)
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
            "EXCLUDE", "CHANGED_PATHS_GLOB", "DECISIONS_DIR", "STE_EXCLUDE_FILE", "TREE_CITES", PIN_NOTE_ENV)
FINDING = re.compile(r"^\S.*:\d+: [A-Z]+\d+ ")

# Test temp files (decision test-temp-standard): one run folder for this run, from the repo's one helper.
# Every case below makes its folder inside it, and the run folder is removed at exit.
sys.path.append(os.path.join(ROOT, "lint"))
sys.path.append(os.path.join(ROOT, "testing"))
import _test_temp  # noqa: E402
import tracked_tree  # noqa: E402  copies what git lists, so no case here lists files
import shallow_clone  # noqa: E402  the one shallow-clone fixture (testing/shallow_clone.py)
from workflow_steps import job_block, step_blocks, step_key  # noqa: E402  the one home of the step parser (lint/workflow_steps.py)
RUN_FOLDER = _test_temp.run_folder()
atexit.register(tracked_tree.rm_tree, RUN_FOLDER)


@contextlib.contextmanager
def scratch(label):
    d = tempfile.mkdtemp(prefix=label + "-", dir=RUN_FOLDER)
    try:
        yield d
    finally:
        tracked_tree.rm_tree(d)


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


def exclude_patterns():
    """The repo's exclude home, .ste-lint-exclude: one git pathspec per line, '#' starts a comment. Read, never copied."""
    lines = (l.strip() for l in open(EXCLUDE_FILE, encoding="utf-8"))
    return [l for l in lines if l and not l.startswith("#")]


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


def run(scope, fail="true", base=BASE_FILES, change=default_change, on_main=False, after=None, **over):
    """Build a bare remote, commit `base` on main, branch to topic (or stay on main when
    on_main), apply `change(work)`, then run the step script. `after(work)`, when given, runs last: after the fetch,
    just before the step. `over` overrides env vars."""
    with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:  # test-temp-standard: the run folder, never the system temp
        work = make_repo(d, base, change, on_main)
        if after:
            after(work)
        env = dict(os.environ, EVENT_NAME="pull_request", BASE_REF="main", DEFAULT_BRANCH="main",
                   REF_NAME="topic", SCOPE=scope, FAIL=fail, PATHS_GLOB="**/*.md", EXCLUDE="",
                   CHANGED_PATHS_GLOB="*.md", DECISIONS_DIR="", GITHUB_STEP_SUMMARY=os.path.join(d, "sum"))
        env.update(over)
        return run_step(d, work, env)


def run_command(work, extra=None, sub=None):
    """bin/ste-changed main in the scratch repo, with the step's variables stripped: it finds its own config.
    `extra` sets more variables on the command, to check that they are not read.
    `sub` is a subdirectory of the repo to run it from: the command must not depend on the current directory."""
    if not os.path.exists(CMD):
        return 127, "bin/ste-changed is missing: %s" % CMD
    env = {k: v for k, v in os.environ.items() if k not in STEP_ENV}
    env.update(extra or {})
    p = subprocess.run([sys.executable, CMD, "main"], cwd=os.path.join(work, sub) if sub else work, env=env,
                       capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def run_pair(change, base=BASE_FILES, exclude=EXCLUDE_TEXT, command_env=None, sub=None):
    """One diff in one target repo, two runs: the step, then bin/ste-changed with no config of its own.
    `exclude` is the target's .ste-lint-exclude text, committed on main; None means the target has no file.
    The step reads that file from the repo root, as the CI step does. Neither run gets this repo's file.
    The step runs at the repo root, as in CI. `sub` runs the command from that subdirectory instead."""
    files = dict(base)
    if exclude is not None:
        files[".ste-lint-exclude"] = exclude
    with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:  # test-temp-standard: the run folder, never the system temp
        work = make_repo(d, files, change)
        env = {k: v for k, v in os.environ.items() if k not in STEP_ENV}
        env.update(EVENT_NAME="pull_request", BASE_REF="main", DEFAULT_BRANCH="main",
                   REF_NAME="topic", SCOPE="changed", FAIL="true", PATHS_GLOB="**/*.md",
                   EXCLUDE="", CHANGED_PATHS_GLOB=changed_paths_default(), DECISIONS_DIR="",
                   GITHUB_STEP_SUMMARY=os.path.join(d, "sum"))
        return run_step(d, work, env), run_command(work, command_env, sub)


def parts(out):
    """What a job log shows about scope: the header, the scoped files, the failing findings, the verdict."""
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


# A contraction, a Latin abbreviation, a nominalization, a phrasal verb, a condition after its instruction
# and an omitted "that" are warnings. They reach the log and the annotation as warnings and never fail the step.
ADVISORY = "They'd finished the work, e.g. before it runs.\n"


def advisory_change(work):
    write(work, "a.md", "\n" + ADVISORY, "a")
    git(work, "commit", "-qam", "advisory")


rc, out = run("changed", change=advisory_change)
check("advisory only: exit 0, PASS verdict, no error counted", rc == 0 and "ste-lint: PASS, 0 error(s)" in out, out)
check("advisory only: the finding is logged and annotated as a warning, never an error",
      "a.md:5: STE008 " in out and "::warning file=a.md,line=5::STE008 " in out and "::error" not in out, out)
rc, out = run("all")
check("all: exit 0, finding logged", rc == 0 and "a.md:5: STE001" in out and "::error file=a.md,line=5::" in out, out)


# This step fails on STE001, STE011 and STE013 on changed lines. STE001 is above.
for code, line in (("STE011", "In conclusion, the plan works."), ("STE013", "This step is not unsafe.")):
    def kept_change(work, line=line):
        write(work, "a.md", "\n" + line + "\n", "a")
        git(work, "commit", "-qam", "kept")
    rc, out = run("changed", change=kept_change)
    check("%s on a changed line fails the step" % code,
          rc == 1 and "a.md:5: %s " % code in out and "::error file=a.md,line=5::%s " % code in out, out)


# A changed UI file still fails on bloat, and a five-word button is no finding (no label-length cap).
def tsx_change(work):
    write(work, "B.tsx", "export const B = () => <p>In order to save, press it.</p>;\n"
                         "export const C = () => <button>Save the file right now</button>;\n")
    git(work, "add", "."); git(work, "commit", "-qm", "tsx")


rc, out = run("changed", change=tsx_change, CHANGED_PATHS_GLOB="*.tsx")
check("changed UI file: STE011 on the copy still fails the step", rc == 1 and "B.tsx:1: STE011 " in out, out)
check("changed UI file: a five-word button is not a finding", "STE020" not in out and "B.tsx:2:" not in out, out)


# Fail only on the lines the diff added: a long line already on main does not fail (the job summary lists it).
def touch_elsewhere(work):
    write(work, "a.md", "# T\n\n" + LONG + "\n\nAnother short line.\n")
    git(work, "commit", "-qam", "touch")


rc, out = run("changed", base={"a.md": "# T\n\n" + LONG + "\n"}, change=touch_elsewhere)
check("unchanged line: a finding there never fails the check",
      rc == 0 and "ste-lint: PASS, 0 error(s)" in out and "STE001" not in out, out)


# A one-line hunk prints "+3" with no ",1" count. It must still count as one added line.
def replace_line(work):
    write(work, "a.md", "# T\n\n" + LONG + "\n")
    git(work, "commit", "-qam", "replace")


rc, out = run("changed", change=replace_line)
check("one-line hunk with no count: linted", rc == 1 and "a.md:3: STE001" in out, out)


# A pull request diffs origin/base...HEAD, wider than the last commit: an earlier commit's
# finding must fail the check.
def two_commits(work):
    default_change(work)
    write(work, "a.md", "\nTiny.\n", "a")
    git(work, "commit", "-qam", "tiny")


rc, out = run("changed", change=two_commits)
check("pull request: an earlier commit of the branch is linted", rc == 1 and "a.md:5: STE001" in out, out)
# A push to the default branch has no other side: HEAD~1..HEAD only, so the earlier commit is skipped.
rc, out = run("changed", change=two_commits, on_main=True, BASE_REF="", REF_NAME="main", EVENT_NAME="push")
check("push to default branch: only the last commit is linted", rc == 0 and "STE001" not in out, out)


# The action's `exclude` input keeps working (a pinned caller passes it): comma- or newline-separated
# pathspecs, each dropping its file, added to the target's .ste-lint-exclude patterns.
def three_files(work):
    write(work, "a.md", "# A\n\nShort line.\n")
    write(work, "b.md", "# B\n\n" + LONG + "\n")
    write(work, "c.md", "# C\n\n" + LONG + "\n")
    git(work, "add", "."); git(work, "commit", "-qm", "three")


rc, out = run("changed", base={"a.md": "# A\n"}, change=three_files, EXCLUDE="b.md,c.md")
check("exclude input: comma-separated patterns each drop their file",
      rc == 0 and "1 file(s) in scope, 2 excluded" in out and "STE001" not in out, out)
check("exclude input: action.yml declares it, default empty, and hands it to the step as EXCLUDE",
      re.search(r'^  exclude:\n(?:    .*\n)*?    default: ""', text, re.M) is not None
      and "EXCLUDE: ${{ inputs.exclude }}" in text, "action.yml lacks the exclude input or its EXCLUDE mapping")


# The pinned caller's value, '.claude/skills/neon*/**', drops a changed file under that folder with no
# .ste-lint-exclude in the repo, and alongside the file's own patterns (union) when there is one.
NEON = ".claude/skills/neon*/**"


def neon_change(work):
    write(work, "a.md", "# A\n\nShort line.\n")
    write(work, ".claude/skills/neon-x/a.md", "# N\n\n" + LONG + "\n")
    git(work, "add", "."); git(work, "commit", "-qm", "neon")


def neon_gen_change(work):
    write(work, "gen/x.md", "# G\n\n" + LONG + "\n")
    neon_change(work)


rc, out = run("changed", base={"a.md": "# A\n"}, change=neon_change, EXCLUDE=NEON)
check("exclude input, no .ste-lint-exclude: the neon pattern drops the neon file, a.md stays",
      rc == 0 and "1 file(s) in scope, 1 excluded" in out and "STE001" not in out, out)
rc, out = run("changed", base={"a.md": "# A\n", ".ste-lint-exclude": "gen/**\n"}, change=neon_gen_change, EXCLUDE=NEON)
check("exclude input with .ste-lint-exclude: the input's pattern and the file's pattern both apply",
      rc == 0 and "1 file(s) in scope, 2 excluded" in out and "STE001" not in out, out)


# '%' in an annotation property is escaped as %25, or the runner decodes the path wrongly.
def pct_file(work):
    write(work, "50%.md", "# T\n\n" + LONG + "\n")
    git(work, "add", "."); git(work, "commit", "-qm", "pct")


rc, out = run("changed", change=pct_file)
check("annotation escapes % in the file property", "::error file=50%25.md,line=3::STE001 " in out, out)


# bin/ste-changed <base> lints the files the checks job lints for the same diff, and gives the same
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


# Files the step skips, pinned to the step's own skips: the first pattern of .ste-lint-exclude (read from
# that file, so the case follows a change to it), a non-Markdown file, and a deleted Markdown file.
# The target repo carries that file too (run_pair), so the command reads the same excludes as the step.
EXCLUDED = exclude_patterns()[0].replace("**", "probe.md")


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


# No .ste-lint-exclude in the target: nothing is excluded. This repo's file lists skills/impeccable/**, so
# a changed file there must be linted by the step and by the command.
def no_file_change(work):
    write(work, EXCLUDED, "# P\n\n" + LONG + "\n", "w")
    git(work, "add", "-A"); git(work, "commit", "-qm", "probe")


(s_rc, s_out), (c_rc, c_out) = run_pair(no_file_change, base={EXCLUDED: "# P\n"}, exclude=None)
s, c = parts(s_out), parts(c_out)
check("no target file: the step lints the changed file that this repo's file would skip",
      s_rc == 1 and s["files"] == [EXCLUDED] and s["head"].endswith("0 excluded") and bool(s["findings"]), s_out)
check("no target file: the command lints it too, same header, files, findings, verdict and exit code",
      c_rc == s_rc and c["head"] == s["head"] and c["files"] == s["files"] and c["findings"] == s["findings"]
      and c["verdict"] == s["verdict"], c_out)


# A target repo's own .ste-lint-exclude: the paths it lists are skipped by the step and by the command.
# Its patterns are not this repo's, so this case fails if the command reads this repo's file instead.
def target_exclude_change(work):
    write(work, "a.md", "# A\n\n" + LONG + "\n", "w")
    write(work, "gen/x.md", "# G\n\n" + LONG + "\n", "w")
    git(work, "add", "-A"); git(work, "commit", "-qm", "gen")


(s_rc, s_out), (c_rc, c_out) = run_pair(target_exclude_change, base={"a.md": "# A\n", "gen/x.md": "# G\n"},
                                         exclude="# Generated, never linted.\ngen/**\n")
s, c = parts(s_out), parts(c_out)
check("target exclude: the step skips the path the target's .ste-lint-exclude lists, lints the rest",
      s_rc == 1 and s["files"] == ["a.md"] and s["head"].endswith("1 excluded") and s["findings"][0].startswith("a.md:"),
      s_out)
check("target exclude: the command skips it too, same header, files, findings, verdict and exit code",
      c_rc == s_rc and c["head"] == s["head"] and c["files"] == s["files"] and c["findings"] == s["findings"]
      and c["verdict"] == s["verdict"], c_out)


# bin/ste-changed takes no exclude input. An EXCLUDE value in its environment changes nothing: the command
# lints the same files, findings and exit code as the step does with EXCLUDE empty (the input's default).
# The step reads EXCLUDE, so the command must set it to that default and not pass the caller's value on.
(s_rc, s_out), (c_rc, c_out) = run_pair(target_exclude_change, base={"a.md": "# A\n", "gen/x.md": "# G\n"},
                                         exclude=None, command_env={"EXCLUDE": "gen/**"})
s, c = parts(s_out), parts(c_out)
check("exclude input: an EXCLUDE value given to the command drops nothing, same files and findings as the step",
      c_rc == s_rc == 1 and s["files"] == ["a.md", "gen/x.md"] and c["files"] == s["files"]
      and c["findings"] == s["findings"] and c["verdict"] == s["verdict"], c_out)


# A .ste-lint-exclude whose last line has no newline still excludes that line's pattern.
(s_rc, s_out), (c_rc, c_out) = run_pair(target_exclude_change, base={"a.md": "# A\n", "gen/x.md": "# G\n"},
                                         exclude="gen/**")
s, c = parts(s_out), parts(c_out)
check("no final newline: the step excludes the file's only pattern",
      s_rc == 1 and s["files"] == ["a.md"] and s["head"].endswith("1 excluded"), s_out)
check("no final newline: the command excludes it too, same header, files, findings, verdict and exit code",
      c_rc == s_rc and c["files"] == ["a.md"] and c["head"] == s["head"] and c["files"] == s["files"]
      and c["findings"] == s["findings"] and c["verdict"] == s["verdict"], c_out)


# The command run from a subdirectory lints what it lints at the root, and fails on the same lines.
# `git diff --name-only` prints root-relative paths, so the pathspecs and the file names must not
# depend on the current directory.
SUB_BASE = {"a.md": "# A\n", "sub/keep.txt": "x\n"}


def root_and_sub_change(work):
    default_change(work)
    write(work, "sub/b.md", "# B\n\n" + LONG + "\n")
    git(work, "add", "."); git(work, "commit", "-qm", "sub")


for label, change, files in [("a changed root file", default_change, ["a.md"]),
                             ("a changed root file and a changed file in the subdirectory",
                              root_and_sub_change, ["a.md", "sub/b.md"])]:
    (s_rc, s_out), (c_rc, c_out) = run_pair(change, base=SUB_BASE, sub="sub")
    s, c = parts(s_out), parts(c_out)
    check("subdirectory, %s: the step at the root lints them and fails" % label,
          s_rc == 1 and s["files"] == files and len(s["findings"]) == len(files), s_out)
    check("subdirectory, %s: the command lints the same files, fails on the same lines, exits 1" % label,
          c_rc == s_rc and c["head"] == s["head"] and c["files"] == s["files"] and c["findings"] == s["findings"]
          and c["verdict"] == s["verdict"], c_out)


# '**/' matches zero directories in the exclude, as in the include: a root file is excluded, a nested one too.
def decisions_change(work):
    write(work, "a.md", "# A\n\nShort line.\n", "w")
    write(work, "decisions/x.md", "# X\n\n" + LONG + "\n", "w")
    write(work, "sub/decisions/y.md", "# Y\n\n" + LONG + "\n", "w")
    git(work, "add", "-A"); git(work, "commit", "-qm", "decisions")


(s_rc, s_out), (c_rc, c_out) = run_pair(decisions_change, base={"a.md": "# A\n"}, exclude="**/decisions/**\n")
s, c = parts(s_out), parts(c_out)
check("double-star exclude: the step excludes a root file and a nested file, lints the rest",
      s_rc == 0 and s["files"] == ["a.md"] and s["head"].endswith("2 excluded") and s["findings"] == [], s_out)
check("double-star exclude: the command excludes them too, same header, files, findings, verdict and exit code",
      c_rc == s_rc and c["files"] == ["a.md"] and c["head"] == s["head"] and c["files"] == s["files"]
      and c["findings"] == s["findings"] and c["verdict"] == s["verdict"], c_out)


# Exit-code parity on three diffs: a failing finding, a finding only on an unchanged line, no change.
for label, change, base, want in [
        ("a finding on a changed line", default_change, BASE_FILES, 1),
        ("a finding only on an unchanged line", touch_elsewhere, {"a.md": "# T\n\n" + LONG + "\n"}, 0),
        ("advisory findings only", advisory_change, BASE_FILES, 0),
        ("nothing changed", lambda work: None, BASE_FILES, 0)]:
    (s_rc, s_out), (c_rc, c_out) = run_pair(change, base=base)
    check("exit parity, %s: both exit %d" % (label, want),
          s_rc == want and c_rc == want and parts(s_out) == parts(c_out),
          s_out + "\n--- command ---\n" + c_out)


# An uncommitted or untracked markdown file is outside origin/main...HEAD, so the diff finds no markdown. The command
# then printed "no markdown changed" and passed: a false green for a file that fails lint at hand-off. It must lint the
# file (listed in its scope) or exit non-zero and name it. A file .gitignore matches is not linted. Each case checks
# git's own state first (P7), read before the command runs.
UNCOMMITTED_BASE = {"draft-note.md": "# Draft\n\nShort line.\n", "data.txt": "x\n", ".gitignore": "ignored-*.md\n"}


def edit_draft(work):
    write(work, "draft-note.md", "# Draft\n\n" + LONG + "\n", "w")  # a markdown edit, not committed


def edit_data(work):
    write(work, "data.txt", "y\n", "w")  # a non-markdown edit, not committed


def edit_new(work):
    write(work, "new-note.md", "# New\n\n" + LONG + "\n", "w")  # a new markdown file, never git-added


def edit_ignored(work):
    write(work, "ignored-note.md", "# Ignored\n\n" + LONG + "\n", "w")  # a new markdown file .gitignore matches


def git_read(cwd, *a):
    return subprocess.run(["git", "-C", cwd, *a], capture_output=True, text=True).stdout


def uncommitted_run(change, base=UNCOMMITTED_BASE):
    """A topic fixture with `base` committed on main and `change` applied and not committed, then bin/ste-changed main
    there. Returns whether HEAD is origin/main's commit, git status (ignored files too), and the command's exit code and output."""
    with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:  # test-temp-standard: the run folder, never the system temp
        work = make_repo(d, base, change)
        at_base = git_read(work, "rev-parse", "HEAD") == git_read(work, "rev-parse", "origin/main")
        status = git_read(work, "status", "--porcelain", "--ignored")
        rc, out = run_command(work)
    return at_base, status, rc, out


at_base, status, rc, out = uncommitted_run(edit_draft)
check("uncommitted scope: HEAD is origin/main and draft-note.md is modified, not committed",
      at_base and " M draft-note.md" in status, status)
check("uncommitted: exits non-zero on the 41-word sentence in draft-note.md", rc != 0, out)
check("uncommitted: the verdict is FAIL and names draft-note.md",
      "ste-lint: FAIL" in out and "draft-note.md" in out, out)
at_base, status, rc, out = uncommitted_run(edit_data)
check("uncommitted control scope: HEAD is origin/main, data.txt is modified, no markdown is",
      at_base and " M data.txt" in status and ".md" not in status, status)
check("uncommitted control: no markdown changed still passes with exit 0",
      rc == 0 and "ste-lint: no markdown changed" in out and "Traceback" not in out, out)
at_base, status, rc, out = uncommitted_run(edit_new)
check("untracked scope: HEAD is origin/main and new-note.md is untracked, not ignored",
      at_base and "?? new-note.md" in status, status)
check("untracked: exits non-zero on the 41-word sentence in new-note.md", rc != 0, out)
check("untracked: the verdict is FAIL and names new-note.md",
      "ste-lint: FAIL" in out and "new-note.md" in out, out)
at_base, status, rc, out = uncommitted_run(edit_ignored)
check("ignored control scope: HEAD is origin/main and .gitignore matches ignored-note.md",
      at_base and "!! ignored-note.md" in status, status)
check("ignored control: a markdown file .gitignore matches is not linted, plain PASS with exit 0",
      rc == 0 and "ste-lint: no markdown changed" in out and "ignored-note.md" not in out and "Traceback" not in out, out)


# Another git process holds .git/index.lock (an agent's `git add`) while the tree is dirty. The step must not go silent:
# one ste-lint line says unknown and names the lock, and the exit is 0, as in the no-merge-base case (decision
# stale-cites-at-merge, rule verification-report-unknown-reads). Empty output is the bug. The lock is set in the change, so
# the scope fact is read there (P7).
lock = {}


def hold_index_lock(work):
    """Another git process holds .git/index.lock: an empty file there, as an agent's `git add` leaves it. True if it exists."""
    path = os.path.join(work, ".git", "index.lock")
    open(path, "w").close()
    return os.path.exists(path)


def touch_same_bytes(work, name):
    """A tracked file's mtime moves 60 seconds, its bytes stay: the index's stat data goes stale, its content does not."""
    path = os.path.join(work, name)
    before = os.stat(path)
    os.utime(path, (before.st_atime, before.st_mtime + 60))
    return before


def content_clean(work):
    """git's content check on the tracked files, with no optional index write: a read that refreshes the index would
    hide the stale stat data the case needs, so the scope fact must leave the index as it found it."""
    return subprocess.run(["git", "--no-optional-locks", "-C", work, "diff", "--quiet", "HEAD", "--"]).returncode == 0


def edit_data_locked(work):
    edit_data(work)  # a non-markdown edit, not committed: the tree is dirty
    lock["held"] = hold_index_lock(work)


at_base, status, rc, out = uncommitted_run(edit_data_locked)
check("index lock scope: the lock is held, data.txt is modified and HEAD is origin/main",
      lock.get("held") is True and at_base and " M data.txt" in status, status)
check("index lock: exits 0, as the no-merge-base case does", rc == 0, out)
check("index lock: one ste-lint line says unknown and names index.lock",
      any(l.startswith("ste-lint:") and "unknown" in l and "index.lock" in l for l in out.splitlines()), out)


# An uncommitted removal. A tracked doc cites hooks/keep.py, and the working tree deletes it, uncommitted. Once
# committed, the range removes the path and the cite is STALE001 (CI fails on it). The command read only the committed
# range, so the uncommitted removal passed. It must fail the same way. The committed removal is the control: CI's check.
STALE_LOCAL_BASE = {"a.md": "# T\n\nShort line.\n", "docs/guide.md": "# Guide\n\n- see `hooks/keep.py`\n",
                    "hooks/keep.py": "X = 1\n"}


def remove_keep(work):
    os.remove(os.path.join(work, "hooks", "keep.py"))  # a deletion, not committed


def remove_keep_committed(work):
    remove_keep(work)
    git(work, "commit", "-qam", "remove hooks/keep.py")


at_base, status, rc, out = uncommitted_run(remove_keep, base=STALE_LOCAL_BASE)
check("uncommitted removal scope: HEAD is origin/main and hooks/keep.py is deleted, not committed",
      at_base and " D hooks/keep.py" in status, status)
check("uncommitted removal: exits non-zero", rc != 0, out)
check("uncommitted removal: names the stale cite docs/guide.md:3 as STALE001",
      "docs/guide.md:3: STALE001 " in out, out)
rc, out = run("changed", base=STALE_LOCAL_BASE, change=remove_keep_committed)
check("committed removal, control: the step fails on the same stale cite, as CI does",
      rc == 1 and "docs/guide.md:3: STALE001 " in out, out)


# An untracked Markdown file cites a path the working tree removed. The stale-cites check reads Markdown as committed at
# head, never from the working tree (decision stale-cites-at-merge), so it cannot read cite.md. That read cannot run, so
# the output names cite.md as unknown and never prints `stale-cites: PASS` (rule verification-report-unknown-reads).
# No tracked Markdown cites hooks/keep.py, so cite.md is the only cite; the scope fact is read inside the change (P7).
UNTRACKED_CITE_BASE = {"a.md": "# T\n\nShort line.\n", "hooks/keep.py": "X = 1\n"}
untracked_cite = {}


def remove_keep_untracked_cite(work):
    remove_keep(work)  # a deletion, not committed
    write(work, "cite.md", "# Cite\n\n- see `hooks/keep.py`\n")  # a new file, never git-added
    untracked_cite["cites"] = git_read(work, "grep", "hooks/keep.py", "HEAD", "--", "*.md")


at_base, status, rc, out = uncommitted_run(remove_keep_untracked_cite, base=UNTRACKED_CITE_BASE)
check("untracked cite scope: hooks/keep.py is deleted, not committed, and cite.md is untracked",
      at_base and " D hooks/keep.py" in status and "?? cite.md" in status, status)
check("untracked cite scope: no tracked Markdown cites hooks/keep.py", untracked_cite.get("cites") == "",
      str(untracked_cite))
check("untracked cite: the output does not print `stale-cites: PASS`", "stale-cites: PASS" not in out, out)
check("untracked cite: an unknown line names cite.md",
      any(l.startswith("stale-cites: unknown,") and "cite.md" in l for l in out.splitlines()), out)


# A non-ASCII untracked name. git quotes such a name in `git ls-files` output unless -z is passed ("caf\303\251.md"),
# so the step read a name no file has. The name the file has is listed and linted, and a clean sentence passes. The ASCII
# name beside it is the control: the same shape, with no quoting to get wrong.
def untracked_run(name, text):
    """A topic fixture with one new markdown file `name`, untracked and never git-added, then bin/ste-changed main there.
    Returns the untracked names git lists with -z (no quoting), and the command's exit code and output."""
    with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:  # test-temp-standard: the run folder, never the system temp
        work = make_repo(d, UNCOMMITTED_BASE, lambda w: write(w, name, text, "w"))
        names = git_read(work, "ls-files", "--others", "--exclude-standard", "-z").split("\0")
        rc, out = run_command(work)
    return names, rc, out


names, rc, out = untracked_run("café.md", "# Café\n\nShort line.\n")
check("non-ASCII untracked scope: café.md is untracked, not ignored", "café.md" in names, str(names))
check("non-ASCII untracked: the scope lists café.md by its own name", "café.md" in parts(out)["files"], out)
check("non-ASCII untracked: exits 0 with PASS on a clean sentence", rc == 0 and "ste-lint: PASS" in out, out)
names, rc, out = untracked_run("clean-note.md", "# Clean\n\nShort line.\n")
check("ASCII untracked control: clean-note.md is listed, exits 0 and PASSes",
      "clean-note.md" in parts(out)["files"] and rc == 0 and "ste-lint: PASS" in out, out)


# A name with a space. git ends the `+++ b/` header of such a name with a tab, so the changed-line map read a name with
# that tab, no finding landed on a changed line, and the step passed. The name is linted by its own name, and a 42-word
# sentence in it fails. `space.md` is the control: the same sentence under a name with no space.
LONG42 = " ".join(["word"] * 41) + " end."  # 42 words, over the STE001 limit of 40


def long_sentence(name):
    def change(work):
        write(work, name, "# S\n\n" + LONG42 + "\n", "w")
        git(work, "commit", "-qam", "long")
    return change


rc, out = run("changed", base={"sp ace.md": "# S\n\nShort line.\n"}, change=long_sentence("sp ace.md"))
check("space in name: sp ace.md is in scope", "sp ace.md" in parts(out)["files"], out)
check("space in name: exits 1 on the 42-word sentence", rc == 1, out)
check("space in name: STE001 names sp ace.md:3", "sp ace.md:3: STE001 " in out, out)
rc, out = run("changed", base={"space.md": "# S\n\nShort line.\n"}, change=long_sentence("space.md"))
check("space control: space.md with the same sentence exits 1 and names space.md:3",
      rc == 1 and "space.md:3: STE001 " in out, out)


# A stat-only change: a tracked file is touched, so its mtime moves and its content does not. The committed STE001 in the PR
# range is still a finding. The stat refresh is not an unknown read: the step lints the range and exits 1, as main does.
# The touch is the change's last act, since a commit refreshes the index first. The scope facts read no index (P7).
STAT_BASE = {**UNCOMMITTED_BASE, "long-note.md": "# S\n\nShort line.\n"}
stat = {}


def stat_only(work):
    long_sentence("long-note.md")(work)  # committed: a STE001 error in the PR range
    path = os.path.join(work, "data.txt")
    before = touch_same_bytes(work, "data.txt")  # touch: the mtime moves, the content does not
    with open(path, encoding="utf-8") as f:
        stat["same"] = f.read() == git_read(work, "show", "HEAD:data.txt")
    stat["committed"] = "long-note.md" in git_read(work, "ls-tree", "--name-only", "HEAD").split()
    stat["moved"] = os.stat(path).st_mtime != before.st_mtime


rc, out = run("changed", base=STAT_BASE, change=stat_only)
check("stat-only scope: long-note.md is committed, data.txt has a new mtime and its committed bytes",
      stat.get("committed") and stat.get("moved") and stat.get("same"), str(stat))
check("stat-only: exits 1 on the committed STE001, as main does", rc == 1, out)
check("stat-only: the log names long-note.md:3 STE001", "long-note.md:3: STE001 " in out, out)
check("stat-only: no ste-lint unknown line, so the stat refresh did not stop the read",
      "ste-lint: unknown" not in out, out)
rc, out = run("changed", base=STAT_BASE, change=long_sentence("long-note.md"))
check("stat-only control: the same committed STE001 with no touch exits 1 and names long-note.md:3",
      rc == 1 and "long-note.md:3: STE001 " in out, out)


# A dirty tree whose snapshot fails. The step reads the working tree with `git stash create`, and exit 1 with no output
# can also be a real failure, not only "no local changes". A tracked FIFO, which git cannot read ("unsupported file type"),
# makes the snapshot fail on a dirty tree. The step must say unknown and exit 0, and never print PASS or "stale-cites: PASS",
# since the uncommitted STE001 in a.md is not read. A FIFO is a POSIX file type, so a platform with no os.mkfifo prints SKIP.
# The scope facts are read in the change, before the step runs (P7).
UNREADABLE_BASE = {"a.md": "# T\n\nShort line.\n", "data.txt": "x\n"}
unreadable = {}


def unreadable_dirty(work):
    write(work, "a.md", "# T\n\n" + LONG + "\n", "w")  # a markdown edit, not committed: the tree is dirty
    path = os.path.join(work, "data.txt")
    os.remove(path)
    os.mkfifo(path)  # a tracked file git cannot read: the snapshot fails
    unreadable["dirty"] = not content_clean(work)
    snap = subprocess.run(["git", "-c", "user.name=ste-lint", "-c", "user.email=ste-lint@localhost", "-C", work,
                           "stash", "create"], capture_output=True, text=True)
    unreadable["snapshot_empty"] = snap.returncode != 0 and snap.stdout == ""
    unreadable["snapshot_cause"] = "unsupported file type" in snap.stderr


if not hasattr(os, "mkfifo"):
    print("SKIP ste-lint unreadable dirty tree: a FIFO is a POSIX file type, and this platform has no os.mkfifo")
else:
    rc, out = run("changed", base=UNREADABLE_BASE, change=unreadable_dirty)
    check("unreadable dirty scope: git's content check reads the tree as dirty", unreadable.get("dirty") is True,
          str(unreadable))
    check("unreadable dirty scope: the snapshot exits non-zero with no output", unreadable.get("snapshot_empty") is True,
          str(unreadable))
    check("unreadable dirty scope: the snapshot names data.txt as unsupported", unreadable.get("snapshot_cause") is True,
          str(unreadable))
    check("unreadable dirty: exits 0, as the other unknown reads do", rc == 0, out)
    check("unreadable dirty: one ste-lint line says unknown",
          any(l.startswith("ste-lint: unknown") for l in out.splitlines()), out)
    check("unreadable dirty: no ste-lint PASS verdict", "ste-lint: PASS" not in out, out)
    check("unreadable dirty: no stale-cites PASS line", "stale-cites: PASS" not in out, out)


# A clean tree with .git/index.lock held. Touching a tracked file moves its mtime and keeps its bytes: git's content check
# reads the tree as clean, but the index's stat data is stale, and the snapshot needs the lock to refresh it. With the lock
# held, the step must still lint the committed range as main does: FAIL on the committed error, exit 1, no unknown line.
# The untouched clean tree with the lock is the control.
clean_lock = {}


def touched_clean_locked(work):
    long_sentence("long-note.md")(work)  # committed: a STE001 error in the PR range
    touch_same_bytes(work, "data.txt")  # touch: the mtime moves, the content does not
    clean_lock["held"] = hold_index_lock(work)  # the lock first, so no scope read below can refresh the index
    clean_lock["clean"] = content_clean(work)
    clean_lock["in_range"] = "long-note.md" in git_read(work, "diff", "--name-only", "HEAD~1", "HEAD").split()


rc, out = run("changed", base=STAT_BASE, change=touched_clean_locked)
check("clean lock scope: git's content check reads the touched tree as clean", clean_lock.get("clean") is True,
      str(clean_lock))
check("clean lock scope: long-note.md is committed in the range", clean_lock.get("in_range") is True, str(clean_lock))
check("clean lock scope: the index lock is held", clean_lock.get("held") is True, str(clean_lock))
check("clean lock: exits 1 on the committed STE001, as main does", rc == 1, out)
check("clean lock: the log names long-note.md:3 STE001", "long-note.md:3: STE001 " in out, out)
check("clean lock: no ste-lint unknown line", "ste-lint: unknown" not in out, out)


def clean_locked(work):
    long_sentence("long-note.md")(work)  # committed: a STE001 error in the PR range, and no tracked file is touched
    clean_lock["control_held"] = hold_index_lock(work)
    clean_lock["control_clean"] = content_clean(work)


rc, out = run("changed", base=STAT_BASE, change=clean_locked)
check("clean lock control scope: git's content check reads the tree as clean", clean_lock.get("control_clean") is True,
      str(clean_lock))
check("clean lock control scope: the index lock is held", clean_lock.get("control_held") is True, str(clean_lock))
check("clean lock control: exits 1 on the committed STE001, as main does",
      rc == 1 and "long-note.md:3: STE001 " in out, out)
check("clean lock control: no ste-lint unknown line", "ste-lint: unknown" not in out, out)


# An untracked Markdown file that .ste-lint-exclude matches is not read, so it is no unknown read. The step printed
# "untracked Markdown is not read" for any untracked .md, excluded or not. The control has no exclude entry: there the same
# file is named unknown. The exclude file is committed, so the scope facts come from ls-files (P7).
EXCL_BASE = {"a.md": "# T\n\nShort line.\n", ".ste-lint-exclude": "gen/**\n"}
excl = {}


def untracked_gen(work):
    write(work, "gen/x.md", "# G\n\n" + LONG42 + "\n", "w")  # untracked, never git-added, matched by gen/**
    excl["untracked"] = git_read(work, "ls-files", "--others", "--exclude-standard").split()
    excl["tracked"] = git_read(work, "ls-files").split()


rc, out = run("changed", base=EXCL_BASE, change=untracked_gen)
check("untracked excluded scope: gen/x.md is untracked and .ste-lint-exclude is committed",
      "gen/x.md" in excl.get("untracked", []) and ".ste-lint-exclude" in excl.get("tracked", []), str(excl))
check("untracked excluded: exits 0, as an excluded file is not read", rc == 0, out)
check("untracked excluded: no line says untracked Markdown is not read",
      "untracked Markdown is not read" not in out, out)
check("untracked excluded: the stale-cites line says PASS", "stale-cites: PASS" in out, out)
rc, out = run("changed", base={"a.md": "# T\n\nShort line.\n"}, change=untracked_gen)
check("untracked excluded control: with no exclude entry, gen/x.md is named unknown",
      any(l.startswith("stale-cites: unknown,") and "gen/x.md" in l for l in out.splitlines()), out)


# No merge base. The topic branch starts a history of its own, so origin/main and HEAD share no commit. The
# unknown-base rule (decision stale-cites-at-merge, docs/decisions/stale-cites-at-merge.md: a base that does not resolve
# is unknown, not a finding, and the check exits 0; rule verification-report-unknown-reads) holds here too: the command
# exits 0 and names the missing merge base as unknown. It must not print nothing and exit 1, as it does today.
def unrelated_change(work):
    git(work, "checkout", "-q", "--orphan", "unrelated")
    git(work, "rm", "-q", "-r", "--cached", ".")  # the index only: the files stay on disk, untracked
    write(work, "u.md", "# U\n\nShort line.\n")
    git(work, "add", "u.md")
    git(work, "commit", "-qm", "unrelated")


with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:  # test-temp-standard: the run folder, never the system temp
    work = make_repo(d, BASE_FILES, unrelated_change)
    has_base = subprocess.run(["git", "merge-base", "origin/main", "HEAD"], cwd=work, capture_output=True).returncode == 0
    rc, out = run_command(work)
check("no merge base scope: origin/main and HEAD share no commit", not has_base, str(has_base))
check("no merge base (decision stale-cites-at-merge, an unknown base exits 0): the command exits 0", rc == 0, out)
check("no merge base (decision stale-cites-at-merge, an unknown base exits 0): the output names the missing merge base",
      re.search(r"merge[ -]base", out, re.I) is not None, out)
check("no merge base (decision stale-cites-at-merge, an unknown base exits 0): the output says the result is unknown",
      "unknown" in out, out)


# A push to the default branch whose HEAD is a root commit has no HEAD~1. The step diffs HEAD~1..HEAD, and the stale-cites
# check reads that base as unknown: decision stale-cites-at-merge exits 0 for `<head>~1` of a root commit, as main does. The
# output must say `stale-cites: unknown,` in lower case; `stale-cites: UNKNOWN,` with exit 2 is the bug. The tree is
# clean and HEAD has no parent, both read inside the change (P7). The control has a second commit, so HEAD~1 exists.
root = {}


def root_commit(work):
    root["parents"] = git_read(work, "rev-list", "--parents", "-n", "1", "HEAD").split()
    root["status"] = git_read(work, "status", "--porcelain")


def second_commit(work):
    write(work, "b.md", "# B\n\nShort line.\n")
    git(work, "add", "b.md")
    git(work, "commit", "-qm", "second")


rc, out = run("changed", on_main=True, change=root_commit, EVENT_NAME="push", BASE_REF="", REF_NAME="main")
check("root push scope: HEAD has no parent and the tree is clean",
      len(root.get("parents", [])) == 1 and root.get("status") == "", str(root))
check("root push: exits 0, as main does (an unknown base, decision stale-cites-at-merge)", rc == 0, out)
check("root push: the output says `stale-cites: unknown,` in lower case", "stale-cites: unknown," in out, out)
check("root push: no `no markdown changed` line, since HEAD~1 was never read", "no markdown changed" not in out, out)
check("root push: an ste-lint unknown line names the missing HEAD~1",
      any(l.startswith("ste-lint: unknown") and "HEAD~1" in l for l in out.splitlines()), out)
rc, out = run("changed", on_main=True, change=second_commit, EVENT_NAME="push", BASE_REF="", REF_NAME="main")
check("root push control: with HEAD~1 present, exits 0 and says `stale-cites: PASS`",
      rc == 0 and "stale-cites: PASS" in out, out)
check("root push control: with HEAD~1 present, no ste-lint unknown line",
      not any(l.startswith("ste-lint: unknown") for l in out.splitlines()), out)


# A changed-file read that git refuses. A .ste-lint-exclude line git rejects as a pathspec, such as ../gen/*.md (a path outside
# the repo), fails the diff that lists the changed files. That read printed "no markdown changed" with exit 0: a false green for
# files nobody read. The step must print one ste-lint unknown line, exit 0, and never "no markdown changed" or PASS. The valid
# exclude line is the control: the same committed STE001 fails as main does. git's rejection is read in the change (P7).
BAD_PATHSPEC_BASE = {"a.md": "# T\n\nShort line.\n", "long-note.md": "# S\n\nShort line.\n",
                     ".ste-lint-exclude": "../gen/*.md\n"}
bad_pathspec = {}


def bad_pathspec_change(work):
    long_sentence("long-note.md")(work)  # committed: a STE001 error in the PR range
    p = subprocess.run(["git", "-C", work, "diff", "--name-only", "origin/main...HEAD", "--", "*.md",
                        ":(exclude,glob)../gen/*.md"], capture_output=True, text=True)
    bad_pathspec.update(rc=p.returncode, err=p.stderr)


rc, out = run("changed", base=BAD_PATHSPEC_BASE, change=bad_pathspec_change)
check("bad pathspec scope: git rejects the exclude line, exit non-zero, naming the path outside the repository",
      bad_pathspec.get("rc", 0) != 0 and "outside repository" in bad_pathspec.get("err", ""), str(bad_pathspec))
check("bad pathspec: exits 0, as an unknown read does", rc == 0, out)
check("bad pathspec: one ste-lint line says unknown",
      any(l.startswith("ste-lint: unknown") for l in out.splitlines()), out)
check("bad pathspec: no `no markdown changed` line, since the changed files were not read",
      "no markdown changed" not in out, out)
check("bad pathspec: no ste-lint PASS verdict", "ste-lint: PASS" not in out, out)
rc, out = run("changed", base={**BAD_PATHSPEC_BASE, ".ste-lint-exclude": "gen/**\n"}, change=long_sentence("long-note.md"))
check("bad pathspec control: a valid exclude line lints long-note.md and exits 1 on its STE001",
      rc == 1 and "long-note.md:3: STE001 " in out, out)


# The content check of the tracked files cannot run (run.sh, the DIFF_RC branch). The copy of .git/index fails when the index
# is gone or is a directory, so the working tree was not read. The step must print one ste-lint unknown line, exit 0, and print
# no PASS, though a Markdown edit is uncommitted. The index is replaced after the fetch and just before the step (P7).
index_state = {}


def index_replaced(how):
    def after(work):
        index = os.path.join(work, git_read(work, "rev-parse", "--git-path", "index").strip())
        index_state["dirty"] = " M draft-note.md" in git_read(work, "status", "--porcelain")
        index_state["was_file"] = os.path.isfile(index)
        os.remove(index)
        if how == "dir":
            os.mkdir(index)  # cp -p of a directory fails, as a missing file does
        index_state["now"] = "dir" if os.path.isdir(index) else "missing" if not os.path.lexists(index) else "other"
    return after


for how in ("missing", "dir"):
    rc, out = run("changed", base=UNCOMMITTED_BASE, change=edit_draft, after=index_replaced(how))
    check("index %s scope: .git/index was a file, is now %s, and draft-note.md is modified" % (how, how),
          index_state.get("was_file") is True and index_state.get("now") == how and index_state.get("dirty") is True,
          str(index_state))
    check("index %s: exits 0, as an unknown read does" % how, rc == 0, out)
    check("index %s: exactly one ste-lint line says unknown" % how,
          sum(l.startswith("ste-lint: unknown") for l in out.splitlines()) == 1, out)
    check("index %s: no PASS line, from ste-lint or stale-cites" % how,
          "ste-lint: PASS" not in out and "stale-cites: PASS" not in out, out)
    check("index %s: no `no markdown changed` line" % how, "no markdown changed" not in out, out)


# The step summary of a run with no merge base. It must say unknown, not "No markdown changed": nothing was read.
# The summary is read inside the scratch folder, which is removed when the block ends. The control is a committed
# non-markdown change with a merge base, where "No markdown changed." is the true line.
def add_notes(work):
    write(work, "notes.txt", "x\n")
    git(work, "add", "notes.txt")
    git(work, "commit", "-qm", "notes")


with scratch("summary") as s:
    summary = os.path.join(s, "sum")
    rc, out = run("changed", change=unrelated_change, GITHUB_STEP_SUMMARY=summary)
    text = open(summary, encoding="utf-8").read() if os.path.exists(summary) else ""
check("no merge base summary: the step summary has its STE lint section", "### STE lint" in text, text)
check("no merge base summary: it does not say `No markdown changed`", "No markdown changed" not in text, text)
check("no merge base summary: it says unknown", "unknown" in text.lower(), text)
with scratch("summary") as s:
    summary = os.path.join(s, "sum")
    rc, out = run("changed", change=add_notes, GITHUB_STEP_SUMMARY=summary)
    text = open(summary, encoding="utf-8").read() if os.path.exists(summary) else ""
check("summary control: a committed non-markdown change with a merge base says `No markdown changed.`",
      "No markdown changed." in text, text)


# Shadowed imports. The step runs from the linted repo's root, so a planted json.py, json/ package or
# ste_emit.py there must not run when the step imports its helpers. A package wins over a module of the
# same name, so each shape gets its own run. Each planted file writes its own marker when imported.
def shadow_run(scope, json_path):
    with tempfile.TemporaryDirectory() as outer:
        marks, summary = os.path.join(outer, "marks"), os.path.join(outer, "sum")
        os.mkdir(marks)
        planted = {}
        for path in (json_path, "ste_emit.py"):
            marker = os.path.join(marks, path.replace("/", "_") + ".marker")
            planted[path] = "open(%r, 'w').close()\n" % marker
        rc, out = run(scope, base={**BASE_FILES, **planted}, GITHUB_STEP_SUMMARY=summary)
        text = open(summary, encoding="utf-8").read() if os.path.exists(summary) else ""
        return sorted(os.listdir(marks)), text, out


for scope in ("all", "changed"):
    for json_path in ("json.py", "json/__init__.py"):
        written, text, out = shadow_run(scope, json_path)
        label = "SCOPE %s, planted %s" % (scope, json_path)
        check("%s: no planted file runs on import" % label, written == [],
              out + "\nmarkers written: %s" % written)
        check("%s: the summary still prints" % label,
              "### STE lint" in text and "Files checked:" in text, out + "\nsummary file:\n" + text)


# The pin check. A scratch claude-settings clone holds the command, its imports and LINT_FILES, so the
# command's ROOT is that clone. History: A, then C changes the lint, then D changes only README.md (HEAD).
# E, off D on a side branch, changes the lint again: a pin this copy does not hold.
src = open(CMD, encoding="utf-8").read()
m = re.search(r"^LINT_FILES = (\([^)]*\))", src, re.M)
check("the command names the files the step runs (LINT_FILES)", bool(m), "")
LINT_FILES = ast.literal_eval(m.group(1)) if m else ()
# The linter's imports, followed at any depth through lint/ and hooks/ (the folders its sys.path reaches).
# The pin check hashes only LINT_FILES, so every file these imports reach must be listed there.
IMPORT_DIRS = ("lint", "hooks")


def repo_imports(rel):
    """The lint/ and hooks/ files that the module at `rel` imports, as repo-relative paths."""
    tree = ast.parse(open(os.path.join(ROOT, rel), encoding="utf-8").read())
    mods = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    mods |= {n.module.split(".")[0] for n in ast.walk(tree)
             if isinstance(n, ast.ImportFrom) and n.module and not n.level}
    return sorted("%s/%s.py" % (d, m) for m in mods for d in IMPORT_DIRS
                  if os.path.exists(os.path.join(ROOT, d, m + ".py")))


def import_closure(entry):
    seen, todo = set(), [entry]
    while todo:
        rel = todo.pop()
        if rel not in seen:
            seen.add(rel)
            todo.extend(repo_imports(rel))
    return seen


reached = set().union(*(import_closure(e) for e in ("lint/ste_lint.py", "lint/layout.py")))
for rel in sorted(reached):
    check("LINT_FILES holds %s, which the linter imports" % rel, rel in LINT_FILES,
          "%s is imported by the linter (lint/ and hooks/ at any depth), and LINT_FILES in bin/ste-changed omits it" % rel)
check("LINT_FILES holds the linter run.sh runs",
      "lint/ste_lint.py" in LINT_FILES and "../../lint/ste_lint.py" in open(os.path.join(HERE, "run.sh")).read(), "")


def head(cs):
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=cs, capture_output=True, text=True).stdout.strip()


def scratch_clone(cs, zizmor_step=False):
    """A claude-settings clone at `cs`: the files bin/ste-changed and install.sh read, copied from what git lists here
    (tracked_tree), so the installed hooks hold every module the command may import. History: A, then C changes the
    lint, then D changes only README.md. With `zizmor_step`, Z follows D and changes only actions/zizmor/run.sh, and Y
    follows Z and changes only actions/zizmor/action.yml; the main branch is then at Y, else at D (HEAD, main and
    origin/main). E, off main on a side branch, changes the lint again. Returns {label: sha}, with "Z" and "Y" when zizmor_step."""
    tracked_tree.copy_tracked(cs, "bin", "hooks", "lint", "actions/ste-lint", "actions/zizmor")
    for rel in (".ste-lint-exclude", "landed-dirs.txt", "install.sh"):
        shutil.copy2(os.path.join(ROOT, rel), os.path.join(cs, rel))
    write(cs, "CLAUDE.md", "# claude-settings fixture\n")  # install.sh takes a folder with these two as its source
    write(cs, "settings.json", "{}\n")
    write(cs, "README.md", "x\n")
    git(os.path.dirname(cs), "init", "-q", "-b", "main", cs)
    shas = {}
    for label, rel in (("A", None), ("C", "lint/ste_lint.py"), ("D", "README.md")):
        if rel:
            write(cs, rel, "\n# %s\n" % label, "a")
        git(cs, "add", "."); git(cs, "commit", "-qm", label)
        shas[label] = head(cs)
    if zizmor_step:
        write(cs, "actions/zizmor/run.sh", "\n# Z\n", "a")
        git(cs, "add", "."); git(cs, "commit", "-qm", "Z")
        shas["Z"] = head(cs)
        write(cs, "actions/zizmor/action.yml", "\n# Y\n", "a")
        git(cs, "add", "."); git(cs, "commit", "-qm", "Y")
        shas["Y"] = head(cs)
    git(cs, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(cs, "checkout", "-q", "-b", "side")
    write(cs, "lint/ste_lint.py", "\n# E\n", "a")
    git(cs, "commit", "-qam", "E")
    shas["E"] = head(cs)
    git(cs, "checkout", "-q", "main")
    return shas


def pin_child(d, shas, pin, change=lambda work: None, dead=None, zizmor=None, step_name=None):
    """A child repo under `d` whose CI pins ste-lint at `pin` and zizmor at `zizmor`: each a label of `shas`, or a sha,
    or None for no pin of that action. The ste-lint pin is written first, so it is line 5, and `step_name`, when given,
    names that step on line 6. `dead` is a label that is pinned in a comment only. Returns its working folder."""
    steps = []
    if pin is not None:
        steps.append("      - uses: o/claude-settings/actions/ste-lint@%s # main\n" % shas.get(pin, pin)
                     + ("        name: %s\n" % step_name if step_name else ""))
    if zizmor is not None:
        steps.append("      - uses: o/claude-settings/actions/zizmor@%s # main\n" % shas.get(zizmor, zizmor))
    wf = "on: pull_request\njobs:\n  l:\n    steps:\n" + "".join(steps)
    if dead:
        wf += "      # - uses: o/claude-settings/actions/ste-lint@%s\n" % shas[dead]
    return make_repo(d, {**BASE_FILES, ".github/workflows/ci.yml": wf}, change)


def run_ste_changed(cmd, work, home=None, extra=None, err=None):
    """`cmd main` in `work`, with the step's variables, the pin note's variable and CLAUDE_CONFIG_DIR stripped. `home`
    replaces HOME, so a command that reads ~/.claude reads the temp one. `extra` sets variables on the command, and
    `err`, a list, takes its stderr. Returns (rc, output)."""
    env = {k: v for k, v in os.environ.items() if k not in STEP_ENV + ("CLAUDE_CONFIG_DIR",)}
    if home:
        env["HOME"] = home
    env.update(extra or {})
    p = subprocess.run([sys.executable, cmd, "main"], cwd=work, env=env, capture_output=True, text=True)
    if err is not None:
        err.append(p.stderr)
    return p.returncode, p.stdout + p.stderr


def zizmor_facts(cs, sha):
    """What the clone holds for the zizmor action at `sha` and at HEAD: run.sh exists at each, whether run.sh differs
    (`differ`), and whether action.yml differs (`yml_differ`)."""
    def blob(rev, name):
        p = subprocess.run(["git", "show", rev + ":actions/zizmor/" + name], cwd=cs, capture_output=True, text=True)
        return p.stdout if p.returncode == 0 else None
    at, now = blob(sha, "run.sh"), blob("HEAD", "run.sh")
    return {"at_pin": at is not None, "at_head": now is not None, "differ": at != now,
            "yml_differ": blob(sha, "action.yml") != blob("HEAD", "action.yml")}


def pin_case(pin, change=lambda work: None, dead=None, shallow=False, proof=None, zizmor=None, zizmor_step=False,
             extra=None, err=None):
    """Run the scratch clone's command in a child repo whose CI pins ste-lint at `pin` and zizmor at `zizmor`. A pin
    may name a commit label of the scratch clone, or be None. Returns (rc, output, {label: sha}). `shallow` runs the
    command from a shallow clone that holds the pin's object and cuts the history above it. `zizmor_step` adds the Z
    commit (see scratch_clone). `proof`, a dict, takes that clone's facts. `extra` and `err` pass to run_ste_changed."""
    with scratch("pin") as d:
        cs = os.path.join(d, "claude-settings")
        if shallow:
            source = os.path.join(d, "source")
            shas = scratch_clone(source)
            error = shallow_clone.make(source, cs, shas[pin])
            if error:
                raise RuntimeError("shallow fixture could not be built: " + error)
            if proof is not None:
                proof.update(shallow_clone.facts(cs, shas[pin]))
        else:
            shas = scratch_clone(cs, zizmor_step)
            if proof is not None and zizmor is not None:
                proof.update(zizmor_facts(cs, shas.get(zizmor, zizmor)))
        rc, out = run_ste_changed(os.path.join(cs, "bin", "ste-changed"),
                                  pin_child(d, shas, pin, change, dead, zizmor), extra=extra, err=err)
        return rc, out, shas


rc, out, shas = pin_case("A")
check("pin drift: an older pin's lint differs, so the command exits 3 though the lint passed",
      rc == 3 and "CI pins ste-lint at %s" % shas["A"][:7] in out and ".github/workflows/ci.yml:5" in out, out)
check("pin drift: the remedy names claude-settings main and the rule",
      "Move the pin to %s" % shas["D"] in out and "git-integration-branch-merge" in out, out)
check("pin drift, ste-lint: its older remedy keeps the clause the owner's rule grants for ste-lint pins",
      any("CI pins ste-lint at %s" % shas["A"][:7] in l and "with no question (rule git-integration-branch-merge)" in l
          for l in out.splitlines()), out)
rc, out, shas = pin_case("C")
check("no drift: a pin whose lint files equal this copy's exits 0, though README.md moved since",
      rc == 0 and "CI pins ste-lint at %s" % shas["C"][:7] in out and "the same lint as this copy" in out, out)
rc, out, shas = pin_case("C", dead="A")
check("a commented-out pin is not a pin: an old one in a comment changes nothing",
      rc == 0 and shas["A"][:7] not in out, out)
rc, out, shas = pin_case("E")
check("pin ahead: a pin this copy's history lacks exits 3 and says to pull claude-settings",
      rc == 3 and "pull claude-settings" in out, out)
check("pin ahead, full clone: says does not hold and off main, never unknown (shallow clone)",
      "does not hold" in out and "off main" in out and "unknown (shallow clone)" not in out, out)
rc, out, _ = pin_case("f" * 40)
check("unknown pin: a commit this clone does not hold is unknown and exits 0",
      rc == 0 and "Unknown whether it matches" in out, out)
rc, out, _ = pin_case("A", default_change)
check("lint red and drift: the lint's exit code wins, and the drift line still prints",
      rc == 1 and "older than this copy's lint" in out, out)

# The pin note (decision action-pins-follow-sessions). With STE_CHANGED_PIN_NOTE=1 a drifted pin never turns a passing
# lint into exit 3: the drift stays on stderr, and a failing lint keeps its own exit code. Without the variable, exit 3.
PIN_NOTE = {PIN_NOTE_ENV: "1"}


def short_change(work):
    """A changed Markdown line that passes the lint: the base has a.md, so the commit can stage it."""
    write(work, "a.md", "# T\n\nA short sentence.\n", "w")
    git(work, "commit", "-qam", "short")


err = []
rc, out, shas = pin_case("A", short_change, extra=PIN_NOTE, err=err)
check("pin note scope: the drift line is on stderr, and the lint passed",
      "CI pins ste-lint at %s" % shas["A"][:7] in "".join(err) and "ste-lint: PASS" in out, out + "".join(err))
check("pin note: a drifted pin with a passing lint exits 0", rc == 0, out)
err = []
rc, out, shas = pin_case("A", default_change, extra=PIN_NOTE, err=err)
check("pin note, failing lint: the drift line is on stderr, and the lint's FAIL is the verdict",
      "CI pins ste-lint at %s" % shas["A"][:7] in "".join(err) and "ste-lint: FAIL" in out, out + "".join(err))
check("pin note, failing lint: exit 1, never masked as a note", rc == 1, out)


# ci-job's ste-lint step (bin/ci-job runs bin/ste-changed in place) in a child whose CI pins ste-lint. The job runs from
# the scratch clone's own bin/ci-job, so the step's ste-changed and its pin check are that clone's too.
def ci_job_case(change, pin="A", step=False):
    """`bin/ci-job l --lint --base origin/main` in a child repo whose CI pins ste-lint at `pin`. With `step`, the child's
    ste-lint step is named in its workflow and run as `--step NAME`, with no --lint, as merge's ready checks run it.
    Returns (rc, stdout, the job's verdict log, {label: sha}, the step's name, or "" without `step`). The log is read
    before the run folder is removed."""
    with scratch("cijob") as d:
        cs = os.path.join(d, "claude-settings")
        shas = scratch_clone(cs)
        work = pin_child(d, shas, pin, change, step_name="ste-lint" if step else None)
        name = ""
        if step:  # read back from the workflow the fixture wrote, through the one step parser (lint/workflow_steps.py)
            with open(os.path.join(work, ".github", "workflows", "ci.yml"), encoding="utf-8") as f:
                wf = f.read()
            name = next((step_key(st, "name") for st in step_blocks(job_block(wf, "l"))
                         if "actions/ste-lint@" in st), None) or ""
        log, tmp = os.path.join(d, "verdict.log"), os.path.join(d, "tmp")
        os.makedirs(tmp)
        env = {k: v for k, v in os.environ.items() if k not in STEP_ENV + ("CLAUDE_CONFIG_DIR",)}
        env.update(VERDICT_LOG=log, TMPDIR=tmp)  # the job's logs and step scripts stay in this run's folder
        mode = ["--step", name] if step else ["--lint"]
        p = subprocess.run([sys.executable, os.path.join(cs, "bin", "ci-job"), "l", "--workflow",
                            os.path.join(".github", "workflows", "ci.yml"), *mode, "--base", "origin/main"],
                           cwd=work, env=env, capture_output=True, text=True)
        text = open(log, encoding="utf-8", errors="replace").read() if os.path.exists(log) else ""
        return p.returncode, p.stdout, text, shas, name


def step_line(stdout):
    """The first line of a job run that starts with a verdict word, or '' when none."""
    words = ("PASS ", "FAIL ", "SKIP ", "unknown ", "not run")
    return next((l for l in stdout.splitlines() if l.startswith(words)), "")


rc, stdout, log, shas, _ = ci_job_case(short_change)
line = step_line(stdout)
# A stale pin under --lint is a note on the step's PASS line, judged against the stable head, else the local copy, exit 0
# (decision action-pins-follow-sessions: drift under --lint is a note, not an exit).
check("ci-job pinned tree, pass: scope, the lint passed and the log holds the pin's drift line",
      "CI pins ste-lint at %s" % shas["A"][:7] in log and "ste-lint: PASS" in log, log)
check("ci-job pinned tree, pass: the ste-lint step reads PASS and its line carries the drift as a pin note",
      line.startswith("PASS ") and PIN_NOTE_MARKER in line, stdout)
check("ci-job pinned tree, pass: the job exits 0, the stale pin is a note under --lint", rc == 0, stdout)
rc, stdout, log, shas, _ = ci_job_case(default_change)
line = step_line(stdout)
check("ci-job pin note, failing lint: scope, the drift is in the log and the lint FAILs",
      "CI pins ste-lint at %s" % shas["A"][:7] in log and "ste-lint: FAIL" in log, log)
check("ci-job pin note, failing lint: the step reads FAIL and its line never says `pin note`",
      line.startswith("FAIL ") and "pin note" not in line, stdout)
check("ci-job pin note, failing lint: the job exits 1", rc == 1, stdout)
rc, stdout, log, shas, _ = ci_job_case(short_change, pin="C")
line = step_line(stdout)
check("ci-job, no drift: scope, the pinned lint runs and the log says the pin is the same as this copy",
      "ste-lint: PASS" in log and "as this copy" in log, log)
check("ci-job, no drift: the step reads PASS with no `pin note`, and the job exits 0",
      rc == 0 and line.startswith("PASS ") and "pin note" not in line, stdout)

# merge's ready checks run ci-job with --step and no --lint (merge/merge.py run_ready_checks). A stale pin under --step is a
# FAIL of the named step, and the job exits 1 (decision action-pins-follow-sessions).
rc, stdout, log, shas, name = ci_job_case(short_change, step=True)
line = step_line(stdout)
check("ci-job --step, drifted pin: scope, the step is named in its workflow, its lint PASSes, and the log holds the pin's drift line",
      bool(name) and "CI pins ste-lint at %s" % shas["A"][:7] in log and "ste-lint: PASS" in log, log)
check("ci-job --step, drifted pin: the named step reads FAIL", line.startswith("FAIL ") and name + ":" in line, stdout)
check("ci-job --step, drifted pin: the job exits 1", rc == 1, stdout)
rc, stdout, log, shas, name = ci_job_case(short_change, pin="C", step=True)
check("ci-job --step, no drift: the named step reads PASS and the job exits 0",
      rc == 0 and step_line(stdout).startswith("PASS "), stdout)

# The zizmor pin. The check reads `<owner>/claude-settings/actions/zizmor@<sha>` pins in the same workflows and compares
# actions/zizmor/run.sh at each pinned commit with this copy's, with the same verdict lines, each naming its action.
# Each line is found by its prefix, so one action's line never answers for the other's (zizmor_step: see scratch_clone).
def pin_lines(out, action):
    """The output lines that name a pin of `action`."""
    return [l for l in out.splitlines() if "CI pins %s at " % action in l]


facts = {}
rc, out, shas = pin_case(None, zizmor="D", zizmor_step=True, proof=facts)
drift = pin_lines(out, "zizmor")
line = drift[0] if drift else ""
check("zizmor drift scope: run.sh exists at the pin and at HEAD, and the two differ",
      facts.get("at_pin") is True and facts.get("at_head") is True and facts.get("differ") is True, str(facts))
check("zizmor drift: the command prints one line that names zizmor", len(drift) == 1, out)
check("zizmor drift: the line names the pinned commit", shas["D"][:7] in line, out)
check("zizmor drift: the line points at the workflow line that pins it", ".github/workflows/ci.yml:5" in line, out)
check("zizmor drift: exit 3, though the lint passed", rc == 3, out)
check("zizmor older remedy: it names moving the pin to claude-settings main", bool(line) and "Move the pin to %s" % shas["Y"] in line, out)
check("zizmor older remedy: no 'with no question' clause, which the owner's rule grants for ste-lint pins only",
      bool(line) and "with no question" not in line and "git-integration-branch-merge" not in line, out)

# Only action.yml moved: run.sh is the same at the pin and at HEAD, so the action.yml file set alone makes the drift.
facts = {}
rc, out, shas = pin_case(None, zizmor="Z", zizmor_step=True, proof=facts)
yml = pin_lines(out, "zizmor")
line = yml[0] if yml else ""
check("zizmor action.yml only scope: action.yml differs from the pin's, run.sh is the same",
      facts.get("yml_differ") is True and facts.get("differ") is False and facts.get("at_pin") is True, str(facts))
check("zizmor action.yml only: the command prints one line that names zizmor at the pinned commit, not the same",
      len(yml) == 1 and shas["Z"][:7] in line and "the same" not in line, out)
check("zizmor action.yml only: exit 3 from the action.yml drift", rc == 3, out)

facts = {}
rc, out, shas = pin_case(None, zizmor="A", proof=facts)
same = pin_lines(out, "zizmor")
line = same[0] if same else ""
check("zizmor same scope: run.sh at the pin equals HEAD's, so an equal result is not a missing file",
      facts.get("at_pin") is True and facts.get("at_head") is True and facts.get("differ") is False, str(facts))
check("zizmor same: the command prints one line that names zizmor at the pinned commit",
      len(same) == 1 and shas["A"][:7] in line, out)
check("zizmor same: the line says the same, its zizmor files equal this copy's though the lint differs",
      "the same" in line, out)
check("zizmor same: exit 0, no drift from the zizmor pin", rc == 0, out)

rc, out, shas = pin_case("D", zizmor="C", zizmor_step=True)
ste, zz = pin_lines(out, "ste-lint"), pin_lines(out, "zizmor")
check("both pins, different commits: one line per action", len(ste) == 1 and len(zz) == 1, out)
check("both pins, ste-lint: its line names D and says the same lint, judged on its own files",
      len(ste) == 1 and shas["D"][:7] in ste[0] and "the same lint as this copy" in ste[0], out)
check("both pins, zizmor: its line names C and does not say the same, judged on its own files",
      len(zz) == 1 and shas["C"][:7] in zz[0] and "the same" not in zz[0], out)
check("both pins, different commits: exit 3 comes from the zizmor drift", rc == 3, out)

rc, out, shas = pin_case("D", zizmor="D", zizmor_step=True)
ste, zz = pin_lines(out, "ste-lint"), pin_lines(out, "zizmor")
check("both pins, same commit: each action keeps its own line", len(ste) == 1 and len(zz) == 1, out)
check("both pins, same commit: the ste-lint line says the same lint", len(ste) == 1 and "the same lint as this copy" in ste[0], out)
check("both pins, same commit: the zizmor line is its own, at ci.yml:6, after the ste-lint pin",
      len(zz) == 1 and ".github/workflows/ci.yml:6" in zz[0] and shas["D"][:7] in zz[0], out)
check("both pins, same commit: exit 3 from the zizmor drift", rc == 3, out)

# The shallow clone: the command's clone holds the pin's object but cuts the history between the pin and HEAD, so
# `merge-base --is-ancestor` exits 1 there. That answer is unknown, never "not on main" (verification-report-unknown-reads).
facts = {}
rc, out, _ = pin_case("A", shallow=True, proof=facts)
check("shallow fixture: the command's clone is shallow and holds the pin's object",
      facts.get("shallow") is True and facts.get("pin_present") is True, str(facts))
check("shallow fixture: the pin's ancestry is cut, so merge-base --is-ancestor exits 1",
      facts.get("ancestor_rc") == 1, str(facts))
check("shallow pin: the drift still exits 3, since the lint files differ", rc == 3, out)
check("shallow pin: the line says unknown (shallow clone) and names git fetch --unshallow",
      "unknown (shallow clone)" in out and "git fetch --unshallow" in out, out)
check("shallow pin: the line never says does not hold or off main",
      "does not hold" not in out and "off main" not in out, out)


# The installed copy. install.sh lands bin/ste-changed in ~/.claude: a copy in cloud mode, a symlink into the
# <clone>-live checkout in local mode. In the copy, the command's own folder holds no actions/ and is no git clone.
# The checkout is the one the global CLAUDE.md names on its `@<dir>/CLAUDE.md` line. The cases run the clone's own
# install.sh into a temp HOME, so each one reads what an install lands. Only PATH and HOME reach the installer:
# CLAUDE_CODE_REMOTE in the caller's environment would force cloud mode, and CLAUDE_CONFIG_DIR would move ~/.claude.
# A pipx stub stands in for the cloud-only `pip install --user pipx`, which needs the network.
def install_case(mode, pointer=None, mkdirs=()):
    """The scratch clone's install.sh in `mode` ("cloud": --cloud; "local": symlinks) into a temp HOME, then
    ~/.claude/bin/ste-changed in a child repo whose CI pins ste-lint at the older commit A. A text in `pointer`
    replaces ~/.claude/CLAUDE.md after the install; `mkdirs` are folders made under HOME first. Returns a dict."""
    with scratch("install-" + mode) as d:
        home = os.path.join(d, "home")
        clone = os.path.join(home, "claude-settings")
        shas = scratch_clone(clone)
        write(os.path.join(d, "stub-bin"), "pipx", "#!/bin/sh\nexit 0\n")
        os.chmod(os.path.join(d, "stub-bin", "pipx"), 0o755)
        env = {"PATH": os.path.join(d, "stub-bin") + os.pathsep + os.environ["PATH"], "HOME": home}
        p = subprocess.run([BASH, os.path.join(clone, "install.sh"), *(["--cloud"] if mode == "cloud" else [])],
                           cwd=d, env=env, capture_output=True, text=True)
        cfg, installed = os.path.join(home, ".claude"), os.path.join(home, ".claude", "bin", "ste-changed")
        md = os.path.join(cfg, "CLAUDE.md")
        facts = {"shas": shas, "install_rc": p.returncode, "install_out": p.stdout + p.stderr,
                 "is_file": os.path.isfile(installed), "is_link": os.path.islink(installed),
                 "real": os.path.realpath(installed), "live": os.path.realpath(clone + "-live"),
                 "actions": os.path.exists(os.path.join(cfg, "actions")),
                 "pointer": open(md, encoding="utf-8").read().split("\n")[0] if os.path.exists(md) else ""}
        for rel in mkdirs:
            os.makedirs(os.path.join(home, rel))
        if pointer is not None:
            write(cfg, "CLAUDE.md", pointer)
        facts["rc"], facts["out"] = run_ste_changed(installed, pin_child(d, shas, "A"), home)
        return facts


def shown(r):
    return "install exit %s:\n%s\n--- command, exit %s ---\n%s" % (r["install_rc"], r["install_out"], r["rc"], r["out"])


def drifted_from_checkout(r):
    """The pin check ran against the checkout: exit 3, the pin and the remedy that names that checkout's main."""
    return (r["rc"] == 3 and "Traceback" not in r["out"] and "Unknown whether it matches" not in r["out"]
            and "CI pins ste-lint at %s" % r["shas"]["A"][:7] in r["out"]
            and "Move the pin to %s" % r["shas"]["D"] in r["out"])


NAMES_CHECKOUT = re.compile(r"(?<![\w/\\.-])claude-settings(?![\w/\\-])")  # the word, never a part of a path


def one_line_no_traceback(r):
    """The command failed with one non-blank line that names the claude-settings checkout in words, and no traceback.
    Every fixture path holds "claude-settings", so a caught exception that prints its own path does not count."""
    lines = [l for l in r["out"].splitlines() if l.strip()]
    return (r["rc"] != 0 and "Traceback" not in r["out"] and "Errno" not in r["out"] and len(lines) == 1
            and bool(NAMES_CHECKOUT.search(lines[0])))


with scratch("sweep") as root:
    own, old, new = (os.path.join(root, "%d-%s" % (n, uuid.uuid4().hex)) for n in (1, 2, 3))
    for folder in (own, old, new):
        os.makedirs(folder)
    two_days_ago = time.time() - 2 * 24 * 60 * 60
    os.utime(old, (two_days_ago, two_days_ago))
    _test_temp.sweep(root, own)
    check("test temp: the sweep removes a sibling run folder over a day old and keeps a new one and its own",
          not os.path.exists(old) and os.path.isdir(new) and os.path.isdir(own), str(sorted(os.listdir(root))))

if os.name == "nt":
    print("skip - installed copy: install.sh does not run on Windows")
else:
    r = install_case("cloud")
    check("installed copy, cloud: install.sh exits 0 and copies bin/ste-changed, with no actions/ beside it",
          r["install_rc"] == 0 and r["is_file"] and not r["is_link"] and not r["actions"], shown(r))
    check("installed copy, cloud: the global CLAUDE.md names the checkout", r["pointer"] == "@~/claude-settings/CLAUDE.md",
          r["pointer"])
    check("installed copy, cloud: a drifted pin exits 3 with the pin message read from the checkout the pointer names",
          drifted_from_checkout(r), shown(r))
    for label, text, mkdirs in (
            ("no pointer line", "# my own rules\n", ()),
            ("the pointer names a folder that is gone", "@~/no-such-checkout/CLAUDE.md\n", ()),
            ("the pointer names a folder that is no claude-settings checkout", "@~/other-repo/CLAUDE.md\n",
             ("other-repo",))):
        r = install_case("cloud", text, mkdirs)
        check("installed copy, cloud, %s: install.sh exits 0" % label, r["install_rc"] == 0 and r["is_file"], shown(r))
        check("installed copy, cloud, %s: exits non-zero with one line naming claude-settings, no traceback" % label,
              one_line_no_traceback(r), shown(r))
    r = install_case("local")
    check("installed copy, local: install.sh exits 0 and links bin/ste-changed into the pinned checkout",
          r["install_rc"] == 0 and r["is_link"]
          and r["real"] == os.path.join(r["live"], "bin", "ste-changed"), shown(r) + "\nlinks to " + r["real"])
    check("installed copy, local: a drifted pin exits 3 with the pin message", drifted_from_checkout(r), shown(r))
# The tree-cites input (decision stale-cites-at-merge): off by default. When "true", the step runs `--tree` in both
# scopes, so a stale cite in any tracked file fails the step. The cite sits in a file this PR does not touch.
STALE_TREE_BASE = {"a.md": "# T\n\nShort line.\n", "docs/old.md": "# Old\n\n- see `hooks/gone.py`\n",
                   "hooks/keep.py": "X = 1\n"}  # hooks/ is a tracked top folder, so hooks/gone.py is a dead path


def edit_a(work):
    write(work, "a.md", "# T\n\nShort line, edited.\n", "w")
    git(work, "commit", "-qam", "edit")


def action_yml():
    with open(os.path.join(HERE, "action.yml"), encoding="utf-8") as f:
        return f.read()


def tree_cites_default():
    """The default of the tree-cites input, read from action.yml. None when the input is not declared."""
    head = action_yml().split("\n  tree-cites:\n", 1)
    if len(head) < 2:
        return None
    block = re.split(r"\n  [\w-]+:\n|\nruns:", head[1], 1)[0]
    found = re.search(r'default: "([^"]*)"', block)
    return found.group(1) if found else None


check('tree-cites: the input is declared with default "false"', tree_cites_default() == "false",
      "default: %r" % tree_cites_default())
check("tree-cites: the step passes the input to run.sh as TREE_CITES",
      "TREE_CITES: ${{ inputs.tree-cites }}" in action_yml(), "")
rc, out = run("changed", base=STALE_TREE_BASE, change=edit_a, TREE_CITES="false")
check("tree-cites off: a stale tree passes the step and no tree finding prints",
      rc == 0 and "STALE003" not in out, out)
rc, out = run("changed", base=STALE_TREE_BASE, change=edit_a, TREE_CITES="true")
check("tree-cites on: the step fails on the stale cite in the untouched file",
      rc == 1 and "docs/old.md:3: STALE003 " in out, out)
rc, out = run("changed", "false", base=STALE_TREE_BASE, change=edit_a, TREE_CITES="true")
check("tree-cites on, fail=false: the finding prints and the step exits 0",
      rc == 0 and "docs/old.md:3: STALE003 " in out, out)
rc, out = run("all", base=STALE_TREE_BASE, change=edit_a, TREE_CITES="true")
check("tree-cites on, scope all: the step checks the whole tree",
      rc == 1 and "docs/old.md:3: STALE003 " in out, out)

# The pin reader. A pin is found in any YAML shape the old line reader found it in: a flow-style step, and a steps
# list indented four spaces. Each is a pin that drifts (exit 3), as on main.
def pin_shape_case(shape, pin="A", before=""):
    """Run the scratch clone's command in a child whose CI pins ste-lint at `pin` in one shape: `flow`, a step written
    as a flow mapping, `indent4`, a steps list indented four spaces, or `dash`, a step whose first line is its `uses:`.
    `before` is the text of the steps above the pin. Returns (rc, output, {label: sha})."""
    with scratch("shape") as d:
        cs = os.path.join(d, "claude-settings")
        shas = scratch_clone(cs)
        item = {"flow": "      - {uses: o/claude-settings/actions/ste-lint@%s}\n",
                "indent4": "    - uses: o/claude-settings/actions/ste-lint@%s # main\n",
                "dash": "      - uses: o/claude-settings/actions/ste-lint@%s # main\n"}[shape]
        wf = "on: pull_request\njobs:\n  l:\n    steps:\n" + before + item % shas[pin]
        rc, out = run_ste_changed(os.path.join(cs, "bin", "ste-changed"),
                                  make_repo(d, {**BASE_FILES, ".github/workflows/ci.yml": wf}, lambda work: None))
        return rc, out, shas


for shape in ("flow", "indent4"):
    rc, out, shas = pin_shape_case(shape)
    check("pin shape %s: an older ste-lint pin in this shape is found and drifts, exit 3" % shape,
          rc == 3 and "CI pins ste-lint at %s" % shas["A"][:7] in out, out)

# A pin on the first line of the step after a `run:` block. The blank line after the block is no part of the block, so
# the pin's own line is read. A reader that counts that blank line as the block's body skips the pin and exits 0.
for header in ("|", ">"):
    rc, out, shas = pin_shape_case("dash", before="      - name: build\n        run: %s\n          make\n\n" % header)
    check("pin after a `run: %s` block: the pin on the step's first line is found and drifts, exit 3" % header,
          rc == 3 and "CI pins ste-lint at %s" % shas["A"][:7] in out and ".github/workflows/ci.yml:9" in out, out)
rc, out, shas = pin_shape_case("dash", before="      - name: build\n        run: make\n\n")  # control: a one-line run
check("pin after a one-line run: the same pin is found and drifts at ci.yml:8, exit 3 (control)",
      rc == 3 and "CI pins ste-lint at %s" % shas["A"][:7] in out and ".github/workflows/ci.yml:8" in out, out)

sys.exit(1 if failed else 0)
