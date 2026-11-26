#!/usr/bin/env python3
"""Starts hooks/guard.py from its bytecode cache, so a guard call does not compile the guard's 9000 lines again.

Python compiles a script's own source on every start and never caches it, so `python guard.py` pays that compile on
each call (about 115 ms). This file is the tiny script that runs in its place: it loads guard.py's code object through
the standard source loader, which keeps it in hooks/__pycache__ (or under PYTHONPYCACHEPREFIX), and runs it as
`__main__`, exactly as the script start does. The guard's own code, its exits and its fail-closed load check
(`__name__ == "__main__"`) are unchanged.

Each cache of a file of this repo (guard.py, the modules it imports, the janitor, lint and merge files it loads) is a
checked-hash cache: the loader reads the file's source on every start and uses the cache only when the cache holds the
hash of that source. The stock cache trusts the source's modification time (whole seconds) and size, so a same-size edit
inside one second leaves a stale cache that judges with the old code. A timestamp cache, written by an earlier start or
by another Python, is rewritten as a checked-hash one before it is used. Files outside the repo keep the stock loader.

It writes the cache even when the host sets PYTHONDONTWRITEBYTECODE=1: that setting made every guard call compile
guard.py and each module it imports. Nothing the host or the owner set asks for this override; it is a choice made here
so the cache pays off. A load that asks for no cache (the sim_lease load in guard.py) still writes none, and gets the
source's own code.

Fail safe: a stale, timestamp, corrupt or other-version cache is rebuilt, and any error while getting the cached code
falls back to compiling guard.py's source here, the plain start. This file never judges a call and never decides to
allow one.

    python3 hooks/guard_launch.py     (stdin: the hook payload, as for guard.py)
"""
import os
import sys

# The installer stamps guard.py and every guard_*.py it copies, this launcher too, and logs each landing with the id
# the file carries. The launcher judges nothing. main() removes the stamped name before it runs guard.py in this
# module's globals, because guard.py reads its own INSTALL_ID from those globals and must not see this file's.
# INSTALL_ID = "uninstalled"


def own_file(path, root):
    """True for a source file of this repo: under `root`, or in a guard.d set folder (an installed set may sit in a
    sibling generation outside `root`)."""
    real = os.path.realpath(path)
    return real.startswith(root + os.sep) or (os.sep + "guard.d" + os.sep) in real


def holds_hash_of(cache, source):
    """True when the file at `cache` is a checked-hash cache of this Python that records the hash of `source`."""
    import importlib.util
    try:
        with open(cache, "rb") as handle:
            head = handle.read(16)
    except OSError:
        return False
    return head == importlib.util.MAGIC_NUMBER + b"\x03\x00\x00\x00" + importlib.util.source_hash(source)


def use_checked_hash_caches(root):
    """Makes the source loader, for the files of this repo, load only from a cache that holds the hash of the source it
    reads. Any other cache is rewritten here, by one writer, so a rebuilt cache has the bytes a first build has."""
    import importlib.machinery
    import importlib.util
    loader_class = importlib.machinery.SourceFileLoader
    stock_get_code = loader_class.get_code

    def get_code(self, fullname):
        path = self.get_filename(fullname)
        if not own_file(path, root):
            return stock_get_code(self, fullname)
        source = self.get_data(path)
        cache = importlib.util.cache_from_source(path)
        if not holds_hash_of(cache, source):
            # No cache, a timestamp cache, another version's, or one of other source: never trust it. Write a
            # checked-hash one, or, where none may be written, use the source's own code.
            if sys.dont_write_bytecode:
                return self.source_to_code(source, path)
            try:
                import py_compile
                py_compile.compile(path, cache, doraise=True,
                                   invalidation_mode=py_compile.PycInvalidationMode.CHECKED_HASH)
            except Exception:
                return self.source_to_code(source, path)
        # The stock loader reads the hash-checked cache, and checks its hash once more, as it does for any such cache.
        return stock_get_code(self, fullname)

    loader_class.get_code = get_code


def cached_code(path, root):
    """The code object of `path` from its checked-hash cache, rebuilt once when the cache will not load. None when the
    cache path fails twice, so the caller compiles the source itself."""
    try:
        import importlib.machinery
        import importlib.util
        sys.dont_write_bytecode = False   # the loader writes the cache even when the host asks for none
        use_checked_hash_caches(root)
        loader = importlib.machinery.SourceFileLoader("__main__", path)
        try:
            return loader.get_code("__main__")
        except Exception:
            # A cache whose hash matches the source but whose body will not load. The remove is the one rebuild.
            os.remove(importlib.util.cache_from_source(path))
            return loader.get_code("__main__")
    except Exception:
        return None


def main():
    path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "guard.py")
    root = os.path.dirname(os.path.dirname(path))
    code = cached_code(path, root)
    if code is None:
        with open(path, "rb") as handle:
            code = compile(handle.read(), path, "exec")
    scope = sys.modules["__main__"].__dict__
    scope["__file__"] = path
    scope.pop("INSTALL_ID", None)
    exec(code, scope)


if __name__ == "__main__":
    main()
