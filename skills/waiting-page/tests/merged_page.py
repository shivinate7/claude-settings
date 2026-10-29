#!/usr/bin/env python3
"""Print a waiting page rebuilt and republished the way the writer does it, for page.test.mjs.

    python3 skills/waiting-page/tests/merged_page.py --page LIVE.html [--no-roadmap]

Builds the roadmap data block of a fixture roadmap repo (skills/roadmap/build.py --block), splices
it into LIVE.html (skills/waiting-page/splice.py) and prints the result. With --no-roadmap the repo
has no record branch, so the block holds ROADMAP_DATA = null. The fixture repo is the one in
skills/roadmap/test_build.py (make_repo). Its folder is this run's folder from lint/_test_temp.py,
removed before the script ends (decision test-temp-standard). A step that fails prints its stderr
and exits 1, so a missing builder or splice reads as that, not as a blank page.
"""
import argparse
import os
import pathlib
import shutil
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "skills" / "roadmap"))
sys.path.insert(1, str(ROOT / "lint"))
sys.path.insert(2, str(ROOT / "hooks"))
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)
import _test_temp  # noqa: E402
import test_build  # noqa: E402

# Distinctive text the status panel must show from the baked data and never take from the database.
BAKED_STEP = {"title": "Baked roadmap step zebra", "status": "active", "phase": "cleanup", "order": 0,
              "note": "n", "updatedAt": "2026-10-26T00:00:00Z"}
BAKED_PHASES = {"cleanup": {"metrics": [{"label": "Baked phase tile zebra", "value": "1 of 3"}]}}


def run(argv, what):
    done = _nowindow.run(argv, capture_output=True, text=True, encoding="utf-8")
    if done.returncode != 0:
        sys.stderr.write("%s failed (exit %d): %s\n%s%s" % (what, done.returncode, " ".join(argv), done.stdout, done.stderr))
        raise SystemExit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--page", required=True, help="the live page to splice the block into")
    ap.add_argument("--no-roadmap", action="store_true", help="a repo with no record branch")
    args = ap.parse_args()
    folder = _test_temp.run_folder()
    try:
        if args.no_roadmap:
            repo = pathlib.Path(folder) / "repo"
            repo.mkdir()
            test_build.git(repo, "init", "-q", "-b", "main")
            (repo / "README.md").write_text("# r\n", encoding="utf-8")
            test_build.git(repo, "add", "-A")
            test_build.git(repo, "commit", "-q", "-m", "main")
        else:
            repo = test_build.make_repo(folder, steps={"z1": BAKED_STEP}, meta={"phases": BAKED_PHASES})
            test_build.git(repo, "checkout", "-q", "main")
        block, merged = os.path.join(folder, "block.html"), os.path.join(folder, "merged.html")
        run([sys.executable, str(ROOT / "skills" / "roadmap" / "build.py"), "--repo", str(repo), "--block",
             "--out", block], "the roadmap build")
        run([sys.executable, str(ROOT / "skills" / "waiting-page" / "splice.py"), "--page", args.page,
             "--block", block, "--out", merged], "the splice")
        with open(merged, "rb") as f:
            sys.stdout.buffer.write(f.read())
    finally:
        shutil.rmtree(folder, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


if __name__ == "__main__":
    main()
