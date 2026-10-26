# Roadmap

data/ holds one JSON file per document: data/steps/<id>.json, data/topics/<id>.json and
data/meta/{advisor,cull,phases}.json. Each file is the document's fields (title, status, phase,
order, why, note, ask, updatedAt). It moved here from the claude.ai page's database on Oct 22.

page/index.html is the viewer. build.py bakes data/ into roadmap.html, which opens from disk and
is published as the roadmap page: https://claude.ai/artifact/R3iCpK91QRjC5he8bwfY7m. Republish
it to that URL after each build.
