#!/usr/bin/env python3
"""Fixture suite for lint/_test_git.py, the one home of the test-run commit-signing opt-out.

Run: python3 lint/test_test_git.py
Roadmap step test-runs-skip-signing: test fixtures never call the commit-signing service.
Incident: parallel test fixtures that commit exhausted the cloud signing service. The global config here
sets commit.gpgsign=true, gpg.format=ssh and gpg.ssh.program=/tmp/code-sign. Importing _test_git (or
sourcing _test_git.sh, or importing _test_git.mjs) appends commit.gpgsign=false and tag.gpgsign=false to
the git config that children read, so a test commit or tag never reaches the signer.

Every case runs git with a stub signer that appends a line to a log and exits 1. A commit or tag that
calls the stub fails and leaves a log line, so the log is the signal. Every case builds its own fixture
under the run folder (lint/_test_temp.py). Every import runs in a child process, never in this test
process, so this process's os.environ stays clean and the child proves that the change reaches the
children it starts.
"""
import json, os, re, shutil, subprocess, sys, tempfile, time, unittest, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _test_temp  # noqa: E402  test-temp-standard: the run folder's one home (lint/_test_temp.py)

TWIN_SH = os.path.join(HERE, "_test_git.sh")
TWIN_MJS = os.path.join(HERE, "_test_git.mjs")
RUN = None

GIT_CONFIG_KEY = re.compile(r"GIT_CONFIG_(COUNT|KEY_\d+|VALUE_\d+)$")
SHED = ("GIT_CONFIG_PARAMETERS", "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")
SIGNING_CONFIG = """[user]
\tname = t
\temail = t@t
\tsigningkey = {key}
[commit]
\tgpgsign = true
[tag]
\tgpgsign = true
[gpg]
\tformat = ssh
[gpg "ssh"]
\tprogram = {stub}
"""
STUB = '#!/bin/sh\necho "signer called" >> "$SIGNER_LOG"\nexit 1\n'

COMMIT_AND_TAG = r'''
import subprocess, sys
sys.path.insert(0, sys.argv[1])
import _test_git  # noqa: F401  the opt-out under test: appends to os.environ
repo = sys.argv[2]
for args in (["init", "-q", "-b", "main", "."], ["commit", "-q", "--allow-empty", "-m", "first"],
             ["tag", "-a", "v1", "-m", "release"]):
    subprocess.run(["git", *args], cwd=repo, check=True)
'''

APPEND_REPORT = r'''
import json, os, re, sys
sys.path.insert(0, sys.argv[1])
import _test_git  # noqa: F401  the import under test, in a fresh process
seen = {k: v for k, v in os.environ.items() if re.match(r"GIT_CONFIG_(COUNT|KEY_\d+|VALUE_\d+)$", k)}
d = {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "user.useConfigOnly", "GIT_CONFIG_VALUE_0": "true"}
out = _test_git.apply(d)
again = _test_git.apply(dict(out))
print(json.dumps({"environ": seen, "same_dict": out is d, "applied": out, "applied_again": again}))
'''

CLONE_AND_COMMIT = r'''
import subprocess, sys
sys.path.insert(0, sys.argv[1])
import _test_git  # noqa: F401  the opt-out under test: appends to os.environ
origin, work = sys.argv[2], sys.argv[3]
subprocess.run(["git", "clone", "-q", origin, work], check=True)
subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "clone"], cwd=work, check=True)
'''


def setUpModule():
    global RUN
    RUN = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN, ignore_errors=True)


def base_env():
    """os.environ without any git config the helper sets, so a case starts with no opt-out."""
    return {k: v for k, v in os.environ.items() if not GIT_CONFIG_KEY.match(k) and k not in SHED}


def signing_env(case):
    """One case's fixture in `case`: a git config that signs commits and tags, a key file, and a stub
    signer that logs each call and fails. Returns (env, log). Each case gets its own folder and log."""
    key = os.path.join(case, "key")
    stub = os.path.join(case, "signer.sh")
    cfg = os.path.join(case, "gitconfig")
    log = os.path.join(case, "signer.log")
    with open(key, "w") as f:
        f.write("not a real key\n")
    with open(stub, "w") as f:
        f.write(STUB)
    os.chmod(stub, 0o755)
    with open(cfg, "w") as f:
        f.write(SIGNING_CONFIG.format(key=key.replace("\\", "/"), stub=stub.replace("\\", "/")))
    env = base_env()
    env.update(GIT_CONFIG_GLOBAL=cfg, GIT_CONFIG_NOSYSTEM="1", SIGNER_LOG=log, GIT_AUTHOR_NAME="t",
               GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    return env, log


def signer_log(log):
    try:
        with open(log) as f:
            return f.read()
    except FileNotFoundError:
        return ""


def git(env, cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=120)


def run_py(env, cwd, code, *args):
    return subprocess.run([sys.executable, "-c", code, HERE, *args], cwd=cwd, env=env,
                          capture_output=True, text=True, timeout=120)


def config_of(env):
    return {k: v for k, v in env.items() if GIT_CONFIG_KEY.match(k)}


class SigningOptOut(unittest.TestCase):
    def setUp(self):
        self.case = tempfile.mkdtemp(prefix="case-", dir=RUN)

    def new_repo(self, env):
        repo = os.path.join(self.case, "repo")
        os.makedirs(repo)
        r = git(env, repo, "init", "-q", "-b", "main", ".")
        self.assertEqual(r.returncode, 0, r.stderr)
        return repo

    def test_python_child_commit_and_annotated_tag_do_not_sign(self):
        env, log = signing_env(self.case)
        repo = os.path.join(self.case, "repo")
        os.makedirs(repo)
        r = run_py(env, repo, COMMIT_AND_TAG, repo)
        self.assertEqual(r.returncode, 0, "child failed:\n" + r.stderr)
        self.assertEqual(signer_log(log), "", "the signer was called")
        self.assertIn("v1", git(env, repo, "tag", "--list").stdout)

    def test_positive_control_without_the_helper_the_signer_is_called(self):
        env, log = signing_env(self.case)
        repo = self.new_repo(env)
        r = git(env, repo, "commit", "-q", "--allow-empty", "-m", "unsigned?")
        self.assertNotEqual(r.returncode, 0, "a commit without the helper must reach the signer and fail")
        self.assertNotEqual(signer_log(log), "", "the signer was never called without the helper")
        os.remove(log)
        git(env, repo, "-c", "commit.gpgsign=false", "commit", "-q", "--allow-empty", "-m", "seed")
        git(env, repo, "tag", "-a", "v1", "-m", "release")  # git 2.43 exits 0 when the signer fails, so the log is the signal
        self.assertNotEqual(signer_log(log), "", "the signer was never called for the tag without the helper")

    def test_import_appends_to_a_preset_count_and_a_second_import_adds_nothing(self):
        env, _ = signing_env(self.case)
        env.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="user.useConfigOnly", GIT_CONFIG_VALUE_0="true")
        first = run_py(env, self.case, APPEND_REPORT)
        self.assertEqual(first.returncode, 0, "first import failed:\n" + first.stderr)
        report = json.loads(first.stdout.strip().splitlines()[-1])
        cfg = report["environ"]
        self.assertEqual(cfg.get("GIT_CONFIG_COUNT"), "3", cfg)
        self.assertEqual((cfg.get("GIT_CONFIG_KEY_0"), cfg.get("GIT_CONFIG_VALUE_0")),
                         ("user.useConfigOnly", "true"), "the preset key 0 was not kept")
        self.assertEqual({(cfg.get("GIT_CONFIG_KEY_1"), cfg.get("GIT_CONFIG_VALUE_1")),
                          (cfg.get("GIT_CONFIG_KEY_2"), cfg.get("GIT_CONFIG_VALUE_2"))},
                         {("commit.gpgsign", "false"), ("tag.gpgsign", "false")})
        self.assertNotIn("GIT_CONFIG_KEY_3", cfg)
        self.assertTrue(report["same_dict"], "apply() must return the dict it was given")
        self.assertEqual(report["applied"].get("GIT_CONFIG_COUNT"), "3", report["applied"])
        self.assertEqual(report["applied_again"], report["applied"], "a second apply() added keys")

        env2 = {k: v for k, v in env.items() if not GIT_CONFIG_KEY.match(k)}
        env2.update(cfg)
        second = run_py(env2, self.case, APPEND_REPORT)
        self.assertEqual(second.returncode, 0, "second import failed:\n" + second.stderr)
        self.assertEqual(config_of(json.loads(second.stdout.strip().splitlines()[-1])["environ"]), config_of(cfg),
                         "a second import in a new process added keys")

    def test_a_repo_cloned_after_the_import_does_not_sign_its_commit(self):
        env, log = signing_env(self.case)
        seed = self.new_repo(env)
        git(env, seed, "-c", "commit.gpgsign=false", "commit", "-q", "--allow-empty", "-m", "seed")
        origin = os.path.join(self.case, "origin.git")
        git(env, self.case, "init", "-q", "--bare", origin)
        git(env, seed, "push", "-q", origin, "main")
        work = os.path.join(self.case, "work")
        r = run_py(env, self.case, CLONE_AND_COMMIT, origin, work)
        self.assertEqual(r.returncode, 0, "child failed:\n" + r.stderr)
        self.assertEqual(signer_log(log), "", "the signer was called for the clone's commit")

    def test_shell_twin_sourced_commit_does_not_sign(self):
        env, log = signing_env(self.case)
        repo = self.new_repo(env)
        script = 'set -e; source "$1"; git commit -q --allow-empty -m shell; git tag -a v1 -m shell'
        r = subprocess.run(["bash", "-c", script, "bash", TWIN_SH], cwd=repo, env=env,
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, "sourcing lint/_test_git.sh failed:\n" + r.stderr)
        self.assertEqual(signer_log(log), "", "the signer was called from the sourced shell twin")

    @unittest.skipUnless(shutil.which("node"), "node is not on PATH: the JS twin case is skipped")
    def test_js_twin_imported_commit_does_not_sign(self):
        env, log = signing_env(self.case)
        repo = self.new_repo(env)
        code = ("const { execFileSync } = await import('node:child_process');\n"
                "const { pathToFileURL } = await import('node:url');\n"
                "await import(pathToFileURL(%s).href);\n"
                "execFileSync('git', ['commit', '-q', '--allow-empty', '-m', 'js'], { cwd: %s, stdio: 'inherit' });\n"
                "execFileSync('git', ['tag', '-a', 'v1', '-m', 'js'], { cwd: %s, stdio: 'inherit' });\n"
                % (json.dumps(TWIN_MJS), json.dumps(repo), json.dumps(repo)))
        r = subprocess.run([shutil.which("node"), "--input-type=module", "-e", code], cwd=repo, env=env,
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, "importing lint/_test_git.mjs failed:\n" + r.stderr)
        self.assertEqual(signer_log(log), "", "the signer was called from the imported JS twin")


class RunFolderSweep(unittest.TestCase):
    def test_a_new_run_removes_old_sibling_run_folders_and_keeps_new_ones(self):
        root = tempfile.mkdtemp(prefix="sweep-", dir=RUN)
        old = os.path.join(root, "%d-%s" % (os.getpid() + 1, uuid.uuid4().hex))
        new = os.path.join(root, "%d-%s" % (os.getpid() + 2, uuid.uuid4().hex))
        for path, age in ((old, 2 * 24 * 60 * 60), (new, 60)):
            os.makedirs(path)
            stamp = time.time() - age
            os.utime(path, (stamp, stamp))
        own = _test_temp.run_folder(temp_root=root)
        self.assertFalse(os.path.exists(old), "an old sibling run folder survived the sweep")
        self.assertTrue(os.path.isdir(new), "a new sibling run folder was removed by the sweep")
        self.assertTrue(os.path.isdir(own), "the run's own folder is missing")


if __name__ == "__main__":
    unittest.main()
