"""Bake roadmap/data/ into roadmap/roadmap.html, a read-only page that opens straight from disk.

The viewer in page/index.html reads its data through the artifact database (window.claude.use('db')).
This script puts a small stand-in for that database, holding every JSON file, in front of the
page's own script, so the same viewer runs with no server and no login. Run it after each edit to
roadmap/data/:  python roadmap/build.py
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent
DATA = ROOT / "data"


def load(folder):
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted((DATA / folder).glob("*.json"))}


STUB = """<script>
(() => {
  const DATA = %s;
  const snap = docs => ({docs: docs.map(([id, d]) => ({id, data: () => d}))});
  const byOrder = (a, b) => (typeof a[1].order === 'number' ? a[1].order : 1e9) - (typeof b[1].order === 'number' ? b[1].order : 1e9);
  const collection = name => ({
    orderBy: () => ({onSnapshot: ok => ok(snap(Object.entries(DATA[name] || {}).sort(byOrder)))}),
  });
  const doc = path => {
    const [col, id] = path.split('/');
    const d = (DATA[col] || {})[id];
    return {
      onSnapshot: ok => ok({exists: !!d, data: () => d}),
      update: () => Promise.reject(new Error('read only')),
    };
  };
  window.claude = {use: async () => ({collection, doc})};
})();
</script>
"""


def main():
    data = {"steps": load("steps"), "topics": load("topics"), "meta": load("meta")}
    page = (ROOT / "page" / "index.html").read_text(encoding="utf-8")
    stub = STUB % json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    head, sep, rest = page.partition("<body>")
    if not sep:
        raise SystemExit("page/index.html has no <body> tag")
    (ROOT / "roadmap.html").write_text(head + sep + "\n" + stub + rest, encoding="utf-8")
    print(f"roadmap.html: {len(data['steps'])} steps, {len(data['topics'])} topics, {len(data['meta'])} meta")


if __name__ == "__main__":
    main()
