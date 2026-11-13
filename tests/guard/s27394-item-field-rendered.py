# section 27394
FAMILY = "item-field-rendered"
#
# docs/decisions/item-field-rendered.md, rule item-field-rendered, built against a named incident
# (incident in the record): live items carried `reply`, and page.html never showed it. A write of a waiting item is refused when it names a
# top-level field the page does not render. The page lists those fields in one block,
# <script type="application/json" id="itemFields">[...]</script>. The page and the guard both read that
# block, so no copy of the list lives anywhere else. An update may remove a field with
# {"__delete__": true}, which passes. A key inside options or steps is not judged. A page with no block,
# a block that is no JSON list of strings, or an empty list reads as unknown and the write passes. IF_SEAM names the
# page.html the guard reads in place of the repo's own, so a case can hand the guard any page.

IF_SEAM = "GUARD_ITEM_FIELDS_PAGE"
IF_PAGE = os.path.join(REPO, "skills", "waiting-page", "page.html")
IF_DOC = "logo-colour"
IF_BOGUS = "zzUnrenderedField"
# The fields the real page must list: the incident's three, the ten the guard's own rules read, and every
# other top-level key an item case in this file writes. A field dropped from the page goes red by name.
IF_REQUIRED = ("reply", "lastAnswer", "lane",
               "port", "stands", "kind", "holds", "group", "rank", "by", "pick", "options", "context",
               "id", "status", "title", "why", "steps", "links", "command", "multi", "ranked")
# lastAnswer is an object, as the writer stores it.
IF_LAST = {"choice": "b", "note": "n", "at": "2026-10-29T19:05:00Z"}
IF_VALUE = {"port": False, "stands": True, "rank": 3, "multi": True, "ranked": True, "kind": "decision",
            "status": "open", "options": [{"key": "a", "label": "Keep the blue"}], "pick": "a",
            "steps": ["Open the page."], "links": [{"label": "Page", "url": "https://example.com/p"}],
            "command": CMD_BOTH_SHELLS, "lastAnswer": IF_LAST}
IF_OWN = '["id", "kind", "status", "title", "context", "zzCustom"]'   # a block of a page of its own
os.makedirs(os.path.join(ROOT, "ifr"), exist_ok=True)


def if_item(**over):
    """A decision that every other waiting-page rule passes, with `over` on top. A None value drops a key."""
    return pq_item(**{"title": "Which logo colour?", "context": "Brand colours differ.", "holds": None,
                      "departs": True, **over})


def if_page(slug, body):
    """The path of a page.html of its own, in this run's folder. A body of None writes no file."""
    path = os.path.join(ROOT, "ifr", slug + ".html")
    if body is not None:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("<!doctype html>\n<html><head><title>Waiting</title></head><body>\n" + body + "\n</body></html>\n")
    return path


def if_block(text):
    return '<script type="application/json" id="itemFields">' + text + "</script>"


def ifr(name, expected, item, action="set", doc_id=IF_DOC, **extra):
    """One write of an item to the waiting page of the fixture repo, judged against the real page.html."""
    wp_write("item field: " + name, expected, "item-field-rendered", item, action=action, doc_id=doc_id, **extra)


def ifr_seam(name, expected, page, item, action="set", **extra):
    """ifr, with the guard reading `page` through IF_SEAM in place of the real page.html."""
    ifr(name, expected, item, action=action, **extra)
    CASES[-1]["env"] = {IF_SEAM: page}


def ifr_replace(name, expected, field):
    ifr("a str_replace " + name, expected, None, action="str_replace", field=field, old_str="blue", new_str="green")


def ifr_batch(name, expected, writes):
    add("item field: " + name, expected, "item-field-rendered" if expected == "deny" else None,
        tool="ArtifactData", cwd=PQ_REPO, url=PQ_URL, action="batch", writes=writes)


def ifr_write(data, op="set", collection="items"):
    return {"op": op, "collection": collection, "doc_id": IF_DOC, "data": data}


# The real page.html: a field the block lists is allowed, and one it omits is refused.
ifr("a set with a field the page does not render is denied", "deny", if_item(**{IF_BOGUS: "x"}))
ifr("the refusal names the list to add the field to", "deny", if_item(**{IF_BOGUS: "x"}), carries=("itemFields",))
ifr("an update with a field the page does not render is denied", "deny", {IF_BOGUS: "x"}, action="update")
ifr("an update with one unlisted field among listed ones is denied", "deny", {"rank": 3, IF_BOGUS: "x"},
    action="update")
ifr("a field that differs from a listed one only in case is denied", "deny", {"Reply": "x"}, action="update")
ifr("a set of listed fields only is allowed", "allow", if_item())
ifr("a set that carries reply, lastAnswer and lane is allowed", "allow",
    if_item(reply="Use the blue.", lastAnswer=IF_LAST, lane="page-shows-last-answer", group="logo", rank=2, by="owner"))
for _field in IF_REQUIRED:
    ifr("an update of %s is allowed once the page lists it" % _field, "allow", {_field: IF_VALUE.get(_field, "x")},
        action="update")

# __delete__ removes a field, so it passes on an update, and only there.
ifr("an update that deletes an unlisted field is allowed", "allow", {IF_BOGUS: {"__delete__": True}}, action="update")
ifr("an update that deletes an unlisted field and sets a listed one is allowed", "allow",
    {IF_BOGUS: {"__delete__": True}, "reply": "x"}, action="update")
ifr("an update that deletes one unlisted field and sets another is denied", "deny",
    {IF_BOGUS: {"__delete__": True}, "zzOtherField": "x"}, action="update")
ifr("an update whose delete marker is false is denied", "deny", {IF_BOGUS: {"__delete__": False}}, action="update")
ifr("a set that carries a delete marker on an unlisted field is denied", "deny",
    if_item(**{IF_BOGUS: {"__delete__": True}}))

# Only a top-level key is judged.
ifr("an unlisted key inside an option is not judged", "allow",
    {"options": [{"key": "a", "label": "Keep the blue", IF_BOGUS: 1}]}, action="update")
ifr("an unlisted key inside a step is not judged", "allow",
    {"steps": [{"text": "Open the page.", IF_BOGUS: 1}]}, action="update")
ifr("an unlisted key inside a listed field is not judged", "allow", {"reply": {IF_BOGUS: 1}}, action="update")

ifr_replace("on a field the page does not render is denied", "deny", IF_BOGUS)
ifr_replace("on reply is allowed once the page lists it", "allow", "reply")
ifr_replace("on context is allowed", "allow", "context")
ifr_replace("on the title is allowed", "allow", "title")

# A batch is judged entry by entry, whatever the entry's position or op.
ifr_batch("a batch with an unlisted field in its last write is denied", "deny",
          [ifr_write(if_item()), ifr_write({"rank": 3}, "update"), ifr_write({IF_BOGUS: "x"}, "update")])
ifr_batch("a batch with an unlisted field in its first write is denied", "deny",
          [ifr_write(if_item(**{IF_BOGUS: "x"})), ifr_write({"rank": 3}, "update")])
ifr_batch("a batch with a str_replace on an unlisted field is denied", "deny",
          [ifr_write(if_item()),
           {"op": "str_replace", "collection": "items", "doc_id": IF_DOC, "field": IF_BOGUS,
            "old_str": "blue", "new_str": "green"}])
ifr_batch("a batch of listed fields and a delete of an unlisted one is allowed", "allow",
          [ifr_write(if_item(reply="x")), ifr_write({IF_BOGUS: {"__delete__": True}, "lane": "x"}, "update")])
ifr_batch("a batch with an unlisted field in another collection is allowed", "allow",
          [ifr_write({IF_BOGUS: "x"}, collection="answers"), ifr_write(if_item())])

# file_path data is read as the data of the write.
IF_FILE_BAD = os.path.join(ROOT, "ifr", "bad.json")
IF_FILE_GOOD = os.path.join(ROOT, "ifr", "good.json")
with open(IF_FILE_BAD, "w", encoding="utf-8") as _f:
    json.dump(if_item(**{IF_BOGUS: "x"}), _f)
with open(IF_FILE_GOOD, "w", encoding="utf-8") as _f:
    json.dump(if_item(reply="x"), _f)
ifr("file_path data with an unlisted field is denied", "deny", None, file_path=IF_FILE_BAD)
ifr("file_path data of listed fields is allowed", "allow", None, file_path=IF_FILE_GOOD)
ifr("an unreadable file_path is not judged", "allow", None, file_path=os.path.join(ROOT, "ifr", "missing.json"))

# Only a write of an item to this repo's waiting page is judged.
ifr("a set to another collection is not judged", "allow", if_item(**{IF_BOGUS: "x"}), collection="answers")
ifr("a set to another artifact is not judged", "allow", if_item(**{IF_BOGUS: "x"}),
    url="https://claude.ai/artifact/other")
add("item field: a repo with no waiting page is not judged", "allow", tool="ArtifactData", cwd=NOGIT, url=PQ_URL,
    action="set", collection="items", doc_id=IF_DOC, data=if_item(**{IF_BOGUS: "x"}))
add("item field: a read is not judged", "allow", tool="ArtifactData", cwd=PQ_REPO, url=PQ_URL, action="get",
    collection="items", doc_id=IF_DOC)

# The guard reads the block of the page it is handed, so no copy of the list sits in the guard. The
# block spans lines here, as a hand-edited page may.
IF_PRETTY = if_page("pretty", if_block('[\n  "id",\n  "kind",\n  "status",\n  "title",\n  "context",\n  "zzCustom"\n]'))
ifr_seam("a page of its own lists zzCustom, so a set that carries it is allowed", "allow", IF_PRETTY,
         if_item(zzCustom="x"))
ifr_seam("a page of its own omits reply, so a set that carries it is denied", "deny", IF_PRETTY,
         if_item(reply="x"))

# A page with no block, a block that is no JSON list of strings, or an empty list reads as unknown: the write passes.
for _slug, _body in (("no-block", "<p>No list here.</p>"),
                     ("object-block", if_block('{"id": true}')),
                     ("number-member", if_block('["id", 3]')),
                     ("broken-json", if_block('["id", ')),
                     ("empty-list", if_block("[]")),
                     ("no-file", None)):
    ifr_seam("a page with %s is not judged" % _slug.replace("-", " "), "allow", if_page(_slug, _body),
             if_item(**{IF_BOGUS: "x"}))

# An empty block lists no field, so it reads as unknown for every op, as the set above does for a set. The
# update, the str_replace and the batch each pass on it.
IF_EMPTY = if_page("empty-list-ops", if_block("[]"))
ifr_seam("an empty itemFields block is not judged: an update with an unlisted field is allowed", "allow",
         IF_EMPTY, {IF_BOGUS: "x"}, action="update")
ifr_seam("an empty itemFields block is not judged: a str_replace on an unlisted field is allowed", "allow",
         IF_EMPTY, None, action="str_replace", field=IF_BOGUS, old_str="blue", new_str="green")
add("item field: an empty itemFields block is not judged: a batch with an unlisted field is allowed", "allow",
    tool="ArtifactData", cwd=PQ_REPO, url=PQ_URL, action="batch",
    writes=[ifr_write({IF_BOGUS: "x"}, "update"), ifr_write(if_item(**{IF_BOGUS: "x"}))])
CASES[-1]["env"] = {IF_SEAM: IF_EMPTY}

# The scanner cases: the block is found, and its list read, whatever text sits around it.
# Comment openers sit inside strings, and their closers come after the block.
IF_SCAN_PAGES = {
    "comment openers in strings": '<script>var a = "<!--", b = "//", c = "/*";</script>\n'
                                  + if_block(IF_OWN) + '\n<p>end --> and */</p>',
    # A decoy block inside a multi-line template literal comes first, and is no block of the page.
    "a multi-line template literal": '<script>\nconst tpl = `\n  <script type="application/json" id="itemFields">'
                                     '["reply", "zzCustom"]<\\/script>\n`;\n</script>\n' + if_block(IF_OWN),
    "a lone quote in text": "<p>Don't forget the list.</p>\n" + if_block(IF_OWN) + "\n<p>It's the list.</p>",
}
for _what, _body in IF_SCAN_PAGES.items():
    _page = if_page("scan-" + _what.replace(" ", "-"), _body)
    ifr_seam("a block after " + _what + " is read: reply is denied", "deny", _page, if_item(reply="x"))
    ifr_seam("a block after " + _what + " is read: zzCustom is allowed", "allow", _page, if_item(zzCustom="x"))


def item_fields_page_case():
    """The real page.html holds one itemFields block: type application/json, a JSON list of strings with
    no repeats, naming every field in IF_REQUIRED. An HTML parser finds it, as a browser does."""
    class Blocks(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=False)
            self.found, self.open = [], None

        def handle_starttag(self, tag, attrs):
            if tag == "script" and dict(attrs).get("id") == "itemFields":
                self.open = (dict(attrs).get("type"), [])

        def handle_data(self, data):
            if self.open:
                self.open[1].append(data)

        def handle_endtag(self, tag):
            if tag == "script" and self.open:
                self.found.append((self.open[0], "".join(self.open[1])))
                self.open = None

    try:
        with open(IF_PAGE, encoding="utf-8") as f:
            blocks = Blocks()
            blocks.feed(f.read())
            blocks.close()
    except OSError as err:
        return False, "page.html does not read: %s" % err
    if len(blocks.found) != 1:
        return False, "page.html holds %d itemFields blocks, want 1" % len(blocks.found)
    kind, text = blocks.found[0]
    if kind != "application/json":
        return False, "the itemFields block has type %r, want application/json" % kind
    try:
        fields = json.loads(text)
    except ValueError as err:
        return False, "the itemFields block is no JSON: %s" % err
    if not isinstance(fields, list) or not all(isinstance(f, str) for f in fields):
        return False, "the itemFields block is no list of strings"
    if len(set(fields)) != len(fields):
        return False, "the itemFields block repeats a field"
    missing = [f for f in IF_REQUIRED if f not in fields]
    if missing:
        return False, "the itemFields block does not list %s" % ", ".join(missing)
    return True, "one block of %d fields, and it lists every field a write needs" % len(fields)


def item_field_hit_case():
    """question_form.item_field_hit(op, entry, data) answers truthy for a write it refuses and falsy for one it
    passes, on a page of its own (IF_SEAM). The four shapes: set, update, a delete, a str_replace."""
    page = if_page("unit", if_block('["id", "reply", "context"]'))
    code = ("import json, sys\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "import question_form\n"
            "hit, bogus = question_form.item_field_hit, sys.argv[2]\n"
            "entry = {'collection': 'items', 'doc_id': 'd'}\n"
            "swap = dict(entry, field=bogus, old_str='a', new_str='b')\n"
            "print(json.dumps([bool(x) for x in (\n"
            "    hit('set', entry, {bogus: 1}), hit('set', entry, {'context': 'x', 'reply': 'x'}),\n"
            "    hit('update', entry, {bogus: 1}), hit('update', entry, {bogus: {'__delete__': True}}),\n"
            "    hit('update', entry, None), hit('str_replace', swap, None),\n"
            "    hit('str_replace', dict(swap, field='reply'), None))]))\n")
    env = dict(os.environ, **{IF_SEAM: page})
    run = subprocess.run([sys.executable, "-c", code, os.path.dirname(GUARD), IF_BOGUS],
                         capture_output=True, text=True, env=env, timeout=60)
    if run.returncode != 0:
        return False, "question_form.item_field_hit does not run: %s" % run.stderr.strip()[-120:]
    got = json.loads(run.stdout.strip().splitlines()[-1])
    want = [True, False, True, False, False, True, False]
    if got != want:
        names = ("set, unlisted", "set, listed", "update, unlisted", "update, delete", "update, no data",
                 "str_replace, unlisted", "str_replace, listed")
        return False, "item_field_hit is wrong for: " + ", ".join(n for n, g, w in zip(names, got, want) if g != w)
    return True, "item_field_hit refuses an unlisted field and passes a listed one, a delete and no data"


LOG_CHECKS_EXTRA.append(("item field: the real page.html holds one itemFields block that lists every field a "
                         "write needs", item_fields_page_case))
LOG_CHECKS_EXTRA.append(("item field: question_form.item_field_hit refuses an unlisted field and passes the rest",
                         item_field_hit_case))
FIXTURELESS_CHECKS.update((item_fields_page_case, item_field_hit_case))
