"""The guard's checkout family: the hand-made-worktree, worktree-home, other-checkout and session-home rules.

guard.py is the only entry point, and it calls these checks in its fixed order. The four rules read
each other's helpers: a worktree comes only from the tool's isolation (hand-made-worktree), an agent
works inside its own recorded worktree (worktree-home), no session writes into another checkout of
its clone (other-checkout), and a session whose worktree is gone writes nowhere in the primary
(session-home). Other files reach these names through `guard`.

Rule index, in check order:

  hand-made-worktree   deny. A real worktree add whose new tree lands outside
                       `<primary>/.claude/worktrees/`. A repo under the temp folder passes.
                       A call from an agent (valid `agent_id`) is refused inside that folder
                       too, unless the tree is its own home or its own red-run folder.
                       (lanes-start-in-tool-worktrees)

  worktree-home        deny. A call from an agent whose shell cwd or write target is outside its
                       own recorded worktree. Read and Grep pass, so a stranded agent can report.
                       A Write or Edit strictly inside the caller's own `agent-<id>-<suffix>`
                       red-run folder passes.
                       No record (a non-isolated agent, or the orchestrator) allows everything.
                       No override lifts it. (an-agent-outside-its-home-tree-must-stop)

  other-checkout       deny. Any session's write whose target sits in a checkout of this clone
                       other than the one holding its cwd. A nested worktree owns its own files.
                       A target in no checkout, or in the clone's `.git`, passes; so does a
                       linked checkout in this session's own scratchpad, for a call with no
                       `agent_id` and a valid session id. Unreadable git passes. The shell form
                       reads the targets frozen-path reads, after a leading `cd`. An override
                       lifts it.
                       A Bash or PowerShell `cd`, `pushd` or `Set-Location` into another
                       checkout is refused too, bare or chained; the cd target in the caller's
                       recorded home, a session's recorded home, or the caller's own
                       `agent-<id>-<suffix>` red-run folder passes that act. A write strictly
                       inside that red-run folder passes too, here and in worktree-home; the
                       folder root does not (no `rm -rf <red>`).
                       A write or `cd` into a separate clone of the same repo (same origin, read
                       from the config files) is refused too, as is a write from a cwd stranded
                       in one while `CLAUDE_PROJECT_DIR` names the home clone; a git verb that
                       changes files (OTHER_CHECKOUT_GIT_VERBS: SESSION_HOME_GIT_VERBS, `add`, `rm`, `mv`,
                       `update-index`, `read-tree`, `checkout-index`)
                       is refused from that stranded cwd and as `git -C <separate clone>`, and as
                       `git -C <another checkout of this clone>` by the same exemptions as the
                       `cd` form, while `git log`, `git show` and `git status` pass; the
                       temp folder, other repos, an unreadable origin and the home clone pass.
                       (an-agent-outside-its-home-tree-must-stop)

  session-home         deny. A session whose recorded worktree folder is gone, with its cwd in the primary
                       checkout, and a write (Write family or shell) that lands in the primary's own
                       files. Its record is `<primary>/.git/session-homes/<session_id>`, written by a
                       call with no `agent_id` from a `.claude/worktrees/<name>` folder, cleared by that
                       session's ExitWorktree. The reason names the EnterWorktree tool. The clone's
                       `.git`, a target outside the clone, reads and non-writing shell pass. A git
                       `clean` counts only with a force flag. An
                       override lifts it. It adds no git spawn beyond what the call already spends.
"""
# INSTALL_ID = "uninstalled"

import os
import re

from guard_core import (
    POWERSHELL_CALL, SHELL_TOOLS, WRITE_TOOLS, _checkout_root_by_stat, _expanded, _resolved, _segment_cd_target,
    _segment_git_c_target, _strip_heredoc_bodies_unconditionally, _unexpanded, basename, clone_checkouts,
    dir_before_segment, drive_form_cwd, git_calls, git_common_dir, is_move_into, path_is_inside, primary_checkout,
    record, resolve_command, segment_tokens, segment_with_vars as _segment_with_vars, shell_abs, split_segments,
    strip_heredoc_bodies, write_targets,
)
from guard_frozen import MUTATING_COMMAND, _shell_write_hit, interpreter_may_write, interpreter_write_hit
from guard_merge import CREATE_SESSION_TOOL
from guard_shared_tree import (
    SESSION_ID_RE, STASH_READ_ACTIONS, clean_deletes_files, in_any_session_scratchpad, stash_action,
    under_session_scratchpad,
)


# decision lanes-start-in-tool-worktrees: a worktree comes only from the tool's own isolation.
HAND_MADE_VALUE_OPTIONS = ("-b", "-B", "--reason")


def worktree_add_target(args):
    """The new-tree path of a `worktree add` call's arguments, else None (no path, or a help
    flag). `-b`, `-B` and `--reason` take a value. `--orphan` is a flag in git 2.42 and later and
    took a value before, so its next word is a value only when another path word follows. `--`
    ends the options."""
    words, ended, cursor = [], False, 0
    while cursor < len(args):
        arg = args[cursor]
        cursor += 1
        if ended or not arg.startswith("-") or arg == "-":
            words.append(arg)
        elif arg == "--":
            ended = True
        elif arg in ("-h", "--help"):
            return None
        elif arg in HAND_MADE_VALUE_OPTIONS:
            cursor += 1
        elif arg == "--orphan" and cursor < len(args) and not args[cursor].startswith("-"):
            if len([a for a in args[cursor:] if not a.startswith("-")]) > 1:
                cursor += 1
    return words[0] if words else None


def hand_made_worktree_hit(segments, number: int, cwd: str, ends=(), payload=None) -> str:
    """The new-tree path when `segments[number]` is a real worktree add whose tree lands
    outside `<primary>/.claude/worktrees/`, else "". The primary is the one of the repo the call
    runs in (`dir_before_segment`, then its own `-C`). A repo under the temp folder is a throwaway
    and passes, so the repo is judged, never the target. A call whose PAYLOAD carries a valid
    `agent_id`, or an `agent_type` alone, is refused inside that folder too, unless the tree is the agent's recorded home
    (`agent_worktree_home` status "home") or its own red-run folder (`_own_red_run`); a "no-record"
    agent has no home to match. A variable target is read from an assignment earlier in the same
    command; one left unresolved (or a substitution) is refused from a non-temp repo, since its
    value is unknown; a `-C` variable is read the same way. Other unreadable parts (a repo, a
    cwd) allow."""
    if "worktree" not in segments[number]:
        return ""   # early exit: resolving variables re-reads every earlier segment, so it runs only for a segment that holds the word `worktree`
    read = _segment_with_vars(segments, number, ends)
    tokens = segment_tokens(read)
    index = resolve_command(tokens) if tokens else None
    if index is None or basename(tokens[index]) not in ("git", "git.exe"):
        return ""
    target = None
    for subcommand, args in git_calls(read):
        if subcommand == "worktree" and args and args[0] == "add":
            target = worktree_add_target(args[1:])
            break
    if target is None:
        return ""
    where = dir_before_segment(segments, number, cwd, ends)
    named = _segment_git_c_target(tokens)
    if named is not None:
        where = None if _unexpanded(named) else shell_abs(named, where)
    if not where:
        return ""
    primary = primary_checkout(where)
    if not primary:
        return ""
    import tempfile   # lazy: only a real worktree add reaches here
    if path_is_inside(primary, tempfile.gettempdir()):
        return ""
    if _unexpanded(target):
        return target   # a variable the command does not set: the shell's value is unknown
    tree = shell_abs(target, where)
    if tree is None:
        return ""
    if path_is_inside(tree, os.path.join(primary, ".claude", "worktrees")) is not True:
        return target
    status, home, _ = agent_worktree_home(payload, drive_form_cwd(cwd))
    if status == "unknown" and (os.path.normcase(os.path.normpath(where))
                                != os.path.normcase(os.path.normpath(drive_form_cwd(cwd)))):
        # a gone cwd reads unknown: ask again from the readable repo, unless it is the same folder
        status, home, _ = agent_worktree_home(payload, where)
    if status == "none" and isinstance(payload, dict) and payload.get("agent_type"):
        status = "no-record"   # an agent_type with no agent_id is an agent with no record
    flat = os.path.normpath(tree)   # `agent-<me>-red/../lane9` must not match by its unflattened name
    if status in ("none", "unknown") or _own_red_run(payload, primary, flat):
        return ""
    own = path_is_inside(flat, home) is True and path_is_inside(home, flat) is True
    return "" if own else target


WORKTREE_HAND_MADE_REASON = (
    "Rule (hand-made worktree): a worktree comes only from the Agent tool's isolation "
    "'worktree' option or from the EnterWorktree tool, never from a tree made by hand. "
    "A hand-made tree sends an agent or a session to work in the main clone and loses the isolation. "
    "Remedy: start the work with one of those two tools. Call EnterWorktree with a `name` and no "
    "`path`. A path the guard cannot read, such as one held in a variable or a substitution, is "
    "refused too. If the tree is your own red-run checkout, write its path out in full, with no "
    "variable or substitution. If the tool's isolation was refused, "
    "make no tree by hand: stop and report to the owner which layer refused and its exact "
    "message. A guard refusal starts \"Rule (\" and names its rule. Any other refusal is the "
    "harness's."
)


# ------------------------------------------------------------------ each agent's own worktree
#
# MEASURED 2026-09-27, macOS, one Explore agent with `isolation: 'worktree'`: a PreToolUse payload
# from an agent carries `agent_id` (17 hex characters) and `agent_type`. The
# orchestrator's own payloads carry no `agent_id`. `session_id` is the SAME for the orchestrator
# and its agents, so it never tells them apart. The agent's `cwd` was
# `<primary>/.claude/worktrees/agent-<agent_id>`, on branch `worktree-agent-<agent_id>`.
#
# An agent resumed after the harness auto-removed its worktree loses BOTH the folder and the
# branch, so git alone cannot tell "never had a worktree" from "worktree was removed". A RECORD
# is needed: docs/decisions/an-agent-outside-its-home-tree-must-stop.md.
#
# The record lives under the CLONE's git common directory, not inside any one worktree, so it
# survives that worktree's removal (`git_common_dir` above). Unmeasured: Windows, and the
# Write/Edit payload shape; covered by fixture in `test_guard.py`, not by a live probe.
AGENT_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def agent_home_record_path(where: str, agent_id: str):
    """Return the file that holds `agent_id`'s recorded worktree home, or None when the clone's
    common directory could not be read. Stored under
    `<git-common-dir>/agent-homes/<agent_id>`, so it survives the worktree's own removal."""
    common = git_common_dir(where)
    return os.path.join(common, "agent-homes", agent_id) if common else None


def read_agent_home(where: str, agent_id: str):
    """Return the recorded home for `agent_id`, `''` when no record exists yet, or None when the
    record could not be read at all (no git, no common dir, an unreadable file). `None` is
    UNKNOWN, never a hit."""
    path = agent_home_record_path(where, agent_id)
    if not path:
        return None
    if not os.path.exists(path):
        return ""
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read().strip()
    except Exception:
        return None


def write_agent_home(where: str, agent_id: str, home: str) -> None:
    path = agent_home_record_path(where, agent_id)
    if not path:
        return
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(home)
    except Exception:
        pass


def agent_worktree_home(payload, cwd: str):
    """Return (status, home, primary) for this call's agent.

    status:
      "none"      no valid `agent_id` on the payload: the orchestrator, or a call this rule does
                  not judge at all.
      "unknown"   an `agent_id` is present, but the home record could not be read (no git, no
                  common directory, an unreadable file). Allowed, never a hit.
      "no-record" the record reads clean and holds nothing, and this call's own `cwd` is not the
                  agent's worktree shape either: a non-isolated agent. Allow everything.
      "home"      `home` names the agent's recorded worktree, whether just written on this call
                  or read back from an earlier one.
    """
    agent_id = payload.get("agent_id") if isinstance(payload, dict) else None
    if not isinstance(agent_id, str) or not AGENT_ID.match(agent_id):
        return "none", "", None
    if not isinstance(cwd, str) or not cwd:
        return "unknown", "", None
    primary = primary_checkout(cwd)
    if not primary:
        return "unknown", "", None
    candidate = os.path.join(primary, ".claude", "worktrees", "agent-" + agent_id)
    recorded = read_agent_home(cwd, agent_id)
    if recorded is None:
        return "unknown", "", primary
    if recorded:
        return "home", recorded, primary
    if path_is_inside(cwd, candidate) is True:
        write_agent_home(cwd, agent_id, candidate)
        return "home", candidate, primary
    return "no-record", "", primary


WORKTREE_HOME_REASON = (
    "Rule (worktree home): this agent's own working tree is gone, or this call reaches outside "
    "it. "
    "Remedy: make no further change. Stop, and report this to your orchestrator."
)


OTHER_CHECKOUT_REASON = (
    "Rule (other checkout): this write lands in another checkout of this clone, not the one this "
    "session stands in. "
    "Remedy: write only inside your own checkout, or report the change to the session that owns "
    "the other one. To work in a checkout you own, call the EnterWorktree tool with `path` set to "
    "it. To remove a whole worktree, use `git worktree remove`, or leave it to the janitor sweep."
)

OTHER_CHECKOUT_CD_DETAIL = "cd into another checkout: "
OTHER_CHECKOUT_CD_REASON = (
    "Rule (other checkout): this command changes directory into another checkout of this clone, "
    "not the one this session stands in. "
    "Remedy: stay in your own checkout. To work in a checkout you own, call the EnterWorktree tool "
    "with `path` set to it. To read another one, use `git -C <dir>` or a path."
)

OTHER_CLONE_DETAIL = "write into another clone: "
OTHER_CLONE_CD_DETAIL = "cd into another clone: "
OTHER_CLONE_GIT_DETAIL = "git write into another clone: "
OTHER_CHECKOUT_GIT_DETAIL = "git write into another checkout: "
OTHER_CLONE_REMEDY = (
    "Remedy: change files only in your home checkout. To read another clone, use "
    "`git -C <dir> log` or `git -C <dir> show`, or a path."
)
OTHER_CLONE_REASON = (
    "Rule (other checkout): this command writes into a separate clone of this repo, or runs from one "
    "while this session's home is another clone. " + OTHER_CLONE_REMEDY
)
OTHER_CLONE_CD_REASON = (
    "Rule (other checkout): this command changes directory into, or writes into, a separate clone of "
    "this repo. " + OTHER_CLONE_REMEDY
)


def worktree_home_hit(payload, tool: str, tool_input: dict, cwd: str) -> str:
    """Rule 0, worktree-home: return the log detail when an agent's call reaches outside its own
    worktree, else ''. `status` is "none" for the orchestrator (no `agent_id`) and for tools this
    rule does not judge; "unknown" when the record could not be read at all, which allows (an
    unreadable state is never a hit); "no-record" for a non-isolated agent, which allows everything;
    "home" once the agent's worktree is known, from this call or an earlier one. Read/Grep are never
    checked here: the agent must still be able to read and report
    (decision an-agent-outside-its-home-tree-must-stop)."""
    # Rule 0 alone reads a Git Bash `/c/Users/...` cwd in the form the home record is written in. Off
    # Windows `/c/` is a real folder. One reader of the drive spelling: `_expanded`. Every other
    # rule sees `cwd` as main does.
    home_cwd = drive_form_cwd(cwd)
    home_status, home, home_primary = agent_worktree_home(payload, home_cwd)
    if home_status != "home":
        return ""
    if tool in SHELL_TOOLS:
        # The one allowed call is a lone `cd` back into the home (a recovery step).
        if (path_is_inside(home_cwd, home) is False
                and not is_move_into(tool, str(tool_input.get("command", "")), home_cwd, home)):
            return "shell cwd outside recorded agent home"
    elif tool in WRITE_TOOLS:
        for write_target in (write_targets(tool_input) if home_primary else ()):
            # A relative `file_path` resolves against the CALLER's cwd, the payload's own
            # `cwd`, never the guard process's. `_resolved` (already used by `is_frozen` and
            # `is_project_config` for the same reason) joins it before either check.
            try:
                resolved_target = _resolved(write_target, home_cwd)
            except Exception:
                resolved_target = write_target
            if (path_is_inside(resolved_target, home_primary) is True
                    and path_is_inside(resolved_target, home) is False
                    and not _own_red_run(payload, home_primary, resolved_target, False)):
                return "write target outside recorded agent home"
    return ""


# A shell command with none of these can write no named file, so it spends no git read here. A
# redirect onto a stream (`2>&1`) or the null device writes no checkout, so it is dropped first.
SHELL_QUIET_REDIRECT = re.compile(r"\d*>>?[ \t]*(?:&[0-9-]|/dev/null\b)")
SHELL_WRITE_HINT = re.compile(r">|" + MUTATING_COMMAND + r"|\bsed\b")


def _owning_checkout(path: str, roots) -> str:
    """The deepest checkout root that holds `path`, else ''. A nested worktree under the
    primary's `.claude/worktrees/` is deeper than the primary, so it owns its own files."""
    owners = [root for root in roots if path_is_inside(path, root) is True]
    return max(owners, key=len) if owners else ""


def _git_common_dir(root: str) -> str:
    """The git common directory of the checkout at ROOT, read from files alone, else ''. A `.git`
    folder is its own; a `.git` file names `gitdir: <dir>`, and `<dir>/commondir` names the common
    one, relative to `<dir>`. No git is spawned."""
    dot = os.path.join(root, ".git")
    try:
        if os.path.isdir(dot):
            return os.path.realpath(dot)
        with open(dot, encoding="utf-8") as handle:
            first = handle.readline(4096).strip()
        if not first.startswith("gitdir:"):
            return ""
        git_dir = os.path.join(root, first[len("gitdir:"):].strip())
        try:
            with open(os.path.join(git_dir, "commondir"), encoding="utf-8") as handle:
                git_dir = os.path.join(git_dir, handle.readline(4096).strip())
        except OSError:
            pass  # no commondir: a submodule's or a bare-style git dir is its own common dir
        return os.path.realpath(git_dir)
    except (OSError, UnicodeDecodeError):
        return ""


def _clone_origin(common: str) -> str:
    """The `[remote "origin"]` url in COMMON's config file, else '' (no file, no origin, no url)."""
    try:
        with open(os.path.join(common, "config"), encoding="utf-8") as handle:
            lines = handle.read(1 << 20).splitlines()
    except (OSError, UnicodeDecodeError):
        return ""
    in_origin = False
    for line in lines:
        line = line.strip()
        if line.startswith("["):
            in_origin = re.fullmatch(r'\[remote\s+"origin"\]', line, re.IGNORECASE) is not None
        elif in_origin:
            found = re.match(r"url\s*=\s*(.+)$", line, re.IGNORECASE)
            if found:
                return found.group(1).strip().strip('"')
    return ""


def _origin_local(url: str) -> str:
    """The realpath a local-path origin names, else '' for a network url."""
    if url.startswith("file://"):
        url = url[len("file://"):]
    if os.path.isabs(url):
        return os.path.realpath(url)
    return ""


def _origin_key(url: str) -> str:
    """The `owner/repo` of a network origin url, lower case, with a `.git` suffix and a trailing `/`
    dropped, in any form (https, ssh `git@host:owner/repo`, a proxy url); '' when it names none."""
    url = url.rstrip("/\\")
    if url.endswith(".git"):
        url = url[:-len(".git")].rstrip("/")
    parts = [part for part in re.split(r"[/:\\]", url) if part]
    return "/".join(parts[-2:]).lower() if len(parts) >= 2 else ""


def _same_repo(common: str, other: str) -> bool:
    """True when the clones with git common dirs COMMON and OTHER are the same repo: a local-path
    origin that names the other clone, or two network origins naming one `owner/repo`. An origin
    that is missing or unreadable on either side is unknown, never a match."""
    urls = (_clone_origin(common), _clone_origin(other))
    for url, theirs in ((urls[0], other), (urls[1], common)):
        local = _origin_local(url) if url else ""
        if local and local in (theirs, os.path.dirname(theirs)):
            return True
    if urls[0] and _origin_local(urls[0]) and _origin_local(urls[0]) == _origin_local(urls[1] or ""):
        return True  # two clones of one local bare repository
    return (all(urls) and not any(_origin_local(url) for url in urls)
            and _origin_key(urls[0]) != "" and _origin_key(urls[0]) == _origin_key(urls[1]))


def _git_verb_called(command: str, verbs) -> bool:
    """True when COMMAND runs a git verb of VERBS. A text with no `git` in it is never scanned, so a
    call with no git word spends nothing."""
    return "git" in command and any(
        verb in verbs
        for segment in split_segments(command, []) for verb, _args in git_calls(segment))


def _git_verb_may_hit(command: str, where: str, verbs) -> bool:
    """True when a git verb of VERBS in COMMAND can change another checkout's or clone's files, so
    it is worth the one `git worktree list`: the cwd is stranded in a separate clone of the
    `CLAUDE_PROJECT_DIR` clone, or a `-C` or `cd` folder's nearest `.git` is not the cwd's. The folder
    of each verb is read by session_home_git_hit, the one reader. Stat and small file reads; no git."""
    own_root = _checkout_root_by_stat(os.path.realpath(where)) if where else ""
    if not own_root:
        return False
    stranded = _clone_scope(None, own_root)[2]
    return bool(session_home_git_hit(
        command, where,
        lambda folder, _at: stranded or _checkout_root_by_stat(os.path.realpath(folder)) != own_root,
        verbs))


def _separate_clone(path: str, tops, common: str) -> bool:
    """True when PATH sits in a separate clone of the same repo as the checkouts TOPS, whose git
    common dir is COMMON: the nearest `.git` above it is not inside a top (a submodule), not above
    one (a dotfiles repo), names another common dir, and that clone has the same origin. Stat and
    small file reads only."""
    root = _checkout_root_by_stat(os.path.realpath(path))
    if not root or not common:
        return False
    if any(path_is_inside(root, top) is True or path_is_inside(top, root) is True for top in tops):
        return False
    other = _git_common_dir(root)
    return bool(other) and other != common and _same_repo(common, other)


def _clone_scope(roots, own: str):
    """(tops, common, stranded): the checkouts and common dir a path must sit in, to be no separate
    clone. Normally this clone's own. When `CLAUDE_PROJECT_DIR` names a folder in a clone that is a
    separate clone of the cwd's, the session is stranded: its home clone is the reference, and
    `stranded` is True. An unset, unreadable or unrelated value is unknown, and changes nothing."""
    home = os.environ.get("CLAUDE_PROJECT_DIR", "")
    try:
        top = _checkout_root_by_stat(os.path.realpath(home)) if home else ""
        common = _git_common_dir(top) if top else ""
        if common and _separate_clone(own, [top], common):
            return [top], common, True
    except Exception:
        pass
    return roots, _git_common_dir(own), False


def _cd_targets(tool: str, command: str, where: str):
    """The folder each real `cd`, `pushd` or `Set-Location` segment of COMMAND moves into, as a
    realpath. Read the way `_run_dir` reads the shell: heredoc bodies dropped first, one segment at a
    time, so a `cd` in a quote, a comment or a heredoc body is text. A target that holds a variable,
    a bare `cd`, `cd -`, a bare `pushd` or `pushd +N`, and a folder that does not exist are not read."""
    POWERSHELL_CALL[0] = tool == "PowerShell"
    command = _strip_heredoc_bodies_unconditionally(command)
    if not re.search(r"\bcd\b|set-location|\bpushd\b", command, re.IGNORECASE):
        return []
    found, ends = [], []
    segments = split_segments(command, ends)
    for number, segment in enumerate(segments):
        tokens = segment_tokens(segment)
        named = _segment_cd_target(tokens, ("cd", "set-location", "pushd")) if tokens else None
        if named is None or _unexpanded(named):
            continue
        # An absolute target needs no known folder.
        at = dir_before_segment(segments, number, where, ends)
        folder = shell_abs(named, at)
        if folder and os.path.isdir(folder):
            found.append(os.path.realpath(folder))
    return found


def _cd_home_exempt(payload, cwd: str, target: str) -> bool:
    """True when a `cd` into TARGET goes into the caller's recorded agent home (the recovery step
    worktree-home allows) or, for a call with no `agent_id`, the session's recorded home. It skips
    the `cd` act only; the write scan still judges every write in the same command. File reads,
    no git."""
    status, home, _ = agent_worktree_home(payload, cwd)
    if status == "home" and path_is_inside(target, home) is True:
        return True
    if isinstance(payload, dict) and payload.get("agent_id"):
        return False
    primary, _lane = session_home_place(cwd)
    record = session_home_record(payload, primary) if primary else ""
    try:
        with open(record, encoding="utf-8") as handle:
            held = handle.read().strip()
    except OSError:
        return False
    return bool(held) and path_is_inside(target, held) is True


# The shell verbs that may name the red-run folder's own root: `cp x <red>/` writes inside it. No
# other verb may, so `rm -rf <red>` stays refused (an-agent-outside-its-home-tree-must-stop).
RED_RUN_ROOT_VERBS = ("cp",)


def _own_red_run(payload, primary: str, path: str, root_ok: bool = True) -> bool:
    """True when PATH is inside the caller's own test-author red-run folder
    `<primary>/.claude/worktrees/agent-<its agent id>-<suffix>`. The one home for that test: the
    `cd` act and the write act of other-checkout, and worktree-home's Write target, all ask it.
    PRIMARY is the primary checkout alone, so a folder under a linked worktree never counts. The id and
    its dash match whole, so a sibling whose id only starts with this one does not pass. ROOT_OK False
    leaves the folder itself out: a write passes only strictly inside it, so a delete of the folder
    is still refused. Both sides compare case-folded and realpath'd (`path_is_inside`)."""
    agent_id = payload.get("agent_id") if isinstance(payload, dict) else None
    if not isinstance(agent_id, str) or not agent_id or not primary or not path:
        return False
    holder = os.path.join(primary, ".claude", "worktrees")
    folder = path
    while True:
        parent = os.path.dirname(folder)
        if parent == folder:
            return False
        if (path_is_inside(parent, holder) is True and path_is_inside(holder, parent) is True
                and os.path.normcase(os.path.basename(folder)).startswith(
                    os.path.normcase("agent-" + agent_id + "-"))):
            return root_ok or folder != path
        folder = parent


def other_checkout_hit(tool: str, tool_input: dict, cwd: str, session_id: str = "",
                       payload=None,
                       has_agent: bool = True) -> str:
    """Rule 0, other-checkout, for every session: the log detail when a write lands in a checkout
    of this clone other than the one holding `cwd`, else ''. A target in no checkout passes. A
    linked checkout in this session's own scratchpad passes for a call with no `agent_id` and a
    valid `session_id`; a caller that omits `has_agent` gets no exemption. An unreadable git
    state, or a cwd in no checkout, is unknown and passes. One git read per call that can write.
    A shell `cd`, `pushd` or `Set-Location` that moves into another checkout is refused too, unless
    `payload` marks the target as the caller's own home or red-run folder (a write strictly inside that red-run
    folder passes too, a shell `cp` may also name its root); a `cd` toward a folder
    under another `.git` entry spends the git read. A target in a separate clone of the same repo
    (the nearest `.git` above it names another common dir with the same origin, read by file) is
    refused the same way; the clone check spawns no git. A git verb that changes files
    (OTHER_CHECKOUT_GIT_VERBS) run as `git -C <path>`, or after a `cd`, in another checkout or a
    separate clone is refused by that same `elsewhere()` test, and the red-run exemption reads the
    resolved folder, as the `cd` form reads its target;
    `git -C <primary> status` passes and spends no git. Liftable by an owner override, unlike `worktree_home_hit`
    (decision an-agent-outside-its-home-tree-must-stop)."""
    where = _expanded(cwd, "") if cwd and os.name == "nt" else cwd
    moves = []
    if tool in WRITE_TOOLS:
        targets = write_targets(tool_input)
        writes = bool(targets)
    elif tool in SHELL_TOOLS:
        targets = None
        raw = str(tool_input.get("command", "") or "")
        command = strip_heredoc_bodies(raw)
        writes = bool(SHELL_WRITE_HINT.search(SHELL_QUIET_REDIRECT.sub(" ", command))) or interpreter_may_write(raw)
        moves = _cd_targets(tool, raw, where) if where else []
        # A git verb spends the list only when stat and file reads show it can reach another clone.
        writes = writes or (_git_verb_called(command, OTHER_CHECKOUT_GIT_VERBS)
                            and _git_verb_may_hit(command, where, OTHER_CHECKOUT_GIT_VERBS))
    else:
        return ""
    if moves:
        # A `cd` stays in its own checkout when the nearest `.git` above its target is the one above
        # the cwd. Stat alone tells, so only a move toward another `.git` entry spends the git read.
        own_root = _checkout_root_by_stat(os.path.realpath(where))
        moves = [m for m in moves
                 if own_root and _checkout_root_by_stat(m) not in ("", own_root) and not _cd_home_exempt(payload, where, m)]
    if not moves and not writes:
        return ""
    roots = clone_checkouts(where) if where else None
    own = _owning_checkout(where, roots) if roots else ""
    if not own:
        return ""

    tops, common, stranded = _clone_scope(roots, own)
    import tempfile   # lazy: only a call that can write or move reaches here
    temp = os.path.realpath(tempfile.gettempdir())
    clone_hit = {}   # target -> True when the hit was a separate clone, not a checkout of this one

    def elsewhere(target, at, verb=""):
        try:
            resolved = _resolved(target, at)
            owner = _owning_checkout(resolved, roots)
        except Exception:
            return False
        # An agent shares its session's id, and worktree-home judges no shell target, so only a
        # top-level call may write into the session's own scratchpad worktree.
        if not has_agent and under_session_scratchpad(resolved, session_id):
            return False
        # A separate clone of the same repo, or a write from a cwd stranded in one. The temp folder
        # holds scratchpads and throwaway clones, so it passes.
        clone_hit[target] = (
            path_is_inside(resolved, temp) is not True
            and not in_any_session_scratchpad(resolved)
            and ((stranded and bool(owner) and path_is_inside(resolved, os.path.join(owner, ".git")) is not True)
                 or (not owner and _separate_clone(resolved, tops, common))))
        if clone_hit[target]:
            return True
        # The primary's `.git` is the clone's common directory, shared by every checkout.
        return (bool(owner) and owner != own
                and path_is_inside(resolved, os.path.join(owner, ".git")) is not True
                and not _own_red_run(payload, roots[0], resolved, verb in RED_RUN_ROOT_VERBS))

    for move in moves:
        if elsewhere(move, where) and not _own_red_run(payload, roots[0], move):
            return (OTHER_CLONE_CD_DETAIL if clone_hit.get(move) else OTHER_CHECKOUT_CD_DETAIL) + move
    if targets is None:
        hit = _shell_write_hit(command, where, elsewhere, follow_cd=True, predicate_command=True) if writes else ""
        if not hit and interpreter_may_write(raw):
            hit = interpreter_write_hit(raw, where, elsewhere)
        if not hit:
            # A git verb that changes files, run in another checkout or a separate clone of this one,
            # or from a stranded cwd. The one reader of such verbs is session_home_git_hit; only the
            # folder test differs, and it is elsewhere(), so the `cd` form's exemptions hold here too.
            flagged = []

            def in_clone(folder, _at):
                # As the `cd` loop above: the folder's own root counts as the red-run folder, since a
                # git verb run there writes its files, not the folder's name. The test reads the
                # resolved folder, as elsewhere() does, so a `..` climb out of it cannot pass.
                if elsewhere(folder, folder) and not _own_red_run(payload, roots[0], _resolved(folder, folder)):
                    flagged.append(folder)
                    return True
                return False
            verb = (session_home_git_hit(command, where, in_clone, OTHER_CHECKOUT_GIT_VERBS)
                    if "git" in command else "")
            if not verb:
                return ""
            return (OTHER_CLONE_GIT_DETAIL if clone_hit.get(flagged[-1]) else OTHER_CHECKOUT_GIT_DETAIL) + verb
        return ("shell write into another clone: " if clone_hit.get(hit) else
                "shell write into another checkout: ") + hit
    for target in targets:
        if elsewhere(target, where):
            return (OTHER_CLONE_DETAIL if clone_hit.get(target) else "write target in another checkout: ") + target
    return ""


# ------------------------------------------------------------------ the session's own worktree
#
# Rule session-home. The harness removes a session's linked worktree and branch while the session
# runs on, and its shell falls back to the primary checkout. A write there lands on the clone's
# default branch, behind everything. The record `<primary>/.git/session-homes/<session_id>` holds the
# worktree path, so a later call can tell "never had a worktree" from "its worktree is gone". Only a
# call with no `agent_id` writes or clears it: an agent shares its session's id. The primary is found
# by path shape and a stat walk, never by git, so the rule adds no git spawn beyond what the call
# already spends. A git verb in the primary is read off the command text with `git_calls`.
SESSION_HOME_DIR = "session-homes"
# The git verbs that change the primary's files or branch. A `stash` that only reads (STASH_READ_ACTIONS)
# and a `clean` that deletes nothing (no force flag, as `clean -n`) are left out in session_home_git_hit.
SESSION_HOME_GIT_VERBS = ("checkout", "switch", "pull", "merge", "commit", "rebase", "restore", "reset",
                          "stash", "cherry-pick", "revert", "am", "apply", "clean")
# The verbs other-checkout refuses in another checkout or clone: the session-home verbs plus the verbs
# that change that checkout's files or index without moving a branch (`add`, `rm`, `mv`, `update-index`,
# `read-tree`, `checkout-index`). Every form of these counts as a write, `rm --cached` and `rm -n`
# included: the guard does not parse each verb's flags, so a dry run is refused too. session-home
# leaves them out, so this set extends the tuple rather than copying it.
OTHER_CHECKOUT_GIT_VERBS = SESSION_HOME_GIT_VERBS + (
    "add", "rm", "mv", "update-index", "read-tree", "checkout-index")
SESSION_HOME_REASON = (
    "Rule (session-home): this session's worktree is gone, so a write here would land in the primary "
    "checkout. "
    "Remedy: call the EnterWorktree tool first. Call it with a `name` and no `path`. It branches "
    "from origin's default branch. Then write inside that worktree."
)


def session_home_place(cwd: str):
    """Return (primary, lane) for a call's cwd, by path shape and a stat walk. `lane` is the
    `<primary>/.claude/worktrees/<name>` folder holding cwd, or '' when cwd sits in the primary's own
    files. (None, '') when neither shape fits: no checkout, a linked worktree elsewhere, or no
    `.git` directory at the primary."""
    if not cwd:
        return None, ""
    try:
        folder = os.path.realpath(cwd)
    except Exception:
        return None, ""
    while True:
        parent = os.path.dirname(folder)
        grand = os.path.dirname(parent)
        if (os.path.basename(parent) == "worktrees" and os.path.basename(grand) == ".claude"
                and os.path.isdir(os.path.join(os.path.dirname(grand), ".git"))):
            return os.path.dirname(grand), folder
        if os.path.isdir(os.path.join(folder, ".git")):
            return folder, ""
        if os.path.exists(os.path.join(folder, ".git")) or parent == folder:
            return None, ""
        folder = parent


def session_home_agent_tree(lane: str) -> bool:
    """True when LANE has an agent worktree's shape, `.claude/worktrees/agent-<agent_id>` (rule
    worktree-home). A top-level call there is the session inspecting an agent's tree, not its home."""
    name = os.path.basename(lane)
    return name.startswith("agent-") and bool(AGENT_ID.match(name[len("agent-"):]))


def session_home_record(payload, primary: str):
    """The record's path for this session, or '' when the call carries no valid session id."""
    sid = payload.get("session_id") if isinstance(payload, dict) else None
    if not isinstance(sid, str) or not SESSION_ID_RE.match(sid):
        return ""
    return os.path.join(primary, ".git", SESSION_HOME_DIR, sid)


def session_home_keep(payload, tool: str, cwd: str) -> None:
    """Write the session's record from a lane call, only when it is missing or different. The
    session's own ExitWorktree deletes it. An agent call does neither."""
    if not isinstance(payload, dict) or payload.get("agent_id") or tool == CREATE_SESSION_TOOL:
        # create_session reaches the guard for rules lane-effort-pin and agent-model-floor; it keeps no record
        return
    where = _expanded(cwd, "") if cwd and os.name == "nt" else cwd
    primary, lane = session_home_place(where)
    record = session_home_record(payload, primary) if primary else ""
    if not record:
        return
    try:
        try:
            with open(record, encoding="utf-8") as handle:
                held = handle.read().strip()
        except OSError:
            held = ""
        if tool == "ExitWorktree":
            # An exit ends a record whose worktree still stands, from any cwd. A record whose
            # worktree is gone stays, and the guard keeps judging.
            if held and os.path.isdir(held):
                os.remove(record)
            return
        if not lane or held == lane or session_home_agent_tree(lane):
            return
        import tempfile   # lazy: only a first or changed record reaches here
        folder = os.path.dirname(record)
        os.makedirs(folder, exist_ok=True)
        handle, temp = tempfile.mkstemp(dir=folder, prefix=".tmp-")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as out:
                out.write(lane)
            os.replace(temp, record)  # one step: a reader never sees a half-written path
        except BaseException:
            try:
                os.remove(temp)
            except OSError:
                pass
            raise
    except Exception:
        pass  # an unwritable record means no refusal later, never a failed call


def session_home_git_hit(command: str, where: str, in_primary, git_verbs=None) -> str:
    """The verb of a git call in COMMAND that changes files or a branch and runs in a folder that
    IN_PRIMARY accepts, else ''. GIT_VERBS names the verbs; none means SESSION_HOME_GIT_VERBS. A
    leading `cd` and `git -C <path>` name the folder it runs in; a folder that holds a variable is
    unknown and passes."""
    ends = []
    segments = split_segments(command, ends)
    for number, segment in enumerate(segments):
        verbs = [(verb, args) for verb, args in git_calls(segment)
                 if verb in (git_verbs or SESSION_HOME_GIT_VERBS)]
        if not verbs:
            continue
        folder = dir_before_segment(segments, number, where, ends)
        tokens = segment_tokens(segment)
        named = _segment_git_c_target(tokens) if tokens else None
        if named is not None:
            folder = None if _unexpanded(named) else shell_abs(named, folder)
        if not folder:
            continue
        for verb, args in verbs:
            if verb == "stash" and stash_action(args) in STASH_READ_ACTIONS:
                continue
            if verb == "clean" and not clean_deletes_files(args):
                continue
            if in_primary(folder, folder):
                return verb
    return ""


def session_home_hit(payload, tool: str, tool_input: dict, cwd: str) -> str:
    """Rule session-home: the log detail when a session whose recorded worktree is gone writes into
    the primary checkout, else ''. Only a call with no `agent_id` and a cwd in the primary's own files
    is judged. A missing, empty or unreadable record is unknown and passes. The clone's `.git`,
    `.claude/worktrees/`, and a target outside the clone pass. Liftable by an owner override."""
    POWERSHELL_CALL[0] = tool == "PowerShell"
    if not isinstance(payload, dict) or payload.get("agent_id"):
        return ""
    if tool in WRITE_TOOLS:
        targets = write_targets(tool_input)
    elif tool in SHELL_TOOLS:
        targets = None
        command = strip_heredoc_bodies(str(tool_input.get("command", "") or ""))
        writes = bool(SHELL_WRITE_HINT.search(SHELL_QUIET_REDIRECT.sub(" ", command)))
        if not writes and "git" not in command:
            return ""
    else:
        return ""
    where = _expanded(cwd, "") if cwd and os.name == "nt" else cwd
    primary, lane = session_home_place(where)
    record = session_home_record(payload, primary) if primary and not lane else ""
    if not record:
        return ""
    try:
        with open(record, encoding="utf-8") as handle:
            home = handle.read().strip()
    except OSError:
        return ""
    if not home or os.path.isdir(home):
        return ""
    lanes = os.path.join(primary, ".claude", "worktrees")
    clone_git = os.path.join(primary, ".git")

    def in_primary(target, at):
        try:
            resolved = _resolved(target, at)
        except Exception:
            return False
        return (path_is_inside(resolved, primary) is True
                and path_is_inside(resolved, clone_git) is not True
                and (path_is_inside(resolved, lanes) is not True
                     or path_is_inside(resolved, home) is True))  # the gone home path is the primary's too

    if targets is None:
        verb = session_home_git_hit(command, where, in_primary)
        if verb:
            return "git " + verb + " in the primary checkout"
        hit = _shell_write_hit(command, where, in_primary, follow_cd=True) if writes else ""
        return "shell write into the primary checkout: " + hit if hit else ""
    for target in targets:
        if in_primary(target, where):
            return "write target in the primary checkout: " + target
    return ""
