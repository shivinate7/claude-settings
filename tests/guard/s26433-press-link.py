# section 26433
FAMILY = "press-link"
FAMILIES["press-link"] = "the page writer: a press in a web app carries a link to the exact page"
#
# A waiting item that asks the owner to press in a web app (GitHub, a PR, a pull request, a
# `home#374` ref, Settings) carries a link to that exact page: on the option whose label or how asks
# it, or on a task's `links`. The writer refuses it at the same ArtifactData call. The red case is
# the old shape of item 47, rebuilt from its step note: the option said to press Merge, with no link.

WP_DOC = "home-374-merge"
PL_LINK = [{"label": "home#374 on GitHub", "url": "https://github.com/shivinate7/home/pull/374"}]
PL_WRONG = [{"label": "home#375 on GitHub", "url": "https://github.com/shivinate7/home/pull/375"}]
PL_BAD_OPT = {"key": "a", "label": "Merge home#374 yourself", "how": "Mark home#374 ready and press Merge.",
              "gain": "g", "lose": "l"}
PL_KEEP_OPT = {"key": "b", "label": "Leave home#374 open", "how": "Do nothing yet.", "gain": "g", "lose": "l"}


def pl_opt(label, how, key="a", **more):
    return dict({"key": key, "label": label, "how": how, "gain": "g", "lose": "l"}, **more)


def pl_item(**over):
    item = {"id": WP_DOC, "kind": "decision", "status": "open", "title": "Merge home#374 yourself or wait?",
            "context": "The home pull request is ready for review.", "options": [PL_BAD_OPT, PL_KEEP_OPT]}
    item.update(over)
    return with_stake({k: v for k, v in item.items() if v is not None})


def pl_task(steps, links=None, **over):
    # The Why yours line keeps each case on the press-link rule; task-names-check reads it (TN_WHY).
    task = {"id": WP_DOC, "kind": "task", "status": "open", "title": "Merge home#374", "steps": steps,
            "links": links, "context": TN_WHY}
    task.update(over)
    return {k: v for k, v in task.items() if v is not None}


def wp_write(name, expected, rule, item, action="set", doc_id=WP_DOC, **extra):
    """One ArtifactData write of a waiting item to the fixture repo's waiting page. The rule is named on a deny only.
    An item of None sends no `data`, as a str_replace does."""
    kw = dict(action=action, collection="items", doc_id=doc_id)
    if item is not None:
        kw["data"] = with_shown(item)
    kw.update(extra)
    add(name, expected, rule if expected == "deny" else None, tool="ArtifactData", cwd=PQ_REPO,
        **{"url": PQ_URL, **kw})


def pl(name, expected, item, **extra):
    wp_write("press link: " + name, expected, "press-link", item, **extra)


pl("today's item (a press on home#374, no link) is denied", "deny", pl_item())
pl("the refusal names the link to add", "deny", pl_item(), carries=("links", "url"))
pl("a press option with a link to the exact page is allowed", "allow",
   pl_item(options=[dict(PL_BAD_OPT, links=PL_LINK), PL_KEEP_OPT]))
pl("a link to the wrong number, /pull/375, is denied", "deny",
   pl_item(options=[dict(PL_BAD_OPT, links=PL_WRONG), PL_KEEP_OPT]))
pl("a link to /pull/3745 is not the exact page and is denied", "deny",
   pl_item(options=[dict(PL_BAD_OPT, links=[{"label": "home#374 on GitHub",
                                             "url": "https://github.com/shivinate7/home/pull/3745"}]),
                    PL_KEEP_OPT]))
pl("a link to the issue page of the same number is allowed", "allow",
   pl_item(options=[dict(PL_BAD_OPT, links=[{"label": "home#374",
                                             "url": "https://github.com/shivinate7/home/issues/374"}]),
                    PL_KEEP_OPT]))
pl("a link on another option does not stand in for this one", "deny",
   pl_item(options=[PL_BAD_OPT, dict(PL_KEEP_OPT, links=PL_LINK)]))
pl("a press in an option label, with no link, is denied", "deny",
   pl_item(options=[pl_opt("Press Merge in GitHub", "Do it by hand."), PL_KEEP_OPT]))
pl("the PR merged, with no press, is allowed", "allow",
   pl_item(options=[pl_opt("Wait until the PR merged", "Do nothing yet."), PL_KEEP_OPT]))
pl("press on with the plan, with no web marker, is allowed", "allow",
   pl_item(options=[pl_opt("Press on with the plan", "Finish the work in this session."), PL_KEEP_OPT]))
pl("a click on GitHub with no link is denied", "deny",
   pl_item(options=[pl_opt("Merge it", "Click Merge on GitHub."), PL_KEEP_OPT]))
pl("a tap on a PR with no link is denied", "deny",
   pl_item(options=[pl_opt("Merge it", "Tap Merge on the PR."), PL_KEEP_OPT]))
pl("a press on a pull request with no link is denied", "deny",
   pl_item(options=[pl_opt("Merge it", "Press Merge on the pull request."), PL_KEEP_OPT]))
pl("a press in Settings with no link is denied", "deny",
   pl_item(options=[pl_opt("Turn it on", "Press Save in Settings."), PL_KEEP_OPT]))
pl("a press on the settings page with no link is denied", "deny",
   pl_item(options=[pl_opt("Turn it on", "Press Save on the settings page."), PL_KEEP_OPT]))
pl("marking a PR ready with no link is denied", "deny",
   pl_item(options=[pl_opt("Ready it", "Mark the PR ready for review."), PL_KEEP_OPT]))
pl("a press on GitHub with a link to the repo is allowed", "allow",
   pl_item(options=[pl_opt("Merge it", "Press Merge on GitHub.",
                           links=[{"label": "home on GitHub", "url": "https://github.com/shivinate7/home"}]),
                    PL_KEEP_OPT]))
pl("a task step that presses Merge on home#374, with no links, is denied", "deny",
   pl_task(["Press Merge on home#374"]))
pl("a task step that presses Merge on home#374, with the link to /pull/374, is allowed", "allow",
   pl_task(["Press Merge on home#374"], links=PL_LINK))
pl("a task step that presses Merge on home#374, with the link to /pull/375, is denied", "deny",
   pl_task(["Press Merge on home#374"], links=PL_WRONG))
pl("a task step that presses Merge in GitHub, with no links, is denied", "deny",
   pl_task(["Press Merge in GitHub"]))
pl("a task step that presses Merge in GitHub, with any link, is allowed", "allow",
   pl_task(["Press Merge in GitHub"], links=[{"label": "home on GitHub", "url": "https://github.com/shivinate7/home"}]))
pl("a task step with a press and no web marker is allowed", "allow", pl_task(["Press on with the plan"]))
pl("a task step that names the PR with no press is allowed", "allow", pl_task(["Read the PR notes"]))
pl("an update that carries a pressing option with no link is denied", "deny",
   {"options": [PL_BAD_OPT, PL_KEEP_OPT]}, action="update")
pl("an update that carries a pressing option with its link is allowed", "allow",
   {"options": [dict(PL_BAD_OPT, links=PL_LINK), PL_KEEP_OPT]}, action="update")
pl("an update of the status only is allowed", "allow", {"status": "closed"}, action="update")
pl("an update that carries a press step with the exact link is allowed", "allow",
   {"steps": ["Press Merge on home#374"], "links": PL_LINK}, action="update")
pl("an update that carries a press step with a wrong link is denied", "deny",
   {"steps": ["Press Merge on home#374"], "links": PL_WRONG}, action="update")
pl("an items set to another artifact is allowed", "allow", pl_item(), url="https://claude.ai/artifact/other")
add("press link: a batch with the press item among the sets is denied", "deny", "press-link",
    tool="ArtifactData", cwd=PQ_REPO, url=PQ_URL, action="batch",
    writes=[{"op": "set", "collection": "answers", "doc_id": "a", "data": {"note": "x"}},
            {"op": "set", "collection": "items", "doc_id": WP_DOC, "data": pl_item()}])
add("press link: a batch of linked sets is allowed", "allow", tool="ArtifactData", cwd=PQ_REPO,
    url=PQ_URL, action="batch",
    writes=[{"op": "set", "collection": "items", "doc_id": WP_DOC,
             "data": pl_item(options=[dict(PL_BAD_OPT, links=PL_LINK), PL_KEEP_OPT])}])


pl("a Merge on GitHub with no link is denied", "deny",
   pl_item(options=[pl_opt("Merge it", "Merge home#374 on GitHub."), PL_KEEP_OPT]))
pl("an Approve on GitHub with no link is denied", "deny",
   pl_item(options=[pl_opt("Approve it", "Approve the PR on GitHub."), PL_KEEP_OPT]))
pl("a Hit on the PR with no link is denied", "deny",
   pl_item(options=[pl_opt("Merge it", "Hit Merge on the PR."), PL_KEEP_OPT]))
pl("a Go to Settings with no link is denied", "deny",
   pl_item(options=[pl_opt("Turn it on", "Go to Settings and turn it on."), PL_KEEP_OPT]))
pl("a press with a space before the # and no link is denied", "deny",
   pl_item(options=[pl_opt("Merge it", "Press Merge on home #374."), PL_KEEP_OPT]))
pl("a press with a space before the # and a link to /pull/375 is denied", "deny",
   pl_item(options=[pl_opt("Merge it", "Press Merge on home #374.", links=PL_WRONG), PL_KEEP_OPT]))
pl("a press with a space before the # and a link to /pull/374 is allowed", "allow",
   pl_item(options=[pl_opt("Merge it", "Press Merge on home #374.", links=PL_LINK), PL_KEEP_OPT]))
pl("a label with the ref and a how with the click are judged together and denied", "deny",
   pl_item(options=[pl_opt("Merge home#374 yourself", "Click the green button."), PL_KEEP_OPT]))
pl("a task step that opens the PR #374 and approves it, with no links, is denied", "deny",
   pl_task(["Open the PR #374 and approve it"]))
pl("press on with the PR open is allowed", "allow",
   pl_item(options=[pl_opt("Keep going", "Press on; the PR stays open."), PL_KEEP_OPT]))
pl("press on with the claude-settings lane is allowed", "allow",
   pl_item(options=[pl_opt("Keep going", "Press on with the claude-settings lane."), PL_KEEP_OPT]))
pl("press Save after editing settings.json is allowed", "allow",
   pl_item(options=[pl_opt("Keep going", "Press Save after you edit settings.json."), PL_KEEP_OPT]))
pl("marking the decision ready once the PR is open is allowed", "allow",
   pl_item(options=[pl_opt("Keep going", "Mark the decision ready once the PR is open."), PL_KEEP_OPT]))
# Task steps are judged joined: the page named in one step and the press in the next is still a press.
pl("task steps that open home#374 on GitHub, then press Merge, with no link, are denied", "deny",
   pl_task(["Open home#374 on GitHub.", "Press Merge."]))
pl("task steps that open the PR on GitHub, then click Merge, with no link, are denied", "deny",
   pl_task(["Open the PR on GitHub.", "Click Merge."]))
pl("a task titled Merge home#374 with a step that presses Merge, with no link, is denied", "deny",
   pl_task(["Press Merge."]))
pl("the task steps with a link to /pull/374 are allowed", "allow",
   pl_task(["Open home#374 on GitHub.", "Press Merge."], links=PL_LINK))
pl("an option that says then you merge home#374, with no link, is denied", "deny",
   pl_item(options=[pl_opt("Go ahead", "Then you merge home#374."), PL_KEEP_OPT]))
pl("an option that says you approve the PR on GitHub, with no link, is denied", "deny",
   pl_item(options=[pl_opt("Go ahead", "You approve the PR on GitHub."), PL_KEEP_OPT]))
pl("an option that says mark it ready for review on home#374, with no link, is denied", "deny",
   pl_item(options=[pl_opt("Go ahead", "Mark it ready for review on home#374."), PL_KEEP_OPT]))
# The page's own buttons and item numbers are not web-app presses.
pl("task steps that press Send when the PR is merged are allowed", "allow",
   pl_task(["Check the PR is merged.", "Press Send when the PR is merged."]))
pl("an option that answers item #47, then presses Send, is allowed", "allow",
   pl_item(options=[pl_opt("Go ahead", "Answer item #47, then press Send."), PL_KEEP_OPT]))
pl("a step that taps Mark done after step #2 is allowed", "allow",
   pl_task(["Tap Mark done after step #2."]))
pl("a step that takes my pick, then presses Send, is allowed", "allow",
   pl_task(["Take my pick, then press Send."]))
# Decision act-in-place: the rule covers a press the owner makes. An option whose how says the session makes the
# press, after his pick, needs no link. The owner's own press still needs one.
pl("a session merges PR #374 after the pick, with no link, is allowed", "allow",
   pl_item(options=[pl_opt("Merge PR #374", "The session merges PR #374 after your pick."), PL_KEEP_OPT]))
pl("an owner press of Merge PR #374 in GitHub, with no link, is denied", "deny",
   pl_item(options=[pl_opt("Merge PR #374", "Press Merge in GitHub."), PL_KEEP_OPT]))
# Decision act-in-place: an option whose label asks him to press is an owner press, whatever its how says.
for label, how in (("Approve on GitHub", "The session records your pick and reruns CI."),
                   ("Pick this", "The session opens PR #374 after your pick, then press Merge."),
                   ("Click Merge on GitHub", "The session merges after your pick.")):
    pl("an owner press labelled %r, with no link, is denied" % label, "deny",
       pl_item(options=[pl_opt(label, how), PL_KEEP_OPT]))
pl("a session press after the pick, with no link, is allowed when the pick comes first", "allow",
   pl_item(options=[pl_opt("Merge PR #374", "After the pick, the session merges PR #374."), PL_KEEP_OPT]))
# Decision act-in-place: a session clause that names the owner, or a press set off by a colon, dash,
# parenthesis, `but` or `so`, is no session act. The press in it is the owner's and needs a link.
for how in ("The session merges PR #374 after the owner clicks Approve.",
            "The session merges PR #374 but click Merge first.",
            "The session merges PR #374, so click Merge.",
            "The session merges PR #374: press Merge.",
            "The session merges PR #374 - press Merge on GitHub.",
            "The session merges PR #374 (press Merge).",
            "The session merges PR #374 after Shivam approves it on GitHub.",
            "The session merges PR #374 so you hit Merge on GitHub.",
            "The session merges PR #374 but you approve it on GitHub.",
            "The session merges PR #374: you approve it on GitHub."):
    pl("a session clause that hides an owner press, %r, with no link, is refused" % how, "deny",
       pl_item(options=[pl_opt("Merge PR #374", how), PL_KEEP_OPT]))
for how in ("The session merges PR #374.",
            "The session merges PR #374 as the owner asked.",
            "The session merges PR #374 once the owner's approval is in.",
            "The session merges PR #374 as he asked.",
            "The session merges PR #374 after Shivam's OK.",
            "The session merges PR #374 so CI reruns."):
    pl("a session clause with no press, %r, with no link, is allowed" % how, "allow",
       pl_item(options=[pl_opt("Merge PR #374", how), PL_KEEP_OPT]))
# A split cuts a mark-ready press under the label "Go": refused. A page-button press or a past act under the
# label "Merge the PR" asks the owner for no web press: allowed.
for how in ("The session merges it after your pick. Mark the PR (#12) ready for review.",
            "The session merges it after your pick. Mark PR #12: ready for review.",
            "The session merges it after your pick. Mark PR #12 - ready for review.",
            "The session merges it after your pick. Mark PR #12, ready for review.",
            "The session merges it after your pick. Mark the draft PR and ready on GitHub."):
    pl("a split that cuts a mark-ready press, %r, with no link, is refused" % how, "deny",
       pl_item(options=[pl_opt("Go", how), PL_KEEP_OPT]))
for how in ("The session merges it after Shivam hits Take my pick.",
            "The session merges it after he hits Send.",
            "The session merges it after Shivam approves this item.",
            "The session merges it after he has merged the base PR.",
            "The session merges it after the owner approved the plan."):
    pl("a page-button press or a past act, %r, with no link, is allowed" % how, "allow",
       pl_item(options=[pl_opt("Merge the PR", how), PL_KEEP_OPT]))


# --------------------------------------------------------------------------- a task step never sends the owner to a file for a command
