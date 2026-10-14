# Wire %USERPROFILE%\.claude to the files in this clone (Windows local sessions).
#
#   Run once from the clone:   powershell -ExecutionPolicy Bypass -File .\install.ps1
#
# What it does:
#   ~\.claude\CLAUDE.md      -> one-line pointer: @C:/path/to/claude-settings/CLAUDE.md (UTF-8, no BOM)
#   ~\.claude\agents\*.md    -> role definitions (builder, reviewer), symlink per file
#   ~\.claude\lint\*         -> STE linter + hook gate (needs python3 on PATH), symlink per file
#   ~\.claude\hooks\*        -> PreToolUse guard + session-start line, symlink per file
#   ~\.claude\settings.json  -> symlink to <clone>\settings.json (needs Developer Mode or admin),
#                               falls back to a copy plus a git post-merge hook that re-copies
#                               settings.json, agents\*.md, and lint\* after each git pull.
$ErrorActionPreference = 'Stop'

$ScriptPath = $MyInvocation.MyCommand.Path
$RepoDir   = if ($ScriptPath) { Split-Path -Parent $ScriptPath } else { '' }
$ClaudeDir = if ($env:CLAUDE_CONFIG_DIR) { $env:CLAUDE_CONFIG_DIR } else { Join-Path $env:USERPROFILE '.claude' }
New-Item -ItemType Directory -Force -Path $ClaudeDir | Out-Null

function Log([string]$msg) { Write-Host "claude-settings: $msg" }

# $MyInvocation.MyCommand.Path is $null unless this script runs from a file, so a piped run
# (iwr ... | iex) leaves $RepoDir empty and every path built from it points at nowhere. Stop here
# instead of installing to a wrong location.
if (-not $RepoDir -or -not (Test-Path (Join-Path $RepoDir 'CLAUDE.md')) -or -not (Test-Path (Join-Path $RepoDir 'settings.json'))) {
    Log "cannot locate this clone (CLAUDE.md and settings.json not found next to the script)."
    Log "run it from the clone: powershell -ExecutionPolicy Bypass -File .\install.ps1"
    exit 1
}

# One dated line per install.ps1 run, on every exit path, so a copy-mode machine has a record
# of what happened without re-reading Write-Host output.
$InstallLogPath = Join-Path $ClaudeDir 'claude-settings-install.log'
function Write-InstallLog([string]$SettingsMode, [string]$AgentsMode, [string]$HookMode) {
    $line = "$(Get-Date -Format s) install.ps1: settings.json=$SettingsMode agents/lint=$AgentsMode hook=$HookMode`n"
    [System.IO.File]::AppendAllText($InstallLogPath, $line, (New-Object System.Text.UTF8Encoding $false))
}

# Pure: returns $Current with $Bin appended when absent (case-insensitive, trailing \ ignored).
function Join-BinPath([string]$Current, [string]$Bin, [Microsoft.Win32.RegistryValueKind]$Kind = "ExpandString") {
    if (-not $Current) { return $Bin }
    foreach ($e in $Current.Split(';')) {
        if ($e -and $(if ($Kind -eq "String") { $e } else { [Environment]::ExpandEnvironmentVariables($e) }).TrimEnd('\') -ieq $Bin.TrimEnd('\')) { return $Current }
    }
    return "$($Current.TrimEnd(';'));$Bin"
}

# The registry key that holds the user Path. CLAUDE_SETTINGS_USER_ENV_KEY overrides it (tests).
function Get-UserEnvKey {
    if ($env:CLAUDE_SETTINGS_USER_ENV_KEY) { return $env:CLAUDE_SETTINGS_USER_ENV_KEY }
    return 'HKCU:\Environment'
}

# Adds $Bin to the Path value under registry key $KeyPath. Reads it raw and keeps its kind, so
# a %VAR% entry stays unexpanded; writes only when it changed. Returns $true when it wrote.
function Set-UserBinPath([string]$KeyPath, [string]$Bin) {
    $key = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey(($KeyPath -replace '^HKCU:\\?', ''))
    try {
        $raw  = [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames
        $cur  = [string]$key.GetValue('Path', '', $raw)
        $kind = if ($null -eq $key.GetValue('Path', $null)) { 'ExpandString' } else { $key.GetValueKind('Path') }
        $new  = Join-BinPath $cur $Bin $kind
        if ($new -eq $cur) { return $false }
        $key.SetValue('Path', $new, $kind)
        return $true
    } finally { $key.Close() }
}

# Bandaid for machines without symlink rights: a git post-merge hook in this clone re-copies
# settings.json into ~\.claude after every `git pull`, so pull stays the only update step.
# Returns 'installed' or 'skipped', for the install-log summary.
function Install-PostMergeHook {
    $hooksDir = Join-Path $RepoDir '.git\hooks'
    if (-not (Test-Path $hooksDir)) { Log "no .git\hooks directory found; skipping post-merge hook"; return 'skipped' }
    $hookPath = Join-Path $hooksDir 'post-merge'
    $marker   = '# claude-settings post-merge hook'
    if ((Test-Path $hookPath) -and -not ((Get-Content -Raw $hookPath) -match [regex]::Escape($marker))) {
        Log "a post-merge hook already exists at $hookPath and is not ours; left untouched. Re-run install.ps1 after pulls instead."
        return 'skipped'
    }
    $hook = @"
#!/bin/sh
$marker
# Keeps ~/.claude/settings.json, ~/.claude/agents/*, and ~/.claude/lint/* in sync after every
# git pull when symlinks are unavailable. Re-runs install.ps1 when the pull changed it, so a
# changed installer or hook body still lands without a manual re-run.
# Runs only when the checked-out branch is main, so a local merge of an unreviewed branch
# (into any other branch) never pushes its settings.json into ~/.claude.
repo="`$(git rev-parse --show-toplevel)"
branch="`$(git rev-parse --abbrev-ref HEAD)"
if [ "`$branch" != "main" ]; then
  exit 0
fi
cfg="`${CLAUDE_CONFIG_DIR:-`$HOME/.claude}"
log="`$cfg/claude-settings-install.log"
if git rev-parse -q --verify ORIG_HEAD >/dev/null 2>&1 \
   && git diff-tree -r --name-only --no-commit-id ORIG_HEAD HEAD | grep -qx 'install.ps1'; then
  mkdir -p "`$cfg"
  echo "`$(date) post-merge: install.ps1 changed, re-running install.ps1" >> "`$log"
  exec powershell.exe -NoProfile -ExecutionPolicy Bypass -File "`$repo/install.ps1"
fi
# put SRC DEST: build the file at "DEST.cs-new" in DEST's folder, then rename it over DEST, so DEST
# is never absent or half-written (a gate hook reads it at any moment). A .py that carries an
# guard.py or guard_*.py gets this run's id on its whole placeholder line, the same stamp install.ps1
# writes. A rename a reader blocks is retried for about 2.5 s; if it still fails, DEST stays as it
# was, the failure is printed and logged, and the hook exits 1 at the end.
id="`$(date +%Y%m%d%H%M%S)`$`$"
ph='$StampPlaceholder'
cr="`$(printf '\r')"
failed=0
put() {
  t="`$2.cs-new"
  case "`$1" in
    */guard.py|*/guard_*.py) sed "s/^`$ph\(`$cr\{0,1\}\)\`$/INSTALL_ID = \"`$id\"\1/" "`$1" > "`$t" ;;
    *) cp "`$1" "`$t" ;;
  esac && {
    for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25; do
      mv -f "`$t" "`$2" 2>/dev/null && return 0
      sleep 0.1
    done
    false
  }
  rm -f "`$t"
  echo "claude-settings: could not replace `$2; left as it was. Re-run install.ps1." >&2
  mkdir -p "`$cfg"
  echo "`$(date) post-merge: could not replace `$2" >> "`$log"
  failed=1
  return 1
}
dest="`$cfg/settings.json"
if [ -f "`$repo/settings.json" ] && [ ! -L "`$dest" ]; then
  put "`$repo/settings.json" "`$dest" && echo "claude-settings: refreshed `$dest"
fi
# landed-dirs.txt at the repo root names the directories, the same file install.ps1 itself
# reads below and install.sh reads on Linux/macOS. One name per line, `#` comments allowed.
while IFS= read -r sub || [ -n "`$sub" ]; do
  sub=`$(printf '%s' "`$sub" | tr -d '\r' | sed 's/#.*//; s/^[[:space:]]*//; s/[[:space:]]*`$//')
  [ -n "`$sub" ] || continue
  [ -d "`$repo/`$sub" ] || continue
  mkdir -p "`$cfg/`$sub"
  if [ "`$sub" = "skills" ]; then
    for d in "`$repo/`$sub"/*; do
      [ -d "`$d" ] || continue
      dest="`$cfg/`$sub/`$(basename "`$d")"
      if [ -L "`$dest" ]; then continue; fi
      # A real directory here is this same installer's own earlier copy (no symlink
      # rights): replace it, no backup (D: copy-mode-overwrites-no-backup).
      if [ -e "`$dest" ]; then
        rm -rf "`$dest"
      fi
      cp -r "`$d" "`$dest" && echo "claude-settings: refreshed `$dest"
    done
    continue
  fi
  for f in "`$repo/`$sub"/*; do
    [ -f "`$f" ] || continue
    d="`$cfg/`$sub/`$(basename "`$f")"
    [ -L "`$d" ] || { put "`$f" "`$d" && echo "claude-settings: refreshed `$d"; }
  done
done < "`$repo/landed-dirs.txt"
exit "`$failed"
"@
    $hook = $hook -replace "`r`n", "`n"
    $tmpPath = Join-Path $hooksDir 'post-merge.tmp'
    [System.IO.File]::WriteAllText($tmpPath, $hook, (New-Object System.Text.UTF8Encoding $false))
    Move-Item -Force $tmpPath $hookPath
    Log "installed git post-merge hook; 'git pull' on main now refreshes settings.json, agents, and lint, and reruns install.ps1 when it changed. Merges on other branches are skipped."
    return 'installed'
}

# ---- CLAUDE.md pointer -------------------------------------------------------------------------
# Forward slashes: the @import parser is happier with them than with backslashes.
# Written as UTF-8 without a BOM: Windows PowerShell 5.1 `Set-Content -Encoding UTF8` prepends
# U+FEFF, which the @import parser reads as part of the path. The comparison also ignores a
# leading BOM so a file the old installer wrote is not backed up on every rerun.
# Kept as a function so install.test.ps1 can exercise it against a temp directory.
function Write-Pointer([string]$RepoDir, [string]$ClaudeDir) {
    $Pointer  = '@' + (($RepoDir -replace '\\', '/').TrimEnd('/')) + '/CLAUDE.md'
    $TargetMd = Join-Path $ClaudeDir 'CLAUDE.md'

    if (Test-Path $TargetMd) {
        $existing = Get-Content -Raw $TargetMd
        if ($existing.TrimStart([char]0xFEFF).Trim() -ne $Pointer) {
            $bak = "$TargetMd.bak.$(Get-Date -Format yyyyMMddHHmmss)"
            Copy-Item $TargetMd $bak
            Log "existing $TargetMd backed up to $bak; fold anything you want to keep into $RepoDir\CLAUDE.md"
        }
    }
    [IO.File]::WriteAllText($TargetMd, $Pointer, [Text.UTF8Encoding]::new($false))
    Log "wrote $TargetMd -> $Pointer"
}
Write-Pointer -RepoDir $RepoDir -ClaudeDir $ClaudeDir

# ---- agents\ and lint\ : per-file symlinks, copy fallback -----------------------------------------
# After landing every file the source defines now, prune a destination entry this same loop
# symlinked on an earlier run, for a source file that has since gone away. Mirrors install.sh's
# land_dir() prune: see the comment above land_dir() there for the reasoning and the three
# tests. A prune candidate must be a symlink, its target must sit inside $srcDir (never a
# hand-made link elsewhere), and that target must no longer exist. A regular file (including a
# ".bak.*" file this loop writes above) fails the first test and is left alone.
#
# When symlinks are not permitted, this loop falls back to Copy-Item, same as install.sh's
# cloud mode. That copy is pruned no more than install.sh prunes a cloud copy: a copied file
# carries no mark of which source made it, so this loop does not remove it. It is left in
# place as a documented gap, same reasoning as install.sh's cloud-mode comment.
# The set of directories landed here comes from landed-dirs.txt at the repo root, the single
# source the embedded post-merge hook above reads too, and that install.sh reads on
# Linux/macOS (see the comment there). hooks/guard.py's CONFIG_FROZEN_DIRS is a deliberately
# separate literal; see the comment beside it in hooks/guard.py for why. lint/check_landed_dirs.py
# checks the two stay in agreement.
function Get-LandedDirs([string]$FromRepoDir) {
    Get-Content (Join-Path $FromRepoDir 'landed-dirs.txt') |
        ForEach-Object { ($_ -replace '#.*', '').Trim() } |
        Where-Object { $_ -ne '' }
}

# A real file/dir at a landed name is either a person's own pre-existing file (a true
# first install here: back it up) or this same installer's own earlier copy, from a prior
# no-symlink-rights run that fell back to Copy-Item (a repeat install: no backup, per
# D: copy-mode-overwrites-no-backup). Content can't tell the two apart, since the source
# legitimately changes between runs, so this marker does. It is the same file install.sh
# writes and reads ($ClaudeDir\.claude-settings-installed), so either installer having run
# once here is enough to call every later real file "ours". Written once, at every
# successful-run exit, by Write-CopyMarker below.
$CopyMarker = Join-Path $ClaudeDir '.claude-settings-installed'
$FirstLocalRun = -not (Test-Path $CopyMarker)
function Write-CopyMarker { [IO.File]::WriteAllText($CopyMarker, '') }

$AgentCopied = $false
$AgentFailed = $false

# One home for every symlink try. CLAUDE_SETTINGS_FORCE_COPY=1 makes it throw, so copy mode
# runs on any machine (install-no-gap.test.ps1).
function New-Link([string]$Path, [string]$Target) {
    if ($env:CLAUDE_SETTINGS_FORCE_COPY -eq '1') { throw 'symlink forced off by CLAUDE_SETTINGS_FORCE_COPY' }
    New-Item -ItemType SymbolicLink -Path $Path -Target $Target -ErrorAction Stop | Out-Null
}

# Removes a leftover file, directory, or link. A directory link goes without -Recurse, so
# the target's contents are never touched.
function Remove-Leftover([string]$Path) {
    $i = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    if (-not $i) { return }
    if ($i.PSIsContainer -and $i.LinkType) { [IO.Directory]::Delete($Path) }
    elseif ($i.PSIsContainer) { Remove-Item -LiteralPath $Path -Recurse -Force }
    else { Remove-Item -LiteralPath $Path -Force }
}

# Moves the file or link $From onto $To in one OS call (MoveFileEx, REPLACE_EXISTING). $To is
# replaced as a name: a link at $To is replaced, never followed, and no moment has no file at
# $To. Move-Item -Force is not used: PowerShell 5.1 may delete $To before it moves.
function Move-OverFile([string]$From, [string]$To) {
    if ($env:OS -ne 'Windows_NT') { Move-Item -LiteralPath $From -Destination $To -Force; return }
    if (-not ('ClaudeSettingsMove' -as [type])) {
        Add-Type -TypeDefinition @'
using System.Runtime.InteropServices;
public static class ClaudeSettingsMove {
    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    public static extern bool MoveFileEx(string from, string to, int flags);
}
'@
    }
    # A reader that has $To open (a Python import, say) blocks the rename for a moment: retry
    # for about 2.5 s, then give up and leave $To as it was.
    for ($try = 1; ; $try++) {
        if ([ClaudeSettingsMove]::MoveFileEx($From, $To, 1)) { return }
        $code = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
        if ($try -ge 25 -or ($code -ne 5 -and $code -ne 32)) { throw (New-Object ComponentModel.Win32Exception($code)).Message }
        Start-Sleep -Milliseconds 100
    }
}

# One id per run. In guard.py and guard_*.py only, the whole line $StampPlaceholder becomes
# `INSTALL_ID = "<id>"` at copy time, so hooks/guard.py can tell a half-installed set from a whole one.
# The repo copy holds the placeholder. No other line is touched: a prose line that starts the same
# way stays as it is. The post-merge hook above builds its sed from $StampPlaceholder; install.sh
# holds the same literal, because sh cannot share this code.
$InstallId = Get-Date -Format yyyyMMddHHmmssfff
$StampPlaceholder = '# INSTALL_ID = "uninstalled"'
$StampLineRe = '(?m)^' + [regex]::Escape($StampPlaceholder) + '(?=\r?$)'
function Test-StampTarget([string]$Name) { return ($Name -ceq 'guard.py' -or $Name -clike 'guard_*.py') }
function Set-InstallId([string]$Path) {
    $text = [IO.File]::ReadAllText($Path)
    $new  = [regex]::Replace($text, $StampLineRe, "INSTALL_ID = `"$InstallId`"")
    if ($new -ne $text) { [IO.File]::WriteAllText($Path, $new, (New-Object Text.UTF8Encoding $false)) }
}

# No-gap replace, one route for every file: build the new file or link at "$Dest.cs-new" in the
# same folder, stamp it (Set-InstallId), then move it onto $Dest in one call (Move-OverFile).
# $Dest is never absent and never half-written, so a gate hook that reads it mid-run sees the
# old file or the new one. A failed step (a file lock that outlasts the retries, say) leaves
# $Dest as it was. The failure is logged and the run goes on.
# Returns 'linked', 'copied', or 'failed'. The temp name ends in .cs-new, so it does not match a
# name a person gives a file.
$FailedFiles = [ordered]@{}   # dest -> src, for each file Install-File could not replace
function Install-File([string]$Src, [string]$Dest) {
    $new = "$Dest.cs-new"
    try {
        Remove-Leftover $new
        try { New-Link $new $Src; $how = 'linked' }
        catch { $how = 'copied'; Copy-Item -LiteralPath $Src -Destination $new -Force; if (Test-StampTarget (Split-Path $Dest -Leaf)) { Set-InstallId $new } }
        Move-OverFile $new $Dest
        return $how
    } catch {
        $err = $_.Exception.Message
        try { Remove-Leftover $new } catch { Log "could not remove $new ($($_.Exception.Message)); left behind" }
        Log "could not replace $Dest ($err); $Dest unchanged"
        $FailedFiles[$Dest] = $Src
        return 'failed'
    }
}

# Same for a directory. A real directory from an earlier copy is refreshed in place when no
# link can be made. Otherwise: build at
# "$Dest.cs-new", rename $Dest to $Old, rename the new one to $Dest, then remove $Old (unless
# $KeepOld: it is a backup). If the second rename fails the first is undone.
# Named gap: Windows cannot swap a directory in one call, so a real directory replaced by a
# link (or a link by a copy) is absent for the time between the two renames. Skills are not
# gate scripts; no hook fails closed on one. Returns 'linked', 'copied', or 'failed'.
function Install-Dir([string]$Src, [string]$Dest, [string]$Old, [bool]$KeepOld) {
    $new = "$Dest.cs-new"
    $state = 'unchanged'   # unchanged | refreshing | moved-away | rollback-failed
    $how = 'copied'
    try {
        Remove-Leftover $new
        if (-not $KeepOld) { Remove-Leftover $Old }
        try { New-Link $new $Src; $how = 'linked' }
        catch {
            $cur = Get-Item -LiteralPath $Dest -Force -ErrorAction SilentlyContinue
            if ($cur -and $cur.PSIsContainer -and -not $cur.LinkType -and -not $KeepOld) {
                # A real directory from an earlier copy: refresh it in place, so the name is
                # never renamed away. Copy first, then prune what the source no longer has.
                $state = 'refreshing'
                Get-ChildItem -LiteralPath $Src -Force | Copy-Item -Destination $Dest -Recurse -Force
                $want = @{}
                foreach ($f in @(Get-ChildItem -LiteralPath $Src -Recurse -Force)) { $want[$f.FullName.Substring($Src.Length)] = $true }
                $stale = @(Get-ChildItem -LiteralPath $Dest -Recurse -Force) |
                    Where-Object { -not $want.ContainsKey($_.FullName.Substring($Dest.Length)) } |
                    Sort-Object { $_.FullName.Length } -Descending
                foreach ($f in $stale) { Remove-Leftover $f.FullName }
                return $how
            }
            Copy-Item -LiteralPath $Src -Destination $new -Recurse -Force
        }
        if (Get-Item -LiteralPath $Dest -Force -ErrorAction SilentlyContinue) {
            [IO.Directory]::Move($Dest, $Old); $state = 'moved-away'
        }
        try { [IO.Directory]::Move($new, $Dest) }
        catch {
            $e = $_
            if ($state -eq 'moved-away') {
                try { [IO.Directory]::Move($Old, $Dest); $state = 'unchanged' }
                catch { $state = 'rollback-failed'; Log "could not restore $Dest from $Old ($($_.Exception.Message))" }
            }
            throw $e
        }
    } catch {
        $err = $_.Exception.Message
        try { Remove-Leftover $new } catch { Log "could not remove $new ($($_.Exception.Message)); left behind" }
        $left = switch ($state) {
            'refreshing'      { "$Dest may be partly refreshed; the next run finishes it" }
            'rollback-failed' { "$Dest is missing; the old copy is at $Old" }
            default           { "$Dest unchanged" }
        }
        Log "could not replace $Dest ($err); $left"
        return 'failed'
    }
    if ($state -eq 'moved-away' -and -not $KeepOld) {
        try { Remove-Leftover $Old } catch { Log "could not remove $Old ($($_.Exception.Message)); left behind" }
    }
    return $how
}
foreach ($sub in (Get-LandedDirs $RepoDir)) {
    $srcDir  = Join-Path $RepoDir $sub
    $destDir = Join-Path $ClaudeDir $sub
    New-Item -ItemType Directory -Force -Path $destDir | Out-Null

    # skills/ lands differently: each skills/<name>/ is ONE whole-directory symlink, never
    # a per-file link, since a per-file loop skips a directory entry outright (Get-ChildItem
    # -File never returns it) and a landed skill would never appear at all. A pre-existing
    # entry this repo does not ship (a person's own skill) is never touched: the loop only
    # ever looks at names under $srcDir, so a name absent there is never a candidate.
    if ($sub -eq 'skills') {
        foreach ($src in @(Get-ChildItem -Path $srcDir -Directory -ErrorAction SilentlyContinue)) {
            $dest = Join-Path $destDir $src.Name
            $cur  = Get-Item $dest -ErrorAction SilentlyContinue
            if ($cur -and $cur.LinkType -eq 'SymbolicLink' -and $cur.Target -eq $src.FullName) { continue }
            # A real directory (or a symlink pointing elsewhere) at $dest: on the first
            # local install ever, it is a person's own hand-made skill, backed up. After
            # that, it is this same installer's own earlier copy, from a no-symlink-rights
            # machine where the symlink attempt below fell back to Copy-Item: replace it,
            # no backup (D: copy-mode-overwrites-no-backup). Install-Dir swaps by rename,
            # so the skill is never absent.
            $bak  = "$dest.bak.$(Get-Date -Format yyyyMMddHHmmss)"
            $keep = [bool]($cur -and $FirstLocalRun)
            $old  = if ($keep) { $bak } else { "$dest.cs-old" }
            $how  = Install-Dir $src.FullName $dest $old $keep
            if ($how -eq 'failed') { $AgentFailed = $true; continue }
            if ($keep) { Log "existing $dest moved to $bak" }
            if ($how -eq 'linked') {
                Log "linked $dest -> $($src.FullName)"
            } else {
                $AgentCopied = $true
                Log "copied $dest (symlink not permitted)"
            }
        }
        foreach ($entry in @(Get-ChildItem -Path $destDir -Directory -ErrorAction SilentlyContinue)) {
            if ($entry.LinkType -ne 'SymbolicLink') { continue }
            $tgt = @($entry.Target)[0]
            if (-not $tgt) { continue }
            if ((Split-Path $tgt -Parent) -ne $srcDir) { continue }
            if (Test-Path $tgt) { continue }
            Remove-Item $entry.FullName
            Log "removed stale $($entry.FullName) (source $tgt no longer exists)"
        }
        continue
    }

    foreach ($src in @(Get-ChildItem -Path $srcDir -File -ErrorAction SilentlyContinue)) {
        $dest = Join-Path $destDir $src.Name
        $cur  = Get-Item $dest -ErrorAction SilentlyContinue
        if ($cur -and $cur.LinkType -eq 'SymbolicLink' -and $cur.Target -eq $src.FullName) { continue }
        # A real file (or a symlink pointing elsewhere) at $dest: on the first local
        # install ever, it is a person's own file, backed up. After that, it is this same
        # installer's own earlier copy, from a no-symlink-rights machine where the symlink
        # attempt below fell back to Copy-Item: replace it, no backup
        # (D: copy-mode-overwrites-no-backup). Matches the skills branch above, so both
        # branches agree. Install-File swaps by rename, so the file is never absent or half-written.
        if ($cur -and $FirstLocalRun) {
            $bak = "$dest.bak.$(Get-Date -Format yyyyMMddHHmmss)"
            Copy-Item $dest $bak
            Log "existing $dest backed up to $bak"
        }
        $how = Install-File $src.FullName $dest
        if ($how -eq 'linked') {
            Log "linked $dest -> $($src.FullName)"
        } elseif ($how -eq 'copied') {
            $AgentCopied = $true
            Log "copied $dest (symlink not permitted)"
        }
        # A 'failed' file is in $FailedFiles; Resolve-Failures retries it and sets $AgentFailed only
        # for a file that still fails, so a recovered file does not read as failed.
    }
    foreach ($entry in @(Get-ChildItem -Path $destDir -File -ErrorAction SilentlyContinue)) {
        if ($entry.LinkType -ne 'SymbolicLink') { continue }
        # .Target can come back as a one-element array depending on PowerShell version;
        # take the first (only) element either way.
        $tgt = @($entry.Target)[0]
        if (-not $tgt) { continue }
        if ((Split-Path $tgt -Parent) -ne $srcDir) { continue }
        if (Test-Path $tgt) { continue }
        Remove-Item $entry.FullName
        Log "removed stale $($entry.FullName) (source $tgt no longer exists)"
    }
}
if (-not (Get-Command python3 -ErrorAction SilentlyContinue) -and -not (Get-Command python -ErrorAction SilentlyContinue)) {
    Log "python3 not found on PATH; the guard, STE gate and other gates refuse Bash, Write and Edit calls until Python 3 is installed"
}

# Retries each file Install-File could not replace, with a longer back-off (2, 4, 8 s), then re-reads
# the stamp of every copied guard.py and guard_*.py: a copy that does not carry this run's id is a half install,
# so it is retried the same way. A file that still fails is named here and the run exits non-zero
# at its end; the guard then fails closed and its text names this installer as the remedy.
# Links are skipped: a link reads the repo file, and the repo copy holds the placeholder.
$StillFailed = [ordered]@{}
function Resolve-Failures {
    $hooksDest = Join-Path $ClaudeDir 'hooks'
    $hooksSrc  = Join-Path $RepoDir 'hooks'
    $stampRe   = '(?m)^INSTALL_ID = "([^"]*)"'
    foreach ($delay in 2, 4, 8, 0) {
        foreach ($f in @(Get-ChildItem -Path $hooksSrc -Filter 'guard*.py' -File -ErrorAction SilentlyContinue | Where-Object { Test-StampTarget $_.Name })) {
            $d = Join-Path $hooksDest $f.Name
            $i = Get-Item -LiteralPath $d -Force -ErrorAction SilentlyContinue
            if ($i -and $i.LinkType) { continue }
            # The id the copy must carry: this run's id where the source holds the placeholder, else the
            # id the source already carries. A source with neither has nothing to check.
            $srcText = [IO.File]::ReadAllText($f.FullName)
            $want = if ($srcText -match $StampLineRe) { $InstallId }
                    elseif ($srcText -match $stampRe) { $Matches[1] }
                    else { continue }
            $ok = $false
            if ($i) {
                try { $m = [regex]::Match([IO.File]::ReadAllText($d), $stampRe); $ok = ($m.Success -and $m.Groups[1].Value -eq $want) } catch { }
            }
            if (-not $ok -and -not $FailedFiles.Contains($d)) { $FailedFiles[$d] = $f.FullName }
        }
        if ($FailedFiles.Count -eq 0) { return }
        if ($delay -eq 0) { break }
        Log "$($FailedFiles.Count) file(s) not replaced; retrying in $delay s"
        Start-Sleep -Seconds $delay
        foreach ($d in @($FailedFiles.Keys)) {
            $src = $FailedFiles[$d]
            $FailedFiles.Remove($d)
            $r = Install-File $src $d
            if ($r -eq 'copied') { $script:AgentCopied = $true }
        }
    }
    foreach ($d in @($FailedFiles.Keys)) { $StillFailed[$d] = $FailedFiles[$d]; Log "could not replace $d after retries; it is not this install's version" }
    $FailedFiles.Clear()
}
Resolve-Failures
if ($StillFailed.Count -gt 0) { $AgentFailed = $true }

# 'copy+failed': some files were copied and at least one replace failed (the run prints which).
$AgentsMode = if ($AgentCopied -and $AgentFailed) { 'copy+failed' } elseif ($AgentCopied) { 'copy' } elseif ($AgentFailed) { 'kept' } else { 'symlink' }

# On the first local run, a failed replace may have left a person's own file unbacked (a lock
# on a skill blocks its move to .bak). Without the marker, the next run is a first run again,
# so it backs that file up before it replaces it. It never refreshes it in place or prunes it.
function Complete-Run([bool]$Failed) {
    if ($FirstLocalRun -and $Failed) { Log "a replace failed on the first install; no install marker written, so the next run backs up again"; return }
    Write-CopyMarker
}

# ---- settings.json -----------------------------------------------------------------------------
$SrcJson    = Join-Path $RepoDir 'settings.json'
$TargetJson = Join-Path $ClaudeDir 'settings.json'

$item = Get-Item $TargetJson -ErrorAction SilentlyContinue
if ($item -and $item.LinkType -eq 'SymbolicLink' -and $item.Target -eq $SrcJson) {
    Log "$TargetJson already links to $SrcJson"
    $HookMode = 'not needed'
    if ($AgentCopied) { $HookMode = Install-PostMergeHook }
    Write-InstallLog -SettingsMode 'symlink' -AgentsMode $AgentsMode -HookMode $HookMode
    Complete-Run $AgentFailed
    exit $(if ($StillFailed.Count -gt 0) { 1 } else { 0 })
}

# A real file here: on the first local install ever, it is a person's own settings.json,
# backed up. After that, it is this same installer's own earlier copy, from a
# no-symlink-rights machine where the symlink attempt below fell back to Copy-Item:
# replace it, no backup (D: copy-mode-overwrites-no-backup).
if ($item -and -not $item.LinkType -and $FirstLocalRun) {
    $bak = "$TargetJson.bak.$(Get-Date -Format yyyyMMddHHmmss)"
    Copy-Item $TargetJson $bak
    Log "existing $TargetJson backed up to $bak; merge any keys you want (permissions, etc.) into $SrcJson"
}

$how = Install-File $SrcJson $TargetJson
if ($how -eq 'linked') {
    Log "linked $TargetJson -> $SrcJson (git pull in the clone is now the whole update)"
    Write-InstallLog -SettingsMode 'symlink' -AgentsMode $AgentsMode -HookMode 'not needed'
} else {
    if ($how -eq 'copied') { Log "symlink not permitted (enable Windows Developer Mode, or run as admin); copied instead." }
    $HookMode = Install-PostMergeHook
    Write-InstallLog -SettingsMode $(if ($how -eq 'failed') { 'kept' } else { 'copy' }) -AgentsMode $AgentsMode -HookMode $HookMode
}
if ($how -eq 'failed') { Resolve-Failures; if ($StillFailed.Count -gt 0) { $how = 'failed' } else { $how = 'copied' } }
Complete-Run ($AgentFailed -or $how -eq 'failed')

# ~\.claude\bin on the user PATH, so `merge` and `verdict` resolve in new sessions.
if ($env:OS -ne 'Windows_NT') {
    Log "the user PATH step is Windows-only; skipped"
} else {
    $BinDir = Join-Path $env:USERPROFILE '.claude\bin'
    if (Set-UserBinPath (Get-UserEnvKey) $BinDir) {
        Log "added $BinDir to your user PATH; a new session picks it up"
    }
}
if ($StillFailed.Count -gt 0) { exit 1 }
