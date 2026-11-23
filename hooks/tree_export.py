"""The one home of the export of a commit's tree (`git archive` read as a tar stream) into a folder.

bin/ci-job pins a tree at an action's sha, and bin/red-run copies an old commit for a red run. Both call
export_tree, so the rule for what an export leaves out lives once.
"""
import os
import shutil
import subprocess
import tarfile

import _nowindow  # the one home of a no-window child start (hooks/_nowindow.py)


def export_tree(src, sha, dest):
    """Extract `git archive <sha>` of the repo at `src` into the existing folder `dest`. -> None when it worked, else the reason it did not.
    A tracked symlink is extracted as a symlink. A host that refuses os.symlink gets a copy of the target's text at the link's path instead.
    The target may come later in the stream, so those copies wait until the stream is read.
    A partial export may be left in `dest`: the caller removes the folder either way."""
    deferred = []  # symlink members whose os.symlink was refused
    has_filter = hasattr(tarfile, "data_filter")
    extract_args = {"filter": "data"} if has_filter else {}
    try:
        with _nowindow.Popen(["git", "archive", "--format=tar", sha], cwd=src, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL) as proc, tarfile.open(fileobj=proc.stdout, mode="r|") as tar:
            for member in tar:  # the stream is read once; a member is extracted as it passes
                if not member.issym():
                    tar.extract(member, dest, **extract_args)
                    continue
                # tar.extract would fall back to copying the target when os.symlink fails, and that seeks back in a stream
                if has_filter:
                    tarfile.data_filter(member, dest)  # raises for a link or a target outside dest: the check extract applies
                link = os.path.join(dest, member.name)
                os.makedirs(os.path.dirname(link), exist_ok=True)
                try:
                    os.symlink(member.linkname, link)
                except OSError:
                    deferred.append(member)
        if proc.returncode != 0:
            return "git archive exited %d" % proc.returncode
        for member in deferred:
            link = os.path.join(dest, member.name)
            target = os.path.normpath(os.path.join(os.path.dirname(link), member.linkname))
            if os.path.commonpath([os.path.realpath(dest), os.path.realpath(target)]) != os.path.realpath(dest):
                raise OSError("symlink %s points outside the export" % member.name)
            shutil.copyfile(target, link)
        return None
    except (OSError, tarfile.TarError) as exc:
        return "%s: %s" % (type(exc).__name__, exc)
