# section 40500
FAMILY = "answers-session-write"
#
# The answers guard (roadmap step answers-session-write-guard, pick 2 of decision waiting-page-one-store).
# An answer on the waiting page is the owner's own reply. A session that writes one forges it, and Claude has
# written an answer by mistake in normal work, so the guard refuses a session's write into the answers:
#   1. an ArtifactData write whose collection is answers, or whose doc_id or collection names an answers/
#      path, on any page URL (a session has no right to forge an answer on any waiting page). A delete
#      removes a grant and forges none, so a delete of answers passes;
#   2. a Write or Edit whose file_path lies under the answers folder of the waiting data;
#   3. a Bash call that writes there by a redirect, tee, cp, mv, rm or sed -i, or by a git add or commit
#      that names the path. The path may follow a leading cd, and an interpreter (python -c, a python
#      heredoc, node -e) may write it from its script;
#   4. a GitHub MCP write (create_or_update_file, push_files, delete_file) whose path names an answers
#      path, on any branch.
# A read of answers passes. A quoted, heredoc or commented mention of the path passes, since it is no write
# (rule building-scanner-respects-strings). The writer's own copy step passes: its command line names no
# answers path (skills/waiting-page, the copy stays live until step retire-page-copy).
# The rule id the refusal names is RULE, and the reason must not name a forbidden target (names_the_target).

RULE = "answers-session-write"
AA_URL = "https://claude.ai/artifact/aawaiting"        # the waiting page of the fixture repo below
AA_OTHER_URL = "https://claude.ai/artifact/aaother"    # a page that is not the waiting page
AA_REPO = os.path.join(ROOT, "aarepo")                 # a repo whose extras name the waiting page
AA_BARE = os.path.join(ROOT, "aabare")                 # a repo with no extras file, so no waiting page
os.makedirs(os.path.join(AA_REPO, ".git"), exist_ok=True)
os.makedirs(os.path.join(AA_REPO, ".claude"), exist_ok=True)
with open(os.path.join(AA_REPO, ".claude", "layout-extras.json"), "w", encoding="utf-8") as _f:
    json.dump({"kinds": {}, "waiting-page": AA_URL}, _f)
os.makedirs(os.path.join(AA_BARE, ".git"), exist_ok=True)

# The one home of the answers folder name is lint/layout.py, read through layout.path, never a literal.
import layout  # noqa: E402  the one layout module (lint/layout.py)
ANSWERS_FOLDER = layout.path(AA_REPO, "waiting-data")  # the layout's waiting folder, as the tools read it
# The collection's name, one home: lint/layout.py WAITING_ANSWERS. The log check below reads the same constant.
AA_COLLECTION = layout.WAITING_ANSWERS
AA_DOC = "a1"
AA_NOTE = {"note": "A reply, written by a session"}


def aa_art(name, expected, action, url=AA_URL, cwd=AA_REPO, **fields):
    """One ArtifactData call on `url`, with the fields that are not None. A deny names RULE."""
    kw = {k: v for k, v in fields.items() if v is not None}
    add("answers session write: " + name, expected, RULE if expected == "deny" else None,
        tool="ArtifactData", cwd=cwd, url=url, action=action, **kw)


def aa_batch(name, expected, writes, url=AA_URL):
    """One ArtifactData batch of `writes`, each a dict of op, collection, doc_id and data."""
    aa_art(name, expected, "batch", url=url, writes=writes)


def aa_write_op(collection, doc_id=AA_DOC, op="set", data=None):
    entry = {"op": op, "collection": collection, "doc_id": doc_id}
    if data is not None:
        entry["data"] = data
    return entry


def aa_bash(name, command, expected):
    sh("answers session write: " + name, command, expected, RULE if expected == "deny" else None, cwd=AA_REPO)


# ---- 1. ArtifactData: a write into the answers collection is refused, on any page, and every read passes.

aa_art("an ArtifactData set on answers is refused", "deny", "set", collection=AA_COLLECTION, doc_id=AA_DOC,
       data=AA_NOTE)
aa_art("an ArtifactData update on answers is refused", "deny", "update", collection=AA_COLLECTION, doc_id=AA_DOC,
       data=AA_NOTE)
aa_art("an ArtifactData str_replace on answers is refused", "deny", "str_replace", collection=AA_COLLECTION,
       doc_id=AA_DOC, field="note", old_str="reply", new_str="answer")
# A delete removes a grant and forges none, and skills/waiting-page/SKILL.md "Route and close" orders it.
aa_art("an ArtifactData delete on answers is allowed: a delete removes a grant and forges none", "allow", "delete",
       collection=AA_COLLECTION, doc_id=AA_DOC)
aa_art("an ArtifactData delete on answers pinned to a version is allowed", "allow", "delete",
       collection=AA_COLLECTION, doc_id=AA_DOC, if_version=2)
aa_art("an ArtifactData set on answers of a page that is not the waiting page is refused", "deny", "set",
       url=AA_OTHER_URL, collection=AA_COLLECTION, doc_id=AA_DOC, data=AA_NOTE)
aa_art("an ArtifactData set on answers in a repo with no waiting page is refused", "deny", "set",
       cwd=AA_BARE, url=AA_OTHER_URL, collection=AA_COLLECTION, doc_id=AA_DOC, data=AA_NOTE)
aa_art("an ArtifactData set on a collection under answers/ is refused", "deny", "set",
       collection=AA_COLLECTION + "/park", doc_id=AA_DOC, data=AA_NOTE)
aa_art("an ArtifactData set whose doc_id has an answers/ prefix is refused", "deny", "set",
       collection="groups", doc_id=AA_COLLECTION + "/" + AA_DOC, data=AA_NOTE)
aa_batch("an ArtifactData batch whose only write is an answers set is refused", "deny",
         [aa_write_op(AA_COLLECTION, data=AA_NOTE)])
aa_batch("an ArtifactData batch of an answers delete and an answers set is refused", "deny",
         [aa_write_op(AA_COLLECTION, op="delete"), aa_write_op(AA_COLLECTION, data=AA_NOTE)])
aa_batch("an ArtifactData batch whose second write is an answers delete is allowed: a delete forges none", "allow",
         [aa_write_op("groups", "g1", data={"title": "A group"}), aa_write_op(AA_COLLECTION, op="delete")])
aa_batch("an ArtifactData batch of 50 writes whose last is an answers delete is allowed", "allow",
         [aa_write_op("groups", "g%d" % i, data={"title": "A group"}) for i in range(49)]
         + [aa_write_op(AA_COLLECTION, op="delete")])
aa_batch("an ArtifactData batch whose second write is an answers update is refused", "deny",
         [aa_write_op("groups", "g1", data={"title": "A group"}),
          aa_write_op(AA_COLLECTION, op="update", data=AA_NOTE)])
aa_batch("an ArtifactData batch of 50 writes whose last is an answers set is refused", "deny",
         [aa_write_op("groups", "g%d" % i, data={"title": "A group"}) for i in range(49)]
         + [aa_write_op(AA_COLLECTION, data=AA_NOTE)])

aa_art("an ArtifactData get on answers is allowed", "allow", "get", collection=AA_COLLECTION, doc_id=AA_DOC)
aa_art("an ArtifactData list on answers is allowed", "allow", "list", collection=AA_COLLECTION)
aa_art("an ArtifactData query on answers is allowed", "allow", "query", collection=AA_COLLECTION,
       query={"limit": 5})
aa_art("an ArtifactData set on receipts is allowed", "allow", "set", collection="receipts", doc_id=AA_DOC,
       data={"note": "A receipt, written by the owning session"})
aa_art("an ArtifactData set on meta is allowed", "allow", "set", collection="meta", doc_id="page",
       data={"writer": "a-session"})
aa_art("an ArtifactData set on a collection named answersx is allowed", "allow", "set",
       collection=AA_COLLECTION + "x", doc_id=AA_DOC, data={"note": "x"})
aa_art("an ArtifactData set whose doc_id is answers-note, not an answers/ path, is allowed", "allow", "set",
       collection="groups", doc_id=AA_COLLECTION + "-note", data={"title": "A group"})
aa_batch("an ArtifactData batch of receipts and meta writes is allowed", "allow",
         [aa_write_op("receipts", data={"note": "x"}), aa_write_op("meta", "page", data={"writer": "a-session"})])
aa_batch("an ArtifactData batch of 50 group writes is allowed", "allow",
         [aa_write_op("groups", "g%d" % i, data={"title": "A group"}) for i in range(50)])


# ---- 2. Write and Edit: a file under the answers folder is refused, and a doc or a sibling file passes.

def aa_file(name, expected, tool, file_path, **fields):
    add("answers session write: " + name, expected, RULE if expected == "deny" else None,
        tool=tool, cwd=AA_REPO, file_path=file_path, **fields)


aa_file("a Write under waiting/answers is refused", "deny", "Write",
        os.path.join(AA_REPO, "waiting", AA_COLLECTION, AA_DOC + ".json"), content='{"note": "x"}\n')
aa_file("an Edit under waiting/answers is refused", "deny", "Edit",
        os.path.join(AA_REPO, "waiting", AA_COLLECTION, AA_DOC + ".json"), old_string="x", new_string="y")
aa_file("a Write under the layout's waiting folder answers is refused", "deny", "Write",
        os.path.join(AA_REPO, ANSWERS_FOLDER, AA_COLLECTION, AA_DOC + ".json"), content='{"note": "x"}\n')
aa_file("a Write under waiting-data/answers is refused", "deny", "Write",
        os.path.join(AA_REPO, "waiting-data", AA_COLLECTION, AA_DOC + ".json"), content='{"note": "x"}\n')
aa_file("an Edit of a decision doc that names the answers folder in prose is allowed", "allow", "Edit",
        os.path.join(AA_REPO, "docs", "decisions", "aa-note.md"),
        old_string="The page holds the open questions.",
        new_string="The answers to the open questions come from the page, never from a session.")
aa_file("a Write of a file named answers.md at the repo root is allowed", "allow", "Write",
        os.path.join(AA_REPO, AA_COLLECTION + ".md"), content="Notes on the page.\n")
aa_file("a Write under the waiting items folder is allowed: only answers is refused", "allow", "Write",
        os.path.join(AA_REPO, "waiting", "items", "a1.json"), content='{"id": "a1"}\n')


# ---- 3. Bash: a write into the answers folder is refused, and a read, a quoted or heredoc mention, or the
# writer's own copy step passes. Each refusal names the path it writes.

aa_bash("a redirect into waiting/answers is refused", "echo '{}' > waiting/answers/a1.json", "deny")
aa_bash("an append into waiting/answers is refused", "echo '{}' >> waiting/answers/a1.json", "deny")
aa_bash("a tee into waiting/answers is refused", "printf '{}' | tee waiting/answers/a1.json", "deny")
aa_bash("a cp into waiting/answers is refused", "cp src.json waiting/answers/a1.json", "deny")
aa_bash("a mv into waiting/answers is refused", "mv src.json waiting/answers/a1.json", "deny")
aa_bash("an rm of an answer file is refused", "rm waiting/answers/a1.json", "deny")
aa_bash("a sed -i on an answer file is refused", "sed -i 's/a/b/' waiting/answers/a1.json", "deny")
aa_bash("a heredoc redirect into waiting/answers is refused", "cat <<'EOF' > waiting/answers/a1.json\n{}\nEOF",
        "deny")
aa_bash("a cp into waiting-data/answers is refused", "cp src.json waiting-data/answers/a1.json", "deny")
aa_bash("a git add that names an answer file is refused", "git add waiting/answers/a1.json", "deny")
aa_bash("a git add of the answers folder is refused", "git add -A waiting/answers", "deny")
aa_bash("a git commit that names an answer file is refused", "git commit -m 'record' -- waiting/answers/a1.json",
        "deny")
aa_bash("a chained write into waiting/answers after && is refused", "true && echo x > waiting/answers/a1.json",
        "deny")
# A commit message is text, not a path: an answers path inside its quoted -m value passes. A path after the message
# is a real path, and it is refused whichever short option carries the message.
aa_bash("a git commit -am whose message names an answers path is allowed", 'git commit -am "waiting/answers/a1.json x"',
        "allow")
aa_bash("a git commit -sm whose message names an answers path is allowed", 'git commit -sm "waiting/answers/a1.json x"',
        "allow")
aa_bash("a git commit -am that names an answers file as a path is refused", "git commit -am x waiting/answers/a1.json",
        "deny")
aa_bash("a git commit -sm that names an answers file as a path is refused", "git commit -sm x waiting/answers/a1.json",
        "deny")
# The scanner reads a string, a comment opener inside a string, and a lone quote in text as text, and still
# finds the real redirect after them.
aa_bash("a redirect after a hash inside a quoted string is refused", 'echo "#" > waiting/answers/a1.json', "deny")
aa_bash("a redirect after a double slash inside a quoted string is refused", 'echo "//" > waiting/answers/a1.json',
        "deny")
aa_bash("a redirect after a slash-star inside a quoted string is refused", 'echo "/*" > waiting/answers/a1.json',
        "deny")
aa_bash("a redirect after a multi-line quoted string is refused",
        'echo "line one\nline two" > waiting/answers/a1.json', "deny")
aa_bash("a redirect after a lone quote in text is refused", "echo don\\'t > waiting/answers/a1.json", "deny")

aa_bash("a cat of an answer file is allowed", "cat waiting/answers/a1.json", "allow")
aa_bash("an ls of the answers folder is allowed", "ls waiting/answers/", "allow")
aa_bash("a grep of the answers folder is allowed", "grep -rn owner waiting/answers", "allow")
aa_bash("a git log that names the answers folder is allowed", "git log --oneline -- waiting/answers", "allow")
aa_bash("a git diff that names the answers folder is allowed", "git diff -- waiting/answers", "allow")
aa_bash("a git show of an answer file is allowed", "git show HEAD:waiting/answers/a1.json", "allow")
aa_bash("an echo that quotes the answers path is allowed", 'echo "waiting/answers/a1.json"', "allow")
aa_bash("an echo that quotes a redirect sign before the path is allowed", 'echo "a > waiting/answers/a1.json"',
        "allow")
aa_bash("a quoted hash before the path, then a redirect to notes.txt, is allowed",
        'echo "# waiting/answers/a1.json" > notes.txt', "allow")
aa_bash("a heredoc body that names the answers path, redirected to notes.md, is allowed",
        "cat > notes.md <<'EOF'\nwaiting/answers/a1.json\nEOF", "allow")
aa_bash("a comment that names the answers path is allowed", "ls -la # waiting/answers/a1.json", "allow")
aa_bash("a git add of a sibling items file is allowed", "git add waiting/items/a1.json", "allow")
# The writer's own copy step: its command line names no answers path, so the guard must let it run.
aa_bash("the writer's export_page.py copy step is allowed",
        "python3 skills/waiting-page/export_page.py --fetched fetched --out waiting-data --page page.html", "allow")
# The writer stages its copy folder by name. The rule names answers paths, not folders, so this passes until the
# copy step ends (step retire-page-copy). Pinned so no one refuses it early; see the report.
aa_bash("the writer's git add of its copy folder is allowed until the copy step ends", "git add waiting-data",
        "allow")


# ---- 4. Bash after a leading cd: the folder the cd enters is where a relative path lands, so the answers path
# is judged from that folder. The controls keep a write to a sibling folder and a read of an answer file allowed.

aa_bash("a relative redirect after a cd into waiting/answers is refused",
        "cd waiting/%s && echo x > a1.json" % AA_COLLECTION, "deny")
aa_bash("a relative redirect after a cd into waiting, to answers/, is refused",
        "cd waiting && echo x > %s/a1.json" % AA_COLLECTION, "deny")
aa_bash("a relative cp after a cd into waiting-data, to answers/, is refused",
        "cd waiting-data && cp src.json %s/a1.json" % AA_COLLECTION, "deny")
aa_bash("a relative redirect after a cd into waiting, to items/, is allowed",
        "cd waiting && echo x > items/i1.json", "allow")
aa_bash("a cat of an answer file after a cd into waiting/answers is allowed",
        "cd waiting/%s && cat a1.json" % AA_COLLECTION, "allow")
# A copy out of the answers folder reads an answer and writes outside it, so it passes. A copy into it is refused.
aa_bash("a cp of an answer file out to /tmp after a cd into waiting/answers is allowed",
        "cd waiting/%s && cp a1.json /tmp/b.json" % AA_COLLECTION, "allow")
aa_bash("a cp of a file in from /tmp after a cd into waiting/answers is refused",
        "cd waiting/%s && cp /tmp/b.json a1.json" % AA_COLLECTION, "deny")
# A git add that names an answers path, reached through a cd or a -C, is a write to that path. A plain name in a
# folder the cd did not enter is no answers path.
aa_bash("a git add of an answer file after a cd into waiting/answers is refused",
        "cd waiting/%s && git add a1.json" % AA_COLLECTION, "deny")
aa_bash("a git add of answers/ after a cd into waiting is refused",
        "cd waiting && git add %s/a1.json" % AA_COLLECTION, "deny")
aa_bash("a git -C waiting add of answers/ is refused", "git -C waiting add %s/a1.json" % AA_COLLECTION, "deny")


# ---- 5. Interpreters: a python -c, a python heredoc or a node -e that writes an answer file is refused, since the
# script names the path and writes it itself. A python script that only reads the file, and one that writes a
# waiting item, pass.

aa_bash("a python -c that opens an answer file for write is refused",
        "python3 -c \"open('waiting/%s/a1.json','w').write('x')\"" % AA_COLLECTION, "deny")
aa_bash("a python heredoc that opens an answer file for write is refused",
        "python3 - <<'EOF'\nopen(\"waiting/%s/a1.json\",\"w\").write(\"x\")\nEOF" % AA_COLLECTION, "deny")
aa_bash("a node -e that writes an answer file with fs is refused",
        "node -e \"require('fs').writeFileSync('waiting/%s/a1.json','x')\"" % AA_COLLECTION, "deny")
aa_bash("a python -c after a cd into waiting that opens answers/ for write is refused",
        "cd waiting && python3 -c \"open('%s/a1.json','w').write('x')\"" % AA_COLLECTION, "deny")
aa_bash("a python -c that reads an answer file in 'r' mode is allowed",
        "python3 -c \"print(open('waiting/%s/a1.json','r').read())\"" % AA_COLLECTION, "allow")
aa_bash("a python -c that reads an answer file with no mode is allowed",
        "python3 -c \"print(open('waiting/%s/a1.json').read())\"" % AA_COLLECTION, "allow")
aa_bash("a python -c that writes a waiting item is allowed",
        "python3 -c \"open('waiting/items/i1.json','w').write('x')\"", "allow")


# ---- 6. GitHub MCP writes: a create, push or delete whose path names an answers path is refused, with or without a
# branch argument. The same tools on a waiting item pass, and so does a read of an answer file. The 50-file push
# is the full-size state (the batch of 50 above).

def aa_gh(name, expected, tool, **fields):
    """One GitHub MCP call in the fixture repo `x`, owned by `y`. A deny names RULE."""
    add("answers session write: " + name, expected, RULE if expected == "deny" else None,
        tool=tool, cwd=AA_REPO, owner="y", repo="x", **fields)


AA_ANSWER_PATH = "waiting/%s/a1.json" % AA_COLLECTION
AA_ANSWER_DATA_PATH = "waiting-data/%s/a1.json" % AA_COLLECTION
AA_ITEM_PATH = "waiting/items/i1.json"
AA_ITEM_DATA = '{"id": "i1"}\n'

aa_gh("a create_or_update_file of an answer file under waiting/ is refused", "deny",
      "mcp__github__create_or_update_file", path=AA_ANSWER_PATH, content='{"note": "x"}\n', message="record",
      branch="lane-x")
aa_gh("a create_or_update_file of an answer file under waiting-data/ is refused", "deny",
      "mcp__github__create_or_update_file", path=AA_ANSWER_DATA_PATH, content='{"note": "x"}\n', message="record",
      branch="lane-x")
aa_gh("a create_or_update_file of an answer file with no branch argument is refused", "deny",
      "mcp__github__create_or_update_file", path=AA_ANSWER_PATH, content='{"note": "x"}\n', message="record")
aa_gh("a push_files with an answer file entry under waiting-data/ is refused", "deny",
      "mcp__github__push_files", branch="lane-x", message="record",
      files=[{"path": AA_ANSWER_DATA_PATH, "content": '{"note": "x"}\n'}])
aa_gh("a push_files of 50 files whose last is an answer file is refused", "deny",
      "mcp__github__push_files", branch="lane-x", message="record",
      files=[{"path": "waiting/items/g%d.json" % i, "content": "{}\n"} for i in range(49)]
      + [{"path": AA_ANSWER_PATH, "content": '{"note": "x"}\n'}])
aa_gh("a delete_file of an answer file under waiting/ is refused", "deny",
      "mcp__github__delete_file", path=AA_ANSWER_PATH, message="record", branch="lane-x", sha="0")

aa_gh("a create_or_update_file of a waiting item is allowed", "allow",
      "mcp__github__create_or_update_file", path=AA_ITEM_PATH, content=AA_ITEM_DATA, message="record",
      branch="lane-x")
aa_gh("a push_files of a waiting item is allowed", "allow",
      "mcp__github__push_files", branch="lane-x", message="record",
      files=[{"path": AA_ITEM_PATH, "content": AA_ITEM_DATA}])
aa_gh("a push_files of 50 waiting items and no answer file is allowed", "allow",
      "mcp__github__push_files", branch="lane-x", message="record",
      files=[{"path": "waiting/items/g%d.json" % i, "content": "{}\n"} for i in range(50)])
aa_gh("a push_files of an empty files list is allowed", "allow",
      "mcp__github__push_files", branch="lane-x", message="record", files=[])
aa_gh("a delete_file of a waiting item is allowed", "allow",
      "mcp__github__delete_file", path=AA_ITEM_PATH, message="record", branch="lane-x", sha="0")
aa_gh("a get_file_contents of an answer file is allowed", "allow",
      "mcp__github__get_file_contents", path=AA_ANSWER_PATH, ref="lane-x")


# ---- Scope and home checks, run as log checks: a failure names one cause.

def aa_constant_case():
    """The answers collection's name is a home in lint/layout.py, one of its waiting collections."""
    home = getattr(layout, "WAITING_ANSWERS", None)
    if home is None:
        return False, "lint/layout.py has no WAITING_ANSWERS constant"
    if home not in layout.WAITING_COLLECTIONS:
        return False, "WAITING_ANSWERS is %r, which is not in WAITING_COLLECTIONS" % (home,)
    return True, "WAITING_ANSWERS is one of WAITING_COLLECTIONS"


def aa_folder_case():
    """The folder the cases write into is the layout's own waiting folder, read through layout.path."""
    kind = layout.layout()["kinds"]["waiting-data"]["path"].strip("/")
    if ANSWERS_FOLDER != kind:
        return False, "layout.path gives %r, but the waiting-data kind is at %r" % (ANSWERS_FOLDER, kind)
    return True, "the cases' folder is the layout's waiting folder, %r" % (kind,)


LOG_CHECKS_EXTRA.append(("answers session write: the answers collection name is a layout constant",
                         aa_constant_case))
LOG_CHECKS_EXTRA.append(("answers session write: the cases write into the layout's waiting folder",
                         aa_folder_case))
