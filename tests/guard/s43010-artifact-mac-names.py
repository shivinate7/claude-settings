# section 43010
FAMILY = "artifact-mac-names"
#
# The Mac page tools (claude-artifacts) reach the guard under their own names: db_write, db_get and the rest. The
# guard judges a waiting-page item write by its ArtifactData shape, and it maps a Mac call to that shape before it
# judges, so the Mac twin of each write must be refused or allowed as the ArtifactData write is. Built against the
# open gap of lane artifact-guard-matcher-names: the guard matched ArtifactData only, so a Mac write passed unjudged.
# The form lines and the stake of an item come from the port-question section's with_stake, the one builder.

AM_MAC_WRITE = "mcp__claude-artifacts__db_write"
AM_MAC_GET = "mcp__claude-artifacts__db_get"
AM_DOC = "am-1"
AM_LETTERED = [{"key": "a", "label": "Ship it", "gain": "The change lands today.", "lose": "Nobody reads it first."},
               {"key": "b", "label": "Hold it", "gain": "A reviewer reads it first.", "lose": "The change lands a day later."}]
# The option keyed none: the page reads it as "none of these", so option-letter-keys refuses the item.
AM_KEYED_NONE = [AM_LETTERED[0], dict(AM_LETTERED[1], key="none")]


def am_item(options=None):
    """A waiting decision that passes the form, with the given options (lettered by default)."""
    item = {"kind": "decision", "status": "open", "title": "Ship the change today?",
            "context": "The change is ready for review.", "options": options or AM_LETTERED}
    return with_stake(item)


def am_set(name, expected, item, action="set", rule=None):
    """One ArtifactData write of the item, the twin the Mac write is measured against."""
    kw = dict(action=action, collection="items", doc_id=AM_DOC, data=item)
    add("artifact mac names: " + name, expected, rule if expected == "deny" else None,
        tool="ArtifactData", cwd=PQ_REPO, **{"url": PQ_URL, **kw})


def am_write(name, expected, ops, rule=None):
    """One Mac db_write of the given ops, on this repo's waiting page."""
    add("artifact mac names: " + name, expected, rule if expected == "deny" else None,
        tool=AM_MAC_WRITE, cwd=PQ_REPO, url=PQ_URL, ops=ops)


am_set("ArtifactData set of an item with an option keyed none is denied (the twin)", "deny",
       am_item(AM_KEYED_NONE), rule="option-letter-keys")
am_write("db_write set of an item with an option keyed none is denied, as the ArtifactData set is", "deny",
         [{"op": "set", "path": "items/" + AM_DOC, "data": am_item(AM_KEYED_NONE)}], rule="option-letter-keys")
am_write("db_write merge of such an item is denied: a merge is an update", "deny",
         [{"op": "merge", "path": "items/" + AM_DOC, "data": am_item(AM_KEYED_NONE)}], rule="option-letter-keys")
am_write("db_write batch with a keyed-none item among lettered sets is denied", "deny",
         [{"op": "set", "path": "items/am-2", "data": am_item()},
          {"op": "set", "path": "items/" + AM_DOC, "data": am_item(AM_KEYED_NONE)}], rule="option-letter-keys")
am_write("db_write set of a lettered item is allowed", "allow",
         [{"op": "set", "path": "items/" + AM_DOC, "data": am_item()}])
am_write("db_write with no ops is allowed", "allow", [])
add("artifact mac names: db_get of a waiting item is allowed", "allow",
    tool=AM_MAC_GET, cwd=PQ_REPO, url=PQ_URL, path="items/" + AM_DOC)
