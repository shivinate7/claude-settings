"""The Mac input shapes of the artifact tools: the one home that the suites judging them share.

Owner item 440 (home-artifact-input-shapes, 2026-11-08 12:28 CST, from Home transcripts) gives the input of each Mac
tool. Each Mac name is `mcp__claude-artifacts__<name>`. `mac_of_cloud` turns the input of one cloud call into the Mac
input of the same call, so a Mac case is a twin of a cloud case: both carry the same data and expect the same verdict.
The suites that use it are hooks/test_guard.py, hooks/test_call_judge.py and hooks/test_feedback_inbox.py.
This module holds no cases.
"""

MAC_PREFIX = "mcp__claude-artifacts__"

# The Mac op that a cloud write action twins. Mac `merge` has no cloud action of its own: it changes fields, as an
# ArtifactData update does, so both `merge` and `update` twin the cloud update.
CLOUD_ACTION_OF_OP = {"set": "set", "merge": "update", "update": "update"}

# The first publish (no artifact yet) takes these defaults. Item 440 names the keys, not their values.
FIRST_PUBLISH_TITLE = "Page"
FIRST_PUBLISH_ICON = "page"
# A republish takes these. Item 440 names the keys, not their values.
REPUBLISH_BASE_VERSION = 1
REPUBLISH_LABEL = "republish"
PUBLISHED_AS = "index.html"


def mac_tool(name):
    return MAC_PREFIX + name


def slug_of(url):
    """The Mac `slug`: the artifact id at the end of the cloud url."""
    return url.rstrip("/").rsplit("/", 1)[-1]


def item_path(collection, doc_id):
    """`<collection>/<id>`, or `<collection>/` for a call with no id. The collection is the path's first segment."""
    return "%s/%s" % (collection, doc_id) if doc_id is not None else collection + "/"


def _publish(cloud_input):
    files = [{"as": PUBLISHED_AS, "path": cloud_input["file_path"]}]
    url = cloud_input.get("url")
    if url is None:  # form 1: a first publish, with no artifact id yet
        return mac_tool("publish_files"), {"files": files, "title": cloud_input.get("title", FIRST_PUBLISH_TITLE),
                                           "icon": cloud_input.get("icon", FIRST_PUBLISH_ICON)}
    # form 2: a republish, with the slug of the artifact the cloud url names
    return mac_tool("publish_files"), {"slug": slug_of(url), "base_version": REPUBLISH_BASE_VERSION,
                                       "label": REPUBLISH_LABEL, "files": files}


def mac_of_cloud(tool, cloud_input, op=None):
    """(Mac tool name, Mac input) of one cloud call. `tool` is the cloud tool: "Artifact" or "ArtifactData".
    `op` is the Mac op of a write (set, merge or update); it must twin the cloud action."""
    if tool == "Artifact":
        return _publish(cloud_input)
    if tool != "ArtifactData":
        raise ValueError("no Mac shape for the cloud tool %r" % tool)
    action, slug = cloud_input["action"], slug_of(cloud_input["url"])
    collection, doc_id = cloud_input["collection"], cloud_input.get("doc_id")
    path = item_path(collection, doc_id)
    if action in ("set", "update"):
        mac_op = op or action
        if CLOUD_ACTION_OF_OP.get(mac_op) != action:
            raise ValueError("Mac op %r does not twin the cloud action %r" % (mac_op, action))
        entry = {"op": mac_op, "path": path}
        if "data" in cloud_input:
            entry["data"] = cloud_input["data"]
        return mac_tool("db_write"), {"slug": slug, "ops": [entry]}
    if action == "str_replace":
        return mac_tool("db_str_replace"), {"slug": slug, "path": path, "field": cloud_input["field"],
                                            "old_str": cloud_input["old_str"], "new_str": cloud_input["new_str"]}
    if action == "get":
        return mac_tool("db_get"), {"slug": slug, "path": path}
    if action == "list":
        return mac_tool("db_list"), {"slug": slug, "collection": collection}
    if action == "query":  # the cloud query's `where` clauses are the Mac call's `where`
        return mac_tool("db_query"), {"slug": slug, "collection": collection,
                                      "where": cloud_input.get("query", {}).get("where")}
    raise ValueError("no Mac shape for the cloud action %r" % action)
