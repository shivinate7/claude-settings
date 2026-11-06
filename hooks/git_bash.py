"""One home for finding the bash that runs a shell script: Git for Windows' bash.exe on Windows.

Why: on Windows, PATH lists C:\\Windows\\System32 ahead of Git's own bin folder, and System32\\bash.exe
is the WSL launcher, not Git Bash. It runs the script inside Linux, where a Windows path never
resolves (decision bare-bash-on-windows-can-resolve-to-the-wsl-stub). `shutil.which("bash")` is a
plain PATH scan, so it returns that launcher. Every product file that hands a script to bash on
Windows asks here, never for a bare "bash".
"""
import os
import shutil


def find_git_bash(nt=None, environ=None, isfile=os.path.isfile):
    """Git Bash's full path on Windows, else None: never the System32 WSL launcher. Off Windows, PATH's bash
    or None. `nt`, `environ` and `isfile` default to this machine's; a test passes its own."""
    nt = os.name == "nt" if nt is None else nt
    environ = os.environ if environ is None else environ
    if not nt:
        return shutil.which("bash", path=environ.get("PATH"))
    for var in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
        base = environ.get(var)
        if base:
            candidate = os.path.join(base, "Git", "bin", "bash.exe")
            if isfile(candidate):
                return candidate
    # Git installed elsewhere: bin\bash.exe beside the folder that holds git (Git\cmd\git.exe), then a PATH scan.
    git = shutil.which("git", path=environ.get("PATH", ""))
    if git:
        candidate = os.path.join(os.path.dirname(os.path.dirname(git)), "bin", "bash.exe")
        if isfile(candidate):
            return candidate
    # The PATH scan skips System32, where the WSL launcher lives.
    system32 = os.path.normcase(os.path.join(environ.get("SystemRoot", r"C:\Windows"), "System32"))
    for folder in environ.get("PATH", "").split(";"):  # Windows' PATH separator
        if not folder or os.path.normcase(folder).startswith(system32):
            continue
        candidate = os.path.join(folder, "bash.exe")
        if isfile(candidate):
            return candidate
    return None
