"""The one home of the export of a commit's tree (`git archive` read as a tar stream) into a folder.

bin/ci-job pins a tree at an action's sha, and bin/red-run copies an old commit for a red run. Both call
export_tree, so the rule for what an export leaves out lives once.
"""
import subprocess
import tarfile

import _nowindow  # the one home of a no-window child start (hooks/_nowindow.py)


def export_tree(src, sha, dest):
    """Extract `git archive <sha>` of the repo at `src` into the existing folder `dest`. -> None when it worked, else the reason it did not.
    A partial export may be left in `dest`: the caller removes the folder either way."""
    try:
        with _nowindow.Popen(["git", "archive", "--format=tar", sha], cwd=src, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL) as proc, tarfile.open(fileobj=proc.stdout, mode="r|") as tar:
            for member in tar:  # the stream is read once; a member is extracted as it passes
                if member.issym():
                    continue  # the harness reads no symlink, and a host that refuses os.symlink would fail the whole export
                tar.extract(member, dest, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))
        return None if proc.returncode == 0 else "git archive exited %d" % proc.returncode
    except (OSError, tarfile.TarError) as exc:
        return "%s: %s" % (type(exc).__name__, exc)
