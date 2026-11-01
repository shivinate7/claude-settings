# Wire %USERPROFILE%\.claude to the files in this clone (Windows local sessions).
#
#   Run once from the clone:   powershell -ExecutionPolicy Bypass -File .\install.ps1
#
# What it does:
#   ~\.claude\CLAUDE.md      -> one-line pointer: @C:/path/to/claude-settings/CLAUDE.md (UTF-8, no BOM)
#   ~\.claude\agents\*.md    -> role definitions (builder, reviewer), symlink per file
#   ~\.claude\lint\*         -> STE linter and report guard (needs python3 on PATH), symlink per file
#   ~\.claude\hooks\*        -> PreToolUse guard + session-start line, symlink per file
#   ~\.claude\settings.json  -> symlink to <clone>\settings.json (needs Developer Mode or admin),
#                               falls back to a copy plus a git post-merge hook that re-copies
#                               settings.json, agents\*.md, and lint\* after each git pull.
$ErrorActionPreference = 'Stop'

$ScriptPath = $MyInvocation.MyCommand.Path
$RepoDir   = if ($ScriptPath) { Split-Path -Parent $ScriptPath } else { '' }
# git with the error preference off: a failing native call must not throw. Output on stdout only.
function Get-Git { $ErrorActionPreference = 'Continue'; & git @args 2>$null }
function Get-FullDir([string]$p) { [IO.Path]::GetFullPath($p).TrimEnd('\') }
$CloneDir = $RepoDir     # the clone that holds .git\hooks; $RepoDir moves to the pinned checkout below
$IsLinked = $false
# An install from a linked worktree would point the global config at a temp
# checkout. Refuse before any write. --git-dir and --git-common-dir differ only in a linked
# worktree; both print relative to -C, so a string compare is enough. No git, or no .git: go on.
# Decision merge-reinstalls-from-main: the pinned checkout <clone>-live is the one linked worktree
# allowed, and only on a detached HEAD at the clone's local main commit. $CloneDir moves to the
# clone, so the post-merge hook lands in the clone's .git\hooks.
if ($RepoDir) {
    try {
        $gd = Get-Git -C $RepoDir rev-parse --git-dir
        if ($LASTEXITCODE -eq 0) { $gc = Get-Git -C $RepoDir rev-parse --git-common-dir }
        if ($LASTEXITCODE -eq 0 -and $gd -and $gc -and "$gd" -ne "$gc") {
            $IsLinked = $true
            $m = (Get-Git -C $RepoDir worktree list --porcelain | Select-Object -First 1) -replace '^worktree ', ''
            if (-not $m -or (Get-FullDir $RepoDir) -ine ((Get-FullDir $m) + '-live')) {
                Write-Host "claude-settings: ERROR: $RepoDir is a linked git worktree; run the installer from the main clone$(if ($m) { " $m" })."
                exit 1
            }
            $mainAt = Get-Git -C $RepoDir rev-parse --verify -q refs/heads/main
            Get-Git -C $RepoDir symbolic-ref -q HEAD | Out-Null
            $onBranch = $LASTEXITCODE -eq 0
            $headAt = Get-Git -C $RepoDir rev-parse HEAD
            if ($onBranch -or -not $mainAt -or "$headAt" -ne "$mainAt") {
                Write-Host "claude-settings: ERROR: the pinned checkout $RepoDir is not detached at local main; run merge/install_from_main.sh from the clone $m to move it."
                exit 1
            }
            $CloneDir = Get-FullDir $m
        }
    } catch { }
}
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

# ---- one install at a time, one start line and one end line in the install log -----------------------
# Decision install-hooks-whole. The lock is a file made with CreateNew and held open with no
# sharing and delete-on-close, so it goes away when this run ends, even if it dies. install.sh and the
# post-merge hook make the same file with noclobber, so the three paths wait on each other. A run waits
# CLAUDE_SETTINGS_LOCK_WAIT seconds (default 60), then prints one line and exits 1 with nothing written.
# A lock file older than 10 minutes is a dead sh run's: it is removed. The id is unique per run: the
# time plus the process id. The log lines name it with the pid.
$InstallId = (Get-Date -Format yyyyMMddHHmmssfff) + $PID
$InstallLogPath = Join-Path $ClaudeDir 'claude-settings-install.log'
function Add-InstallLogLine([string]$Line) {
    [System.IO.File]::AppendAllText($InstallLogPath, "$Line`n", (New-Object System.Text.UTF8Encoding $false))
}
$script:ExitCode = 1
function Exit-Install([int]$Code) { $script:ExitCode = $Code; exit $Code }
$LockPath = Join-Path $ClaudeDir '.claude-settings-install.lock'
$LockDeadline = (Get-Date).AddSeconds($(if ($env:CLAUDE_SETTINGS_LOCK_WAIT) { [int]$env:CLAUDE_SETTINGS_LOCK_WAIT } else { 60 }))
$LockStream = $null
# merge/install_from_main.sh holds the lock through its install.ps1 call. It writes its id into the
# lock file and passes that id as CLAUDE_SETTINGS_LOCK_TOKEN; when the two match, this run works under
# that lock: it does not wait, and it leaves the lock for its parent to remove.
$HeldByParent = $false
if ($env:CLAUDE_SETTINGS_LOCK_TOKEN) {
    $held = Get-Content -LiteralPath $LockPath -TotalCount 1 -ErrorAction SilentlyContinue
    $HeldByParent = ([string]$held).Trim() -eq $env:CLAUDE_SETTINGS_LOCK_TOKEN
}
while (-not $LockStream -and -not $HeldByParent) {
    try { $LockStream = New-Object IO.FileStream($LockPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None, 4096, [IO.FileOptions]::DeleteOnClose) }
    catch {
        $held = Get-Item -LiteralPath $LockPath -Force -ErrorAction SilentlyContinue
        if ($held -and $held.LastWriteTime -lt (Get-Date).AddMinutes(-10)) { Remove-Item -LiteralPath $LockPath -Force -ErrorAction SilentlyContinue; continue }
        if ((Get-Date) -gt $LockDeadline) {
            Log "ERROR: another install holds the lock $LockPath; nothing was changed. Run install.ps1 again when it ends, or delete that file if no install is running."
            exit 1
        }
        Start-Sleep -Milliseconds 200
    }
}
Add-InstallLogLine "$(Get-Date -Format s) install.ps1: start id=$InstallId pid=$PID"
try {

# Decision merge-reinstalls-from-main: run from a clone that has a branch named main, the links
# point at the pinned checkout <clone>-live, a worktree on a detached HEAD at main's commit, never
# at the clone, whose branch changes. Made here when missing; only merge/install_from_main.sh
# moves it. A clone with no main branch stays unpinned.
if (-not $IsLinked -and (Test-Path -LiteralPath (Join-Path $RepoDir '.git'))) {
    $MainCommit = Get-Git -C $RepoDir rev-parse --verify -q refs/heads/main
    if ($LASTEXITCODE -eq 0 -and $MainCommit) {
        $Pin = (Get-FullDir $RepoDir) + '-live'
        if (-not (Test-Path -LiteralPath $Pin)) {
            $err = & { $ErrorActionPreference = 'Continue'; & git -C $RepoDir worktree add -q --detach --lock --reason 'claude-settings live pin' $Pin $MainCommit 2>&1 }
            if ($LASTEXITCODE -ne 0) { Log "ERROR: cannot make the pinned checkout ${Pin}: $(($err | ForEach-Object { "$_" }) -join ' '); fix that and run install.ps1 again."; Exit-Install 1 }
            Log "made the pinned checkout $Pin at main"
        } else {
            $pc = Get-Git -C $Pin rev-parse --path-format=absolute --git-common-dir
            $rc = Get-Git -C $RepoDir rev-parse --path-format=absolute --git-common-dir
            if (-not $pc -or -not $rc -or (Get-FullDir $pc) -ine (Get-FullDir $rc)) {
                Log "ERROR: $Pin is not a worktree of $RepoDir; move it aside and run install.ps1 again."
                Exit-Install 1
            }
            Get-Git -C $Pin symbolic-ref -q HEAD | Out-Null
            $pinOnBranch = $LASTEXITCODE -eq 0
            if ($pinOnBranch -or "$(Get-Git -C $Pin rev-parse HEAD)" -ne "$MainCommit") {
                Log "ERROR: the pinned checkout $Pin is not detached at local main; run merge/install_from_main.sh from the clone $RepoDir to move it."
                Exit-Install 1
            }
            # Lock an unlocked pin, so the janitor sweep never removes it; a locked one stays as it is.
            & { $ErrorActionPreference = 'Continue'; & git -C $RepoDir worktree lock --reason 'claude-settings live pin' $Pin 2>&1 | Out-Null }
        }
        $RepoDir = $Pin
    } else {
        Log "WARN: $RepoDir has no branch named main; the links follow the clone's checked-out branch"
    }
}

# One dated line per install.ps1 run, on every exit path, so a copy-mode machine has a record
# of what happened without re-reading Write-Host output.
function Write-InstallLog([string]$SettingsMode, [string]$AgentsMode, [string]$HookMode) {
    Add-InstallLogLine "$(Get-Date -Format s) install.ps1: settings.json=$SettingsMode agents/lint=$AgentsMode hook=$HookMode"
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

$PostMergeMarker = '# claude-settings post-merge hook'

# Link mode needs no hook, and a stale one of ours would copy files over the links after a merge.
# Removes only a hook that carries our marker; any other post-merge hook stays untouched.
# Returns 'removed', 'not needed' or 'delete failed', for the install-log summary.
function Remove-PostMergeHook {
    $hookPath = Join-Path $CloneDir '.git\hooks\post-merge'
    if (-not (Test-Path -LiteralPath $hookPath)) { return 'not needed' }
    if (-not ((Get-Content -Raw -LiteralPath $hookPath) -match [regex]::Escape($PostMergeMarker))) { return 'not needed' }
    try { Remove-Item -LiteralPath $hookPath -Force -ErrorAction Stop }
    catch {
        $why = "could not delete the post-merge hook at ${hookPath}: $($_.Exception.Message)"
        Log $why
        Add-InstallLogLine "$(Get-Date -Format s) install.ps1: $why"
        return 'delete failed'
    }
    Log "symlinks work; removed the post-merge hook at $hookPath"
    return 'removed'
}

# Both link-mode exits call this. A copied agent or skill still needs the hook, so it stays then.
function Resolve-PostMergeHook {
    if ($AgentCopied) { return Install-PostMergeHook }
    return Remove-PostMergeHook
}

# Bandaid for machines without symlink rights: a git post-merge hook in this clone re-copies
# settings.json into ~\.claude after every `git pull`, so pull stays the only update step.
# Returns 'installed' or 'skipped', for the install-log summary.
function Install-PostMergeHook {
    $hooksDir = Join-Path $CloneDir '.git\hooks'
    if (-not (Test-Path $hooksDir)) { Log "no .git\hooks directory found; skipping post-merge hook"; return 'skipped' }
    $hookPath = Join-Path $hooksDir 'post-merge'
    $marker   = $PostMergeMarker
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
# This hook lands files but removes none, and keeps no manifest: install.ps1 does that.
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
# is never absent or half-written (a guard hook reads it at any moment). A .py that carries an
# guard.py or guard_*.py gets this run's id on its whole placeholder line, the same stamp install.ps1
# writes. A rename a reader blocks is retried for about 2.5 s; if it still fails, DEST stays as it
# was, the failure is printed and logged, and the hook exits 1 at the end.
id="`$(date +%Y%m%d%H%M%S)`$`$"
ph='$StampPlaceholder'
cr="`$(printf '\r')"
failed=0
# One install at a time, and a start and an end line in the log: the same lock file install.ps1 and
# install.sh take (owner ruling 2026-10-15, install-set). A run waits CLAUDE_SETTINGS_LOCK_WAIT seconds
# (default 60), then prints one line and exits 1 with nothing written. A lock older than 10 minutes
# is a dead run's.
lock="`$cfg/.claude-settings-install.lock"
mkdir -p "`$cfg"
tries=`$(( `${CLAUDE_SETTINGS_LOCK_WAIT:-60} * 5 ))
while ! ( set -C; printf '%s\n' "`$`$" > "`$lock" ) 2>/dev/null; do
  if [ -n "`$(find "`$lock" -mmin +10 2>/dev/null)" ]; then rm -f "`$lock"; continue; fi
  tries=`$((tries - 1))
  if [ "`$tries" -le 0 ]; then
    echo "claude-settings: another install holds the lock `$lock; nothing was changed. Run install.ps1 again when it ends, or delete that file if no install is running." >&2
    exit 1
  fi
  sleep 0.2
done
logline() { printf '%s post-merge: %s id=%s pid=%s\n' "`$(date +%Y-%m-%dT%H:%M:%S)" "`$1" "`$id" "`$`$" >> "`$log"; }
logline start
trap 'rc=`$?; logline "end exit=`$rc"; rm -f "`$lock"' EXIT
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
# land_guard_set SRC DEST: the guard files, as one set (owner ruling 2026-10-15, install-set). Step 1
# writes every guard file, stamped with this run's id, and shared_names.py, git_reads.py, question_form.py and precompact_handoff.py, which the guard imports,
# into DEST/guard.d/<id>/, where no guard reads it
# yet. Step 2 replaces DEST/guard.py, the one landing that switches: a stamped guard.py loads
# guard.d/<its id>/. Step 3 lands the flat guard_*.py. The folder of the set before this one stays;
# older ones go. A step 1 failure removes the new folder and lands nothing: the old set stays whole.
land_guard_set() {
  gdir="`$2/guard.d/`$id"
  prev=`$(sed -n 's/^INSTALL_ID = "\([^"]*\)".*/\1/p' "`$2/guard.py" 2>/dev/null | head -n1)
  mkdir -p "`$gdir" || { failed=1; return 1; }
  for gf in "`$1"/guard.py "`$1"/guard_*.py "`$1"/shared_names.py "`$1"/git_reads.py "`$1"/question_form.py "`$1"/precompact_handoff.py; do
    [ -f "`$gf" ] || continue
    put "`$gf" "`$gdir/`$(basename "`$gf")" || { rm -rf "`$gdir"; return 1; }
  done
  [ -f "`$1/guard.py" ] && { put "`$1/guard.py" "`$2/guard.py" || { rm -rf "`$gdir"; return 1; }; }
  for gf in "`$1"/guard_*.py; do [ -f "`$gf" ] && put "`$gf" "`$2/`$(basename "`$gf")"; done
  for gd in "`$2"/guard.d/*; do
    [ -d "`$gd" ] || continue
    case "`$(basename "`$gd")" in "`$id"|"`$prev") ;; *) rm -rf "`$gd" ;; esac
  done
  return 0
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
  gset=0
  if [ "`$sub" = hooks ] && [ ! -L "`$cfg/hooks/guard.py" ]; then gset=1; land_guard_set "`$repo/hooks" "`$cfg/hooks"; fi
  for f in "`$repo/`$sub"/*; do
    [ -f "`$f" ] || continue
    case "`$(basename "`$f")" in guard.py|guard_*.py) [ "`$gset" = 1 ] && continue ;; esac
    [ "`$sub" = bin ] && [ "`$(basename "`$f")" = rm ] && continue
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
# Each file or skill folder git lists under the clone lands, as a link or, when symlinks are not
# permitted, a copy (Copy-Item, same as install.sh's cloud mode), and goes into the install manifest
# (see the comment above Test-Shipped). A later run removes a recorded entry main no longer ships, only
# when it still matches its record, so a copy is removed as surely as a link, and a person's own file or
# link is never touched. A link is no longer pruned because it dangles.
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
    try { New-Item -ItemType SymbolicLink -Path $Path -Target $Target -ErrorAction Stop | Out-Null; return }
    catch { $newItemErr = $_.Exception.Message }
    # Windows PowerShell 5.1 New-Item needs admin even in Developer Mode; mklink does not.
    # Try it before the caller copies.
    if ($env:OS -eq 'Windows_NT') {
        $flag = if (Test-Path -LiteralPath $Target -PathType Container) { '/D ' } else { '' }
        $out = cmd /c "mklink $flag`"$Path`" `"$Target`" 2>&1"
        $i = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
        if ($LASTEXITCODE -eq 0 -and $i -and $i.LinkType) { return }
        throw "mklink failed ($out); New-Item failed ($newItemErr)"
    }
    throw $newItemErr
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
# $Dest is never absent and never half-written, so a guard hook that reads it mid-run sees the
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
# guard scripts; no hook fails closed on one. Returns 'linked', 'copied', or 'failed'.
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
# ---- install manifest: what a run landed, so a later run removes what main stopped shipping ----------
# The same format and rules as install.sh (see the comment above its MANIFEST). $ClaudeDir\backups\
# install-manifest.txt holds one line per landed entry, outside every landed folder: <sub>/<name>, a tab,
# l (link), f (file) or d (folder), a tab, the link target, the file hash or the folder tree hash.
# After landing, a recorded entry that main no longer ships is removed, only when it still matches its
# record; a mismatch is the person's own, kept and logged. A folder whose landing failed, or a run that
# failed, removes nothing. With no manifest yet (the first run of this version), only the names in
# retired-files.txt are acted on. "Shipped": git lists the path under the clone (tracked, or untracked and
# not ignored); a clone with no .git ships what exists; a git read that fails counts as shipped.
$ManifestPath = Join-Path (Join-Path $ClaudeDir 'backups') 'install-manifest.txt'
$RetiredDir   = Join-Path (Join-Path $ClaudeDir 'backups') 'retired'
$LandedList   = [System.Collections.Generic.List[object]]::new()   # @{ Rel; Dest } for each entry the run landed or kept
$FailedSubs   = @{}

function Test-Shipped([string]$Rel) {
    if (-not (Test-Path -LiteralPath (Join-Path $RepoDir '.git'))) { return (Test-Path -LiteralPath (Join-Path $RepoDir $Rel)) }
    $raw = Get-Git -C $RepoDir ls-files --cached --others --exclude-standard -- ":(literal)$Rel"
    if ($LASTEXITCODE -ne 0) { return $true }
    return (@($raw | Where-Object { "$_".Trim() }).Count -gt 0)
}
function Get-FileSha([string]$Path) { return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
# The tree hash install.sh computes: each file's "./path hash" line, sorted, one hash over all lines.
function Get-TreeSha([string]$Dir) {
    $root = (Get-Item -LiteralPath $Dir).FullName.TrimEnd('\', '/')
    [string[]]$lines = @(Get-ChildItem -LiteralPath $Dir -Recurse -File -Force | ForEach-Object {
        './' + ($_.FullName.Substring($root.Length + 1) -replace '\\', '/') + ' ' + (Get-FileSha $_.FullName)
    })
    [Array]::Sort($lines, [StringComparer]::Ordinal)
    $text = if ($lines.Count) { ($lines -join "`n") + "`n" } else { '' }
    $sha = [Security.Cryptography.SHA256]::Create()
    return ([BitConverter]::ToString($sha.ComputeHash([Text.UTF8Encoding]::new($false).GetBytes($text))) -replace '-', '').ToLowerInvariant()
}
# What sits at $Rel now, as "<kind>`t<value>", or $null when nothing does.
function Get-LandedState([string]$Rel) {
    $p = Join-Path $ClaudeDir $Rel
    $i = Get-Item -LiteralPath $p -Force -ErrorAction SilentlyContinue
    if (-not $i) { return $null }
    if ($i.LinkType) { return "l`t$(@($i.Target)[0])" }
    if ($i.PSIsContainer) { return "d`t$(Get-TreeSha $p)" }
    return "f`t$(Get-FileSha $p)"
}
function Test-ProtectedName([string]$Rel) {
    $n = ($Rel -replace '\\', '/').Split('/')[-1]
    return ($n -eq 'guard.d' -or $n -like '*.bak.*' -or $n -like '*.cs-old' -or $n -like '*.cs-new')
}
function Move-ToRetired([string]$Rel) {
    $p = Join-Path $ClaudeDir $Rel
    New-Item -ItemType Directory -Force -Path $RetiredDir | Out-Null
    $to = Join-Path $RetiredDir (($Rel -replace '[\\/]', '-') + '.' + (Get-Date -Format yyyyMMddHHmmss))
    if (Test-Path -LiteralPath $to) { $to = "$to.$PID" }
    Move-Item -LiteralPath $p -Destination $to
    Log "moved $p to $to (main no longer ships $Rel)"
}
# True when nothing may be removed under $Sub this run: a failed run, a folder whose landing failed, or a
# folder git lists nothing under.
function Test-RetireBlocked([string]$Sub) {
    if ($AgentFailed -or $GuardStageFailed -or $FailedSubs.ContainsKey($Sub)) { return $true }
    return (-not (Test-Shipped $Sub))
}

# Runs once, after every folder landed and every failed file was retried. Writes the manifest atomically.
function Complete-Retire {
    $newLines = [System.Collections.Generic.List[string]]::new()
    $landed = @{}
    foreach ($e in $LandedList) {
        if ($StillFailed.Contains($e.Dest)) { continue }
        $state = Get-LandedState $e.Rel
        if ($state) { $landed[$e.Rel] = $true; $newLines.Add("$($e.Rel)`t$state") }
    }
    $pending = $false
    if (Test-Path -LiteralPath $ManifestPath) {
        foreach ($line in @(Get-Content -LiteralPath $ManifestPath)) {
            $f = $line -split "`t", 3
            if ($f.Count -ne 3 -or -not $f[0] -or $landed.ContainsKey($f[0]) -or (Test-ProtectedName $f[0])) { continue }
            $rel = $f[0]; $sub = $rel.Substring(0, [Math]::Max($rel.LastIndexOf('/'), 0))
            if ((Test-Shipped $rel) -or (Test-RetireBlocked $sub)) { $newLines.Add($line); continue }
            $cur = Get-LandedState $rel
            if ($null -eq $cur) { continue }
            $dest = Join-Path $ClaudeDir $rel
            if ($cur -ceq "$($f[1])`t$($f[2])") {
                try {
                    Remove-Leftover $dest
                    Log "removed $dest (main no longer ships $rel)"
                    if ($rel -like 'skills/*') { Remove-Item -LiteralPath (Join-Path (Join-Path (Join-Path $ClaudeDir 'backups') 'skill-copies') $rel.Substring(7)) -Force -ErrorAction SilentlyContinue }
                } catch { Log "could not remove $dest ($($_.Exception.Message)); left in place" }
            } else {
                Log "kept ${dest}: it is not what the last install put there, so it is yours; main no longer ships $rel"
            }
        }
    } else {
        $listPath = Join-Path $RepoDir 'retired-files.txt'
        if (Test-Path -LiteralPath $listPath) {
            foreach ($raw in @(Get-Content -LiteralPath $listPath)) {
                $rel = ($raw -replace '#.*', '').Trim()
                if (-not $rel -or $rel -notmatch '/' -or (Test-ProtectedName $rel) -or (Test-Shipped $rel)) { continue }
                if (Test-RetireBlocked $rel.Substring(0, $rel.LastIndexOf('/'))) { $pending = $true; continue }
                $dest = Join-Path $ClaudeDir $rel
                $i = Get-Item -LiteralPath $dest -Force -ErrorAction SilentlyContinue
                if (-not $i) { continue }
                try {
                    $tgt = if ($i.LinkType) { [string]@($i.Target)[0] } else { '' }
                    if ($tgt -and ($tgt.StartsWith($RepoDir.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar) -or $tgt.StartsWith($RepoDir.TrimEnd('\', '/') + '/'))) {
                        Remove-Leftover $dest; Log "removed $dest (main no longer ships $rel)"
                    } else { Move-ToRetired $rel }
                } catch { Log "could not retire $dest ($($_.Exception.Message)); left in place"; $pending = $true }
            }
        }
    }
    if ($pending) { return }
    try {
        New-Item -ItemType Directory -Force -Path (Split-Path $ManifestPath) | Out-Null
        [string[]]$sorted = $newLines.ToArray()
        [Array]::Sort($sorted, [StringComparer]::Ordinal)
        $tmp = "$ManifestPath.cs-new"
        [IO.File]::WriteAllText($tmp, $(if ($sorted.Count) { ($sorted -join "`n") + "`n" } else { '' }), [Text.UTF8Encoding]::new($false))
        Move-OverFile $tmp $ManifestPath
    } catch { Log "WARN: could not write ${ManifestPath}: $($_.Exception.Message)" }
}
# Copy mode, the guard files (install-hooks-whole). A guard run sees the old set or the
# new set, never a mix. Step 1 (here) writes every guard file, stamped with this run's id, into
# hooks\guard.d\<id>\, where no guard reads it yet. Step 2 is the landing loop below, which lands
# guard.py first: the one landing that switches, because a stamped guard.py loads guard.d\<its id>\
# (see the comment above INSTALL_ID in hooks\guard.py). The flat guard_*.py land after it, kept beside
# it for tools that read them by path. The folder of the set before this one stays until the next
# install; older ones go. A step 1 failure removes the new folder and lands no guard file: the old set
# stays whole and the run exits 1. Links need no set: a link reads the repo file.
$GuardSetMode = $false
$GuardStageFailed = $false
$PrevGuardId = ''
function Test-LinksWork([string]$AnySrc) {
    $probe = Join-Path $ClaudeDir '.cs-linkprobe'
    try { Remove-Leftover $probe; New-Link $probe $AnySrc; Remove-Leftover $probe; return $true }
    catch { try { Remove-Leftover $probe } catch { }; return $false }
}
function Install-GuardSet([string]$SrcDir, [string]$DestDir) {
    $names = @(Get-ChildItem -LiteralPath $SrcDir -File -ErrorAction SilentlyContinue | Where-Object { Test-StampTarget $_.Name })
    if ($names.Count -eq 0 -or (Test-LinksWork $names[0].FullName)) { return }
    # shared_names.py, git_reads.py, question_form.py and precompact_handoff.py, which the guard imports, ride in the set unstamped (no stamp target).
    foreach ($shared in 'shared_names.py', 'git_reads.py', 'question_form.py', 'precompact_handoff.py') {
        $names += @(Get-ChildItem -LiteralPath $SrcDir -File -Filter $shared -ErrorAction SilentlyContinue)
    }
    $script:GuardSetMode = $true
    $entry = Join-Path $DestDir 'guard.py'
    if (Test-Path -LiteralPath $entry) {
        try { $m = [regex]::Match([IO.File]::ReadAllText($entry), '(?m)^INSTALL_ID = "([^"]*)"'); if ($m.Success) { $script:PrevGuardId = $m.Groups[1].Value } } catch { }
    }
    $gdir = Join-Path $DestDir "guard.d\$InstallId"
    New-Item -ItemType Directory -Force -Path $gdir | Out-Null
    foreach ($f in $names) {
        $how = Install-File $f.FullName (Join-Path $gdir $f.Name)
        if ($how -eq 'failed') {
            $FailedFiles.Remove((Join-Path $gdir $f.Name))
            try { Remove-Item -LiteralPath $gdir -Recurse -Force } catch { }
            Log "the new guard set could not be written; the guard files stay as they were"
            $script:GuardStageFailed = $true
            return
        }
        if ($how -eq 'copied') { $script:AgentCopied = $true }
    }
}
function Remove-StaleSets {
    foreach ($d in @(Get-ChildItem -LiteralPath (Join-Path (Join-Path $ClaudeDir 'hooks') 'guard.d') -Directory -ErrorAction SilentlyContinue)) {
        if ($d.Name -eq $InstallId -or $d.Name -eq $PrevGuardId) { continue }
        try { Remove-Item -LiteralPath $d.FullName -Recurse -Force } catch { Log "could not remove $($d.FullName) ($($_.Exception.Message)); left behind" }
    }
}
foreach ($sub in (Get-LandedDirs $RepoDir)) {
    # GetFullPath turns the '/' in a nested name such as docs/design into this system's separator,
    # so the prune test below compares like with like.
    $srcDir  = [IO.Path]::GetFullPath((Join-Path $RepoDir $sub))
    $destDir = Join-Path $ClaudeDir $sub
    New-Item -ItemType Directory -Force -Path $destDir | Out-Null
    if ($sub -eq 'hooks') { Install-GuardSet $srcDir $destDir }

    # skills/ lands differently: each skills/<name>/ is ONE whole-directory symlink, never
    # a per-file link, since a per-file loop skips a directory entry outright (Get-ChildItem
    # -File never returns it) and a landed skill would never appear at all. A pre-existing
    # entry this repo does not ship (a person's own skill) is never touched: the loop only
    # ever looks at names under $srcDir, so a name absent there is never a candidate.
    if ($sub -eq 'skills') {
        # A skill backup never lands in skills\ or any folder Claude Code scans: it would load as
        # one more skill. Backups go to backups\skills\<name>.<time>; an older installer's
        # skills\<name>.bak.* is moved there too, never deleted.
        $skillBakDir = Join-Path (Join-Path $ClaudeDir 'backups') 'skills'
        foreach ($old in @(Get-ChildItem -LiteralPath $destDir -Directory -Filter '*.bak.*' -Force -ErrorAction SilentlyContinue | Where-Object { $_.Name -match '\.bak\.\d{14}$' -and -not $_.LinkType })) {
            New-Item -ItemType Directory -Force -Path $skillBakDir | Out-Null
            $to = Join-Path $skillBakDir $old.Name
            if (Test-Path -LiteralPath $to) { $to = "$to.$PID" }
            try { Move-Item -LiteralPath $old.FullName -Destination $to; Log "old backup $($old.FullName) moved to $to" }
            catch { Log "could not move $($old.FullName) to $to ($($_.Exception.Message)); left in place" }
        }
        foreach ($src in @(Get-ChildItem -Path $srcDir -Directory -ErrorAction SilentlyContinue)) {
            # A folder with no file git lists (retired, or only ignored files) is not landed.
            if (-not (Test-Shipped "$sub/$($src.Name)")) { continue }
            $dest = Join-Path $destDir $src.Name
            $cur  = Get-Item $dest -ErrorAction SilentlyContinue
            if ($cur -and $cur.LinkType -eq 'SymbolicLink' -and $cur.Target -eq $src.FullName) { $LandedList.Add(@{ Rel = "$sub/$($src.Name)"; Dest = $dest }); continue }
            # A real directory (or a symlink pointing elsewhere) at $dest: on the first
            # local install ever, it is a person's own hand-made skill, backed up. After
            # that, it is this same installer's own earlier copy, from a no-symlink-rights
            # machine where the symlink attempt below fell back to Copy-Item: replace it,
            # no backup (D: copy-mode-overwrites-no-backup). Install-Dir swaps by rename,
            # so the skill is never absent.
            $bak  = Join-Path $skillBakDir "$($src.Name).$(Get-Date -Format yyyyMMddHHmmss)"
            $keep = [bool]($cur -and $FirstLocalRun)
            if ($keep) { New-Item -ItemType Directory -Force -Path $skillBakDir | Out-Null }
            $old  = if ($keep) { $bak } else { "$dest.cs-old" }
            $how  = Install-Dir $src.FullName $dest $old $keep
            if ($how -eq 'failed') { $AgentFailed = $true; $FailedSubs[$sub] = $true; continue }
            $LandedList.Add(@{ Rel = "$sub/$($src.Name)"; Dest = $dest })
            if ($keep) { Log "existing $dest moved to $bak" }
            if ($how -eq 'linked') {
                Log "linked $dest -> $($src.FullName)"
            } else {
                $AgentCopied = $true
                Log "copied $dest (symlink not permitted)"
            }
        }
        continue
    }

    $srcFiles = @(Get-ChildItem -Path $srcDir -File -ErrorAction SilentlyContinue)
    # bin/rm is a posix sh shim; no Windows half lands it.
    if ($sub -eq 'bin') { $srcFiles = @($srcFiles | Where-Object { $_.Name -ne 'rm' }) }
    # Guard set: guard.py goes first, the landing that switches; see the comment above Install-GuardSet.
    if ($GuardSetMode -and $sub -eq 'hooks') { $srcFiles = @($srcFiles | Sort-Object @{ Expression = { $_.Name -cne 'guard.py' } }, Name) }
    foreach ($src in $srcFiles) {
        if ($GuardStageFailed -and $sub -eq 'hooks' -and (Test-StampTarget $src.Name)) { continue }
        # A file git does not list (retired, or ignored) is not landed.
        if (-not (Test-Shipped "$sub/$($src.Name)")) { continue }
        $dest = Join-Path $destDir $src.Name
        $cur  = Get-Item $dest -ErrorAction SilentlyContinue
        if ($cur -and $cur.LinkType -eq 'SymbolicLink' -and $cur.Target -eq $src.FullName) { $LandedList.Add(@{ Rel = "$sub/$($src.Name)"; Dest = $dest }); continue }
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
        # A file that failed is retried by Resolve-Failures; Complete-Retire records it only if it landed.
        $LandedList.Add(@{ Rel = "$sub/$($src.Name)"; Dest = $dest })
        if ($how -eq 'failed') { $FailedSubs[$sub] = $true }
        if ($how -eq 'linked') {
            Log "linked $dest -> $($src.FullName)"
        } elseif ($how -eq 'copied') {
            $AgentCopied = $true
            Log "copied $dest (symlink not permitted)"
        }
        # A 'failed' file is in $FailedFiles; Resolve-Failures retries it and sets $AgentFailed only
        # for a file that still fails, so a recovered file does not read as failed.
    }
}
# A folder an earlier install landed and the repo has since moved: ux, now docs\design (decision
# ux-house-rules). Its links go with the prune test above, then the folder once it is empty. A
# person's own file and a copy stay, as the loop above leaves them.
foreach ($gone in @('ux')) {
    $destDir = Join-Path $ClaudeDir $gone
    $cur = Get-Item $destDir -ErrorAction SilentlyContinue
    if (-not $cur -or $cur.LinkType) { continue }
    foreach ($entry in @(Get-ChildItem -Path $destDir -File -ErrorAction SilentlyContinue)) {
        if ($entry.LinkType -ne 'SymbolicLink') { continue }
        $tgt = @($entry.Target)[0]
        if (-not $tgt) { continue }
        if ((Split-Path $tgt -Parent) -ne (Join-Path $RepoDir $gone)) { continue }
        if (Test-Path $tgt) { continue }
        Remove-Item $entry.FullName
    }
    if (-not (Get-ChildItem -Path $destDir -Force)) {
        Remove-Item $destDir
        Log "removed $destDir (the repo no longer lands it)"
    }
}
# Packages that a skill loads (typescript, for plain-english-map): one `npm ci` in the clone root.
# A skill is linked, so its real path is in the clone, and it finds the clone's node_modules.
# A failure is logged and never fails the install.
if (Test-Path (Join-Path $RepoDir 'package-lock.json')) {
    if (Get-Command npm -ErrorAction SilentlyContinue) {
        Push-Location $RepoDir
        # cmd /c keeps npm's stderr out of PowerShell, where it would raise a NativeCommandError.
        $npmOut = @()
        try { $npmOut = @(& cmd /c 'npm ci --ignore-scripts --no-audit --no-fund 2>&1'); $npmOk = ($LASTEXITCODE -eq 0) } catch { $npmOk = $false } finally { Pop-Location }
        if ($npmOk) { Log "npm ci ran in $RepoDir" } else {
            Log "WARNING: npm ci failed in $RepoDir; the plain-english-map skill cannot load typescript until it passes. Last lines of its output:"
            $npmOut | Select-Object -Last 5 | ForEach-Object { Log "  $_" }
        }
    } else {
        Log "WARNING: npm not found; run npm ci in $RepoDir so the plain-english-map skill can load typescript"
    }
}
if (-not (Get-Command python3 -ErrorAction SilentlyContinue) -and -not (Get-Command python -ErrorAction SilentlyContinue)) {
    Log "python3 not found on PATH; the guard and the other guards refuse Bash, Write and Edit calls until Python 3 is installed"
}

# Retries each file Install-File could not replace, with a longer back-off (2, 4, 8 s), then re-reads
# the stamp of every copied guard.py and guard_*.py: a copy that does not carry this run's id is a half install,
# so it is retried the same way. A file that still fails is named here and the run exits non-zero
# at its end; the guard then fails closed and its text names this installer as the remedy.
# Links are skipped: a link reads the repo file, and the repo copy holds the placeholder.
$StillFailed = [ordered]@{}
if ($GuardStageFailed) { $StillFailed['the new guard set'] = '' }
function Resolve-Failures {
    $hooksDest = Join-Path $ClaudeDir 'hooks'
    $hooksSrc  = Join-Path $RepoDir 'hooks'
    $stampRe   = '(?m)^INSTALL_ID = "([^"]*)"'
    foreach ($delay in 2, 4, 8, 0) {
        foreach ($f in @(Get-ChildItem -Path $hooksSrc -Filter 'guard*.py' -File -ErrorAction SilentlyContinue | Where-Object { Test-StampTarget $_.Name })) {
            if ($GuardStageFailed) { break }
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
if ($GuardSetMode) { Remove-StaleSets }
if ($StillFailed.Count -gt 0) { $AgentFailed = $true }
Complete-Retire

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
    $HookMode = Resolve-PostMergeHook
    Write-InstallLog -SettingsMode 'symlink' -AgentsMode $AgentsMode -HookMode $HookMode
    Complete-Run $AgentFailed
    Exit-Install $(if ($StillFailed.Count -gt 0) { 1 } else { 0 })
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
    Write-InstallLog -SettingsMode 'symlink' -AgentsMode $AgentsMode -HookMode (Resolve-PostMergeHook)
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
if ($StillFailed.Count -gt 0) { Exit-Install 1 }
$script:ExitCode = 0
} finally {
    Add-InstallLogLine "$(Get-Date -Format s) install.ps1: end id=$InstallId pid=$PID exit=$($script:ExitCode)"
    if ($LockStream) { $LockStream.Dispose() }
}
