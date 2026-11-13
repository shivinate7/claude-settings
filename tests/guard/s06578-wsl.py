# section 6578
FAMILY = "wsl"
FAMILIES["wsl"] = "the WSL launch allow list, the refused WSL forms, and quoted or commented text"
for _label, _open, _close, _mw in (
        ("EOF-1", "EOF-1", "EOF-1", "EOF"),
        ('"E"OF', '"E"OF', "EOF", "E"),
        ("EOF.1", "EOF.1", "EOF.1", "EOF"),
):
    sh("heredoc safety hole: delimiter %s, a wsl shutdown in the second body that sh runs, denies" % _label,
       "cat <<" + _open + "\na\n" + _close + "\ncat <<EOF2 > x.sh\necho hi\n" + _mw + "\n" + HOLE_WSL + "\nEOF2\nsh x.sh",
       "deny", "wsl-allow-list", cwd=NOGIT)


# =========================================================================== 2c. live streams
