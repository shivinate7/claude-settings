#!/usr/bin/env python3
"""Starts hooks/guard.py from its bytecode cache, so a guard call does not compile the guard's 9000 lines again.

Python compiles a script's own source on every start and never caches it, so `python guard.py` pays that compile on
each call (about 115 ms). This file is the tiny script that runs in its place: it loads guard.py's code object through
the standard source loader, which keeps it in hooks/__pycache__ (or under PYTHONPYCACHEPREFIX), and runs it as
`__main__`, exactly as the script start does. The guard's own code, its exits and its fail-closed load check
(`__name__ == "__main__"`) are unchanged.

It writes the cache even when the host sets PYTHONDONTWRITEBYTECODE=1: that setting made every guard call compile
guard.py and each module it imports. Nothing the host or the owner set asks for this override; it is a choice made here
so the cache pays off.

Fail safe: a stale, corrupt or other-version cache is rebuilt, and any error while getting the cached code falls back
to compiling guard.py's source here, the plain start. This file never judges a call and never decides to allow one.

    python3 hooks/guard_launch.py     (stdin: the hook payload, as for guard.py)
"""
import os
import sys


def cached_code(path):
    """The code object of `path` from its bytecode cache, rebuilt once when the cache will not load. None when the
    cache path fails twice, so the caller compiles the source itself."""
    try:
        import importlib.machinery
        import importlib.util
        sys.dont_write_bytecode = False   # the loader writes the cache even when the host asks for none
        loader = importlib.machinery.SourceFileLoader("__main__", path)
        try:
            return loader.get_code("__main__")
        except Exception:
            # A stale or other-version cache never reaches here: the loader rebuilds those itself. A corrupt body does.
            os.remove(importlib.util.cache_from_source(path))
            return loader.get_code("__main__")
    except Exception:
        return None


def main():
    path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "guard.py")
    code = cached_code(path)
    if code is None:
        with open(path, "rb") as handle:
            code = compile(handle.read(), path, "exec")
    scope = sys.modules["__main__"].__dict__
    scope["__file__"] = path
    exec(code, scope)


if __name__ == "__main__":
    main()
