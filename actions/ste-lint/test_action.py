"""Runs the ste-lint step script on a fixture repo. `python3 actions/ste-lint/test_action.py`.
Asserts the failing finding reaches the job log and the ::error annotation, both exit codes,
that an advisory finding is a ::warning that never fails the step, the changed-lines scope, the diff range, the exclude split, and annotation escaping.
Also asserts bin/ste-changed matches the step on the same diff: scope, findings, verdict, exit code.
Excludes are the target repo's own .ste-lint-exclude plus the action's `exclude` input, never this repo's file.
Also asserts the file's last line counts with no final newline, '**' matches at the root, and a run from a subdirectory.
Also asserts a planted json.py, json/ package or ste_emit.py in the linted repo never runs on import, and the summary still prints.
Also asserts the command's pin check: a CI pin whose lint differs exits 3 and names the pin and the remedy,
an unrelated commit is no drift, an unknown pin changes no exit code, and LINT_FILES holds every file the step runs.
Also asserts the installed copy: install.sh run into a temp HOME, in cloud (copy) mode and in local (symlink) mode, lands
bin/ste-changed where its own folder holds no actions/. The command still finds the claude-settings checkout the global
CLAUDE.md names, reads the pin check from it, and with no checkout prints one line, never a traceback."""
import ast, atexit, contextlib, os, re, shutil, subprocess, sys, tempfile, time, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
CMD = os.path.join(ROOT, "bin", "ste-changed")
EXCLUDE_FILE = os.path.join(ROOT, ".ste-lint-exclude")
EXCLUDE_TEXT = open(EXCLUDE_FILE, encoding="utf-8").read()  # run_pair writes this as the target's file
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
            "EXCLUDE", "CHANGED_PATHS_GLOB", "DECISIONS_DIR", "STE_EXCLUDE_FILE")
FINDING = re.compile(r"^\S.*:\d+: [A-Z]+\d+ ")

# Test temp files (decision test-temp-standard): one run folder for this run, from the repo's one helper.
# Every case below makes its folder inside it, and the run folder is removed at exit.
sys.path.append(os.path.join(ROOT, "lint"))
sys.path.append(os.path.join(ROOT, "testing"))
import _test_temp  # noqa: E402
import tracked_tree  # noqa: E402  copies what git lists, so no case here lists files
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
    with tempfile.TemporaryDirectory() as d:
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
for name in ("lint/ste_lint.py", "lint/layout.py"):
    tree = ast.parse(open(os.path.join(ROOT, name), encoding="utf-8").read())
    mods = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    mods |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    local = sorted("lint/%s.py" % m for m in mods if os.path.exists(os.path.join(ROOT, "lint", m + ".py")))
    check("LINT_FILES holds every lint module %s imports" % name, set(local) <= set(LINT_FILES), str(local))
check("LINT_FILES holds the linter run.sh runs",
      "lint/ste_lint.py" in LINT_FILES and "../../lint/ste_lint.py" in open(os.path.join(HERE, "run.sh")).read(), "")


def head(cs):
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=cs, capture_output=True, text=True).stdout.strip()


def scratch_clone(cs):
    """A claude-settings clone at `cs`: the files bin/ste-changed and install.sh read, copied from what git lists here
    (tracked_tree), so the installed hooks hold every module the command may import. History: A, then C changes the
    lint, then D changes only README.md (HEAD, main and origin/main). E, off D on a side branch, changes the lint again.
    Returns {label: sha}."""
    tracked_tree.copy_tracked(cs, "bin", "hooks", "lint", "actions/ste-lint")
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
    git(cs, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(cs, "checkout", "-q", "-b", "side")
    write(cs, "lint/ste_lint.py", "\n# E\n", "a")
    git(cs, "commit", "-qam", "E")
    shas["E"] = head(cs)
    git(cs, "checkout", "-q", "main")
    return shas


def pin_child(d, shas, pin, change=lambda work: None, dead=None):
    """A child repo under `d` whose CI pins ste-lint at `pin`: a label of `shas`, or a sha. `dead` is a label
    that is pinned in a comment only. Returns its working folder."""
    wf = ("on: pull_request\njobs:\n  l:\n    steps:\n      - uses: o/claude-settings/actions/ste-lint@%s # main\n"
          % shas.get(pin, pin))
    if dead:
        wf += "      # - uses: o/claude-settings/actions/ste-lint@%s\n" % shas[dead]
    return make_repo(d, {**BASE_FILES, ".github/workflows/ci.yml": wf}, change)


def run_ste_changed(cmd, work, home=None):
    """`cmd main` in `work`, with the step's variables and CLAUDE_CONFIG_DIR stripped. `home` replaces HOME, so a
    command that reads ~/.claude reads the temp one. Returns (rc, output)."""
    env = {k: v for k, v in os.environ.items() if k not in STEP_ENV + ("CLAUDE_CONFIG_DIR",)}
    if home:
        env["HOME"] = home
    p = subprocess.run([sys.executable, cmd, "main"], cwd=work, env=env, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def pin_case(pin, change=lambda work: None, dead=None):
    """Run the scratch clone's command in a child repo whose CI pins ste-lint at `pin`. `pin` may name a
    commit label of the scratch clone. Returns (rc, output, {label: sha})."""
    with scratch("pin") as d:
        cs = os.path.join(d, "claude-settings")
        shas = scratch_clone(cs)
        rc, out = run_ste_changed(os.path.join(cs, "bin", "ste-changed"), pin_child(d, shas, pin, change, dead))
        return rc, out, shas


rc, out, shas = pin_case("A")
check("pin drift: an older pin's lint differs, so the command exits 3 though the lint passed",
      rc == 3 and "CI pins ste-lint at %s" % shas["A"][:7] in out and ".github/workflows/ci.yml:5" in out, out)
check("pin drift: the remedy names claude-settings main and the rule",
      "Move the pin to %s" % shas["D"] in out and "git-integration-branch-merge" in out, out)
rc, out, shas = pin_case("C")
check("no drift: a pin whose lint files equal this copy's exits 0, though README.md moved since",
      rc == 0 and "CI pins ste-lint at %s" % shas["C"][:7] in out and "the same lint as this copy" in out, out)
rc, out, shas = pin_case("C", dead="A")
check("a commented-out pin is not a pin: an old one in a comment changes nothing",
      rc == 0 and shas["A"][:7] not in out, out)
rc, out, shas = pin_case("E")
check("pin ahead: a pin this copy's history lacks exits 3 and says to pull claude-settings",
      rc == 3 and "pull claude-settings" in out, out)
rc, out, _ = pin_case("f" * 40)
check("unknown pin: a commit this clone does not hold is unknown and exits 0",
      rc == 0 and "Unknown whether it matches" in out, out)
rc, out, _ = pin_case("A", default_change)
check("lint red and drift: the lint's exit code wins, and the drift line still prints",
      rc == 1 and "older than this copy's lint" in out, out)


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
sys.exit(1 if failed else 0)
