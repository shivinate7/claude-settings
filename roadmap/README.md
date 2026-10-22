# Roadmap

Exported Oct 22, 2026 from the claude.ai roadmap page (owner ruling: the roadmap moves into this
repo; the old page is frozen). data/ holds one JSON file per document, as the page's database
stored it: data/steps/<id>.json, data/topics/<id>.json, data/meta/{advisor,cull,phases}.json.
Each file's "data" object is the document; "version" and "updatedAt" are the old page's.
page/index.html is the old page. It reads collections steps and topics and docs meta/advisor,
meta/cull and meta/phases through the artifact database, so it can be republished as a viewer.
