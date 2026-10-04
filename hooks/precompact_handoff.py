#!/usr/bin/env python3
"""Claude Code hook: rewrite the session handoff before compaction.

Spec: decisions/precompact-handoff.md. Two modes, one file:

  PreCompact (stdin: session_id, transcript_path, cwd) -- builds a digest of the
  transcript's user/assistant text, runs a sandboxed `claude -p` child that rewrites
  the handoff (and the plan, when named) in place, and records the outcome in
  ~/.claude/state/handoff/<session_id>.json.

  SessionStart --reorient (stdin: session_id) -- reads that state file and prints a
  short reorientation message into context.

Never exits 2 and never blocks compaction: every failure is caught, logged to stderr,
and the hook still exits 0 (case_failure_* in test_precompact_handoff.py).
"""
import datetime
import importlib.util
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROMPT_PATH = os.path.join(HERE, "precompact_handoff_prompt.md")
DIGEST_CAP = 150_000
CHILD_TIMEOUT = 240  # seconds; stays inside the hook's own 300s PreCompact timeout
CHILD_TOOLS = "Read,Write,Edit,Glob,Grep"
RECURSION_GUARD_ENV = "CLAUDE_HANDOFF_CHILD"


def _load_resolve_program():
    """Reuse merge/merge.py's resolve_program for Windows-safe lookup, if it loads.

    Looked up beside this file's own path and its symlink target, same two-candidate
    search guard.py's merge_module() uses, since an installed hook can be a symlink.
    """
    candidates = []
    for base in (os.path.dirname(os.path.abspath(__file__)),
                 os.path.dirname(os.path.realpath(__file__))):
        if base not in candidates:
            candidates.append(base)
    for base in candidates:
        path = os.path.join(base, "..", "merge", "merge.py")
        if not os.path.isfile(path):
            continue
        try:
            spec = importlib.util.spec_from_file_location("precompact_merge_tool", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module.resolve_program
        except Exception:
            continue
    return None


_resolve_program = _load_resolve_program()


def resolve_claude(env):
    """Full path to the `claude` program. Reuses merge.py's resolve_program when it
    loads; otherwise a plain shutil.which, which already walks PATHEXT on Windows."""
    if _resolve_program is not None:
        return _resolve_program("claude", env)
    return shutil.which("claude", path=env.get("PATH")) or "claude"


def config_dir():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(
        os.path.expanduser("~"), ".claude")


def state_path(session_id):
    return os.path.join(config_dir(), "state", "handoff", "%s.json" % session_id)


def build_digest(transcript_path, cap=DIGEST_CAP):
    """User and assistant text only, tool results and thinking dropped, last `cap`
    characters kept (the tail: newest text matters most, see decisions/precompact-
    handoff.md's "Known limits")."""
    parts = []
    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if entry.get("type") not in ("user", "assistant"):
                    continue
                content = (entry.get("message") or {}).get("content")
                if isinstance(content, str):
                    parts.append(content)
                    continue
                if not isinstance(content, list):
                    continue
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text")
                        if isinstance(text, str):
                            parts.append(text)
    except OSError:
        return ""
    digest = "\n".join(parts)
    if len(digest) > cap:
        digest = digest[-cap:]
    return digest


def _repo_top_level(cwd):
    try:
        r = subprocess.run(["git", "-C", cwd, "rev-parse", "--show-toplevel"],
                            capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            top = r.stdout.strip()
            if top:
                return top
    except Exception:
        pass
    return cwd


def _last_json_line(stdout):
    """The child's last output line, parsed as a JSON object -- or None when no line
    in the whole output parses as one (case_failure_child_prints_no_json)."""
    for line in reversed((stdout or "").splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        return obj if isinstance(obj, dict) else None
    return None


def _write_state(session_id, handoff_path, plan_path, ok, failure):
    path = state_path(session_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    state = {
        "handoff": handoff_path,
        "plan": plan_path,
        "ok": bool(ok),
        "time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    if failure:
        state["failure"] = failure
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f)
    os.replace(tmp, path)


def run_precompact(payload):
    if os.environ.get(RECURSION_GUARD_ENV):
        # The child inherits this flag. If the child's own session ever fires
        # PreCompact, stop here: never spawn a grandchild.
        return 0

    session_id = payload.get("session_id", "")
    transcript_path = payload.get("transcript_path", "")
    cwd = payload.get("cwd") or os.getcwd()
    repo_top = _repo_top_level(cwd)

    digest = build_digest(transcript_path)
    try:
        with open(PROMPT_PATH, "r", encoding="utf-8") as f:
            prompt_text = f.read()
    except OSError as e:
        prompt_text = ("Read the prior handoff, then rewrite it in place. "
                        "(prompt file unreadable: %s)\n---\n" % e)
    stdin_payload = prompt_text + "\n" + digest

    env = dict(os.environ)
    env[RECURSION_GUARD_ENV] = "1"
    program = resolve_claude(env)
    args = [program, "-p", "--model", "sonnet", "--tools", CHILD_TOOLS,
            "--settings", json.dumps({"disableAllHooks": True})]

    ok = False
    handoff_path = None
    plan_path = None
    failure = None
    try:
        proc = subprocess.run(args, cwd=repo_top, env=env, input=stdin_payload,
                               capture_output=True, text=True, timeout=CHILD_TIMEOUT)
        if proc.returncode != 0:
            failure = "child exited %r: stdout=%r stderr=%r" % (
                proc.returncode, (proc.stdout or "")[-500:], (proc.stderr or "")[-500:])
        else:
            summary = _last_json_line(proc.stdout)
            if summary is None:
                failure = "child printed no JSON summary line"
            else:
                handoff_path = summary.get("handoff")
                plan_path = summary.get("plan")
                ok = True
    except subprocess.TimeoutExpired:
        failure = "child timed out after %ss" % CHILD_TIMEOUT
    except Exception as e:
        failure = "child could not run: %s" % e

    try:
        _write_state(session_id, handoff_path, plan_path, ok, failure)
    except Exception as e:
        sys.stderr.write("precompact_handoff: could not write state: %s\n" % e)
    if failure:
        sys.stderr.write("precompact_handoff: %s\n" % failure)
    return 0


def run_reorient(payload):
    session_id = payload.get("session_id", "")
    state = None
    try:
        path = state_path(session_id)
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                state = json.load(f)
    except Exception:
        state = None

    if not state or not state.get("ok"):
        why = ((state or {}).get("failure") or "it never ran")[:300]
        print("Context was compacted. The handoff update failed: %s. Rewrite the "
              "handoff yourself now: use the repo's HANDOFF.md or handoff.md, outside "
              "any history folder, or .claude/handoff.md when neither exists. Rewrite "
              "it in place from the compaction summary above. Confirm checkout and "
              "branch before any git write. Then continue the last task." % why)
        return 0

    handoff = state.get("handoff")
    plan = state.get("plan")
    if plan:
        print("Context was compacted. Read the handoff at %s first, then the plan "
              "at %s. Confirm checkout and branch before any git write. Then "
              "continue the last task." % (handoff, plan))
    else:
        print("Context was compacted. Read the handoff at %s first. Confirm "
              "checkout and branch before any git write. Then continue the "
              "last task." % handoff)
    return 0


def main():
    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except ValueError:
        payload = {}

    try:
        if "--reorient" in sys.argv[1:]:
            return run_reorient(payload)
        return run_precompact(payload)
    except Exception as e:
        sys.stderr.write("precompact_handoff: unexpected error: %s\n" % e)
        return 0


if __name__ == "__main__":
    sys.exit(main())
