# Roadmap

data/ holds one JSON file per document: data/steps/<id>.json, data/topics/<id>.json and
data/meta/{advisor,cull,phases}.json. Each file is the document's fields (title, status, phase,
order, why, note, ask, gap, updatedAt). It moved here from the claude.ai page's database on Oct 22.

page/index.html is the viewer. build.py bakes data/ into roadmap.html, which opens from disk and
shows in the waiting page's Status tab (title '<repo> Queue') as a spliced roadmap block (this is the roadmap branch of claude-settings): https://claude.ai/artifact/RddcgXbB6SvTrFZHPmsvFx. The old roadmap page gets no more publishes. Only the triage
thread publishes (step c56): other threads push to the branch and stop there. Triage pulls, builds at the
branch head, and publishes. A publish to a page the session has not viewed is refused once; read the
saved copy it names, check that it equals an earlier commit's roadmap.html, then publish again.

To write, chain every step with `&&`, so a failure stops the chain:

    python roadmap/build.py && git add -A && git commit -m "<what>" && git pull --rebase origin roadmap && python roadmap/build.py && git add roadmap/roadmap.html && git commit --amend --no-edit && git push origin HEAD:roadmap

If the rebase stops on a conflict, stop. Never commit during a rebase. Resolve each file, build
again (build.py refuses a tree with conflict markers and writes no page), then `git rebase --continue`,
then run the chain again from the second build to the push.
`python roadmap/test_build.py` proves the refusal.

The gap-key check (an open step needs its own `gap`, shared by no other open step) runs twice. The
pre-commit hook runs it on the staged files. Every plain `python roadmap/build.py` also runs it on what
the branch added since `origin/roadmap`, read from the HEAD tree, because a `git pull --rebase` or a merge
brings steps in without staging them. A refusal writes no page and exits 1, so the chain above stops before
the amend and the push. With no HEAD or no `origin/roadmap` ref, the build prints one "gap check did not
run" line and goes on. Cost per build: one `merge-base`, one `diff`, one `ls-tree`, one `cat-file --batch`,
and one `git show` per base for each changed open step. It writes no file and starts no process that outlives the build.
