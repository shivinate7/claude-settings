"""Copy what git lists under named repo folders into a fixture tree, so no fixture lists files.

Why: a fixture that copies a hand-picked list of modules breaks the day one of them imports a new
shared module, and CI finds each such fixture one run at a time. Each language has one helper with
the same rules: testing/tracked_tree.py, testing/tracked_tree.sh, testing/TrackedTree.ps1.

The set: every file git tracks under the folder, plus each new file that .gitignore does not name,
so a lane's new module reaches its fixtures before its first commit. A listed file that is gone from
the checkout is left out: the fixture sees what the checkout holds. Suites (test_*, *_test.py,
*.test.*) stay out: a fixture runs modules, and the suites are the largest files.
A folder git cannot list, or that lists nothing, raises: an empty fixture would pass for the wrong reason.
A root with no .git (an exported copy, from bin/red-run) lists by the manifest its export wrote at the root.

    import tracked_tree
    tracked_tree.copy_tracked(tree, "lint", "hooks")        # tree/lint/..., tree/hooks/...
    tracked_tree.copy_folder("hooks", scratch, skip=("git_reads.py",))   # flat into scratch
    self.addCleanup(tracked_tree.rm_tree, tree)             # remove it, read-only git objects included
"""
import functools
import os
import shutil
import stat
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "hooks"))
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)
import tree_export  # noqa: E402  names the manifest an export writes (hooks/tree_export.py, MANIFEST)


def is_suite(name):
    base = os.path.basename(name)
    return base.startswith("test_") or base.endswith("_test.py") or ".test." in base


def tracked(folder, root=REPO):
    """Paths under `folder` (repo-relative, `/`-separated), relative to that folder, sorted."""
    return list(_listing(folder.strip("/"), root))


def _manifest_name():
    """The name of the manifest an export writes at its root (hooks/tree_export.py, MANIFEST). Read here, never copied."""
    name = getattr(tree_export, "MANIFEST", None)
    if not name:
        raise RuntimeError("hooks/tree_export.py names no MANIFEST, so a tree with no .git cannot be listed")
    return name


def _manifest_listing(folder, root):
    """The set `_listing` gives, read from the export's manifest: one repo-relative path per line, at the root of an exported copy."""
    name = _manifest_name()
    path = os.path.join(root, name)
    if not os.path.isfile(path):
        raise RuntimeError("%s has no .git and no %s, so nothing lists the files under %s/" % (root, name, folder))
    with open(path, encoding="utf-8", newline="") as f:
        paths = f.read().split("\n")
    names = set()
    for path in paths:
        if path.startswith(folder + "/") and not is_suite(path) and os.path.isfile(os.path.join(root, *path.split("/"))):
            names.add(path[len(folder) + 1:])
    if not names:
        raise RuntimeError("the manifest %s lists no file under %s/ in %s" % (name, folder, root))
    return tuple(sorted(names))


@functools.lru_cache(maxsize=None)
def _listing(folder, root):
    """One git call per folder and root in a run: a suite builds hundreds of fixtures from one checkout.
    A root with no .git is an exported copy (bin/red-run's), and lists by the manifest its export wrote."""
    if not os.path.lexists(os.path.join(root, ".git")):
        return _manifest_listing(folder, root)
    done = _nowindow.run(["git", "-C", root, "ls-files", "-z", "--cached", "--others", "--exclude-standard",
                          "--", folder + "/"], capture_output=True)
    if done.returncode != 0:
        raise RuntimeError("git ls-files failed for %s/: %s" % (folder, done.stderr.decode(errors="replace").strip()))
    names = set()
    for path in done.stdout.decode("utf-8", "surrogateescape").split("\0"):
        if path and not is_suite(path) and os.path.isfile(os.path.join(root, *path.split("/"))):
            names.add(path[len(folder) + 1:])
    if not names:
        raise RuntimeError("git lists no file under %s/ in %s" % (folder, root))
    return tuple(sorted(names))


def copy_folder(folder, dest, root=REPO, skip=()):
    """Copy each file of tracked(folder) into `dest`, keeping its path below the folder and its mode.
    `skip` names paths (relative to the folder) a case leaves out on purpose. Returns the copied paths."""
    copied = []
    for rel in tracked(folder, root):
        if rel in skip:
            continue
        target = os.path.join(dest, *rel.split("/"))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copyfile(os.path.join(root, folder, *rel.split("/")), target)
        shutil.copymode(os.path.join(root, folder, *rel.split("/")), target)
        copied.append(rel)
    return copied


def copy_tracked(dest_root, *folders, root=REPO):
    """copy_folder for each folder, into dest_root/<folder>. Returns repo-relative copied paths."""
    copied = []
    for folder in folders:
        copied += [folder + "/" + rel for rel in copy_folder(folder, os.path.join(dest_root, folder), root)]
    return copied


def read_tracked(*folders, root=REPO):
    """{repo-relative path: text} for the same set, read with newline="" so a fixture commits the bytes as they are."""
    texts = {}
    for folder in folders:
        for rel in tracked(folder, root):
            with open(os.path.join(root, folder, *rel.split("/")), encoding="utf-8", newline="") as f:
                texts[folder + "/" + rel] = f.read()
    return texts


def clear_readonly(func, path, _exc):
    """rmtree's error handler: clear the read-only bit on `path`, then retry `func`. A vanished file is done."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except FileNotFoundError:
        pass


def rm_tree(path):
    """Remove a fixture tree. Clears the read-only bit and retries, since git objects are read-only on Windows.
    A file that is already gone is not an error: the tree is what the caller wanted removed."""
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=clear_readonly)
    else:
        shutil.rmtree(path, onerror=clear_readonly)
