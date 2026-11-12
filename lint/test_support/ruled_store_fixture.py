"""The one home of a ruled-store fixture: a git repo whose refs hold owner rulings. Test code, standard library only.

A store is the folder roadmap/rulings on origin/roadmap, one JSON file per ruling. The helpers here point refs
with git plumbing only (hash-object, update-index on a temp index, write-tree, commit-tree, update-ref), so no
checkout moves and no branch changes. lint/test_ruled_store.py, hooks/test_session_start.py and
hooks/test_question_form.py all build their stores here.

The caller owns the folder it passes as `scratch` for the temp index. Its run folder (lint/_test_temp.py)
is removed by the caller's teardown.
"""
import json
import os
import subprocess

VCS = "g" + "it"  # assembled, as hooks/test_session_start.py assembles its own git name
IDENT = ("-c", "user.name=test", "-c", "user.email=test@example.invalid")
STORE_REF = "refs/remotes/origin/roadmap"
MAIN_REF = "refs/remotes/origin/main"
RULINGS_DIR = "roadmap/rulings"
AT = "2026-11-12T14:15:00-06:00"
TEST_SUPERSEDES = [{"kind": "test", "ref": "lint/test_ruled_store.py::test_case"}]
# A git start must not read the outer repo: a hook or CI step may set these to point at its own checkout.
STRIPPED = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY", "GIT_NAMESPACE")
ENV = {key: value for key, value in os.environ.items() if key not in STRIPPED}


def git(repo, *args, text=None, env=None):
    """stdout of one git start in `repo`. A failure raises: a fixture that cannot be built is an error, not a case result."""
    answer = subprocess.run([VCS, "-C", repo, *IDENT, *args], input=text, capture_output=True, text=True,
                            env=env or ENV, timeout=60)
    if answer.returncode != 0:
        raise RuntimeError("fixture: %s %s failed: %s" % (VCS, " ".join(args), answer.stderr.strip()))
    return answer.stdout.strip()


def init_repo(path):
    """A new repo at `path`. The folder is made when it is missing."""
    os.makedirs(path, exist_ok=True)
    git(path, "init", "-q")
    return path


def point_ref(repo, ref, files, scratch):
    """Points `ref` at a new commit whose whole tree is `files` ({path: text}). Returns the commit's sha."""
    index = os.path.join(scratch, "index-" + ref.replace("/", "_"))
    if os.path.exists(index):
        os.remove(index)
    env = dict(ENV, GIT_INDEX_FILE=index)
    for path, text in sorted(files.items()):
        blob = git(repo, "hash-object", "-w", "--stdin", text=text, env=env)
        git(repo, "update-index", "--add", "--cacheinfo", "100644,%s,%s" % (blob, path), env=env)
    tree = git(repo, "write-tree", env=env)
    commit = git(repo, "commit-tree", tree, "-m", "fixture for " + ref, env=env)
    git(repo, "update-ref", ref, commit, env=env)
    return commit


def ruling_files(entries):
    """{path: text} for a store: each id maps to roadmap/rulings/<id>.json. A dict is written as JSON; a str is
    written as it is, which is how a case makes a malformed file."""
    return {"%s/%s.json" % (RULINGS_DIR, rid): body if isinstance(body, str) else json.dumps(body, indent=2)
            for rid, body in entries.items()}


def entry(rid, **over):
    """A valid ruling entry for `rid`: open, dated AT, with one test ref under supersedes. A key set to None is left out."""
    body = {"id": rid, "at": AT, "ruling": "Owner: keep the store to one place.",
            "quote": "keep it in one place", "source": "page item 1", "status": "open",
            "supersedes": [dict(ref) for ref in TEST_SUPERSEDES]}
    body.update(over)
    return {key: value for key, value in body.items() if value is not None}
