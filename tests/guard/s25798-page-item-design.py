# section 25798
FAMILY = "page-item-design"

PD_STAMP = "waiting-page-published"  # the stamp file, in the git common dir
PD_DOC = "fill-of-volume-card"
PD_PAGE = os.path.join(ROOT, "pd", "design-page.html")  # main's page, with the mockups the cases name
PD_SLOT = '<script type="application/json" id="designData">{}</script>'
PD_MOCKS = {
    "m1": '<div id="vol" data-state="full" style="width:390px;height:844px">Don\'t // /* # full</div>',
    "m2": '<div id="vol" data-state="full" style="width:2400px;height:300px">x</div>',  # a strip, drawn at 2400
}
with open(WP_SOURCE, encoding="utf-8", newline="") as _handle:
    _pd_template = _handle.read()
wp_must(_pd_template.count(PD_SLOT) == 1, "main's page holds its designData slot once")
wp_put(PD_PAGE, _pd_template.replace(
    PD_SLOT, '<script type="application/json" id="designData">'
    + json.dumps(PD_MOCKS).replace("<", "\\u003c") + "</script>", 1))


def pd_node_ready():
    """True when node can launch a Chromium through playwright, with the environment the guard's checker gets."""
    node = shutil.which("node")
    if node is None:
        return False
    probe = subprocess.run([node, "-e", "require('playwright').chromium.launch().then(b => b.close())"],
                           capture_output=True, text=True, env=dict(os.environ), timeout=120)
    return probe.returncode == 0


# The deny cases render a page through the checker, so they need Chromium. GUARD_CHROMIUM=1 is set only on the
# CI step that installs Chromium: there, a node that cannot launch it fails the run. Without the marker, a
# machine that cannot launch Chromium skips those cases and says so (the rule of testing/skip-locally-fail-in-ci.mjs).
def pd_chromium_missing():
    """The marker says this run has Chromium. A node that cannot launch it is a failure, not a skip."""
    return False, ("GUARD_CHROMIUM=1, but node cannot launch Chromium through playwright, so the checker's deny "
                   "cases cannot run")


PD_MARKER = os.environ.get("GUARD_CHROMIUM") == "1"
PD_NODE = pd_node_ready()
PD_NEEDS_NODE = PD_NODE or PD_MARKER
if PD_MARKER and not PD_NODE:
    LOG_CHECKS_EXTRA.append(("page-item-design: GUARD_CHROMIUM=1 and node cannot launch Chromium", pd_chromium_missing))
elif not PD_NODE:
    print("page-item-design: no node with playwright and Chromium here, so the checker's deny cases are skipped",
          file=sys.stderr)


def pd_repo(name, stamp, origin=None):
    """A real checkout for one case: the waiting page's layout extras and one commit. `stamp` is the path the
    stamp file holds, or None for no stamp. The stamp resolves as the stamp does: <git common dir>/PD_STAMP.
    `origin` is a remote URL to add, for a case whose machine home is named by the repo's origin."""
    where = os.path.join(ROOT, "pd", name)
    wp_put(os.path.join(where, ".claude", "layout-extras.json"), json.dumps({"kinds": {}, "waiting-page": PQ_URL}))
    wp_put(os.path.join(where, "README.md"), "a checkout of the waiting-page fixture\n")
    wp_git(where, "init", "-q")
    if origin:
        wp_git(where, "remote", "add", "origin", origin)
    wp_git(where, "add", "-A")
    wp_git(where, *IDENT, "commit", "-q", "-m", "fixture: waiting page")
    if stamp is not None:
        wp_put(os.path.join(where, ".git", PD_STAMP), stamp + "\n")
    return where


MH_ORIGIN = "git@github.com:owner/fixture.git"
PD_REPO = "owner/fixture"  # the repo MH_ORIGIN names: the `repo` every open decision of this family carries
PD_FILE = "docs/design/item48/a.html"  # a design's file: inside the checkout's design folder (rule mockup-home)


def pd_item(designs=None, **over):
    """A decision that every other waiting-page rule passes. Option a carries the picture, option b has none."""
    item = {"id": PD_DOC, "kind": "decision", "status": "open", "repo": PD_REPO,
            "title": "Which fill should the volume card show?",
            "context": "The volume card shows the stock level.",
            "options": [{"key": "a", "label": "Full card", "how": "The card shows the full stock.", "design": "m1"},
                        {"key": "b", "label": "Empty card", "how": "The card shows no stock."}],
            "designs": designs if designs is not None else
            [{"slug": "m1", "label": "Full card", "option": "a", "focus": "#vol", "state": "full", "file": PD_FILE}]}
    item.update(over)
    return with_stake(item, departs=True)


def pd_plain():
    """A decision with no picture. Its text says design, so a check that reads words would run the checker."""
    return with_stake({"id": PD_DOC, "kind": "decision", "status": "open", "repo": PD_REPO,
                       "title": "Which design review comes first?", "context": "The design review of the volume card is due.",
                       "options": [{"key": "a", "label": "Review first", "how": "A design review before the build."},
                                   {"key": "b", "label": "Build first", "how": "The build before any design review."}]},
                      departs=True)


def pd_body(repo, data, action="set"):
    return {"tool_name": "ArtifactData", "cwd": repo,
            "tool_input": {"url": PQ_URL, "action": action, "collection": "items", "doc_id": PD_DOC,
                           "data": with_shown(data)}}


def pd_run(name, body):
    """One guard run on `body`, with a config folder of the case's own. Returns (decision, reason, guard.log rows)."""
    folder = os.path.join(ROOT, "pd", "cfg-" + name)
    os.makedirs(folder, exist_ok=True)
    env = dict(os.environ, CLAUDE_CONFIG_DIR=folder, CLAUDE_GUARD_ROOT_PID=str(os.getpid()))
    env.pop("CLAUDE_CODE_REMOTE", None)
    env.pop("CLAUDE_CODE_SESSION_ID", None)
    env.pop("CLAUDE_CODE_REMOTE_SESSION_ID", None)
    got = subprocess.run([sys.executable, GUARD], input=json.dumps(body), capture_output=True, text=True,
                         env=env, timeout=120)
    if got.returncode != 0:
        return "error", "exit %d: %s" % (got.returncode, got.stderr.strip()[:200]), []
    decision, reason = read_decision(got.stdout)
    path = os.path.join(folder, "guard.log")
    text = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
    return decision, reason, [line.split("\t") for line in text.splitlines() if line.strip()]


def pd_case(label, name, stamp, data, want, fragment="", action="set", note=False):
    """Register one check: a checkout with `stamp`, one ArtifactData write of `data`, and the verdict wanted.
    A deny's reason must carry `fragment` and no forbidden target. `note` wants one noted line for the rule."""
    def check():
        repo = pd_repo(name, stamp)
        decision, reason, rows = pd_run(name, pd_body(repo, data, action))
        problems = []
        if decision != want:
            problems.append("want %s, got %s: %s" % (want, decision, reason[:160]))
        if want == "deny" and fragment and fragment not in reason:
            problems.append("the reason does not carry %r: %s" % (fragment, reason[:160]))
        leak = names_the_target(reason, "page-item-design") if want == "deny" else ""
        if leak:
            problems.append("the reason names the forbidden target %r" % leak)
        if note:
            noted = [r for r in rows if len(r) == 6 and r[2] == "noted" and r[3] == "page-item-design"]
            if len(noted) != 1:
                problems.append("want one noted/page-item-design line, found %d" % len(noted))
        return (not problems), ("; ".join(problems) or "%s, as wanted" % want)
    LOG_CHECKS_EXTRA.append(("page-item-design: " + label, check))


# The deny cases read the checker's answer, so they run only where the checker can render.
if PD_NEEDS_NODE:
    pd_case("a focus the mockup does not draw is denied, with the page's sentence", "focus", PD_PAGE,
            pd_item(designs=[{"slug": "m1", "label": "Full card", "option": "a", "focus": "#fill", "state": "full",
                              "file": PD_FILE}]),
            "deny", fragment="shows nothing the focus names")
    pd_case("a state the mockup does not draw is denied, with the page's sentence", "state", PD_PAGE,
            pd_item(designs=[{"slug": "m1", "label": "Full card", "option": "a", "focus": "#vol", "state": "empty",
                              "file": PD_FILE}]),
            "deny", fragment="a state its mockup does not draw")
    pd_case("a strip mockup below the picture floor is denied, naming option A", "strip", PD_PAGE,
            pd_item(designs=[{"slug": "m2", "label": "Full card", "option": "a", "focus": "#vol", "state": "full",
                              "drawn": 2400, "file": PD_FILE}]),
            "deny", fragment="option A")
    pd_case("an update that carries a missed picture is denied, with the page's sentence", "update", PD_PAGE,
            pd_item(designs=[{"slug": "m1", "label": "Full card", "option": "a", "focus": "#fill", "state": "full",
                              "file": PD_FILE}]),
            "deny", fragment="shows nothing the focus names", action="update")

pd_case("a good picture, focus #vol and state full, is allowed", "good", PD_PAGE, pd_item(), "allow")
pd_case("a picture whose mockup slug is missing is allowed: the page warns in the frame", "missing", PD_PAGE,
        pd_item(designs=[{"slug": "m9", "label": "Full card", "option": "a", "focus": "#vol", "state": "full",
                          "file": PD_FILE}]),
        "allow")
pd_case("no stamp is allowed, with one noted line", "nostamp", None, pd_item(), "allow", note=True)
pd_case("a stamp of a file that is gone is allowed, with one noted line", "gone", os.path.join(ROOT, "pd", "gone.html"),
        pd_item(), "allow", note=True)


def pd_stamp_case():
    """An allowed publish of this repo's waiting page writes the absolute path of the published file to
    <git common dir>/waiting-page-published. A relative file path resolves against the checkout, and a refused
    publish leaves the stamp as it was."""
    materialize(WP_GUARD)  # builds the one copy this check runs, not every lazy fixture
    stamp = os.path.join(WP_CHECK, ".git", PD_STAMP)

    def stamped():
        return open(stamp, encoding="utf-8").read().strip() if os.path.isfile(stamp) else None

    def names(got):
        return got is not None and os.path.isabs(got) and os.path.realpath(got) == os.path.realpath(WP_WRITER)

    if os.path.exists(stamp):
        os.remove(stamp)
    if wp_publish_run(WP_WRITER):  # a page with live data: main's raw page is refused as a republish
        return False, "the publish of a page with live data was refused"
    if not names(stamped()):
        return False, "after an allowed publish the stamp holds %r, want the absolute path of %s" % (stamped(), WP_WRITER)
    os.remove(stamp)
    if wp_publish_run(os.path.relpath(WP_WRITER, WP_CHECK)):
        return False, "the publish by a relative file path was refused"
    if not names(stamped()):
        return False, "after a relative publish the stamp holds %r, want the absolute path of %s" % (stamped(), WP_WRITER)
    behind = wp_publish_run(WP_BEHIND)
    if "page-stale" not in behind:
        return False, "a behind publish was not refused by page-stale: %r" % behind[:100]
    if not names(stamped()):
        return False, "a refused publish changed the stamp to %r" % stamped()
    return True, "an allowed publish stamps its absolute path, and a refused one leaves the stamp"


FIXTURELESS_CHECKS.add(pd_stamp_case)  # builds only the copy it runs, as wp_stamp_case does
LOG_CHECKS_EXTRA.append(("page-item-design: an allowed publish of the waiting page stamps the published file",
                         pd_stamp_case))


def pd_rows(folder):
    """The guard.log rows of one config folder, split on tabs."""
    path = os.path.join(folder, "guard.log")
    text = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
    return [line.split("\t") for line in text.splitlines() if line.strip()]


def pd_noted(rows):
    """The page-item-design noted rows. A row has six columns, the session last."""
    return [r for r in rows if len(r) == 6 and r[2] == "noted" and r[3] == "page-item-design"]


def pd_judged(payload, name, seam=None, patches=None):
    """(seam calls, printed output, guard.log rows) for one call, judged in this process with its own config folder.
    The seam is the real _run_check_designs unless `seam` replaces it. `patches` sets module constants, created when absent."""
    from unittest import mock
    module = _load_guard_module()
    real = module._run_check_designs
    calls = []

    def spy(*args, **kwargs):
        calls.append(args)
        return (seam or real)(*args, **kwargs)
    folder = os.path.join(ROOT, "pd", "judged-" + name)
    os.makedirs(folder, exist_ok=True)
    saved = os.environ.get("CLAUDE_CONFIG_DIR")
    os.environ["CLAUDE_CONFIG_DIR"] = folder
    try:
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(module, "_run_check_designs", spy))
            for key, value in (patches or {}).items():
                stack.enter_context(mock.patch.object(module, key, value, create=True))
            out = stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            try:
                module.judge(payload)
            except SystemExit:
                pass
    finally:
        if saved is None:
            os.environ.pop("CLAUDE_CONFIG_DIR", None)
        else:
            os.environ["CLAUDE_CONFIG_DIR"] = saved
    return len(calls), out.getvalue(), pd_rows(folder)


def pd_seam_case():
    """The guard calls _run_check_designs once for a write with designs, and never for a write without them."""
    module = _load_guard_module()
    if not hasattr(module, "_run_check_designs"):
        return False, "the guard has no _run_check_designs seam"
    repo = pd_repo("seam", PD_PAGE)
    with_calls, with_out, _ = pd_judged(pd_body(repo, pd_item()), "seam-with")
    without_calls, without_out, _ = pd_judged(pd_body(repo, pd_plain()), "seam-without")
    problems = []
    if with_calls != 1:
        problems.append("a write with designs called the seam %d times, want 1" % with_calls)
    if with_out.strip():
        problems.append("a good write with designs was refused: %s" % with_out[:120])
    if without_calls != 0:
        problems.append("a write with no designs called the seam %d times, want 0" % without_calls)
    if without_out.strip():
        problems.append("a write with no designs was refused: %s" % without_out[:120])
    if problems:
        return False, "; ".join(problems)
    return True, "the seam runs once for a write with designs, and never for one without"


LOG_CHECKS_EXTRA.append(("page-item-design: the checker runs only for a write with designs", pd_seam_case))


def pd_key_case():
    """The checker is handed the item under its doc key. A data `id` field that names another item is ignored, so a
    picture that misses under the key is denied. The seam stands in for the checker: it misses only under the key."""
    seen = []

    def seam(page_file, item):
        seen.append(item.get("id"))
        if item.get("id") == PD_DOC:
            return 1, "The picture of option A shows nothing the focus names."
        return 0, ""
    repo = pd_repo("dockey", PD_PAGE)
    calls, out, _ = pd_judged(pd_body(repo, pd_item(id="other-id")), "dockey", seam=seam)
    if calls != 1:
        return False, "the checker was called %d times for a write with a picture, want 1" % calls
    if seen != [PD_DOC]:
        return False, "checker got item id %r, want the doc key %r: the data id field must not name the item" % (seen[0], PD_DOC)
    decision, _reason = read_decision(out)
    if decision != "deny":
        return False, "a miss under the doc key was %s, want deny" % decision
    return True, "the checker gets the doc key, and a miss under it is denied"


LOG_CHECKS_EXTRA.append(("page-item-design: the item's id is its doc key, not its data id field", pd_key_case))


def pd_partial_options():
    """Two options with gain and lose, one with a picture. A partial update's options must pass the form rule too."""
    return with_stake({"options": [{"key": "a", "label": "Full card", "how": "The card shows the full stock.", "design": "m1"},
                                   {"key": "b", "label": "Empty card", "how": "The card shows no stock."}]})["options"]


PD_FULL_DESIGN = [{"slug": "m1", "label": "Full card", "option": "a", "focus": "#vol", "state": "full", "file": PD_FILE}]


def pd_partial(label, name, data, judged):
    """One update case of rule page-item-design. A write that carries options or designs but not both is not
    judged: the checker is not called, the write is allowed, and one noted line says partial. A write that
    carries both is judged, so the checker is called once."""
    def check():
        repo = pd_repo(name, PD_PAGE)
        calls, out, rows = pd_judged(pd_body(repo, data, "update"), name)
        noted = pd_noted(rows)
        problems = []
        if judged:
            if calls != 1:
                problems.append("a write that carries both was judged %d times, want 1" % calls)
            if out.strip():
                problems.append("a good write that carries both was refused: %s" % out[:120])
        else:
            if calls != 0:
                problems.append("a partial update called the checker %d times, want 0" % calls)
            if out.strip():
                problems.append("a partial update was refused: %s" % out[:120])
            if len(noted) != 1:
                problems.append("want one noted/page-item-design line, found %d" % len(noted))
            elif "partial" not in "\t".join(noted[0]):
                problems.append("the noted line does not say partial: %r" % noted[0])
        return (not problems), ("; ".join(problems) or "as wanted")
    LOG_CHECKS_EXTRA.append(("page-item-design: " + label, check))


pd_partial("a partial update with options and no designs is not judged: one noted line, no checker call",
           "partial-options", {"options": pd_partial_options()}, judged=False)
pd_partial("a partial update with designs and no options is not judged: one noted line, no checker call",
           "partial-designs", {"designs": PD_FULL_DESIGN}, judged=False)
pd_partial("an update that carries both options and designs is judged",
           "update-both", {"options": pd_partial_options(), "designs": PD_FULL_DESIGN}, judged=True)


def pd_budget_case():
    """Pictured items in one batch share one deadline. When the budget is spent, the rest are allowed with a noted
    line, and the checker is not called for them. The stand-in advances a fake clock by 0.6 s per call, and
    page_check reads that clock, so the case takes no real time."""
    from unittest import mock

    class Clock:
        now = 0.0

    class FakeTime:
        def monotonic(self):
            return clk.now

        def __getattr__(self, name):
            return getattr(real_time, name)

    clk = Clock()

    def slow(page_file, item):
        clk.now += 0.6
        return 0, ""
    pc = _load_guard_module()._page_check_module()
    real_time = pc.time
    repo = pd_repo("budget", PD_PAGE)
    writes = [{"op": "set", "collection": "items", "doc_id": "budget-%d" % i, "data": pd_item(id="budget-%d" % i)}
              for i in range(3)]
    payload = {"tool_name": "ArtifactData", "cwd": repo,
               "tool_input": {"url": PQ_URL, "action": "batch", "writes": writes}}
    with mock.patch.object(pc, "time", FakeTime()):
        calls, out, rows = pd_judged(payload, "budget", seam=slow, patches={"PAGE_ITEM_DESIGN_BATCH_SECONDS": 1.0})
    noted = pd_noted(rows)
    problems = []
    if calls != 2:
        problems.append("three pictured items in one batch called the checker %d times, want 2 (one deadline per batch)"
                        % calls)
    if out.strip():
        problems.append("a batch with no miss was refused: %s" % out[:120])
    if len(noted) != 1:
        problems.append("want one noted/page-item-design line for the item past the budget, found %d" % len(noted))
    return (not problems), ("; ".join(problems) or "two judged, one noted, one deadline for the batch")


LOG_CHECKS_EXTRA.append(("page-item-design: pictured items in one batch share one deadline", pd_budget_case))


def pd_batch_miss_case():
    """A batch of three pictured items: the first is unknown, the second misses, the third would pass. The deny names
    the second, the checker is not run on the third (the loop ends at the first miss), and the first's unknown is one
    noted line. The checker is a stand-in that answers by item, so nothing renders and the case stays fast."""
    seen = []
    ids = ["miss-1", "miss-2", "miss-3"]

    def stand_in(page_file, item):
        seen.append(item["id"])
        if item["id"] == "miss-1":
            return 3, "checker cannot run for item one"
        if item["id"] == "miss-2":
            return 1, "item two's mockup draws no focus"
        return 0, ""
    repo = pd_repo("batch-miss", PD_PAGE)
    writes = [{"op": "set", "collection": "items", "doc_id": doc, "data": pd_item(id=doc)} for doc in ids]
    payload = {"tool_name": "ArtifactData", "cwd": repo,
               "tool_input": {"url": PQ_URL, "action": "batch", "writes": writes}}
    _calls, out, rows = pd_judged(payload, "batch-miss", seam=stand_in)
    decision, reason = read_decision(out)
    noted = pd_noted(rows)
    problems = []
    if seen != ids[:2]:
        problems.append("the checker ran on %s, want %s: one call per item up to the first miss, none for item three"
                        % (seen, ids[:2]))
    if decision != "deny":
        problems.append("want deny, got %s: %s" % (decision, reason[:160]))
    elif "item two's mockup draws no focus" not in reason:
        problems.append("the deny does not name item two: %s" % reason[:160])
    if len(noted) != 1:
        problems.append("want one noted/page-item-design line for item one's unknown, found %d" % len(noted))
    elif "checker cannot run for item one" not in "\t".join(noted[0]):
        problems.append("the noted line does not carry item one's unknown: %r" % noted[0])
    return (not problems), ("; ".join(problems)
                            or "the deny names item two, the checker stops there, one noted line for item one")


LOG_CHECKS_EXTRA.append(("page-item-design: a batch whose second item misses is denied there, with no run of the third",
                         pd_batch_miss_case))


# --------------------------------------------------------------------------- a design names its file, in a mockup home

# Rule mockup-home (the file of a waiting item's design, judged at write). The one mockup home is the repo's design
# folder (docs/design/). A designs entry with no file, or a file the judge refuses (lint/layout.py mockup_home_problem),
# is denied before the picture check starts node. The machine-home form ~/Developer/<repo name>-imports is refused too.
# The checker here is a stub that passes, so a call of it is counted and nothing renders. The judge reads no file.
MH_RULE = "mockup-home"
MH_MACHINE = "~/Developer/fixture-imports/item48/a.html"
MH_APP_SUPPORT = "~/Library/Application Support/Claude-Work/side-session-notes/abc123/a.html"
MH_SHOT = "https://claude.ai/artifact/0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d/asset/shot.png"
MH_WIN_OWNER = "C:/Users/x"  # a Windows owner's home, as Path.home returns it
MH_WIN_HOME = "C:\\Users\\x"  # the same home, as the HOME variable holds it


def mh_design(**over):
    """One design entry with a picture and a file in the design folder. `over` sets a key; None removes it."""
    entry = {"slug": "m1", "label": "Full card", "option": "a", "focus": "#vol", "state": "full", "file": PD_FILE}
    entry.update(over)
    return {key: value for key, value in entry.items() if value is not None}


def mh_judged(name, data, action="set", windows=False):
    """(decision, reason, checker calls, guard.log rows) for one ArtifactData write of the fixture's waiting page,
    judged in this process. `windows` makes Path.home a Windows owner's home, the way a Windows computer reads it."""
    import pathlib
    from unittest import mock
    repo = pd_repo(name, PD_PAGE, origin=MH_ORIGIN)
    home = os.path.join(ROOT, "pd", "mh-home-" + name)
    os.makedirs(home, exist_ok=True)
    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch.dict(os.environ, {"HOME": MH_WIN_HOME if windows else home}))
        if windows:  # Path.home and HOME both name the owner's home, so a judge that reads either one sees it
            stack.enter_context(mock.patch.object(pathlib.Path, "home", return_value=pathlib.PureWindowsPath(MH_WIN_OWNER)))
        calls, out, rows = pd_judged(pd_body(repo, data, action), name, seam=lambda page_file, item: (0, ""))
    decision, reason = read_decision(out)
    return decision, reason, calls, rows


def mh_case(label, name, data, want, checker, action="set", windows=False, says=(), not_says=()):
    """One check of rule mockup-home. A deny names the rule and the file field, starts no checker, and logs a deny row
    for the rule. An allow prints nothing and starts `checker` checker calls. A deny's reason holds each `says` text
    and no `not_says` text."""
    def check():
        decision, reason, calls, rows = mh_judged(name, data, action, windows)
        if decision != want:  # one cause per failure: a wrong decision is the cause, the rest follow from it
            return False, "want %s, got %s: %s" % (want, decision, reason[:160])
        if want == "deny":
            if not reason.startswith(MH_RULE + ":"):
                return False, "the reason does not open with rule %s: %s" % (MH_RULE, reason[:160])
            if "file" not in reason.lower():
                return False, "the reason does not name the file field: %s" % reason[:160]
            leak = names_the_target(reason, MH_RULE)
            if leak:
                return False, "the reason names the forbidden target %r" % leak
            for text in says:
                if text not in reason:
                    return False, "the reason does not name %r: %s" % (text, reason[:160])
            for text in not_says:
                if text in reason:
                    return False, "the reason names %r, a home that holds no mockup now: %s" % (text, reason[:160])
            if not any(len(r) == 6 and r[2] == "deny" and r[3] == MH_RULE for r in rows):
                return False, "guard.log holds no deny row for %s" % MH_RULE
        if calls != checker:
            return False, "the checker was called %d time(s), want %d" % (calls, checker)
        return True, "%s, as wanted" % want
    LOG_CHECKS_EXTRA.append(("mockup-home: " + label, check))


mh_case("a design with a file under the machine home is denied, on a machine with no Developer folder",
        "mh-machine", pd_item(designs=[mh_design(file=MH_MACHINE)]), "deny", checker=0)
mh_case("a design with a file in the design folder is allowed",
        "mh-design", pd_item(designs=[mh_design(file=PD_FILE)]), "allow", checker=1)
mh_case("a design with no file is denied, naming the file field",
        "mh-nofile", pd_item(designs=[mh_design(file=None)]), "deny", checker=0)
mh_case("a design with an empty file is denied",
        "mh-empty", pd_item(designs=[mh_design(file="")]), "deny", checker=0)
mh_case("a mockup under Application Support is denied, its path holds spaces",
        "mh-appsupport", pd_item(designs=[mh_design(file=MH_APP_SUPPORT)]), "deny", checker=0)
mh_case("a denied mockup's reason names the design folder, and not the machine home",
        "mh-words", pd_item(designs=[mh_design(file=MH_APP_SUPPORT)]), "deny", checker=0,
        says=("docs/design",), not_says=("-imports", "Developer"))
mh_case("an image hosted as an artifact asset is denied",
        "mh-asset", pd_item(designs=[mh_design(file=MH_SHOT)]), "deny", checker=0)
mh_case("a file that escapes the design folder with .. is denied",
        "mh-dotdot", pd_item(designs=[mh_design(file="docs/design/../../escape/a.html")]), "deny", checker=0)
mh_case("a Windows owner's machine-home file is denied",
        "mh-win-machine", pd_item(designs=[mh_design(file="C:\\Users\\x\\Developer\\fixture-imports\\item48\\a.html")]),
        "deny", checker=0, windows=True)
mh_case("a Windows owner's AppData mockup is denied",
        "mh-win-appdata",
        pd_item(designs=[mh_design(file="C:\\Users\\x\\AppData\\Roaming\\Claude-Work\\side-session-notes\\abc123\\a.html")]),
        "deny", checker=0, windows=True)
mh_case("an update that carries designs with no file is denied",
        "mh-update", {"designs": [mh_design(file=None)]}, "deny", checker=0, action="update")
mh_case("a closed item with a design that has no file is untouched",
        "mh-closed", pd_item(status="closed", designs=[mh_design(file=None)]), "allow", checker=0)
mh_case("a write with no designs is untouched by the file rule",
        "mh-plain", pd_plain(), "allow", checker=0)
mh_case("a design whose file is a folder is denied, since a folder holds no mockup",
        "mh-folder", pd_item(designs=[mh_design(file="docs/design/item48/")]), "deny", checker=0)
mh_case("a Windows-form design path inside the design folder is allowed, as it is today",
        "mh-win-design", pd_item(designs=[mh_design(file="docs\\design\\a.html")]), "allow", checker=1)


# --------------------------------------------------------------------------- a pick never widens a shared tool
