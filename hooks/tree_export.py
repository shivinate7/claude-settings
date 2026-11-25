"""The one home of the export of a commit's tree (`git archive` read as a tar stream) into a folder.

bin/ci-job pins a tree at an action's sha, and bin/red-run copies an old commit for a red run. Both call
export_tree, so the rule for what an export leaves out lives once.
"""
import os
import shutil
import subprocess
import tarfile

import _nowindow  # the one home of a no-window child start (hooks/_nowindow.py)

MANIFEST = ".tree-export-paths"  # the file at the copy root that lists the archived paths: the copy has no .git to list them (testing/tracked_tree.py reads it)


def _inside(root, path):
    """True when the real path of `path` lies in the real folder `root` (or is it)."""
    root = os.path.realpath(root)
    return os.path.commonpath([root, os.path.realpath(path)]) == root


def export_tree(src, sha, dest):
    """Extract `git archive <sha>` of the repo at `src` into the existing folder `dest`. -> None when it worked, else the reason it did not.
    A tracked symlink is extracted as a symlink with its tracked text as the target. A host that refuses os.symlink gets a copy of the
    target's file or folder at the link's path instead; the target may come later in the stream, so those copies wait until it is read.
    A link whose real path leaves `dest` (the target alone looks safe, but a chain of links reaches out) fails the export: each is
    removed and the reason names it. On success the export also writes MANIFEST at the root of `dest`: each archived file and symlink path,
    one per line, read from the same archive stream (no second git call). A partial export may be left in `dest`: the caller removes the folder either way."""
    made = []  # the symlinks os.symlink made
    deferred = []  # symlink members whose os.symlink was refused
    paths = []  # the repo path of each archived file and symlink, for MANIFEST
    has_filter = hasattr(tarfile, "data_filter")
    extract_args = {"filter": "data"} if has_filter else {}
    try:
        with _nowindow.Popen(["git", "archive", "--format=tar", sha], cwd=src, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL) as proc, tarfile.open(fileobj=proc.stdout, mode="r|") as tar:
            for member in tar:  # the stream is read once; a member is extracted as it passes
                if member.isfile() or member.issym():
                    paths.append(member.name)
                if not member.issym():
                    tar.extract(member, dest, **extract_args)
                    continue
                # tar.extract would fall back to copying the target when os.symlink fails, and that seeks back in a stream
                if has_filter:
                    tarfile.data_filter(member, dest)  # an early refusal of an absolute or lexically outside target; the real-path check below is the one that holds
                link = os.path.join(dest, member.name)
                os.makedirs(os.path.dirname(link), exist_ok=True)
                try:
                    os.symlink(member.linkname, link)
                    made.append(member)
                except OSError:
                    deferred.append(member)
        if proc.returncode != 0:
            return "git archive exited %d" % proc.returncode
        escaping = [m.name for m in made if not _inside(dest, os.path.join(dest, m.name))]
        for name in escaping:
            os.remove(os.path.join(dest, name))
        if escaping:
            return "symlink leaves the export: %s" % ", ".join(escaping)
        for member in deferred:
            link = os.path.join(dest, member.name)
            target = os.path.join(os.path.dirname(link), member.linkname)
            if not _inside(dest, target):
                return "symlink leaves the export: %s" % member.name
            if os.path.isdir(target):
                if _inside(target, link):
                    return "symlink to a folder that holds it: %s" % member.name
                shutil.copytree(target, link, symlinks=True)
            else:
                shutil.copyfile(target, link)
        with open(os.path.join(dest, MANIFEST), "w", encoding="utf-8", newline="\n") as handle:
            handle.writelines(path + "\n" for path in paths)
        return None
    except (OSError, tarfile.TarError) as exc:
        return "%s: %s" % (type(exc).__name__, exc)
