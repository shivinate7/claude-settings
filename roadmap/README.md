# Roadmap

data/ holds one JSON file per document: data/steps/<id>.json, data/topics/<id>.json and
data/meta/{advisor,cull,phases}.json. Each file is the document's fields (title, status, phase,
order, why, note, ask, updatedAt). It moved here from the claude.ai page's database on Oct 22.

page/index.html is the viewer. build.py bakes data/ into roadmap.html, which opens from disk and
is published as the roadmap page (this is the roadmap branch of claude-settings): https://claude.ai/artifact/JGqfvgXBuLqWUm1CX6Bv5h. Only the triage
thread publishes (step c56): other threads push to the branch and stop there. Triage pulls, builds at the
branch head, and publishes. A publish to a page the session has not viewed is refused once; read the
saved copy it names, check that it equals an earlier commit's roadmap.html, then publish again.

To write, chain every step with `&&`, so a failure stops the chain:

    python roadmap/build.py && git add -A && git commit -m "<what>" && git pull --rebase origin roadmap && python roadmap/build.py && git add roadmap/roadmap.html && git commit --amend --no-edit && git push origin HEAD:roadmap

If the rebase stops on a conflict, stop. Never commit during a rebase. Resolve each file, build
again (build.py refuses a tree with conflict markers and writes no page), then `git rebase --continue`,
then run the chain again from the second build to the push.
`python roadmap/test_build.py` proves the refusal.
