# section 22192
FAMILY = "lane-closes-after-records"


def archive_override_call(config, seconds):
    """One archive_session of a lane at OV_T0 + seconds, from the calling session the override names."""
    return decide({
        "raw": None, "tool": ARCHIVE_TOOL, "cwd": NOGIT, "session": ARCHIVE_OWNER,
        "env_path": fake_gh_path(ARCHOPEN), "config": config, "agent_id": None, "agent_type": None,
        "temp": None, "load": None, "env": dict(ROLE_ENV, LOCAL_TIME_NOW=ov_clock(seconds)),
        "tool_input": {"session_id": ROLE_OTHER}, "transcript": role_path("archive-lane"),
    })


def archive_override_case():
    """The owner override lifts the archive refusal: refused before a timed override, allowed under it."""
    config = ov_config("archive-lane")
    problem = ov_want(*archive_override_call(config, 0), "deny", ARCHIVE_RULE)
    if problem:
        return False, "before the override: " + problem
    note = ov_type(config, ARCHIVE_OWNER, "override 15m", 30)
    ok, why = ov_story([("under a timed override", lambda: archive_override_call(config, 60), "allow",
                         ARCHIVE_RULE)], note)
    return ok, why or "refused before the override, lifted under it"


def archive_matcher_case():
    """A guard matcher in settings.json covers archive_session, so the guard sees the call at all."""
    with open(os.path.join(REPO, "settings.json"), encoding="utf-8") as handle:
        entries = json.load(handle)["hooks"]["PreToolUse"]
    matchers = [entry.get("matcher", "") for entry in entries
                if any("guard.py" in hook.get("command", "") for hook in entry.get("hooks", []))]
    if any(re.fullmatch(matcher, ARCHIVE_TOOL) for matcher in matchers):
        return True, "a guard matcher covers archive_session"
    return False, "no guard matcher covers archive_session: %r" % (matchers,)


FIXTURELESS_CHECKS.add(archive_matcher_case)
LOG_CHECKS_EXTRA.append(("lane-closes-after-records: an owner override lifts the archive refusal",
                         archive_override_case))
LOG_CHECKS_EXTRA.append(("lane-closes-after-records: a settings.json matcher routes archive_session to the guard",
                         archive_matcher_case))


# The cost of lane-closes-after-records, pinned: one archive of a lane makes one gh call, a non-lane archive makes
# none, and an archive writes no file in the folders the session owns. Each check builds its own counted fake, so no
# other fake logs a call.
ARCHIVE_CALLS = "calls.log"  # the counted fake's log, beside its state: one line per gh call


def archive_judged(transcript, folder, agent_id=None):
    """The guard's verdict on one archive_session of ROLE_OTHER, from the batch runner, with the fake pull request
    tool at `folder` on PATH. The payload's cwd and the guard's process both run in NOGIT, so a write into the working
    folder shows in the snapshot. MERGECFG is the config folder: its rules file points at the repo, so a guard copy
    finds the merge tool there. `agent_id`, when given, makes the call an agent's."""
    return decide({
        "raw": None, "tool": ARCHIVE_TOOL, "cwd": NOGIT, "process_cwd": NOGIT, "session": None,
        "env_path": fake_gh_path(folder), "config": MERGECFG, "agent_id": agent_id, "agent_type": None,
        "temp": None, "load": None, "env": dict(ROLE_ENV), "tool_input": {"session_id": ROLE_OTHER},
        "transcript": transcript,
    })


def archive_counted_gh(repos=None, name="archcount"):
    """A counted pull request tool. Its one open pull request is on no slug, so an archive of a lane reads the open
    list and is allowed: a lane archive is allowed only after that read succeeds. `repos`, when given, holds each
    repo's answers (make_fake_gh's `repos`), for a lane whose record names branches; then no `need` pins a repo."""
    folder = os.path.join(ROOT, name)
    make_fake_gh(folder, "main", need=["o/r"] if repos is None else [], repos=repos,
                 count_file=os.path.join(folder, ARCHIVE_CALLS))
    return folder


def gh_calls_taken(folder, name=ARCHIVE_CALLS):
    """The lines the counted fake at `folder` logged since its log `name` was last taken. Taking the log clears it."""
    path = os.path.join(folder, name)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as handle:
        calls = [line for line in handle.read().splitlines() if line.strip()]
    os.remove(path)
    return calls


def tree_files(*roots):
    """Every file under `roots`, as path -> sha256, so a new file, a removed file and a changed byte each show."""
    files = {}
    for root in roots:
        for folder, _, names in os.walk(root):
            for name in names:
                path = os.path.join(folder, name)
                with open(path, "rb") as handle:
                    files[path] = hashlib.sha256(handle.read()).hexdigest()
    return files


def _gh_route(call):
    """The REST route a counted gh call names: argv[1] of `gh api <route> ...`, else ''."""
    argv = json.loads(call)
    return argv[1] if argv[:1] == ["api"] and len(argv) > 1 else ""


def archive_lane_one_read_case():
    """An archive of a lane reads the open pull requests in one gh call, and its repo's branches under each slug form in one
    call each (git/matching-refs/heads/<form>, the forms of lane_head_refs). Its open list names no slug: allowed."""
    from shared_names import lane_head_refs
    folder = archive_counted_gh()
    gh_calls_taken(folder)
    decision, reason = archive_judged(role_path("archive-lane"), folder)
    calls = gh_calls_taken(folder)
    if decision != "allow" or reason:
        return False, "a lane with no slug pull request on its open list: %s (%r)" % (decision, reason)
    opens, prefixes = 0, []
    for call in calls:
        route = _gh_route(call)
        if "/git/matching-refs/heads/" in route:
            prefixes.append(route.split("/git/matching-refs/heads/", 1)[1])
        elif route.endswith("/pulls"):
            opens += 1
    if opens != 1 or sorted(prefixes) != sorted(lane_head_refs(ARCHIVE_SLUG)) or len(calls) != 3:
        return False, "the open list once and one matching-refs read per slug form wanted, got %d open and refs %r (%d calls)" % (
            opens, prefixes, len(calls))
    return True, "3 gh calls: the open list, and the branches under each slug form; the lane is allowed"


def archive_non_lane_no_read_case():
    """A target that is no lane is not judged: its archive is allowed and makes no gh call, though its record carries
    a step slug that an open-list read would find."""
    folder = archive_counted_gh()
    gh_calls_taken(folder)
    decision, reason = archive_judged(role_path("archive-triage-slug"), folder)
    calls = gh_calls_taken(folder)
    if decision != "allow" or reason:
        return False, "a non-lane target: %s (%r)" % (decision, reason)
    if calls:
        return False, "a non-lane target made %d gh call(s): %r" % (len(calls), calls)
    return True, "allowed, and no gh call"


def archive_writes_nothing_case():
    """An archive of a lane writes no file in its working folder, its transcript folder or the config folder."""
    folder = archive_counted_gh()
    materialize(role_path("archive-lane"))  # the transcripts are written on first use: before the snapshot
    trees = (NOGIT, ROLE_DIR, MERGECFG)
    before = tree_files(*trees)
    decision, _ = archive_judged(role_path("archive-lane"), folder)
    after = tree_files(*trees)
    gh_calls_taken(folder)
    if decision != "allow":
        return False, "the lane archive was %s, not allowed, so it is not the allow path under test" % decision
    changed = sorted(set(before) ^ set(after)) + sorted(p for p in before if p in after and before[p] != after[p])
    if changed:
        return False, "the archive wrote %d file(s): %r" % (len(changed), changed[:5])
    return True, "no file changed in the working, transcript or config folder"


LOG_CHECKS_EXTRA.append(("lane-closes-after-records: a lane archive reads the open pull requests in one gh call",
                         archive_lane_one_read_case))
LOG_CHECKS_EXTRA.append(("lane-closes-after-records: a non-lane archive makes no gh call",
                         archive_non_lane_no_read_case))
LOG_CHECKS_EXTRA.append(("lane-closes-after-records: a lane archive writes no file in the session's folders",
                         archive_writes_nothing_case))


def archive_agent_non_lane_no_read_case():
    """An agent's archive of a target that is no lane is refused by agent-no-remote-tools, and makes no gh call, though
    its own record carries a step slug that an open-list read would find. lane-closes-after-records allows it first."""
    folder = archive_counted_gh()
    gh_calls_taken(folder)
    decision, reason = archive_judged(role_path("agent-own-triage-slug"), folder, agent_id=AGENT_OWN_ID)
    calls = gh_calls_taken(folder)
    if decision != "deny" or AGENT_NO_REMOTE not in reason:
        return False, "an agent's non-lane target: %s (%r)" % (decision, reason)
    if calls:
        return False, "an agent's non-lane target made %d gh call(s): %r" % (len(calls), calls)
    return True, "refused by %s, and no gh call" % AGENT_NO_REMOTE


LOG_CHECKS_EXTRA.append(("lane-closes-after-records: an agent's non-lane archive is refused by agent-no-remote-tools, and makes no gh call",
                         archive_agent_non_lane_no_read_case))


def archive_branch_reads_case():
    """A lane whose record names one branch, checked in each of its two repos, reads in one archive: one open list per
    repo, one matching-refs read per repo and slug form, one repo read per repo, one compare per repo x branch, and one
    pulls read for the branch that is ahead. The branch is ahead in q_max on an open pull request, so the archive is
    allowed, on 2 + 4 + 2 + 2 + 1 = 11 gh calls, not counting a tip read."""
    folder = archive_counted_gh(repos=arch_pair(qmax={"others": [arch_row(ARCH_BRANCH, 24)]}), name="archcount-branch")
    gh_calls_taken(folder)
    decision, reason = archive_judged(role_path("archive-inc"), folder)
    calls = gh_calls_taken(folder)
    if decision != "allow" or reason:
        return False, "a lane whose branch is ahead on an open pull request: %s (%r)" % (decision, reason)
    kinds = {"open list": 0, "repo read": 0, "compare": 0, "branch pulls": 0, "matching refs": 0}
    tips = 0  # a branch's tip read is not pinned here: the tip is read only where a pull request needs it
    for call in calls:
        argv = json.loads(call)
        route = _gh_route(call)
        if "/compare/" in route:
            kinds["compare"] += 1
        elif re.fullmatch(r"repos/[^/]+/[^/]+", route):
            kinds["repo read"] += 1
        elif route.endswith("/pulls") and any(arg.startswith("head=") for arg in argv):
            kinds["branch pulls"] += 1
        elif route.endswith("/pulls"):
            kinds["open list"] += 1
        elif "/git/matching-refs/heads/" in route:
            kinds["matching refs"] += 1
        elif re.search(r"/branches/[^/]", route):
            tips += 1
    want = {"open list": 2, "repo read": 2, "compare": 2, "branch pulls": 1, "matching refs": 4}
    if kinds != want or len(calls) - tips != sum(want.values()):
        return False, "a lane with a branch in each repo made gh calls %r, want %r (%d in all): %r" % (
            kinds, want, sum(want.values()), calls)
    return True, "11 gh calls: two open lists, two repo reads, two compares, one branch pulls read, four matching-refs reads"


LOG_CHECKS_EXTRA.append(("lane-closes-after-records: a lane whose record names a branch reads its repos in eleven gh calls",
                         archive_branch_reads_case))


def archive_copy_reads_case():
    """The archive copies of a stranded branch are listed once, and only the counted ones are compared with the tip. The
    listing is one matching-refs read of archive/<branch>. It holds four refs: the exact copy and archive/<branch>-2 are
    counted, each compared once; archive/<branch>y, which holds the tip, and archive/<branch>-r2 are listed and never
    compared. The branch is ahead on no pull request, so the refusal stands. A branch on an open pull request reads no
    copy at all, because that pull request covers it before any copy is read. Each run takes its own call log, and a copy
    read is a call whose route names archive/."""
    stranded = archive_counted_gh(repos={"o/r": arch_copies({
        ARCH_COPY_REF: "diverged", ARCH_COPY_REF + "-2": "ahead",
        ARCH_COPY_REF + "y": "identical", ARCH_COPY_REF + "-r2": "identical"})}, name="archcount-copy-stranded")
    gh_calls_taken(stranded)
    decision, reason = archive_judged(role_path("archive-copy-lane"), stranded)
    calls = gh_calls_taken(stranded)
    if decision != "deny" or ARCHIVE_NOPR_PIN[0] not in (reason or ""):
        return False, "the copies that miss the tip: %s (%r), want a refusal for no pull request" % (decision, reason)
    listings = [call for call in calls if _gh_route(call).endswith("/git/matching-refs/heads/" + ARCH_COPY_REF)]
    if len(listings) != 1:
        return False, "the refusal path listed the archive copies %d times, want once: %r" % (len(listings), calls)
    compared = sorted(_gh_route(call).split("/compare/", 1)[1] for call in calls if "/compare/archive/" in _gh_route(call))
    want = sorted([ARCH_COPY_REF + "..." + ARCH_COPY_TIP, ARCH_COPY_REF + "-2..." + ARCH_COPY_TIP])
    if compared != want:
        return False, "the archive copies compared were %r, want the exact copy and the -2 copy only, each once: %r" % (
            compared, want)
    covered = archive_counted_gh(repos={"o/r": arch_copy("identical", others=[arch_row(ARCH_COPY_BRANCH, 41)])},
                                 name="archcount-copy-covered")
    gh_calls_taken(covered)
    decision, reason = archive_judged(role_path("archive-copy-lane"), covered)
    calls = gh_calls_taken(covered)
    if decision != "allow" or reason:
        return False, "a branch on an open pull request: %s (%r), want allowed" % (decision, reason)
    touched = [call for call in calls if "/compare/archive/" in _gh_route(call) or "/git/matching-refs/heads/archive/" in _gh_route(call)]
    if touched:
        return False, "a branch on an open pull request read its archive copies %d times, want none: %r" % (len(touched), touched)
    return True, "the refusal path lists the archive copies once and compares the two counted ones once each; a branch on an open pull request reads none"


LOG_CHECKS_EXTRA.append(("lane-closes-after-records: an archive copy of a stranded branch is read once, and not on an open pull request",
                         archive_copy_reads_case))


# The cost of archive_hit's transcript reads: one open of each transcript of the archive (the target's main transcript,
# and for an agent's call the agent's own file beside it), each read once. The count is taken in process, on
# builtins.open, so a second read of the same file shows as a second open of its path.
class _EmptyPulls:
    """The merge tool's Host for one repo: the open list reads empty, and each branch prefix reads no ref."""

    def __init__(self, repo):
        self.repo = repo

    def pages(self, route, **kwargs):
        return []

    def api(self, route):
        return (0, "[]") if "git/matching-refs/heads/" in route else (1, "HTTP 404")


_NOPULL_TIP = "%040d" % 41  # the tip of the stranded branch in _AheadNoPull


class _AheadNoPull:
    """The merge tool's Host for each repo of the incident: the open list reads empty, the default branch is main, every
    compare of main and a branch reads ahead, and no pull request holds the branch. The branch's tip is _NOPULL_TIP, and
    the branch has no archive/ copy, so a compare of archive/<branch> answers 404."""

    def __init__(self, repo):
        self.repo = repo

    def pages(self, route, **kwargs):
        return []

    def api(self, route):
        if route == "":
            return 0, json.dumps({"default_branch": "main"})
        if route.startswith("compare/main..."):
            return 0, json.dumps({"status": "ahead"})
        if route.startswith("compare/archive/"):  # no archive copy of the branch: GitHub answers 404
            return 1, "HTTP 404"
        if "git/matching-refs/heads/" in route:
            return 0, "[]"
        if route.startswith("branches/"):  # the branch's tip, which _covered reads once no pull request holds the branch
            return 0, json.dumps({"name": route[len("branches/"):], "commit": {"sha": _NOPULL_TIP}})
        return 1, "HTTP 404"


def _load_guard_merge():
    """guard_merge.py beside the guard under test (GUARD), loaded fresh, so a patch to it touches no other load."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("guard_merge_under_test",
                                                  os.path.join(os.path.dirname(GUARD), "guard_merge.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _archive_opens(transcript, agent_id):
    """Run one archive of ROLE_OTHER's lane in process, with an empty open list, and count the opens of each transcript
    the archive reads. Returns (decision, {path: opens}), or (None, None) when the fixture is not as the case needs."""
    import builtins
    import types
    guard_merge = _load_guard_merge()
    expected = [os.path.abspath(transcript)]
    if agent_id:
        expected.append(os.path.abspath(guard_merge.own_session.agent_transcript_path(transcript, agent_id)))
    materialize(transcript)  # the fixtures are written on first use: before the count
    if not all(os.path.isfile(path) for path in expected):
        return None, None
    fake_tool = types.SimpleNamespace(Host=_EmptyPulls, shared_deadline=contextlib.nullcontext)
    real_open = builtins.open
    opened = {path: 0 for path in expected}

    def counting_open(file, *args, **kwargs):
        if isinstance(file, (str, os.PathLike)):
            path = os.path.abspath(os.fspath(file))
            if path in opened:
                opened[path] += 1
        return real_open(file, *args, **kwargs)

    with mock.patch.object(guard_merge, "merge_module", return_value=fake_tool), \
            mock.patch("builtins.open", counting_open):
        decision = guard_merge.archive_hit(ARCHIVE_TOOL, {"session_id": ROLE_OTHER}, transcript, agent_id=agent_id)
    return decision, opened


def archive_one_read_per_transcript_case():
    """An archive of a lane reads its target's transcript once. The open list reads empty and the record names no
    branch, so that one open is the whole archive's read of the transcript."""
    decision, opened = _archive_opens(role_path("archive-lane"), None)
    if opened is None:
        return False, "fixture: the lane transcript is not written as the case needs"
    if decision is not None:
        return False, "an archive of the lane with an empty open list was refused: %r" % (decision,)
    if list(opened.values()) != [1]:
        return False, "the archive opened the target's transcript %r times, want 1" % (list(opened.values()),)
    return True, "the archive opened the target's transcript once, and the lane is allowed"


def archive_agent_one_read_per_transcript_case():
    """An agent's archive of a lane reads each of its two transcripts once: the main transcript and the agent's own
    file beside it. The main record names no lane, and the agent's own record is the lane, with no branch to read."""
    decision, opened = _archive_opens(role_path("agent-own-lane"), AGENT_OWN_ID)
    if opened is None:
        return False, "fixture: the main or the agent transcript is not written as the case needs"
    if decision is not None:
        return False, "an agent's archive of the lane with an empty open list was refused: %r" % (decision,)
    if list(opened.values()) != [1, 1]:
        return False, "the agent's archive opened its two transcripts %r times, want one each" % (list(opened.values()),)
    return True, "the agent's archive opened its main and its own transcript once each, and the lane is allowed"


LOG_CHECKS_EXTRA.append(("lane-closes-after-records: an archive of a lane opens its target's transcript once",
                         archive_one_read_per_transcript_case))
LOG_CHECKS_EXTRA.append(("lane-closes-after-records: an agent's archive of a lane opens each of its two transcripts once",
                         archive_agent_one_read_per_transcript_case))


def archive_none_ccr_case():
    """A lane whose record reads as a lane, but whose ccr reads None, is refused. The branch read takes its branches from
    the ccr, so with none it cannot rule out a stranded branch, and the archive is refused rather than allowed. The control
    is the same lane with its ccr read: each repo reads the branch ahead on no pull request, so that archive is refused
    for the branch, and the case proves the fixture can refuse at all."""
    import types
    guard_merge = _load_guard_merge()
    transcript = role_path("archive-inc")
    materialize(transcript)
    real = guard_merge.merge_module()  # the merge tool, unpatched: its is_net reads the archive copy's 404 as the tool does
    if real is None:
        return False, "fixture: the merge tool does not load, so its is_net cannot read the archive copy's 404"
    fake_tool = types.SimpleNamespace(Host=_AheadNoPull, shared_deadline=contextlib.nullcontext, is_net=real.is_net)
    with mock.patch.object(guard_merge, "merge_module", return_value=fake_tool):
        control = guard_merge.archive_hit(ARCHIVE_TOOL, {"session_id": ROLE_OTHER}, transcript)
        with mock.patch.object(guard_merge.own_session, "own_session_ccr", return_value=None):
            decision = guard_merge.archive_hit(ARCHIVE_TOOL, {"session_id": ROLE_OTHER}, transcript)
    if control is None or control[0] != "archive of a lane with a branch that has no pull request":
        return False, "fixture: the lane with its ccr read is not refused for its stranded branch: %r" % (control,)
    if decision is None:
        return False, "an archive of a lane whose ccr reads None was allowed, want refused"
    return True, "an archive of a lane whose ccr reads None is refused: %s" % (decision[0],)


LOG_CHECKS_EXTRA.append(("lane-closes-after-records: an archive of a lane whose ccr reads None is refused",
                         archive_none_ccr_case))


def archive_closed_replaced_read_case():
    """A branch whose only cover is a closed pull request, replaced by a merged one, is allowed on one compare: the replacing
    head against the tip, one compare per closed pull request. The compare's base is the replacing head and its head is the
    tip, so behind or identical means the tip is contained in it, as the draft containment read reads its own."""
    replaced = {"others": [arch_row(ARCH_BRANCH, 23, state="closed"), arch_row(ARCH_BRANCH, 24, state="closed", merged=True)],
                "tips": {ARCH_BRANCH: REPLACED_TIP},
                "compares": {"main..." + ARCH_BRANCH: "ahead", REPLACING_HEAD + "..." + REPLACED_TIP: "behind"}}
    folder = archive_counted_gh(repos=arch_pair(qmax=replaced), name="archcount-closed")
    gh_calls_taken(folder)
    decision, reason = archive_judged(role_path("archive-inc"), folder)
    calls = gh_calls_taken(folder)
    if decision != "allow" or reason:
        return False, "a closed pull request replaced by a merged one holding the tip: %s (%r)" % (decision, reason)
    replacing = [call for call in calls if _gh_route(call).endswith("/compare/" + REPLACING_HEAD + "..." + REPLACED_TIP)]
    if len(replacing) != 1:
        return False, "one compare of the replacing head with the tip wanted, %d seen" % len(replacing)
    return True, "allowed, on one compare of the replacing head with the tip"


LOG_CHECKS_EXTRA.append(("lane-closes-after-records: a closed pull request replaced by a merged one reads one compare of the replacement",
                         archive_closed_replaced_read_case))


def archive_empty_branches_read_case():
    """A lane whose current_branches is an empty list is allowed, and its archive makes no branch read: no repo read, no
    compare, no pull request list of a branch and no tip read. Its open lists and slug-form reads are the only calls."""
    folder = archive_counted_gh(repos=arch_pair(qmax={"others": []}), name="archcount-empty")
    gh_calls_taken(folder)
    decision, reason = archive_judged(role_path("archive-inc-list-empty"), folder)
    calls = gh_calls_taken(folder)
    if decision != "allow" or reason:
        return False, "a lane whose current_branches is an empty list: %s (%r)" % (decision, reason)
    branch_reads = []
    for call in calls:
        route = _gh_route(call)
        if "/compare/" in route or re.fullmatch(r"repos/[^/]+/[^/]+", route) or re.search(r"/branches/[^/]", route):
            branch_reads.append(call)
        elif route.endswith("/pulls") and any(arg.startswith("head=") for arg in json.loads(call)):
            branch_reads.append(call)
    if branch_reads:
        return False, "an empty current_branches made %d branch read(s): %r" % (len(branch_reads), branch_reads)
    return True, "allowed, and the archive makes no branch read"


LOG_CHECKS_EXTRA.append(("lane-closes-after-records: a current_branches that is an empty list makes no branch read",
                         archive_empty_branches_read_case))


# The own-record reader on each shape, read directly. A check passes when the tags it reads are one of `accept`,
# where None is no record. The guard's archive and brief reads both go through this reader.
def _load_own_session():
    """hooks/own_session.py beside the guard under test (GUARD), so a mutant copy of the guard is the reader read."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("own_session_under_test",
                                                  os.path.join(os.path.dirname(GUARD), "own_session.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def own_read_case(fixture, accept):
    """A check: own_session_read, for the target ROLE_OTHER, reads the fixture's tags as one of `accept`. A raise
    fails the check and names the raise, so one bad fixture never ends the run."""
    def check():
        try:
            got = _load_own_session().own_session_read(role_path(fixture), ROLE_OTHER)[0]
        except Exception as error:
            return False, "own_session_read(%s) raises %s: %s" % (fixture, type(error).__name__, error)
        if any(got == want for want in accept):
            return True, "own_session_read reads %r" % (got,)
        return False, "own_session_read reads %r from %s, want one of %r" % (got, fixture, accept)
    return check


