# Test: a re-run of install.ps1 leaves no gap in the landed copies.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File install-no-gap.test.ps1
#
# The defect: with no symlink rights, install.ps1 deletes each landed copy and then copies it
# again. Between the two steps the file is absent. The gate hooks fail closed on a missing
# script, so every session is refused for as long as the gap lasts (incident 2026-10-13).
#
# The main case runs install.ps1 twice against a scratch clone and a scratch CLAUDE_CONFIG_DIR,
# with copy mode forced. A FileSystemWatcher on the scratch CLAUDE dir records Deleted and Renamed
# events during run 2. It fails if any name the clone ships is deleted or renamed away. A name
# the clone no longer ships may be removed. The fixture skill has nested dirs, so the same check
# covers nested files, and a nested file the source drops must be pruned.
#
# Three more cases, each in its own scratch tree. symrun and linkfail need symlink rights. On a
# runner without them they print SKIP with the reason and do not count:
#   symrun    a real file from an earlier copy, then a run where links can be made: no gap event.
#   linkfail  dest is a symlink to elsewhere and the copy fails: a file must still exist at dest.
#   lock1     first local run, skill locked: a .bak or no copy marker after run 1, and no person
#             file lost after run 2. Needs no symlink rights; copy mode is forced.
#
# Seams. install.ps1 must honour each one:
#   CLAUDE_CONFIG_DIR              target dir.
#   CLAUDE_SETTINGS_USER_ENV_KEY   throwaway registry key for the PATH write.
#   CLAUDE_SETTINGS_FORCE_COPY=1   every symlink attempt throws (New-Link), so copy mode runs on any machine.
#
# The main case also fails when copy mode was not forced: a shipped name is a symlink after run 1.
# Without that check, a run on a machine with symlink rights would pass and prove nothing.
#
# Windows only. Elsewhere it prints SKIP and exits 0. Exits 1 on any FAIL.
$ErrorActionPreference = 'Stop'

if ($env:OS -ne 'Windows_NT') { Write-Host 'SKIP: install no-gap (Windows only)'; exit 0 }

$Repo   = Split-Path -Parent $MyInvocation.MyCommand.Path
$Failed = 0
function Check([string]$name, [bool]$ok) {
    if ($ok) { Write-Host "PASS: $name" } else { Write-Host "FAIL: $name"; $script:Failed++ }
}

# Records Deleted and Renamed events on one directory tree. Relative names only.
# A canary is a file the test creates and deletes; Arm sets its name, WaitCanary waits for it.
Add-Type -TypeDefinition @'
using System;
using System.Collections.Concurrent;
using System.IO;
using System.Threading;

public class NoGapRecorder : IDisposable
{
    private readonly string root;
    private readonly FileSystemWatcher watcher;
    private readonly object armLock = new object();
    private readonly ManualResetEvent canarySeen = new ManualResetEvent(false);
    private string canary = "";
    public readonly ConcurrentQueue<string> Gone = new ConcurrentQueue<string>();
    public readonly ConcurrentQueue<string> Errors = new ConcurrentQueue<string>();

    public NoGapRecorder(string dir)
    {
        root = dir.TrimEnd('\\');
        watcher = new FileSystemWatcher(dir);
        watcher.IncludeSubdirectories = true;
        watcher.InternalBufferSize = 65536;
        watcher.NotifyFilter = NotifyFilters.FileName | NotifyFilters.DirectoryName;
        watcher.Deleted += OnDeleted;
        watcher.Renamed += OnRenamed;
        watcher.Error += OnError;
        watcher.EnableRaisingEvents = true;
    }

    private string Rel(string full)
    {
        if (full.Length > root.Length + 1
            && full.StartsWith(root, StringComparison.OrdinalIgnoreCase)
            && full[root.Length] == '\\')
            return full.Substring(root.Length + 1);
        return "OUTSIDE:" + full;
    }

    public void Arm(string name)
    {
        lock (armLock) { canary = name; canarySeen.Reset(); }
    }

    public bool WaitCanary(int ms)
    {
        return canarySeen.WaitOne(ms);
    }

    private void Seen(string rel)
    {
        lock (armLock)
        {
            if (string.Equals(rel, canary, StringComparison.OrdinalIgnoreCase)) canarySeen.Set();
        }
    }

    private void OnDeleted(object sender, FileSystemEventArgs e)
    {
        string rel = Rel(e.FullPath);
        Gone.Enqueue("D|" + rel);
        Seen(rel);
    }

    private void OnRenamed(object sender, RenamedEventArgs e)
    {
        Gone.Enqueue("R|" + Rel(e.OldFullPath) + "|" + Rel(e.FullPath));
    }

    private void OnError(object sender, ErrorEventArgs e)
    {
        Errors.Enqueue(e.GetException().Message);
    }

    public void Dispose()
    {
        watcher.EnableRaisingEvents = false;
        watcher.Dispose();
    }
}
'@

$Tmp    = Join-Path ([IO.Path]::GetTempPath()) ('claude-settings-nogap-' + [guid]::NewGuid().ToString('N'))
$Clone  = Join-Path $Tmp 'clone'
$Cfg    = Join-Path $Tmp 'claude'
$EnvSub = 'Software\claude-settings-test-' + [guid]::NewGuid().ToString('N')
$Utf8   = New-Object Text.UTF8Encoding($false)
$Landed = @('agents', 'lint', 'hooks', 'skills')
$Rec    = $null

# Writes one fixture file. $path is absolute.
function Write-FixtureFile([string]$path, [string]$text) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $path) | Out-Null
    [IO.File]::WriteAllText($path, $text, $Utf8)
}

# Writes one fixture file under the main clone.
function Write-Fixture([string]$rel, [string]$text) {
    Write-FixtureFile (Join-Path $Clone $rel) $text
}

# Runs install.ps1 from the clone $CloneDir in a child shell. Returns its exit code.
function Invoke-Install([string]$CloneDir, [string]$LogName) {
    $log     = Join-Path $Tmp $LogName
    $argLine = '-NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $CloneDir 'install.ps1') + '"'
    $p = Start-Process -FilePath 'powershell.exe' -ArgumentList $argLine -Wait -PassThru -NoNewWindow `
        -RedirectStandardOutput $log -RedirectStandardError ($log + '.err')
    return $p.ExitCode
}

# Creates and deletes one canary file in $Dir, then waits (bounded) for its Deleted event.
# Returns $true when the watcher delivered it. Events queued before it are then delivered too.
function Flush-Canary($Recorder, [string]$Name, [string]$Dir) {
    $Recorder.Arm($Name)
    $p = Join-Path $Dir $Name
    [IO.File]::WriteAllText($p, '', $Utf8)
    Remove-Item -LiteralPath $p -Force
    return $Recorder.WaitCanary(15000)
}

# Names the clone ships, relative to the CLAUDE dir: CLAUDE.md, settings.json, and every entry
# under each landed dir, nested ones too.
function Get-ShippedNames([string]$CloneDir, [string[]]$Dirs) {
    $names = @('CLAUDE.md', 'settings.json')
    foreach ($sub in $Dirs) {
        $base = Join-Path $CloneDir $sub
        $names += $sub
        foreach ($item in @(Get-ChildItem -LiteralPath $base -Recurse -Force)) {
            $names += $sub + $item.FullName.Substring($base.Length)
        }
    }
    return $names
}

# A set of names. Hashtable keys ignore case.
function Get-NameSet([string[]]$Names) {
    $set = @{}
    foreach ($n in $Names) { $set[$n] = $true }
    return $set
}

# Gap events: each Deleted or Renamed event whose name (the old name, for a rename) is in $Set.
function Get-GapHits($Events, $Set) {
    $hits = @()
    foreach ($ev in $Events) {
        $f    = $ev.Split('|')
        $name = $f[1]
        $kind = if ($f[0] -eq 'D') { 'deleted' } else { 'renamed away' }
        if ($Set.ContainsKey($name)) { $hits += "$kind $name" }
    }
    return $hits
}

# True when $Path is a symlink or junction. A missing path is not a link.
function Test-ReparsePoint([string]$Path) {
    $i = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    if (-not $i) { return $false }
    return (([int]$i.Attributes) -band [int][IO.FileAttributes]::ReparsePoint) -ne 0
}

# Empty when this runner can make symlinks, else the reason it cannot.
function Get-SymlinkBlocker {
    $probe = Join-Path ([IO.Path]::GetTempPath()) ('nogap-symprobe-' + [guid]::NewGuid().ToString('N'))
    try {
        New-Item -ItemType SymbolicLink -Path $probe -Target (Join-Path $Repo 'install.ps1') -ErrorAction Stop | Out-Null
        Remove-Item -LiteralPath $probe -Force
        return ''
    } catch {
        return $_.Exception.Message
    }
}

# Copies install.py into a fixture clone at $Dest when the repo has one (L1, the installer spine).
# Every fixture clone below gets it, so none loses the spine.
function Copy-InstallPy([string]$Dest) {
    $py = Join-Path $Repo 'install.py'
    if (Test-Path -LiteralPath $py) { Copy-Item -LiteralPath $py -Destination (Join-Path $Dest 'install.py') }
}

# A scratch clone and CLAUDE dir for one extra case, under $Tmp. It ships CLAUDE.md, settings.json
# and the given landed dirs. The caller adds the rest with Write-FixtureFile.
function New-Scratch([string]$Name, [string[]]$Dirs) {
    $root = Join-Path $Tmp $Name
    $s = @{ Root = $root; Clone = (Join-Path $root 'clone'); Cfg = (Join-Path $root 'claude') }
    New-Item -ItemType Directory -Force -Path $s.Clone, $s.Cfg | Out-Null
    Copy-Item -LiteralPath (Join-Path $Repo 'install.ps1') -Destination (Join-Path $s.Clone 'install.ps1')
    Copy-InstallPy $s.Clone
    Write-FixtureFile (Join-Path $s.Clone 'CLAUDE.md') '# scratch fixture'
    Write-FixtureFile (Join-Path $s.Clone 'settings.json') '{}'
    Write-FixtureFile (Join-Path $s.Clone 'landed-dirs.txt') (($Dirs -join "`n") + "`n")
    return $s
}

# ---- fixture: a small clone with the landed dirs that matter, plus the real install.ps1 --------
New-Item -ItemType Directory -Force -Path $Clone, $Cfg | Out-Null
Copy-Item -LiteralPath (Join-Path $Repo 'install.ps1') -Destination (Join-Path $Clone 'install.ps1')
Copy-InstallPy $Clone
Write-Fixture 'CLAUDE.md' '# nogap fixture'
Write-Fixture 'settings.json' '{}'
Write-Fixture 'landed-dirs.txt' (($Landed -join "`n") + "`n")
Write-Fixture 'agents\builder.md' '# builder'
Write-Fixture 'lint\ste_gate.py' '# gate'
Write-Fixture 'lint\ste_lint.py' '# lint'
Write-Fixture 'hooks\guard.py' '# guard'
Write-Fixture 'hooks\guard_core.py' '# guard core'
Write-Fixture 'skills\sample\SKILL.md' '# sample'
Write-Fixture 'skills\sample\notes.md' '# notes'
# Nested dirs, as real skills have (skills/impeccable/reference/, scripts/data/). The source drops
# scripts\data\old.json between run 1 and run 2, so run 2 must prune it from the landed copy.
Write-Fixture 'skills\sample\reference\guide.md' '# guide'
Write-Fixture 'skills\sample\scripts\data\table.json' '{"rows":1}'
Write-Fixture 'skills\sample\scripts\data\old.json' '{"dropped":true}'
$DroppedRel = 'skills\sample\scripts\data\old.json'

$Shipped    = @(Get-ShippedNames $Clone $Landed)
$ShippedSet = Get-NameSet $Shipped
Write-Host "info: $($Shipped.Count) shipped names in the fixture"

$env:CLAUDE_CONFIG_DIR = $Cfg
[Microsoft.Win32.Registry]::CurrentUser.CreateSubKey($EnvSub).Close()
$env:CLAUDE_SETTINGS_USER_ENV_KEY = "HKCU:\$EnvSub"

try {
    # ---- run 1: land the copies (copy mode forced) ---------------------------------------------
    $env:CLAUDE_SETTINGS_FORCE_COPY = '1'
    $rc1 = Invoke-Install $Clone 'run1.log'
    Check "setup: run 1 exits 0 (exit $rc1)" ($rc1 -eq 0)

    $Missing1 = @($Shipped | Where-Object { -not (Test-Path -LiteralPath (Join-Path $Cfg $_)) })
    Check "setup: run 1 lands every shipped name" ($Missing1.Count -eq 0)
    foreach ($m in $Missing1) { Write-Host "  missing after run 1: $m" }
    Check "setup: run 1 lands the nested file the source drops later" (Test-Path -LiteralPath (Join-Path $Cfg $DroppedRel))

    # Copy mode must be real. A symlink here means the seam is not honoured by install.ps1.
    $Linked = @()
    foreach ($item in $Shipped) {
        $p = Join-Path $Cfg $item
        if (-not (Test-Path -LiteralPath $p)) { continue }
        $attr = [int](Get-Item -LiteralPath $p -Force).Attributes
        if (($attr -band [int][IO.FileAttributes]::ReparsePoint) -ne 0) { $Linked += $item }
    }
    Check "copy mode forced: no shipped name is a symlink after run 1" ($Linked.Count -eq 0)
    foreach ($l in $Linked) { Write-Host "  symlink, seam not honoured: $l" }

    # The source drops one nested file between the runs. Its name leaves the shipped set, so its
    # removal is not a gap. Run 2 must still prune it from the landed copy.
    Remove-Item -LiteralPath (Join-Path $Clone $DroppedRel) -Force
    $Shipped     = @(Get-ShippedNames $Clone $Landed)
    $ShippedSet  = Get-NameSet $Shipped
    $NestedNames = @($Shipped | Where-Object { ($_ -split '\\').Count -ge 4 })
    $NestedSet   = Get-NameSet $NestedNames
    Check "fixture: nested names are in the shipped set ($($NestedNames.Count))" ($NestedNames.Count -ge 3)

    # ---- run 2: the re-run under watch ---------------------------------------------------------
    $Rec = New-Object -TypeName NoGapRecorder -ArgumentList $Cfg
    $pre = Flush-Canary $Rec '__nogap_canary_pre.tmp' $Cfg
    Check "watcher live before run 2 (canary delivered)" $pre

    $rc2 = Invoke-Install $Clone 'run2.log'
    Check "setup: run 2 exits 0 (exit $rc2)" ($rc2 -eq 0)

    $post = Flush-Canary $Rec '__nogap_canary_post.tmp' $Cfg
    Check "watcher delivered run 2 events (post canary)" $post
    $Errs = @($Rec.Errors.ToArray())
    Check "watcher raised no error (an overflow would make the result unknown)" ($Errs.Count -eq 0)
    foreach ($e in $Errs) { Write-Host "  watcher error: $e" }
    Remove-Item Env:\CLAUDE_SETTINGS_FORCE_COPY -ErrorAction SilentlyContinue

    $Gone = @($Rec.Gone.ToArray())
    Write-Host "info: $($Gone.Count) Deleted or Renamed events during run 2"
    $Hits = @(Get-GapHits $Gone $ShippedSet)
    foreach ($h in $Hits) { Write-Host "  gap: $h during run 2" }
    Check "run 2 deletes or renames no shipped name ($($Hits.Count) gap events)" ($Hits.Count -eq 0)

    $NestedHits = @(Get-GapHits $Gone $NestedSet)
    foreach ($h in $NestedHits) { Write-Host "  nested gap: $h during run 2" }
    Check "run 2 deletes or renames no nested file under skills ($($NestedHits.Count) gap events)" ($NestedHits.Count -eq 0)
    Check "run 2 prunes the nested file the source dropped" (-not (Test-Path -LiteralPath (Join-Path $Cfg $DroppedRel)))

    $Missing2 = @($Shipped | Where-Object { -not (Test-Path -LiteralPath (Join-Path $Cfg $_)) })
    Check "all shipped names present after run 2" ($Missing2.Count -eq 0)
    foreach ($m in $Missing2) { Write-Host "  missing after run 2: $m" }

    # ---- symrun: a real file from an earlier copy, then a run where links can be made ----------
    $Blocker = Get-SymlinkBlocker
    if ($Blocker) {
        Write-Host "SKIP: symrun (no symlink rights: $Blocker)"
    } else {
        $Sym      = New-Scratch 'symrun' @('hooks')
        Write-FixtureFile (Join-Path $Sym.Clone 'hooks\guard.py') '# guard v1'
        $SymSet   = Get-NameSet (@(Get-ShippedNames $Sym.Clone @('hooks')))
        $SymGuard = Join-Path $Sym.Cfg 'hooks\guard.py'

        $env:CLAUDE_CONFIG_DIR = $Sym.Cfg
        $env:CLAUDE_SETTINGS_FORCE_COPY = '1'
        $rcS1 = Invoke-Install $Sym.Clone 'symrun-run1.log'
        Remove-Item Env:\CLAUDE_SETTINGS_FORCE_COPY -ErrorAction SilentlyContinue
        Check "symrun: run 1 (forced copy) exits 0 (exit $rcS1)" ($rcS1 -eq 0)
        Check "symrun: run 1 leaves a real file at hooks\guard.py, the earlier copy" ((Test-Path -LiteralPath $SymGuard) -and (-not (Test-ReparsePoint $SymGuard)))

        $RecS = New-Object -TypeName NoGapRecorder -ArgumentList $Sym.Cfg
        try {
            $preS = Flush-Canary $RecS '__nogap_canary_pre.tmp' $Sym.Cfg
            Check "symrun: watcher live before run 2 (canary delivered)" $preS
            Check "symrun: FORCE_COPY is unset for run 2, so links can be made" (-not $env:CLAUDE_SETTINGS_FORCE_COPY)
            $rcS2 = Invoke-Install $Sym.Clone 'symrun-run2.log'
            Check "symrun: run 2 exits 0 (exit $rcS2)" ($rcS2 -eq 0)
            $postS = Flush-Canary $RecS '__nogap_canary_post.tmp' $Sym.Cfg
            Check "symrun: watcher delivered run 2 events (post canary)" $postS
            $HitsS = @(Get-GapHits @($RecS.Gone.ToArray()) $SymSet)
            foreach ($h in $HitsS) { Write-Host "  gap: $h during symrun run 2" }
            Check "symrun: run 2 deletes or renames no shipped name when a real file is replaced ($($HitsS.Count) gap events)" ($HitsS.Count -eq 0)
        } finally {
            $RecS.Dispose()
            Remove-Item Env:\CLAUDE_CONFIG_DIR -ErrorAction SilentlyContinue
        }
    }

    # ---- linkfail: dest is a symlink to elsewhere and the copy fails: a file must remain -------
    if ($Blocker) {
        Write-Host "SKIP: linkfail (no symlink rights: $Blocker)"
    } else {
        $Lf     = New-Scratch 'linkfail' @('hooks')
        $LfSrc  = Join-Path $Lf.Clone 'hooks\guard.py'
        Write-FixtureFile $LfSrc '# guard'
        $LfElse = Join-Path $Lf.Root 'elsewhere\guard.py'
        Write-FixtureFile $LfElse '# elsewhere'
        $LfDest = Join-Path $Lf.Cfg 'hooks\guard.py'
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $LfDest) | Out-Null
        New-Item -ItemType SymbolicLink -Path $LfDest -Target $LfElse -ErrorAction Stop | Out-Null

        $Lock = [IO.File]::Open($LfSrc, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::None)
        try {
            $DestItem = Get-Item -LiteralPath $LfDest -Force
            Check "linkfail: dest is a symlink to elsewhere before the run" (($DestItem.LinkType -eq 'SymbolicLink') -and (@($DestItem.Target)[0] -eq $LfElse))

            $LockHeld = $false
            try { Copy-Item -LiteralPath $LfSrc -Destination (Join-Path $Lf.Root 'probe.py') -ErrorAction Stop }
            catch { $LockHeld = $true }
            Check "linkfail: the source is locked, so a read through Copy-Item fails" $LockHeld

            $env:CLAUDE_CONFIG_DIR = $Lf.Cfg
            $env:CLAUDE_SETTINGS_FORCE_COPY = '1'
            $rcL = Invoke-Install $Lf.Clone 'linkfail-run.log'
            Remove-Item Env:\CLAUDE_SETTINGS_FORCE_COPY, Env:\CLAUDE_CONFIG_DIR -ErrorAction SilentlyContinue
            $After = Get-Item -LiteralPath $LfDest -Force -ErrorAction SilentlyContinue
            Check "linkfail: a file still exists at dest after the failed copy (exit $rcL)" ($null -ne $After)
        } finally {
            $Lock.Dispose()
            Remove-Item Env:\CLAUDE_SETTINGS_FORCE_COPY, Env:\CLAUDE_CONFIG_DIR -ErrorAction SilentlyContinue
        }
    }

    # ---- lock1: first local run, the person's skill is locked, so its backup rename fails ----------
    # Review finding 1. No copy marker yet, so the person's own skill dir is a first-run backup
    # candidate. A handle held open on one of its files, with FileShare.Read (no Delete), makes the
    # rename of the directory fail. Run 1 must leave a .bak of that skill, or no copy marker, so
    # run 2 is still a first run. After the lock is released, run 2 must keep the person's files at
    # the skill dir or in a .bak, and prune none of them. Copy mode is forced: no symlink needed.
    $L1      = New-Scratch 'lock1' @('skills')
    Write-FixtureFile (Join-Path $L1.Clone 'skills\lockskill\SKILL.md') '# shipped lockskill'
    $L1Skill  = Join-Path $L1.Cfg 'skills\lockskill'
    $L1Notes  = Join-Path $L1Skill 'my-notes.md'
    $L1Marker = Join-Path $L1.Cfg '.claude-settings-installed'
    Write-FixtureFile (Join-Path $L1Skill 'SKILL.md') "person's own skill"
    Write-FixtureFile $L1Notes "person's own notes"

    $L1Lock = [IO.File]::Open($L1Notes, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    $env:CLAUDE_CONFIG_DIR = $L1.Cfg
    $env:CLAUDE_SETTINGS_FORCE_COPY = '1'
    try {
        # Fixture: the open handle must block a rename of the skill dir, or run 1 proves nothing.
        $Blocked = $false
        try { [IO.Directory]::Move($L1Skill, "$L1Skill.probe") } catch { $Blocked = $true }
        if (-not $Blocked) { [IO.Directory]::Move("$L1Skill.probe", $L1Skill) }
        Check "lock1 fixture: a rename of the locked skill dir is refused while the handle is open" $Blocked

        $rcL1 = Invoke-Install $L1.Clone 'lock1-run1.log'
        Write-Host "info: lock1 run 1 exit $rcL1"
        $BakL1    = @(Get-ChildItem -LiteralPath (Join-Path $L1.Cfg 'skills') -Directory -Filter 'lockskill.bak.*' -ErrorAction SilentlyContinue)
        $MarkerL1 = Test-Path -LiteralPath $L1Marker
        Check "lock1: run 1 leaves a .bak of the skill, or no copy marker ($($BakL1.Count) bak, marker $MarkerL1)" (($BakL1.Count -gt 0) -or (-not $MarkerL1))
    } finally {
        $L1Lock.Dispose()
    }

    # The lock is released. Run 2 must keep the person's files and prune none of them.
    try {
        $rcL2 = Invoke-Install $L1.Clone 'lock1-run2.log'
        Write-Host "info: lock1 run 2 exit $rcL2"
    } finally {
        Remove-Item Env:\CLAUDE_CONFIG_DIR, Env:\CLAUDE_SETTINGS_FORCE_COPY -ErrorAction SilentlyContinue
    }
    $L1Roots   = @($L1Skill) + @(Get-ChildItem -LiteralPath (Join-Path $L1.Cfg 'skills') -Directory -Filter 'lockskill.bak.*' -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })
    $NotesKept = @($L1Roots | Where-Object { (Test-Path -LiteralPath (Join-Path $_ 'my-notes.md')) -and ((Get-Content -Raw -LiteralPath (Join-Path $_ 'my-notes.md')).Trim() -eq "person's own notes") }).Count -gt 0
    $SkillKept = @($L1Roots | Where-Object { (Test-Path -LiteralPath (Join-Path $_ 'SKILL.md')) -and ((Get-Content -Raw -LiteralPath (Join-Path $_ 'SKILL.md')).Trim() -eq "person's own skill") }).Count -gt 0
    Check "lock1: run 2 keeps the person's my-notes.md at the skill dir or in a .bak, never pruned" $NotesKept
    Check "lock1: run 2 keeps the person's SKILL.md content at the skill dir or in a .bak" $SkillKept

} finally {
    if ($Rec) { $Rec.Dispose() }
    Remove-Item Env:\CLAUDE_CONFIG_DIR, Env:\CLAUDE_SETTINGS_FORCE_COPY, Env:\CLAUDE_SETTINGS_USER_ENV_KEY -ErrorAction SilentlyContinue
    try { [Microsoft.Win32.Registry]::CurrentUser.DeleteSubKeyTree($EnvSub, $false) } catch { }
    Remove-Item -LiteralPath $Tmp -Recurse -Force -ErrorAction SilentlyContinue
}

if ($Failed) { Write-Host "$Failed case(s) failed"; exit 1 }
Write-Host "all cases passed"
exit 0
