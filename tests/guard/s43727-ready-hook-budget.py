# section 43727
FAMILY = "ready-mcp-mark-guard"
#
# One call's ready reads share one budget. A hook that runs past its 60 s timeout lets the call through, so the reads of one
# `gh pr ready` (the records-page read of rule records-page-ready, its worktree's removal, and the head read of rule
# ready-mcp-mark-guard) must end inside 50 s of the first read. The page read keeps 10 s back for the removal; a head read
# that finds under 1 s left passes unread, and a page read that finds under 1 s left to use reads as unknown and refuses.
#
# WHY IN PROCESS. The verdict depends on elapsed time, so a synthetic clock stands in for time.monotonic and nothing sleeps.
# Each check loads guard_merge fresh (_load_guard_merge, section 22192, the guard under test), because the budget's clock is
# per process: one fresh load is one hook process. The merge tool, the pass shas and the clock are fakes, patched on that load;
# the guard code between them is real, and ci_wake.triggers, the one parser of a ready mark, reads each command for real.
# Names the old guard lacks (READY_HOOK_BUDGET, ready_budget_left) are never read here: the claim is the literal 50 s, so a
# case on the old guard fails on an assert, not on a missing name.
#
# SCOPE FIRST. Each case asserts that the reads it measures ran before it asserts what they cost, because a budget that no
# read spent is a budget no read exceeded.

import types as _rb_types

RB_PREFIX = "ready-budget: "
RB_BUDGET = 50        # seconds: the total the reads of one call may take
RB_CLEANUP = 10       # seconds: the worktree's removal after a page read, which merge.py runs under its own 10 s
RB_WHERE = "/work/repo"
RB_STOOD = "aaaaaaa"  # a sha that a ready pass stood for
RB_HEAD = "b" * 40    # the head of every fake pull request: no stood sha is a prefix of it, so a head read that runs refuses


class _RbWorld:
    """The ready reads of one hook process against a synthetic clock. A fake page read spends page_spend(granted) seconds and
    reads current; a fake head read spends head_spend(granted) and reads RB_HEAD. `granted` is the deadline the guard asked for."""

    def __init__(self, page_spend, head_spend=lambda granted: granted):
        self.clock = 0.0
        self.loads = 0                # merge_module() calls
        self.page_grants = []         # the deadline of each page read, in order
        self.head_grants = []         # the deadline of each head read, in order
        self.page = None              # ready_page_hit's answer
        self.mark = None              # ready_mark_hit's answer
        self._granted = None
        world = self

        @contextlib.contextmanager
        def shared_deadline(seconds):
            world._granted = seconds
            yield

        class Host:
            def __init__(self, repo=None, cwd=None):
                pass

            def pr_number(self, selector):
                return int(selector) if str(selector).isdigit() else 12

            def pr(self, number):
                world.head_grants.append(world._granted)
                world.clock += head_spend(world._granted)
                return {"head": RB_HEAD}

        def ready_page_state(where, number, host):
            world.page_grants.append(world._granted)
            world.clock += page_spend(world._granted)
            return "current"

        self.tool = _rb_types.SimpleNamespace(shared_deadline=shared_deadline, Host=Host, ready_page_state=ready_page_state)
        self.time = _rb_types.SimpleNamespace(monotonic=lambda: world.clock)

    def module(self):
        self.loads += 1
        return self.tool

    def judge(self, command, stood, page=True):
        """ready_page_hit and then ready_mark_hit, as judge_shell calls them, on one fresh guard_merge. A refused page read ends
        the call, as it does there, so the mark is judged only when the page read passed. page=False judges the mark alone."""
        gm = _load_guard_merge()
        with mock.patch.object(gm, "merge_module", self.module), \
                mock.patch.object(gm, "uses_merge_tool", return_value=True), \
                mock.patch.object(gm, "_ready_pass_shas", return_value=stood), \
                mock.patch.object(gm, "time", self.time, create=True):
            if page:
                self.page = gm.ready_page_hit("Bash", {}, command, RB_WHERE)
            if self.page is None:
                self.mark = gm.ready_mark_hit("Bash", {}, "a transcript", RB_WHERE, command)
        return self


def _rb_whole_deadline(granted):
    return granted


def _rb_whole_deadline_and_removal(granted):
    return granted + RB_CLEANUP


def _rb_fast(granted):
    return 5.0


# 1. A page read that spends its whole deadline leaves the head read a capped timeout.
def rb_case_page_read_leaves_head_read_a_cap():
    world = _RbWorld(_rb_whole_deadline).judge("gh pr ready 12", {RB_STOOD})
    if len(world.page_grants) != 1 or len(world.head_grants) != 1:
        return False, "scope: want one page read and one head read, got %r and %r" % (world.page_grants, world.head_grants)
    granted = world.page_grants + world.head_grants
    if sum(granted) > RB_BUDGET:
        return False, "the page read was granted %s s and the head read %s s: %s s in all, over the %d s call budget" % (
            granted[0], granted[1], sum(granted), RB_BUDGET)
    if world.clock > RB_BUDGET:
        return False, "the reads spent %s s on the synthetic clock, over the %d s call budget" % (world.clock, RB_BUDGET)
    return True, "page read %s s, head read %s s: %s s in all, within %d s" % (granted[0], granted[1], sum(granted), RB_BUDGET)


# The control of 1: a quick page read leaves the head read its own 20 s, and a head no pass stood for is refused. So the cap of
# case 1 comes from the budget spent, and not from a head read that never runs or never refuses.
def rb_case_quick_page_read_leaves_head_read_its_timeout():
    world = _RbWorld(_rb_fast).judge("gh pr ready 12", {RB_STOOD})
    if world.page is not None:
        return False, "scope: the page read refused: %r" % (world.page,)
    if world.head_grants != [20]:
        return False, "the head read was granted %r after a 5 s page read, want [20]" % (world.head_grants,)
    if world.mark is None or not world.mark[1].startswith("ready mark with no ready pass"):
        return False, "the head no pass stood for was not refused: %r" % (world.mark,)
    return True, "the head read ran with 20 s and refused the head no pass stood for"


# 2a. With the call's budget spent, a page read reads unknown and refuses. The second mark of one call begins after the first
# mark's page read spent its whole deadline and its removal.
def rb_case_page_read_with_budget_spent_refuses_unknown():
    world = _RbWorld(_rb_whole_deadline_and_removal).judge("gh pr ready 12 && gh pr ready 13", {RB_STOOD})
    if world.clock < RB_BUDGET or world.page_grants[:1] != [40]:
        return False, "scope: the first page read should spend the whole %d s budget, got grants %r and a clock at %s" % (
            RB_BUDGET, world.page_grants, world.clock)
    if world.page is None:
        return False, "the second page read, begun with the %d s spent, was allowed with %r s granted" % (
            RB_BUDGET, world.page_grants[1:])
    if world.page[1] != "ready, page read unknown":
        return False, "the second page read was refused as %r, want an unknown read" % (world.page[1],)
    if len(world.page_grants) != 1:
        return False, "the second page read started with no budget left: grants %r" % (world.page_grants,)
    return True, "the second page read refused as unknown and started no read"


# The control of 2a: after a quick first read, the second page read runs and passes.
def rb_case_page_read_with_budget_left_runs():
    world = _RbWorld(_rb_fast).judge("gh pr ready 12 && gh pr ready 13", {RB_STOOD})
    if world.page is not None:
        return False, "the second page read refused with budget left: %r" % (world.page,)
    if len(world.page_grants) != 2:
        return False, "want both page reads to run, got grants %r" % (world.page_grants,)
    return True, "both page reads ran, with %r s granted" % (world.page_grants,)


# 2b. With the call's budget spent, the head read passes unread.
def rb_case_head_read_with_budget_spent_passes_unread():
    world = _RbWorld(_rb_whole_deadline_and_removal).judge("gh pr ready 12", {RB_STOOD})
    if world.page is not None or len(world.page_grants) != 1 or world.clock < RB_BUDGET:
        return False, "scope: want one page read that passed and spent the %d s budget, got %r, grants %r, clock %s" % (
            RB_BUDGET, world.page, world.page_grants, world.clock)
    if world.head_grants:
        return False, "a head read was granted %r s after the page read spent the whole %d s budget" % (
            world.head_grants, RB_BUDGET)
    if world.mark is not None:
        return False, "the unread head was refused: %r" % (world.mark,)
    return True, "no head read ran, and the call passed"


# 3. A shell text that holds "already", and no `gh pr ready`, loads no merge tool: it is only parsed.
def rb_case_text_with_already_loads_no_merge_tool():
    text = "echo already done"
    gm = _load_guard_merge()
    if "ready" not in text.lower() or gm.ready_page_calls("Bash", {}, text) != []:
        return False, "scope: want a text that holds `ready` and no ready mark, the parser read %r" % (
            gm.ready_page_calls("Bash", {}, text),)
    world = _RbWorld(_rb_fast).judge(text, {RB_STOOD}, page=False)
    if world.loads:
        return False, "ready_mark_hit loaded the merge tool %d time(s) for a text that marks nothing ready" % world.loads
    if world.mark is not None:
        return False, "a text that marks nothing ready was refused: %r" % (world.mark,)
    return True, "no merge tool load, and the call passed"


# The control of 3: a real `gh pr ready` does load it, so the count above can read a load.
def rb_case_ready_mark_loads_the_merge_tool():
    world = _RbWorld(_rb_fast).judge("gh pr ready 12", {RB_STOOD}, page=False)
    if world.loads != 1:
        return False, "a gh pr ready loaded the merge tool %d time(s), want 1" % world.loads
    return True, "a gh pr ready loaded the merge tool once"


# 4. A bare `gh pr ready` (the current branch, no selector) with no ready pass is refused, with no head read to name.
def rb_case_bare_ready_with_no_pass_is_refused():
    world = _RbWorld(_rb_fast).judge("gh pr ready", set(), page=False)
    if world.loads != 1:
        return False, "scope: a bare gh pr ready should load the merge tool once, it loaded it %d time(s)" % world.loads
    if world.mark is None:
        return False, "a bare gh pr ready with no ready pass was allowed"
    reason, matched = world.mark
    if "merge <pr> --ready" not in reason or "ready-mcp-mark-guard" not in reason:
        return False, "the refusal names neither the rule nor the ready run: %r" % (reason[:120],)
    if world.head_grants:
        return False, "a head read ran with no pass to compare: %r" % (world.head_grants,)
    return True, "refused as %r" % (matched,)


RB_CHECKS = tuple((RB_PREFIX + label, check) for label, check in (
    ("page read leaves the head read a capped timeout, so the call's reads stay within the budget",
     rb_case_page_read_leaves_head_read_a_cap),
    ("a quick page read leaves the head read its own timeout (control)",
     rb_case_quick_page_read_leaves_head_read_its_timeout),
    ("a page read with the call's budget spent reads unknown and refuses",
     rb_case_page_read_with_budget_spent_refuses_unknown),
    ("a page read with budget left runs (control)", rb_case_page_read_with_budget_left_runs),
    ("a head read with the call's budget spent passes unread", rb_case_head_read_with_budget_spent_passes_unread),
    ("a shell text holding already, and no gh pr ready, loads no merge tool",
     rb_case_text_with_already_loads_no_merge_tool),
    ("a gh pr ready loads the merge tool (control)", rb_case_ready_mark_loads_the_merge_tool),
    ("a bare gh pr ready with no ready pass is refused", rb_case_bare_ready_with_no_pass_is_refused)))
# Late sections join LOG_CHECKS directly: LOG_CHECKS_EXTRA joined in section 40805, and a later append is in no run.
for _label, _check in RB_CHECKS:
    LOG_FAMILY[_label] = FAMILY
    FIXTURELESS_CHECKS.add(_check)  # a fake merge tool and a fake clock: no fixture folder is read
LOG_CHECKS = LOG_CHECKS + RB_CHECKS

# 4, at the hook: the same bare mark through judge_shell. A bare mark resolves through the working directory's branch, so it runs in
# the clone that sits on feat-dev-behind, whose fake gh holds that branch's pull request (the page read then passes: its base is not
# the default branch). The deny must name rule ready-mcp-mark-guard, and the refusal names the ready run and never the mark.
sh("ready-shell-mark: a bare gh pr ready with no ready pass is refused", "gh pr ready", "deny", rule=RPM_RULE,
   cwd=RPR_DEV_BEHIND_CLONE, env_path=_rpr_env(GHREADY_DEV_BEHIND), config=MERGECFG, transcript=RPM_NO_PASS,
   carries=("merge <pr> --ready",), lacks=RPM_TARGET_LACKS)
# The control: the same bare mark after a pass for this head is allowed, so the deny above splits on the transcript alone and the
# bare mark resolved to the clone's pull request.
sh("ready-shell-mark: a bare gh pr ready after a dry-merge pass for this head is allowed", "gh pr ready", "allow",
   cwd=RPR_DEV_BEHIND_CLONE, env_path=_rpr_env(GHREADY_DEV_BEHIND), config=MERGECFG, transcript=RPM_DRY_PASS)
