#!/usr/bin/env python3
"""Cases for hooks/session_tier.py: the grant CLI, the bind of a grant to a session, and the proof of a bound file.

Standard library only, and no test runner. The guard-level cases of the same rule (roadmap-one-writer, section 5e-3)
are in hooks/test_guard.py.

Run it from the repository root:

    python3 hooks/test_session_tier.py

Contract the builder codes against. The spec names the file formats and the CLI, and it names no Python API, so the
names below are chosen here and the module keeps them:

    tier_dir() -> str                              ${CLAUDE_CONFIG_DIR:-~/.claude}/session-tiers, read at call time
    norm_folder(path) -> str                       the folder key (hooks/tier_fixture_test.py norm_key); on Windows
                                                   a Git Bash /c/ path reads as its drive path
    grant_path(folder) -> str                      the grant file for the folder
    bound_path(session_id) -> str                  the bound file for the session
    bind_grant(session_id, agent_id, cwd) -> bool  True when this call bound a grant to the session. The cwd's
                                                   folder key must equal the grant's: no parent or child walk
    file_proved(session_id, agent_id) -> bool      True when the session's bound file proves the triage tier
    GRANT_TTL_SECONDS = 3600
    CLI: python3 hooks/session_tier.py grant triage --folder <path>
         exit 0 and the grant path printed; exit 2 and nothing written for an unknown tier, a missing --folder,
         or a folder that does not exist.

A missing name, or an exception raised by a call, is a failure of the case that needs it, with the name in the
message. It never stops the run.
"""
import contextlib
import importlib
import json
import os
import shutil
import subprocess
import sys
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lint"))
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
import tier_fixture_test as fx  # noqa: E402  the tier-file fixtures and folder key, shared with test_guard.py
from case_runner_test import run_cases  # noqa: E402  the shared case runner (hooks/case_runner_test.py)

CLI = os.path.join(HERE, "session_tier.py")
AGENT_ID = "a64a7f84210a8721d"
ROOT = _test_temp.run_folder()
# The module may read CLAUDE_CONFIG_DIR when it is imported. The import sees a sentinel under this run's folder,
# so no case reads the real ~/.claude, and config_dir() reloads the module for each case's own folder.
os.environ["CLAUDE_CONFIG_DIR"] = os.path.join(ROOT, "import-sentinel")

try:
    import session_tier as tier  # noqa: E402
except Exception:  # not built yet: each case fails on the name it needs (see call)
    tier = None


def fresh(name):
    """An empty config dir for one case, under this run's folder."""
    path = os.path.join(ROOT, "cfg", name)
    os.makedirs(path, exist_ok=True)
    return path


def folder_of(name):
    """A folder for one case, under this run's folder. It exists."""
    path = os.path.join(ROOT, "folders", name)
    os.makedirs(path, exist_ok=True)
    return path


@contextlib.contextmanager
def config_dir(path):
    """CLAUDE_CONFIG_DIR set to `path` for the block, then restored. The module is reloaded under it, so a constant
    the module reads at import sees this folder too."""
    prior = os.environ.get("CLAUDE_CONFIG_DIR")
    os.environ["CLAUDE_CONFIG_DIR"] = path
    if tier is not None:
        importlib.reload(tier)
    try:
        yield
    finally:
        if prior is None:
            os.environ.pop("CLAUDE_CONFIG_DIR", None)
        else:
            os.environ["CLAUDE_CONFIG_DIR"] = prior


def call(name, *args):
    """(True, value) from session_tier.<name>(*args), or (False, why): a missing name, or a raise, is a named failure."""
    fn = getattr(tier, name, None) if tier is not None else None
    if fn is None:
        return False, "session_tier.%s is not defined" % name
    try:
        return True, fn(*args)
    except Exception as exc:  # a bind or a proof never raises into its caller (the guard's rule)
        return False, "session_tier.%s raised %s: %s" % (name, type(exc).__name__, exc)


def run_cli(config, args):
    """(exit code, stdout, stderr) of the grant CLI, run with this config dir."""
    env = dict(os.environ)
    env["CLAUDE_CONFIG_DIR"] = config
    result = subprocess.run([sys.executable, CLI] + args, capture_output=True, text=True, env=env, timeout=60)
    return result.returncode, result.stdout, result.stderr


def read_json(path):
    with open(path, "rb") as handle:
        return json.loads(handle.read().decode("utf-8-sig").strip())


def tier_body_problems(path, folder):
    """The problems with a grant or bound file's three fields, for the folder it names."""
    if not os.path.isfile(path):
        return ["no file at %s" % os.path.basename(path)]
    body = read_json(path)
    problems = []
    if body.get("tier") != "triage":
        problems.append("the file's tier is %r, want 'triage'" % body.get("tier"))
    if body.get("folder") != fx.norm_key(folder):
        problems.append("the file's folder is not the folder key")
    at = body.get("at")
    if not isinstance(at, int) or isinstance(at, bool):
        problems.append("the file's time is %r, want an integer" % (at,))
    return problems


def tier_dir_is_empty(config):
    return not os.path.isdir(fx.tier_dir(config)) or not os.listdir(fx.tier_dir(config))


# ---- the grant CLI: `grant triage --folder <path>`

def case_grant_writes_grant_file():
    """grant triage --folder writes the grant at the spec's name, with the tier, the folder key, and an integer time"""
    config = fresh("grant-writes")
    folder = folder_of("grant-writes")
    code, out, err = run_cli(config, ["grant", "triage", "--folder", folder])
    if code != 0:
        return ["grant triage --folder: exit %d, want 0 (%s)" % (code, err.strip()[:120])]
    path = fx.grant_file(config, folder)
    problems = tier_body_problems(path, folder)
    if os.path.isfile(path) and os.path.basename(path) not in out:
        problems.append("grant triage --folder did not print the grant path")
    return problems


def case_grant_leaves_only_the_grant_file():
    """grant writes through a temp file and a rename, so the tier dir holds only the grant file after one write"""
    config = fresh("grant-atomic")
    folder = folder_of("grant-atomic")
    code, _out, err = run_cli(config, ["grant", "triage", "--folder", folder])
    if code != 0:
        return ["grant triage --folder: exit %d, want 0 (%s)" % (code, err.strip()[:120])]
    names = sorted(os.listdir(fx.tier_dir(config)))
    if names != [os.path.basename(fx.grant_file(config, folder))]:
        return ["the tier dir holds %s after one grant, want only the grant file" % names]
    return []


def case_regrant_replaces_the_grant():
    """a second grant for the same folder replaces the first: one grant file, still the triage tier"""
    config = fresh("grant-regrant")
    folder = folder_of("grant-regrant")
    for _ in range(2):
        code, _out, err = run_cli(config, ["grant", "triage", "--folder", folder])
        if code != 0:
            return ["grant triage --folder: exit %d, want 0 (%s)" % (code, err.strip()[:120])]
    names = os.listdir(fx.tier_dir(config))
    if len(names) != 1:
        return ["two grants for one folder left %d files, want one" % len(names)]
    return tier_body_problems(fx.grant_file(config, folder), folder)


def grant_refused(label, args, config):
    """Run `args`, a grant the CLI must refuse, after a control grant that must succeed. Returns the problems."""
    control = fresh(label + "-control")
    control_folder = folder_of(label + "-control")
    code, _out, err = run_cli(control, ["grant", "triage", "--folder", control_folder])
    problems = []
    if code != 0:
        problems.append("control: grant triage --folder exit %d, want 0 (%s)" % (code, err.strip()[:120]))
    code, _out, _err = run_cli(config, args)
    if code != 2:
        problems.append("%s: exit %d, want 2" % (label, code))
    if not tier_dir_is_empty(config):
        problems.append("%s wrote a file into the tier dir" % label)
    return problems


def case_grant_unknown_tier_refused():
    """grant with an unknown tier exits 2 and writes nothing"""
    config = fresh("grant-unknown-tier")
    folder = folder_of("grant-unknown-tier")
    return grant_refused("grant lane", ["grant", "lane", "--folder", folder], config)


def case_grant_without_folder_refused():
    """grant with no --folder exits 2 and writes nothing"""
    return grant_refused("grant triage with no --folder", ["grant", "triage"], fresh("grant-no-folder"))


def case_grant_missing_folder_refused():
    """grant for a folder that does not exist exits 2 and writes nothing"""
    config = fresh("grant-missing-folder")
    missing = os.path.join(ROOT, "folders", "no-such-folder")
    return grant_refused("grant triage for a folder that does not exist", ["grant", "triage", "--folder", missing],
                         config)


# ---- the bind: a grant becomes its session's tier on the session's first top-level call

def case_bind_fresh_grant_binds_once():
    """bind_grant: a fresh grant binds the session, writes its bound file, and is removed"""
    config = fresh("bind-fresh")
    folder = folder_of("bind-fresh")
    fx.write_grant(config, folder, age=fx.FRESH_AGE)
    with config_dir(config):
        ok, bound = call("bind_grant", "tier-bind-fresh", None, folder)
    if not ok:
        return [bound]
    problems = []
    if not bound:
        problems.append("bind_grant returned %r for a fresh grant, want True" % (bound,))
    problems += ["bound file: " + p for p in tier_body_problems(fx.bound_file(config, "tier-bind-fresh"), folder)]
    if os.path.exists(fx.grant_file(config, folder)):
        problems.append("the grant was kept after it bound, want it consumed")
    return problems


def case_bind_agent_call_binds_nothing():
    """bind_grant with an agent id binds nothing and keeps the grant"""
    config = fresh("bind-agent")
    folder = folder_of("bind-agent")
    fx.write_grant(config, folder, age=fx.FRESH_AGE)
    with config_dir(config):
        ok, bound = call("bind_grant", "tier-bind-agent", AGENT_ID, folder)
    if not ok:
        return [bound]
    problems = []
    if bound:
        problems.append("bind_grant bound a grant for an agent call")
    if os.path.exists(fx.bound_file(config, "tier-bind-agent")):
        problems.append("an agent call wrote a bound file")
    if not os.path.isfile(fx.grant_file(config, folder)):
        problems.append("an agent call consumed the grant")
    return problems


def case_bind_without_a_session_id_binds_nothing():
    """bind_grant with no session id, an empty one, or one with a path separator binds nothing and writes nothing"""
    config = fresh("bind-no-session")
    folder = folder_of("bind-no-session")
    problems = []
    for session in (None, "", "../tier-escape"):
        fx.write_grant(config, folder, age=fx.FRESH_AGE)
        with config_dir(config):
            ok, bound = call("bind_grant", session, None, folder)
        if not ok:
            return [bound]
        if bound:
            problems.append("bind_grant bound a grant for session id %r" % (session,))
    if os.path.exists(os.path.join(config, "tier-escape.json")) or os.path.exists(
            os.path.join(fx.tier_dir(config), "..", "tier-escape.json")):
        problems.append("a session id with a path separator wrote a file outside the tier dir")
    return problems


def case_bind_stale_grant_is_deleted_and_binds_nothing():
    """bind_grant: a grant older than the hour binds nothing, and is deleted"""
    config = fresh("bind-stale")
    folder = folder_of("bind-stale")
    fx.write_grant(config, folder, age=fx.STALE_AGE)
    with config_dir(config):
        ok, bound = call("bind_grant", "tier-bind-stale", None, folder)
    if not ok:
        return [bound]
    problems = []
    if bound:
        problems.append("bind_grant bound a stale grant")
    if os.path.exists(fx.bound_file(config, "tier-bind-stale")):
        problems.append("a stale grant wrote a bound file")
    if os.path.exists(fx.grant_file(config, folder)):
        problems.append("the stale grant was kept, want it deleted")
    return problems


def case_bind_sibling_with_a_shared_prefix_binds_nothing():
    """bind_grant: a cwd whose folder name only starts with the granted name's binds nothing"""
    config = fresh("bind-prefix")
    folder = folder_of("bind-prefix")
    sibling = folder_of("bind-prefix-sibling")
    fx.write_grant(config, folder, age=fx.FRESH_AGE)
    with config_dir(config):
        ok, bound = call("bind_grant", "tier-bind-prefix", None, sibling)
    if not ok:
        return [bound]
    problems = []
    if bound:
        problems.append("a sibling folder that starts with the granted name bound the grant")
    if not os.path.isfile(fx.grant_file(config, folder)):
        problems.append("a sibling folder consumed the grant")
    return problems


def case_bind_parent_of_the_grant_binds_nothing():
    """bind_grant: a cwd above the granted folder binds nothing"""
    config = fresh("bind-parent")
    folder = folder_of("bind-parent-child")
    parent = os.path.dirname(folder)
    fx.write_grant(config, folder, age=fx.FRESH_AGE)
    with config_dir(config):
        ok, bound = call("bind_grant", "tier-bind-parent", None, parent)
    if not ok:
        return [bound]
    if bound:
        return ["a cwd above the granted folder bound the grant"]
    return []


def case_bind_subfolder_of_the_grant_binds_nothing():
    """bind_grant: a cwd in a subfolder of the granted folder binds nothing; the grant is for the exact folder only"""
    config = fresh("bind-subfolder")
    folder = folder_of("bind-subfolder")
    inside = folder_of(os.path.join("bind-subfolder", "inside"))
    fx.write_grant(config, folder, age=fx.FRESH_AGE)
    with config_dir(config):
        ok, bound = call("bind_grant", "tier-bind-subfolder", None, inside)
    if not ok:
        return [bound]
    problems = []
    if bound:
        problems.append("a subfolder of the granted folder bound the grant, want the exact folder only")
    if not os.path.isfile(fx.grant_file(config, folder)):
        problems.append("a subfolder of the granted folder consumed the grant")
    return problems


def case_bind_corrupt_grant_binds_nothing_and_does_not_raise():
    """bind_grant: a corrupt grant file binds nothing, and the call returns instead of raising"""
    config = fresh("bind-corrupt")
    folder = folder_of("bind-corrupt")
    fx.write_file(fx.grant_file(config, folder), b"{ not json")
    with config_dir(config):
        ok, bound = call("bind_grant", "tier-bind-corrupt", None, folder)
    if not ok:
        return [bound]
    if bound:
        return ["bind_grant bound a corrupt grant"]
    return []


def case_bind_crlf_grant_with_bom_binds():
    """bind_grant: a grant in CRLF lines with a BOM binds the session, as a plain grant does"""
    config = fresh("bind-crlf")
    folder = folder_of("bind-crlf")
    fx.write_grant(config, folder, age=fx.FRESH_AGE, crlf_bom=True)
    with config_dir(config):
        ok, bound = call("bind_grant", "tier-bind-crlf", None, folder)
    if not ok:
        return [bound]
    if not bound:
        return ["bind_grant did not bind a CRLF and BOM grant"]
    return []


def case_bind_blocked_tier_dir_binds_nothing_and_does_not_raise():
    """bind_grant: a tier dir that cannot be made (a file holds its name) binds nothing, and the call returns"""
    config = fresh("bind-blocked")
    folder = folder_of("bind-blocked")
    os.makedirs(config, exist_ok=True)
    with open(fx.tier_dir(config), "w", encoding="utf-8") as handle:
        handle.write("in the way\n")
    with config_dir(config):
        ok, bound = call("bind_grant", "tier-bind-blocked", None, folder)
    if not ok:
        return [bound]
    if bound:
        return ["bind_grant reported a bind with no tier dir to hold it"]
    return []


# ---- the folder key: the spec's rule for a grant's folder and a cwd

def case_norm_folder_ignores_a_trailing_separator():
    """norm_folder: a folder with and without a trailing separator is one key"""
    folder = folder_of("norm-trailing")
    ok, plain = call("norm_folder", folder)
    if not ok:
        return [plain]
    ok, slashed = call("norm_folder", folder + os.sep)
    if not ok:
        return [slashed]
    if plain != slashed:
        return ["a trailing separator changes the key: %r and %r" % (plain, slashed)]
    return []


def case_norm_folder_folds_case_only_on_windows():
    """norm_folder: two spellings that differ only in case are one key on Windows, and two keys on a POSIX system"""
    lower = os.path.join(ROOT, "norm-case-fold")
    upper = os.path.join(ROOT, "NORM-CASE-FOLD")
    ok, low_key = call("norm_folder", lower)
    if not ok:
        return [low_key]
    ok, up_key = call("norm_folder", upper)
    if not ok:
        return [up_key]
    same = low_key == up_key
    if os.name == "nt" and not same:
        return ["on Windows the two cases give two keys: %r and %r" % (low_key, up_key)]
    if os.name != "nt" and same:
        return ["on a POSIX system the two cases give one key, %r" % (low_key,)]
    return []


def case_norm_folder_reads_a_git_bash_path_on_windows():
    """norm_folder: on Windows a Git Bash /c/ path keys as its drive path; on a POSIX system it is an ordinary path"""
    ok, bash_key = call("norm_folder", "/c/Users/tier-user/proj")
    if not ok:
        return [bash_key]
    if os.name == "nt":
        ok, drive_key = call("norm_folder", "C:\\Users\\tier-user\\proj")
        if not ok:
            return [drive_key]
        if bash_key != drive_key:
            return ["the Git Bash path keys as %r, the drive path as %r" % (bash_key, drive_key)]
        return []
    if bash_key != fx.norm_key("/c/Users/tier-user/proj"):
        return ["on a POSIX system the /c/ path keys as %r, want its own real path" % (bash_key,)]
    return []


# ---- the proof: a bound file proves the triage tier to the push check

def proof_problems(label, write, want):
    """Write a bound file with `write`, then ask whether it proves the session. Returns the problems."""
    config = fresh("proof-" + label)
    session = "tier-proof-" + label
    write(config, session)
    with config_dir(config):
        ok, proved = call("file_proved", session, None)
    if not ok:
        return [proved]
    if bool(proved) != want:
        return ["file_proved returned %r, want %r" % (bool(proved), want)]
    return []


def case_proof_bound_triage_proves_its_session():
    """file_proved: a bound triage file proves its own session"""
    return proof_problems("triage", lambda c, s: fx.write_bound(c, s, folder_of("proof-triage")), True)


def case_proof_crlf_bom_bound_file_proves():
    """file_proved: a bound triage file in CRLF lines with a BOM proves its session"""
    return proof_problems("crlf", lambda c, s: fx.write_bound(c, s, folder_of("proof-crlf"), crlf_bom=True), True)


def case_proof_lane_tier_does_not_prove():
    """file_proved: a bound file whose tier is lane proves nothing"""
    return proof_problems("lane", lambda c, s: fx.write_bound(c, s, folder_of("proof-lane"), tier="lane"), False)


def case_proof_corrupt_file_does_not_prove_and_does_not_raise():
    """file_proved: a corrupt bound file proves nothing, and the call returns instead of raising"""
    return proof_problems("corrupt", lambda c, s: fx.write_file(fx.bound_file(c, s), b"{ not json"), False)


def case_proof_no_file_does_not_prove():
    """file_proved: a session with no bound file, such as a new session after an ended one, proves nothing"""
    return proof_problems("none", lambda c, s: None, False)


def case_proof_another_sessions_file_does_not_prove():
    """file_proved: a bound file names one session id, so another session's file proves nothing here"""
    return proof_problems("other",
                          lambda c, s: fx.write_bound(c, "tier-proof-someone-else", folder_of("proof-other")), False)


def case_proof_agent_call_is_never_proved():
    """file_proved: an agent call is never proved, even by a bound triage file of its session"""
    config = fresh("proof-agent")
    session = "tier-proof-agent"
    fx.write_bound(config, session, folder_of("proof-agent"))
    with config_dir(config):
        ok, proved = call("file_proved", session, AGENT_ID)
    if not ok:
        return [proved]
    if bool(proved):
        return ["file_proved returned True for an agent call"]
    return []


# ---- the run folder: this suite's temp files follow the standard (lint/_test_temp.py)

def case_run_folder_sweep_removes_old_and_keeps_new():
    """the run-folder sweep removes a sibling run folder over a day old, keeps a newer one, and makes its own"""
    temp_root = os.path.join(ROOT, "sweep-root")
    os.makedirs(temp_root, exist_ok=True)
    old = os.path.join(temp_root, "1-" + uuid.uuid4().hex)
    new = os.path.join(temp_root, "2-" + uuid.uuid4().hex)
    os.makedirs(old)
    os.makedirs(new)
    two_days_ago = time.time() - 2 * 24 * 60 * 60
    os.utime(old, (two_days_ago, two_days_ago))
    own = _test_temp.run_folder(temp_root=temp_root)
    problems = []
    if os.path.exists(old):
        problems.append("the sweep kept a sibling run folder older than a day")
    if not os.path.isdir(new):
        problems.append("the sweep removed a sibling run folder newer than a day")
    if not os.path.isdir(own):
        problems.append("run_folder made no run folder of its own")
    return problems


CASES = [
    case_grant_writes_grant_file,
    case_grant_leaves_only_the_grant_file,
    case_regrant_replaces_the_grant,
    case_grant_unknown_tier_refused,
    case_grant_without_folder_refused,
    case_grant_missing_folder_refused,
    case_bind_fresh_grant_binds_once,
    case_bind_agent_call_binds_nothing,
    case_bind_without_a_session_id_binds_nothing,
    case_bind_stale_grant_is_deleted_and_binds_nothing,
    case_bind_sibling_with_a_shared_prefix_binds_nothing,
    case_bind_parent_of_the_grant_binds_nothing,
    case_bind_subfolder_of_the_grant_binds_nothing,
    case_bind_corrupt_grant_binds_nothing_and_does_not_raise,
    case_bind_crlf_grant_with_bom_binds,
    case_bind_blocked_tier_dir_binds_nothing_and_does_not_raise,
    case_norm_folder_ignores_a_trailing_separator,
    case_norm_folder_folds_case_only_on_windows,
    case_norm_folder_reads_a_git_bash_path_on_windows,
    case_proof_bound_triage_proves_its_session,
    case_proof_crlf_bom_bound_file_proves,
    case_proof_lane_tier_does_not_prove,
    case_proof_corrupt_file_does_not_prove_and_does_not_raise,
    case_proof_no_file_does_not_prove,
    case_proof_another_sessions_file_does_not_prove,
    case_proof_agent_call_is_never_proved,
    case_run_folder_sweep_removes_old_and_keeps_new,
]


if __name__ == "__main__":
    try:
        rc = run_cases(CASES)
    finally:
        shutil.rmtree(ROOT, ignore_errors=True)
    sys.exit(rc)
