# section 22900
# =========================================================================== brief scope
#
# An agent's commit, push and stop are judged against the paths its brief names (roadmap step
# agent-commit-file-scope). A modified or deleted existing file outside them is refused under rule
# brief-scope-diff, and the reason names no path. A new file is logged and allowed. A brief that names no
# path, or cannot be read, is logged and allowed. The brief is the agent's own first user message, in its
# own transcript, never another agent's. A generated page never counts. Judged roles: builder, test-author
# and record-writer. The refusal is final: no override lifts it (decision owner-override).
FAMILY = "brief-scope"
BS_RULE = "brief-scope-diff"
BS_NEW = "brief-scope-new"
BS_UNNAMED = "brief-scope-unnamed"
BS_UNREAD = "brief-scope-unread"
# Both must be read: the undo the refusal gives, and the route for a need the brief did not name.
BS_REMEDY = ("restore", "orchestrator")
# The push refusal also says to stop and report a change an own commit holds, as builder_diff_reason does.
BS_STOP_REPORT = "if a commit of yours holds the change, stop and report it"
BS_TIME = "2026-11-08T10:00:00Z"
BS_PROJECT = os.path.join(ROOT, "briefscope", "projects", "-briefscope-slug")
BS_SESSION = "briefscope-session-0001"
BS_TRANSCRIPT = os.path.join(BS_PROJECT, BS_SESSION + ".jsonl")   # the payload's transcript_path
BS_TOOL_NOTES = ["notes/tool-a-%02d.md" % n for n in range(1, 13)]   # twelve notes of another tool
BS_POINTER_TEXT = "Task: fix the guard.\nFiles: `hooks/guard.py`. Report in 10 lines."
BS_LONG_NAME = "src/" + "a" * 40 + ".txt"   # the name a ten-star glob fails on: separated stars backtrack over it
BS_BASE = {**BASE_FILES, "src/contest/old.py": "z = 1\n", "src/myapp.py": "m = 1\n",
           "hooks/test_guard.py": "def test_g():\n    assert True\n",
           "lint/test_retired_repos.py": "def test_retired():\n    assert True\n",
           "docs/catalog.md": "catalog\n", "docs/records.md": "records\n", "docs/map/hooks.md": "map\n",
           # an in-repo pointer's target, and the files the pointer and folder cases change
           "docs/briefs/brief-t7.md": BS_POINTER_TEXT + "\n",
           "hooks/guard.py": "g = 1\n", "hooks/other.py": "o = 1\n",
           "app/[id]/page.tsx": "export default 1\n", "app/other/index.tsx": "export default 2\n",
           "docs/decisions/x.md": "x\n", "docs/decisions-old/x.md": "y\n",
           # a cited brief file in the checkout, a file a route path with a dollar sign names, and a pointer misfire's file
           "docs/decisions/brief-claim-has-probe.md": "Claim has a probe.\nFiles: `hooks/guard.py`.\n",
           "hooks/agent_brief.py": "a = 1\n", "src/routes/posts.$id.tsx": "route 1\n",
           BS_LONG_NAME: "s\n"}
BS_NOTES_BASE = {**BASE_FILES, "notes/verdict-1.md": "v1\n", "notes/verdict-2.md": "v2\n",
                 **{name: "t\n" for name in BS_TOOL_NOTES}}
# The briefs, by key. Each is one agent's first user message.
BS_BRIEFS = {
    "exact": "Task: fix the contest score.\nFiles: `src/app.py`. Report in 10 lines.",
    "bare": "Task: fix the contest score.\nFiles: app.py. Report in 10 lines.",
    "dir": "Task: add the contest cases.\nFiles: the cases under `src/contest/`. Report in 10 lines.",
    "glob": "Task: tidy the sources.\nFiles: `src/*.py`. Report in 10 lines.",
    "nopaths": "Task: make the timeout case pass and report back.",
    "lone": "Don't rewrite the parser.\nFiles: `src/app.py`. Report in 10 lines.",
    "author": "Task: add the retired-repos case.\nFiles: `hooks/test_guard.py`. Report in 10 lines.",
    "notes": "Task: write the verdict notes.\nFiles: the notes named by the prefix `verdict-`. Report in 10 lines.",
    "other": "Task: fix the contest score.\nFiles: `src/contest.py`. Report in 10 lines.",
    "bracket": "Task: fix the page.\nFiles: `app/[id]/page.tsx`. Report in 10 lines.",
    "folder": "Task: amend the decisions.\nFiles: `docs/decisions`. Report in 10 lines.",
    "slowglob": "Task: tidy the sources.\nFiles: `src/*a*a*a*a*a*a*a*a*a*a.py`. Report in 10 lines.",
    "misfire": "Task: fix hooks/agent_brief.py. Governing: docs/decisions/brief-claim-has-probe.md.",
    "prose": "Task: make the timeout case pass and/or report back. Check I/O and pass/fail in Round 2/3. "
             "Report in 10 lines.",
    "dollar": "Task: fix the post route.\nFiles: `src/routes/posts.$id.tsx`. Report in 10 lines.",
    "abs-other": "Task: fix the guard.\nFiles: " + os.path.join(DIFFROOT, "bs-abs-other-main", "hooks", "guard.py")
                 + ". Report in 10 lines.",
    "abs-guard": "Task: fix the guard.\nFiles: " + os.path.join(DIFFROOT, "bs-abs-guard-main", "hooks", "guard.py")
                 + ". Report in 10 lines.",
    # a Windows drive path quoted with no repo path, and the same brief beside a repo path
    "drive": r"Fix the Windows failure. The log is at C:\Users\runneradmin\out.txt",
    "drive-named": "Fix the Windows failure. The log is at C:\\Users\\runneradmin\\out.txt\n"
                   "Files: `src/app.py`. Report in 10 lines.",
}


def _bs_user(content):
    """One user record, as the harness writes it. The content is a string, or a list of text blocks."""
    return json.dumps({"type": "user", "timestamp": BS_TIME,
                       "message": {"role": "user", "content": content}})


BS_LINES = {key: [_bs_user(text)] for key, text in BS_BRIEFS.items()}
# The first user message is the brief. A later one that names a path adds nothing.
BS_LINES["later"] = [_bs_user(BS_BRIEFS["exact"]),
                     _bs_user("Also change `src/contest.py` while you are there.")]
# A brief whose content is a list of text blocks, the other shape a user record takes.
BS_LINES["list"] = [json.dumps({"type": "user", "timestamp": BS_TIME, "message": {
    "role": "user", "content": [{"type": "text", "text": BS_BRIEFS["exact"]}]}})]
# A pointer brief: its first user message names a file that holds the brief. The target is in tmp (an
# absolute path); the chain file names the target, and the guard must not follow it a second time.
BS_POINTER_DIR = os.path.join(ROOT, "briefscope", "pointers")
BS_POINTER_TARGET = os.path.join(BS_POINTER_DIR, "brief-guard.md")
BS_POINTER_CHAIN = os.path.join(BS_POINTER_DIR, "brief-chain.md")
BS_POINTER_MISSING = os.path.join(BS_POINTER_DIR, "brief-missing.md")   # never written
BS_LINES["ptr-abs"] = [_bs_user("Read your full brief at " + BS_POINTER_TARGET)]
BS_LINES["ptr-repo"] = [_bs_user("Read your full brief at docs/briefs/brief-t7.md")]
BS_LINES["ptr-missing"] = [_bs_user("Read your full brief at " + BS_POINTER_MISSING)]
BS_LINES["ptr-chain"] = [_bs_user("Read your full brief at " + BS_POINTER_CHAIN)]
# A pointer cited inside a message that names its own files: the message's names stand beside the file's.
BS_LINES["ptr-names"] = [_bs_user("Files: hooks/other.py. Full brief at " + BS_POINTER_TARGET)]
BS_LINES["ptr-missing-names"] = [_bs_user("Files: `hooks/guard.py`. Full brief at " + BS_POINTER_MISSING)]
# One id per agent, none a prefix of another. `missing` gets no file; `unreadable` gets a folder.
BS_IDS = {key: "b5a%013x" % n for n, key in enumerate(
    ["exact", "bare", "dir", "glob", "nopaths", "lone", "author", "notes", "other", "later", "list",
     "ptr-abs", "ptr-repo", "ptr-missing", "ptr-chain", "bracket", "folder", "slowglob",
     "missing", "unreadable", "misfire", "prose", "dollar", "abs-other", "abs-guard", "ptr-names",
     "ptr-missing-names", "drive", "drive-named"], 1)}


def bs_agent(key):
    """The agent's own transcript, beside the session's: `<session stem>/subagents/agent-<id>.jsonl`."""
    return os.path.join(BS_PROJECT, BS_SESSION, "subagents", "agent-%s.jsonl" % BS_IDS[key])


def build_bs_transcripts():
    write(BS_TRANSCRIPT, _bs_user("session") + "\n")
    for key, lines in BS_LINES.items():
        write(bs_agent(key), "\n".join(lines) + "\n")
    os.makedirs(bs_agent("unreadable"), exist_ok=True)   # a folder where the file belongs: open() fails
    write(BS_POINTER_TARGET, BS_POINTER_TEXT + "\n")
    write(BS_POINTER_CHAIN, "Read your full brief at " + BS_POINTER_TARGET + "\n")


lazy_fixture([BS_TRANSCRIPT] + [bs_agent(key) for key in BS_IDS], build_bs_transcripts)


def bs_repo(name, change, files=None):
    return diff_repo("bs-" + name, change, files=files or BS_BASE)


def _write_all(*pairs):
    """A change that writes each (path, text) pair into the worktree."""
    def go(w):
        for rel, text in pairs:
            write(os.path.join(w, rel), text)
    return go


bs_app_unnamed = bs_repo("app-unnamed", _put("src/contest.py", "y = 2\n"))   # only `other` names this file
bs_app_named = bs_repo("app-named", _put("src/app.py", "x = 2\n"))
bs_new_file = bs_repo("new-file", _write_all(("src/app.py", "x = 2\n"), ("src/new_helper.py", "n = 1\n")))
bs_mixed = bs_repo("mixed", _write_all(("src/new_helper.py", "n = 1\n"), ("src/contest.py", "y = 2\n")))
bs_deleted = bs_repo("deleted", _rm("src/contest.py"))
bs_dir_named = bs_repo("dir-named", _put("src/contest/old.py", "z = 2\n"))
bs_myapp = bs_repo("myapp", _put("src/myapp.py", "m = 2\n"))
bs_results = bs_repo("results", _put("latest_results.md", "better\n"))
bs_generated = bs_repo("generated", _write_all(("src/app.py", "x = 2\n"), ("docs/catalog.md", "catalog 2\n"),
                                               ("docs/records.md", "records 2\n"), ("docs/map/hooks.md", "map 2\n")))
bs_author_named = bs_repo("author-named", _put("hooks/test_guard.py", "def test_g():\n    assert 1\n"))
bs_author_retired = bs_repo("author-retired", _put("lint/test_retired_repos.py", "def test_retired():\n    assert 1\n"))
bs_notes_named = bs_repo("notes-named", _write_all(("notes/verdict-1.md", "v1 2\n"),
                                                   ("notes/verdict-2.md", "v2 2\n")), files=BS_NOTES_BASE)
bs_notes_other = bs_repo("notes-other", _write_all(("notes/verdict-1.md", "v1 2\n"),
                                                   *[(name, "t 2\n") for name in BS_TOOL_NOTES]),
                         files=BS_NOTES_BASE)


def bs_judge(name, expected, repo, role=None, key=None, command=COMMIT, transcript=True, rule=None, lacks=(),
             carries=None):
    """One commit or push by an agent of `role` whose brief is `key`. Role None is the main session.
    `carries` replaces the fragments a refusal must hold, which are BS_REMEDY when a rule is named."""
    sh(name, command, expected, rule=rule, cwd=repo, agent_id=BS_IDS[key] if key else None,
       agent_type=role, transcript=BS_TRANSCRIPT if transcript else None, lacks=lacks,
       carries=carries if carries is not None else (BS_REMEDY if rule else ()))


def bs_stop(name, expected, repo, role, key, stop_active=False, rule=None, lacks=()):
    """The agent's SubagentStop, with both transcript fields the harness sends at a stop."""
    body = {"hook_event_name": "SubagentStop", "cwd": repo, "agent_id": BS_IDS[key], "agent_type": role,
            "transcript_path": BS_TRANSCRIPT, "agent_transcript_path": bs_agent(key)}
    if stop_active:
        body["stop_hook_active"] = True
    # The raw JSON doubles Windows backslashes, so materialize_for cannot match the transcript in it.
    add(name, expected, rule=rule, raw=json.dumps(body), cwd=repo, lacks=lacks, transcript=BS_TRANSCRIPT,
        carries=BS_REMEDY if rule else ())


# ---- refused: a modified or deleted file outside the brief, at commit, push and the first stop
bs_judge("brief-scope: a builder's commit of an unnamed existing file is denied", "deny", bs_app_unnamed,
         "builder", "exact", rule=BS_RULE, lacks="src/contest.py")
bs_judge("brief-scope: a builder's push of an unnamed existing file is denied", "deny", bs_app_unnamed,
         "builder", "exact", command=PUSH, rule=BS_RULE, lacks="src/contest.py")
bs_stop("brief-scope: a builder's first stop with an unnamed existing file is blocked", "deny", bs_app_unnamed,
        "builder", "exact", rule=BS_RULE, lacks="src/contest.py")
# The second stop of that same diff is allowed (stop_hook_active). Its log line is in the log checks below.
bs_stop("brief-scope: a builder's second stop with that file is allowed", "allow", bs_app_unnamed,
        "builder", "exact", stop_active=True)
bs_judge("brief-scope: a test-author's commit of an unnamed test file is denied", "deny", bs_author_retired,
         "test-author", "author", rule=BS_RULE, lacks="lint/test_retired_repos.py")
bs_judge("brief-scope: a test-author's push of an unnamed test file is denied", "deny", bs_author_retired,
         "test-author", "author", command=PUSH, rule=BS_RULE, lacks="lint/test_retired_repos.py")
bs_stop("brief-scope: a test-author's first stop with an unnamed test file is blocked", "deny", bs_author_retired,
        "test-author", "author", rule=BS_RULE, lacks="lint/test_retired_repos.py")
bs_judge("brief-scope: a record-writer's commit of 12 notes its brief does not name is denied", "deny",
         bs_notes_other, "record-writer", "notes", rule=BS_RULE, lacks="notes/tool-a-01.md")
bs_judge("brief-scope: a record-writer's push of 12 notes its brief does not name is denied", "deny",
         bs_notes_other, "record-writer", "notes", command=PUSH, rule=BS_RULE, lacks="notes/tool-a-01.md")
bs_stop("brief-scope: a record-writer's first stop with 12 notes its brief does not name is blocked", "deny",
        bs_notes_other, "record-writer", "notes", rule=BS_RULE, lacks="notes/tool-a-01.md")
bs_judge("brief-scope: a deleted unnamed file is denied", "deny", bs_deleted, "builder", "exact",
         rule=BS_RULE, lacks="src/contest.py")
bs_judge("brief-scope: a new unnamed file beside a modified unnamed one is denied", "deny", bs_mixed,
         "builder", "exact", rule=BS_RULE, lacks="src/contest.py")
bs_judge("brief-scope: a dir ending in a slash does not name a file that only shares its prefix", "deny",
         bs_app_unnamed, "builder", "dir", rule=BS_RULE, lacks="src/contest.py")
bs_judge("brief-scope: a bare basename does not name a file that only contains it", "deny", bs_myapp,
         "builder", "bare", rule=BS_RULE, lacks="src/myapp.py")
bs_judge("brief-scope: a glob names only the files it matches", "deny", bs_results, "builder", "glob",
         rule=BS_RULE, lacks="latest_results.md")
bs_judge("brief-scope: a lone apostrophe in the brief does not hide its named path", "deny", bs_app_unnamed,
         "builder", "lone", rule=BS_RULE, lacks="src/contest.py")
bs_judge("brief-scope: only the first user message of the agent's transcript is its brief", "deny",
         bs_app_unnamed, "builder", "later", rule=BS_RULE, lacks="src/contest.py")
bs_judge("brief-scope: a brief whose content is a list of text blocks is read", "deny", bs_app_unnamed,
         "builder", "list", rule=BS_RULE, lacks="src/contest.py")
# ---- allowed: a file the brief names, a file it covers, a generated page, a new file, and the non-judged calls
bs_judge("brief-scope: a file named exactly is allowed", "allow", bs_app_named, "builder", "exact")
bs_judge("brief-scope: a file under a named dir is allowed", "allow", bs_dir_named, "builder", "dir")
bs_judge("brief-scope: a file a named glob matches is allowed", "allow", bs_app_named, "builder", "glob")
bs_judge("brief-scope: a named bare basename allows its file", "allow", bs_app_named, "builder", "bare")
bs_judge("brief-scope: a generated page beside the named file is not counted", "allow", bs_generated,
         "builder", "exact")
bs_judge("brief-scope: a record-writer's commit of the named notes is allowed", "allow", bs_notes_named,
         "record-writer", "notes")
bs_stop("brief-scope: a record-writer's first stop with the named notes is allowed", "allow", bs_notes_named,
        "record-writer", "notes")
bs_judge("brief-scope: a test-author's commit of the named test file is allowed", "allow", bs_author_named,
         "test-author", "author")
bs_judge("brief-scope: an agent may commit a file its own brief names, though another brief names it too",
         "allow", bs_app_unnamed, "builder", "other")
bs_judge("brief-scope: a new unnamed file is allowed", "allow", bs_new_file, "builder", "exact")
bs_judge("brief-scope: a brief that names no path allows an unnamed file", "allow", bs_app_named, "builder",
         "nopaths")
bs_judge("brief-scope: a brief file that is missing allows the commit", "allow", bs_app_unnamed, "builder",
         "missing")
bs_judge("brief-scope: a brief file that cannot be read allows the commit", "allow", bs_app_unnamed,
         "builder", "unreadable")
bs_judge("brief-scope: a call with no transcript path allows the commit", "allow", bs_app_unnamed, "builder",
         "exact", transcript=False)
bs_judge("brief-scope: the main session's commit is not judged", "allow", bs_app_unnamed)
bs_judge("brief-scope: a reviewer's commit is not judged", "allow", bs_app_unnamed, "reviewer", "exact")


def bs_history(name, *steps, primary=False):
    """A worktree on `work`, cut from a base that is also origin/main, after `steps` (each takes the
    worktree): the agent's own commits and its uncommitted changes, as the agent leaves them. `primary`
    puts the worktree under the main checkout's .claude/worktrees, where an agent's worktree sits."""
    main = os.path.join(DIFFROOT, "bs-" + name + "-main")
    where = (os.path.join(main, ".claude", "worktrees", "agent-" + name) if primary
             else os.path.join(DIFFROOT, "bs-" + name))

    def build():
        make_repo(main, BS_BASE)
        _must(main, "update-ref", "refs/remotes/origin/main", "HEAD")
        made = run_vcs(main, "worktree", "add", "-q", "-b", "work", where)
        if made.returncode != 0:
            sys.exit("fixture setup failed: worktree in %r: %s" % (where, made.stderr.strip()))
        for step in steps:
            step(where)
    lazy_fixture([where, main], build)
    return where


def _own_commit(message, *pairs):
    """An own commit that writes each (path, text) pair, then commits them with `message`."""
    def go(w):
        for rel, text in pairs:
            write(os.path.join(w, rel), text)
        _must(w, "add", "-A")
        _must(w, *IDENT, "commit", "-q", "-m", message)
    return go


def _revert_head(w):
    _must(w, *IDENT, "revert", "--no-edit", "HEAD")


# ---- a pointer brief is read, and the pointer path itself is not a scope path
bs_ptr_other = bs_repo("ptr-other", _put("hooks/other.py", "o = 2\n"))
bs_ptr_guard = bs_repo("ptr-guard", _put("hooks/guard.py", "g = 2\n"))
bs_ptr_pointer = bs_repo("ptr-pointer", _put("docs/briefs/brief-t7.md", BS_POINTER_TEXT + "\nEdited.\n"))
bs_judge("brief-scope: a pointer to a brief in tmp is read: a commit of a file it does not name is denied",
         "deny", bs_ptr_other, "builder", "ptr-abs", rule=BS_RULE, lacks="hooks/other.py")
bs_judge("brief-scope: a pointer to a brief in tmp is read: a commit of the file it names is allowed",
         "allow", bs_ptr_guard, "builder", "ptr-abs")
bs_judge("brief-scope: an in-repo pointer is read: a commit of the file it names is allowed",
         "allow", bs_ptr_guard, "builder", "ptr-repo")
bs_judge("brief-scope: an in-repo pointer is read: a commit of a file it does not name is denied",
         "deny", bs_ptr_other, "builder", "ptr-repo", rule=BS_RULE, lacks="hooks/other.py")
bs_judge("brief-scope: the pointer file is not a scope path: a commit of it is denied", "deny", bs_ptr_pointer,
         "builder", "ptr-repo", rule=BS_RULE, lacks="docs/briefs/brief-t7.md")
bs_judge("brief-scope: a pointer inside a pointer is not followed a second time", "allow", bs_ptr_other,
         "builder", "ptr-chain")

# ---- a file an own earlier commit added is new, judged against the agent's base (origin/main)
bs_hist_new = bs_history("hist-new", _own_commit("add helper", ("src/new_helper.py", "n = 1\n")),
                         _put("src/new_helper.py", "n = 2\n"))
bs_hist_new2 = bs_history("hist-new2", _own_commit("add helper", ("src/new_helper.py", "n = 1\n")),
                          _own_commit("change helper", ("src/new_helper.py", "n = 2\n")))
bs_hist_old = bs_history("hist-old", _own_commit("change contest", ("src/contest.py", "y = 2\n")))
bs_revert = bs_history("revert", _own_commit("add helper", ("src/new_helper.py", "n = 1\n")), _revert_head)
bs_judge("brief-scope: a file an own commit added is new: a later change to it in the tree is allowed",
         "allow", bs_hist_new, "builder", "exact")
bs_judge("brief-scope: a file one own commit added and a later own commit changed is new: the push is allowed",
         "allow", bs_hist_new2, "builder", "exact", command=PUSH)
bs_judge("brief-scope: a file at the base that an own commit changes is refused at push", "deny", bs_hist_old,
         "builder", "exact", command=PUSH, rule=BS_RULE, lacks="src/contest.py")
bs_judge("brief-scope: a git revert of an own commit is not judged", "allow", bs_revert, "builder", "exact",
         command=PUSH)

# ---- a bracketed path keeps its brackets; a folder with no slash or extension covers its files
bs_brackets_other = bs_repo("brackets-other", _put("app/other/index.tsx", "export default 3\n"))
bs_brackets_named = bs_repo("brackets-named", _put("app/[id]/page.tsx", "export default 3\n"))
bs_folder_under = bs_repo("folder-under", _put("docs/decisions/x.md", "x 2\n"))
bs_folder_sibling = bs_repo("folder-sibling", _put("docs/decisions-old/x.md", "y 2\n"))
bs_judge("brief-scope: a bracketed path keeps its brackets: a commit of a sibling folder is denied", "deny",
         bs_brackets_other, "builder", "bracket", rule=BS_RULE, lacks="app/other/index.tsx")
bs_judge("brief-scope: a bracketed path names its file whole: a commit of that file is allowed", "allow",
         bs_brackets_named, "builder", "bracket")
bs_judge("brief-scope: a folder named with no slash or extension covers the files under it", "allow",
         bs_folder_under, "builder", "folder")
bs_judge("brief-scope: a folder covers whole segments: one that only shares its name is denied", "deny",
         bs_folder_sibling, "builder", "folder", rule=BS_RULE, lacks="docs/decisions-old/x.md")

# ---- a glob with ten stars is judged in under two seconds
bs_slow_glob = bs_repo("slow-glob", _put(BS_LONG_NAME, "s 2\n"))
add("brief-scope: a glob with ten stars is judged in under two seconds", "deny", rule=BS_RULE,
    tool="Bash", cwd=bs_slow_glob, agent_id=BS_IDS["slowglob"], agent_type="builder",
    transcript=BS_TRANSCRIPT, max_seconds=2, carries=BS_REMEDY, lacks=BS_LONG_NAME, command=COMMIT)


# ---- a cited brief file is read beside the message's own names; a slash word in prose is no path; a path keeps
# its dollar sign; an absolute path under the primary checkout names its file; the push refusal names the stop
bs_misfire = bs_repo("misfire", _put("hooks/agent_brief.py", "a = 2\n"))
bs_dollar = bs_repo("dollar", _put("src/routes/posts.$id.tsx", "route 2\n"))
bs_abs_other = bs_history("abs-other", _put("hooks/other.py", "o = 2\n"), primary=True)
bs_abs_guard = bs_history("abs-guard", _put("hooks/guard.py", "g = 2\n"), primary=True)
bs_judge("brief-scope: a cited brief file that is not the whole brief adds the message's own names: a commit of the "
         "file the message names is allowed", "allow", bs_misfire, "builder", "misfire")
bs_judge("brief-scope: a read pointer adds the message's own names: a commit of the file the message names is allowed",
         "allow", bs_ptr_other, "builder", "ptr-names")
bs_judge("brief-scope: an unreadable pointer allows a commit of a file the message does not name",
         "allow", bs_ptr_other, "builder", "ptr-missing-names")
bs_judge("brief-scope: slash words in prose are not paths: a commit of an unnamed file is allowed", "allow",
         bs_app_named, "builder", "prose")
bs_judge("brief-scope: a path with a dollar sign stays whole: a commit of the file it names is allowed", "allow",
         bs_dollar, "builder", "dollar")
bs_judge("brief-scope: an absolute path under the primary checkout names the repo-relative file: a commit of another "
         "file is denied", "deny", bs_abs_other, "builder", "abs-other", rule=BS_RULE, lacks="hooks/other.py")
bs_judge("brief-scope: an absolute path under the primary checkout names the repo-relative file: a commit of that "
         "file is allowed", "allow", bs_abs_guard, "builder", "abs-guard")
bs_judge("brief-scope: a push refusal says to stop and report a change an own commit holds", "deny", bs_app_unnamed,
         "builder", "exact", command=PUSH, rule=BS_RULE, lacks="src/contest.py",
         carries=BS_REMEDY + (BS_STOP_REPORT,))

# ---- a Windows drive path in the brief is no repo path: beside a named file it names nothing, so it adds no name
bs_judge("brief-scope: a drive path beside a repo path that names the changed file: a commit of that file is allowed",
         "allow", bs_app_named, "builder", "drive-named")
bs_judge("brief-scope: a drive path beside a named repo file: a commit of an unnamed file is denied", "deny",
         bs_app_unnamed, "builder", "drive-named", rule=BS_RULE, lacks="src/contest.py")


def _bs_scope(repo, rel):
    """The fixture's own change, read from git before any guard call: a log check judges only what it built."""
    status = run_vcs(repo, "status", "--porcelain", "--untracked-files=all")
    if rel in status.stdout:
        return ""
    return "the fixture does not change %s in %s: %s" % (rel, repo, status.stdout.strip()[:80])


def _bs_bodies(repo, role, key, commands, transcript=True, stop_active=False):
    """The payloads of one agent: each command, then its SubagentStop, as the harness sends them."""
    base = {"cwd": repo, "agent_type": role}
    if key:
        base["agent_id"] = BS_IDS[key]
    if transcript:
        base["transcript_path"] = BS_TRANSCRIPT
    bodies = [dict(base, tool_name="Bash", tool_input={"command": c}) for c in commands]
    stop = dict(base, hook_event_name="SubagentStop")
    if transcript and key:
        stop["agent_transcript_path"] = bs_agent(key)
    if stop_active:
        stop["stop_hook_active"] = True
    return bodies + [stop]


def bs_logged(folder, repo, changed, bodies, rule, startswith=False):
    """Scope first: the fixture changed each path in `changed`. Then every call is allowed and the log holds `rule`."""
    materialize(repo)
    materialize(BS_TRANSCRIPT)
    for rel in changed:
        problem = _bs_scope(repo, rel)
        if problem:
            return False, problem
    outs, rows = _log_run(folder, bodies)
    decisions = [read_decision(out)[0] for out in outs]
    rules = [row[3] for row in rows if len(row) > 3]
    problems = []
    if any(d != "allow" for d in decisions):
        problems.append("expected an allow at each call, got %r" % decisions)
    if not any(r == rule or (startswith and r.startswith(rule)) for r in rules):
        problems.append("no %s line in the log: %r" % (rule, rules))
    return (not problems), ("; ".join(problems) or "each call allowed, and the log holds %s" % rule)


def bs_new_log():
    return bs_logged(os.path.join(ROOT, "briefscope-log-new"), bs_new_file, ["src/new_helper.py", "src/app.py"],
                     _bs_bodies(bs_new_file, "builder", "exact", [COMMIT]), BS_NEW)


def bs_nopaths_log():
    return bs_logged(os.path.join(ROOT, "briefscope-log-nopaths"), bs_app_named, ["src/app.py"],
                     _bs_bodies(bs_app_named, "builder", "nopaths", [COMMIT]), BS_UNNAMED)


def bs_second_stop_log():
    return bs_logged(os.path.join(ROOT, "briefscope-log-second-stop"), bs_app_unnamed, ["src/contest.py"],
                     _bs_bodies(bs_app_unnamed, "builder", "exact", [], stop_active=True), "brief-scope",
                     startswith=True)


def bs_unread_log():
    """A brief that cannot be read allows each call and logs brief-scope-unread: no transcript path, no file, a folder."""
    materialize(bs_app_unnamed)
    materialize(BS_TRANSCRIPT)
    problem = _bs_scope(bs_app_unnamed, "src/contest.py")
    if problem:
        return False, problem
    problems = []
    for suffix, key, transcript in (("no-path", "exact", False), ("missing", "missing", True),
                                    ("folder", "unreadable", True)):
        outs, rows = _log_run(os.path.join(ROOT, "briefscope-log-" + suffix),
                              _bs_bodies(bs_app_unnamed, "builder", key, [COMMIT], transcript=transcript))
        decisions = [read_decision(out)[0] for out in outs]
        rules = [row[3] for row in rows if len(row) > 3]
        if any(d != "allow" for d in decisions):
            problems.append("%s: expected an allow at each call, got %r" % (suffix, decisions))
        if BS_UNREAD not in rules:
            problems.append("%s: no %s line in the log: %r" % (suffix, BS_UNREAD, rules))
    return (not problems), ("; ".join(problems) or "an unreadable brief allows each call and logs %s" % BS_UNREAD)


def bs_fixture_check():
    """Each fixture holds the change its cases judge, read from git first: a red case then fails on the rule, not on its repo."""
    wants = [(bs_app_unnamed, "src/contest.py"), (bs_app_named, "src/app.py"),
             (bs_new_file, "src/new_helper.py"), (bs_new_file, "src/app.py"),
             (bs_mixed, "src/new_helper.py"), (bs_mixed, "src/contest.py"), (bs_deleted, "src/contest.py"),
             (bs_dir_named, "src/contest/old.py"), (bs_myapp, "src/myapp.py"), (bs_results, "latest_results.md"),
             (bs_generated, "src/app.py"), (bs_generated, "docs/catalog.md"), (bs_generated, "docs/records.md"),
             (bs_generated, "docs/map/hooks.md"), (bs_author_named, "hooks/test_guard.py"),
             (bs_author_retired, "lint/test_retired_repos.py"), (bs_notes_named, "notes/verdict-1.md"),
             (bs_notes_named, "notes/verdict-2.md")]
    wants += [(bs_notes_other, name) for name in ["notes/verdict-1.md"] + BS_TOOL_NOTES]
    wants += [(bs_ptr_other, "hooks/other.py"), (bs_ptr_guard, "hooks/guard.py"),
              (bs_ptr_pointer, "docs/briefs/brief-t7.md"), (bs_hist_new, "src/new_helper.py"),
              (bs_brackets_other, "app/other/index.tsx"), (bs_brackets_named, "app/[id]/page.tsx"),
              (bs_folder_under, "docs/decisions/x.md"), (bs_folder_sibling, "docs/decisions-old/x.md"),
              (bs_slow_glob, BS_LONG_NAME)]
    wants += [(bs_misfire, "hooks/agent_brief.py"), (bs_dollar, "src/routes/posts.$id.tsx"),
              (bs_abs_other, "hooks/other.py"), (bs_abs_guard, "hooks/guard.py")]
    materialize(bs_misfire)
    if not os.path.isfile(os.path.join(bs_misfire, "docs", "decisions", "brief-claim-has-probe.md")):
        return False, "the fixture in %s has no cited brief file to read" % bs_misfire
    for repo in (bs_abs_other, bs_abs_guard):
        materialize(repo)
        if os.path.basename(os.path.dirname(os.path.dirname(repo))) != ".claude":
            return False, "the fixture in %s has its worktree outside the primary's .claude folder" % repo
    for repo, rel in wants:
        materialize(repo)
        problem = _bs_scope(repo, rel)
        if problem:
            return False, problem
    # The history fixtures hold their own commits, and each has origin/main, read from git.
    history = [(bs_hist_new, "add helper"), (bs_hist_new2, "change helper"), (bs_hist_old, "change contest"),
               (bs_revert, 'Revert "add helper"')]
    for repo, subject in history:
        materialize(repo)
        subjects = run_vcs(repo, "log", "--format=%s", "-n", "3").stdout.splitlines()
        if subject not in subjects:
            return False, "the fixture in %s has no own commit %r: %s" % (repo, subject, subjects)
        if run_vcs(repo, "rev-parse", "--verify", "-q", "origin/main").returncode != 0:
            return False, "the fixture in %s has no origin/main" % repo
    return True, "every fixture holds the change its cases judge (%d paths, %d histories)" % (
        len(wants), len(history))


def bs_pointer_missing_log():
    """A pointer to a brief that is not there allows the commit and logs brief-scope-unread."""
    return bs_logged(os.path.join(ROOT, "briefscope-log-pointer-missing"), bs_ptr_other, ["hooks/other.py"],
                     _bs_bodies(bs_ptr_other, "builder", "ptr-missing", [COMMIT]), BS_UNREAD)


def bs_ptr_missing_names_log():
    """An unreadable pointer beside the message's own names allows the commit and logs brief-scope-unread."""
    return bs_logged(os.path.join(ROOT, "briefscope-log-pointer-missing-names"), bs_ptr_other, ["hooks/other.py"],
                     _bs_bodies(bs_ptr_other, "builder", "ptr-missing-names", [COMMIT]), BS_UNREAD)


def bs_prose_log():
    """A slash word in the prose is no path: the file is allowed and the log holds brief-scope-unnamed."""
    return bs_logged(os.path.join(ROOT, "briefscope-log-prose"), bs_app_named, ["src/app.py"],
                     _bs_bodies(bs_app_named, "builder", "prose", [COMMIT]), BS_UNNAMED)


LOG_CHECKS_EXTRA.append(("brief-scope: each fixture repo holds the change its cases judge", bs_fixture_check))
LOG_CHECKS_EXTRA.append(("brief-scope: a new unnamed file is allowed and logged brief-scope-new", bs_new_log))
LOG_CHECKS_EXTRA.append(("brief-scope: a brief that names no path is allowed and logs brief-scope-unnamed",
                         bs_nopaths_log))
LOG_CHECKS_EXTRA.append(("brief-scope: an unreadable brief is allowed and logs brief-scope-unread, with no "
                         "transcript path, a missing file or a folder", bs_unread_log))
LOG_CHECKS_EXTRA.append(("brief-scope: a second stop with an unnamed file is allowed and logs a brief-scope "
                         "line", bs_second_stop_log))
LOG_CHECKS_EXTRA.append(("brief-scope: a pointer to a missing brief is allowed and logs brief-scope-unread",
                         bs_pointer_missing_log))
LOG_CHECKS_EXTRA.append(("brief-scope: an unreadable pointer beside the message's own names allows the commit and "
                         "logs brief-scope-unread", bs_ptr_missing_names_log))
LOG_CHECKS_EXTRA.append(("brief-scope: a slash word in prose allows an unnamed file and logs brief-scope-unnamed",
                         bs_prose_log))


def bs_drive_log():
    """A Windows drive path quoted in the brief names no repo path off Windows: a change to the existing file
    it does not name is allowed at each call, and the log holds brief-scope-unnamed."""
    return bs_logged(os.path.join(ROOT, "briefscope-log-drive"), bs_app_named, ["src/app.py"],
                     _bs_bodies(bs_app_named, "builder", "drive", [COMMIT]), BS_UNNAMED)


LOG_CHECKS_EXTRA.append(("brief-scope: a drive path quoted in the brief names no repo path: the change is allowed "
                         "and logs brief-scope-unnamed", bs_drive_log))
