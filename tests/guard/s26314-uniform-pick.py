# section 26314
FAMILY = "uniform-pick"
#
# Decision uniform-over-variants (topic t18): an option that widens what a shared tool accepts
# carries `widens: true`, and the item's `pick` never names it. The writer is refused.

UP_WIDE = {"key": "a", "label": "Let the stamp accept banchi's titles", "how": "h", "gain": "g",
           "lose": "l", "widens": True}
UP_MATCH = {"key": "b", "label": "Rename banchi's titles to the shared form", "how": "h", "gain": "g",
            "lose": "l"}


# The line a waiting-page task carries (rule task-names-check, its cases below). It sits here, above its
# first use in this section.
TN_WHY = "Why yours: a session on your computer was asked first and none could reach the remote"


def up_item(**over):
    item = {"id": "banchi-titles", "kind": "decision", "status": "open", "title": "Banchi record titles",
            "context": "Banchi's titles differ from the shared form.", "options": [UP_WIDE, UP_MATCH],
            "pick": "a", "why": "Fewer renames."}
    item.update(over)
    return with_stake({k: v for k, v in item.items() if v is not None})


def up(name, expected, item, action="set", **extra):
    kw = dict(action=action, collection="items", doc_id="banchi-titles", data=with_shown(item))
    kw.update(extra)
    add("uniform pick: " + name, expected, "uniform-pick" if expected == "deny" else None,
        tool="ArtifactData", cwd=PQ_REPO, **{"url": PQ_URL, **kw})


up("today's item (pick names the widening option) is denied", "deny", up_item())
up("a pick of the option that matches the shared form is allowed", "allow", up_item(pick="b"))
up("a widening option offered and not picked is allowed", "allow", up_item(pick="b", why="One form."))
up("an item with no pick is allowed", "allow", up_item(pick=None, why=None))
up("widens false is not a widening option", "allow",
   up_item(options=[dict(UP_WIDE, widens=False), UP_MATCH]))
up("a stood pick of a widening option is denied", "deny", up_item(stands=True))
up("an update that carries options and a widening pick is denied", "deny",
   {"options": [UP_WIDE, UP_MATCH], "pick": "a"}, action="update")
up("an update of the status only is allowed", "allow", {"status": "closed"}, action="update")
# A task now needs its Why yours line (task-names-check, below). The line keeps this case on the pick rule.
up("a task is not judged", "allow", up_item(kind="task", context="Banchi's titles differ from the shared form.\n" + TN_WHY))
up("an items set to another artifact is allowed", "allow", up_item(), url="https://claude.ai/artifact/other")
add("uniform pick: a batch with today's item among the sets is denied", "deny", "uniform-pick",
    tool="ArtifactData", cwd=PQ_REPO, url=PQ_URL, action="batch",
    writes=[{"op": "set", "collection": "items", "doc_id": "banchi-titles", "data": up_item()}])
add("uniform pick: the refusal names the ruling and what to pick", "deny", "uniform-pick",
    carries=("rather than the tool change to fit a repo", "pick"), tool="ArtifactData", cwd=PQ_REPO, url=PQ_URL, action="set",
    collection="items", doc_id="banchi-titles", data=up_item())

# Roadmap c135: a multi item (`multi: true`) or ranked item (`ranked: true`) holds `pick` as a list of
# option keys. The list never holds a key of an option marked `widens: true`, as a string pick never does.
UP_THIRD = {"key": "c", "label": "Keep banchi's titles and skip the stamp", "how": "h", "gain": "g",
            "lose": "l"}
UP_THREE = [UP_WIDE, UP_MATCH, UP_THIRD]

up("a multi item whose list pick holds the widening option is denied", "deny",
   up_item(multi=True, options=UP_THREE, pick=["a", "b"]))
up("a multi item whose list pick holds the widening option last is denied", "deny",
   up_item(multi=True, options=UP_THREE, pick=["b", "c", "a"]))
up("a multi item whose list pick is the widening option alone is denied", "deny",
   up_item(multi=True, options=UP_THREE, pick=["a"]))
up("a multi item whose list pick holds only non-widening keys is allowed", "allow",
   up_item(multi=True, options=UP_THREE, pick=["b", "c"]))
up("a multi item with a widening option offered and not in the list pick is allowed", "allow",
   up_item(multi=True, options=UP_THREE, pick=["c"], why="One form."))
up("a multi item whose widening option has widens false is allowed", "allow",
   up_item(multi=True, options=[dict(UP_WIDE, widens=False), UP_MATCH, UP_THIRD], pick=["a", "b"]))
up("a ranked item whose list pick holds the widening option is denied", "deny",
   up_item(ranked=True, options=UP_THREE, pick=["b", "a"]))
up("a ranked item whose list pick holds only non-widening keys is allowed", "allow",
   up_item(ranked=True, options=UP_THREE, pick=["c", "b"]))
up("a stood multi pick that holds the widening option is denied", "deny",
   up_item(multi=True, options=UP_THREE, pick=["a", "c"], stands=True))
up("a stood multi pick of non-widening keys is allowed", "allow",
   up_item(multi=True, options=UP_THREE, pick=["b", "c"], stands=True))
up("an update that carries options and a widening list pick is denied", "deny",
   {"multi": True, "options": UP_THREE, "pick": ["b", "a"]}, action="update")
up("an update that carries options and a non-widening list pick is allowed", "allow",
   {"multi": True, "options": UP_THREE, "pick": ["b", "c"]}, action="update")
up("a task with a list pick is not judged", "allow",
   up_item(kind="task", multi=True, options=UP_THREE, pick=["a", "b"],
           context="Banchi's titles differ from the shared form.\n" + TN_WHY))
# A list that holds a non-string member still names its string members. The page reads such a list as
# not valid and shows no pick, but the writer judges the keys it can read, not the list's shape.
up("a multi item whose list pick holds the widening key and a null is denied", "deny",
   up_item(multi=True, options=UP_THREE, pick=["a", None]))
up("a multi item whose list pick holds a number and a widening key is denied", "deny",
   up_item(multi=True, options=[dict(UP_WIDE, key="a"), UP_MATCH, UP_THIRD], pick=[1, "a"]))
# A widening option with no key is named by no pick. An item with no pick, or a null pick, picks nothing, so
# the missing pick never reads as the key None. Rule option-letter-keys refuses a keyless option, so these
# cases are refused by it. Each names option-letter-keys, not uniform-pick: a uniform-pick refusal here would
# mean the missing pick read as a key, and the rule-name check in the runner fails that.
UP_KEYLESS = {k: v for k, v in UP_WIDE.items() if k != "key"}


def up_keyless(name, item):
    add("uniform pick: " + name, "deny", "option-letter-keys", tool="ArtifactData", cwd=PQ_REPO, url=PQ_URL,
        action="set", collection="items", doc_id="banchi-titles", data=item)


up_keyless("a widening option with no key and an item with no pick is refused by option-letter-keys",
           up_item(options=[UP_KEYLESS, UP_MATCH], pick=None, why=None))
up_keyless("a widening option with no key and an item with a null pick is refused by option-letter-keys",
           dict(up_item(options=[UP_KEYLESS, UP_MATCH], why=None), pick=None))
up_keyless("a widening option with no key and a multi item with no pick is refused by option-letter-keys",
           up_item(multi=True, options=[UP_KEYLESS, UP_MATCH, UP_THIRD], pick=None, why=None))
add("uniform pick: a batch with a multi item whose list pick holds the widening option is denied",
    "deny", "uniform-pick", tool="ArtifactData", cwd=PQ_REPO, url=PQ_URL, action="batch",
    writes=[{"op": "set", "collection": "items", "doc_id": "banchi-titles",
             "data": up_item(multi=True, options=UP_THREE, pick=["a", "b"])}])
add("uniform pick: the refusal of a widening list pick names the ruling and what to pick", "deny",
    "uniform-pick", carries=("rather than the tool change to fit a repo", "pick"), tool="ArtifactData", cwd=PQ_REPO, url=PQ_URL,
    action="set", collection="items", doc_id="banchi-titles",
    data=up_item(multi=True, options=UP_THREE, pick=["a", "b"]))


# --------------------------------------------------------------------------- a press in a web app carries its link
