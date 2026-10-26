# Roadmap

data/ holds one JSON file per document: data/steps/<id>.json, data/topics/<id>.json and
data/meta/{advisor,cull,phases}.json. Each file is the document's fields (title, status, phase,
order, why, note, ask, updatedAt). It moved here from the claude.ai page's database on Oct 22.

page/index.html is the viewer. build.py bakes data/ into roadmap.html, which opens from disk and
is published as the roadmap page (this is the roadmap branch of claude-settings): https://claude.ai/artifact/R3iCpK91QRjC5he8bwfY7m. Only the triage
thread publishes (step c56): other threads push to the branch and stop there. Triage pulls, builds at the
branch head, and publishes. A publish to a page the session has not viewed is refused once; read the
saved copy it names, check that it equals an earlier commit's roadmap.html, then publish again.
