# Test: a re-run of install.ps1 leaves no gap in the landed copies.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File install-no-gap.test.ps1
#
# The defect: with no symlink rights, install.ps1 deletes each landed copy and then copies it
# again. Between the two steps the file is absent. The gate hooks fail closed on a missing
# script, so every session is refused for as long as the gap lasts (incident 2026-10-13).
#
# The main case runs install.ps1 once, then re-runs it 20 times against a scratch clone and a
# scratch CLAUDE_CONFIG_DIR, with copy mode forced. Each re-run changes both hook files to the other
# of two large versions. A reader loop, in this process, opens and reads guard.py and guard_core.py
# in a tight loop for the whole series. It fails on a missing file, an unreadable file, a read that
# is not one whole version, or a read pair whose INSTALL_ID values differ. This replaces a watcher
# count of Deleted and Renamed events: a rename over a name emits a Deleted event, so that count
# failed a correct atomic replace (a stale proxy, re-pointed per outcomes-tests-are-claims). The
# fixture skill has nested dirs, and a nested file the source drops must be pruned.
#
# Three more cases, each in its own scratch tree. symrun and linkfail need symlink rights. On a
# runner without them they print SKIP with the reason and do not count:
#   symrun    a real file from an earlier copy, then a run where links can be made: no gap event.
#   linkfail  dest is a symlink to elsewhere and the copy fails: a file must still exist at dest.
#   lock1     first local run, skill locked: a .bak or no copy marker after run 1, and no person
#             file lost after run 2. Needs no symlink rights; copy mode is forced.
#
# One more, hooks-whole, at the end of the file: no live hook file is rewritten in place. A rewrite
# in place keeps a file's identity, so each changed hook file must get a new one, through install.ps1
# run 2 and through the post-merge hook it writes. The hook route needs git and a Git Bash sh, and
# FAILs without them.
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

# Reads each hook file in a tight loop on its own thread, until Stop. Every read is opened with
# read, write and delete sharing, so the installer's writes and renames are never refused by the
# reader. A pass reads each path in order, then compares the two. A fault is counted by kind:
#   missing <name>               the file, or a path listed in Present, is not there.
#   unreadable <name>            the open or read failed, a sharing violation for one.
#   short or mixed <name>        the read is not one whole version (Versions1 or Versions2).
#   INSTALL_ID mismatch ...      both reads are whole, and their INSTALL_ID values differ.
Add-Type -TypeDefinition @'
using System;
using System.Collections.Concurrent;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;

public class HookReader
{
    public string[] Paths = new string[0];
    public string[] Versions1 = new string[0];
    public string[] Versions2 = new string[0];
    // Paths that must exist on every pass: a file or a directory. Each one missing is a fault.
    public string[] Present = new string[0];
    private readonly ConcurrentDictionary<string, long> faults = new ConcurrentDictionary<string, long>();
    private static readonly Regex StampRe = new Regex("INSTALL_ID = \"([^\"]*)\"");
    private long passes;
    private volatile bool stop;
    private Thread worker;

    public long Passes { get { return Interlocked.Read(ref passes); } }

    public void Start()
    {
        worker = new Thread(Loop);
        worker.IsBackground = true;
        worker.Start();
    }

    public void Stop()
    {
        stop = true;
        if (worker != null) { worker.Join(); worker = null; }
    }

    public long Count(string prefix)
    {
        long total = 0;
        foreach (var kv in faults) if (kv.Key.StartsWith(prefix, StringComparison.Ordinal)) total += kv.Value;
        return total;
    }

    public long Total()
    {
        long total = 0;
        foreach (var kv in faults) total += kv.Value;
        return total;
    }

    public string[] Report()
    {
        var lines = new System.Collections.Generic.List<string>();
        foreach (var kv in faults) lines.Add(kv.Key + " x" + kv.Value);
        return lines.ToArray();
    }

    private void Fault(string kind)
    {
        faults.AddOrUpdate(kind, 1L, (k, v) => v + 1);
    }

    private static string ReadAll(string path)
    {
        using (FileStream fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
        using (MemoryStream ms = new MemoryStream())
        {
            fs.CopyTo(ms);
            return Encoding.UTF8.GetString(ms.ToArray());
        }
    }

    private static string StampOf(string text)
    {
        Match m = StampRe.Match(text);
        return m.Success ? m.Groups[1].Value : "(none)";
    }

    private void Loop()
    {
        string[] got = new string[Paths.Length];
        while (!stop)
        {
            for (int i = 0; i < Paths.Length; i++)
            {
                string name = Path.GetFileName(Paths[i]);
                got[i] = null;
                try { got[i] = ReadAll(Paths[i]); }
                catch (FileNotFoundException) { Fault("missing " + name); continue; }
                catch (DirectoryNotFoundException) { Fault("missing " + name); continue; }
                catch (IOException) { Fault("unreadable " + name); continue; }
                if (got[i] != Versions1[i] && got[i] != Versions2[i]) Fault("short or mixed " + name);
            }
            for (int j = 0; j < Present.Length; j++)
            {
                if (!File.Exists(Present[j]) && !Directory.Exists(Present[j]))
                    Fault("missing " + Path.GetFileName(Present[j]));
            }
            bool whole0 = got[0] != null && (got[0] == Versions1[0] || got[0] == Versions2[0]);
            bool whole1 = got[1] != null && (got[1] == Versions1[1] || got[1] == Versions2[1]);
            if (whole0 && whole1 && StampOf(got[0]) != StampOf(got[1]))
                Fault("INSTALL_ID mismatch between " + Path.GetFileName(Paths[0]) + " and " + Path.GetFileName(Paths[1]));
            Interlocked.Increment(ref passes);
        }
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

# A scratch clone and CLAUDE dir for one extra case, under $Tmp. It ships CLAUDE.md, settings.json
# and the given landed dirs. The caller adds the rest with Write-FixtureFile.
function New-Scratch([string]$Name, [string[]]$Dirs) {
    $root = Join-Path $Tmp $Name
    $s = @{ Root = $root; Clone = (Join-Path $root 'clone'); Cfg = (Join-Path $root 'claude') }
    New-Item -ItemType Directory -Force -Path $s.Clone, $s.Cfg | Out-Null
    Copy-Item -LiteralPath (Join-Path $Repo 'install.ps1') -Destination (Join-Path $s.Clone 'install.ps1')
    Write-FixtureFile (Join-Path $s.Clone 'CLAUDE.md') '# scratch fixture'
    Write-FixtureFile (Join-Path $s.Clone 'settings.json') '{}'
    Write-FixtureFile (Join-Path $s.Clone 'landed-dirs.txt') (($Dirs -join "`n") + "`n")
    return $s
}

# ---- fixture: a small clone with the landed dirs that matter, plus the real install.ps1 --------
New-Item -ItemType Directory -Force -Path $Clone, $Cfg | Out-Null
Copy-Item -LiteralPath (Join-Path $Repo 'install.ps1') -Destination (Join-Path $Clone 'install.ps1')
Write-Fixture 'CLAUDE.md' '# nogap fixture'
Write-Fixture 'settings.json' '{}'
Write-Fixture 'landed-dirs.txt' (($Landed -join "`n") + "`n")
Write-Fixture 'agents\builder.md' '# builder'
Write-Fixture 'lint\ste_gate.py' '# gate'
Write-Fixture 'lint\ste_lint.py' '# lint'
# The hook files in two versions, A and B. Each file is one stamp line, a label line, then padding,
# so a version is large: a copy of it takes long enough for the reader to land inside it. Both files
# of one version carry that version's INSTALL_ID, as an installed copy does.
$HookPadLines = 40000
$HookStampA = '1a2b3c4d-0000-4000-8000-00000000000a'
$HookStampB = '1a2b3c4d-0000-4000-8000-00000000000b'
function New-HookText([string]$File, [string]$Stamp, [string]$Label) {
    $head = 'INSTALL_ID = "' + $Stamp + '"' + "`n" + '# ' + $File + ' ' + $Label + "`n"
    return $head + (('# padding, so a copy of this file takes a while to write' + "`n") * $HookPadLines)
}
$HookA = @((New-HookText 'guard.py' $HookStampA 'version A'), (New-HookText 'guard_core.py' $HookStampA 'version A'))
$HookB = @((New-HookText 'guard.py' $HookStampB 'version B'), (New-HookText 'guard_core.py' $HookStampB 'version B'))
Write-Fixture 'hooks\guard.py' $HookA[0]
Write-Fixture 'hooks\guard_core.py' $HookA[1]
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
    Check "fixture: nested names are in the shipped set ($($NestedNames.Count))" ($NestedNames.Count -ge 3)

    # ---- run 2 to run 21: the re-runs under the reader -----------------------------------------
    # Each round writes the other version into the clone, then re-runs install.ps1. The reader runs
    # from before the first round to after the last. Its passes are counted per round, so a round
    # the reader did not run in shows up.
    $InstallRounds = 20
    $Reader = New-Object -TypeName HookReader
    $Reader.Paths = [string[]]@((Join-Path $Cfg 'hooks\guard.py'), (Join-Path $Cfg 'hooks\guard_core.py'))
    $Reader.Versions1 = [string[]]$HookA
    $Reader.Versions2 = [string[]]$HookB
    # The shipped names the watcher used to cover, checked for existence on every pass.
    $Reader.Present = [string[]]@((Join-Path $Cfg 'CLAUDE.md'), (Join-Path $Cfg 'settings.json'), (Join-Path $Cfg 'agents'), (Join-Path $Cfg 'lint'), (Join-Path $Cfg 'skills'))
    $RoundPasses = @()
    $RoundFaults = @()
    $RoundsExit0 = 0
    $RoundsLanded = 0
    $Reader.Start()
    try {
        for ($round = 1; $round -le $InstallRounds; $round++) {
            $Want = if ($round % 2 -eq 1) { $HookB } else { $HookA }
            Write-Fixture 'hooks\guard.py' $Want[0]
            Write-Fixture 'hooks\guard_core.py' $Want[1]
            $passesBefore = $Reader.Passes
            $faultsBefore = $Reader.Total()
            $rcR = Invoke-Install $Clone ("run2-round$round.log")
            $RoundPasses += ($Reader.Passes - $passesBefore)
            $RoundFaults += ($Reader.Total() - $faultsBefore)
            if ($rcR -eq 0) { $RoundsExit0++ }
            $landed = ([IO.File]::ReadAllText((Join-Path $Cfg 'hooks\guard.py')) -eq $Want[0]) -and ([IO.File]::ReadAllText((Join-Path $Cfg 'hooks\guard_core.py')) -eq $Want[1])
            if ($landed) { $RoundsLanded++ }
        }
    } finally {
        $Reader.Stop()
    }
    Remove-Item Env:\CLAUDE_SETTINGS_FORCE_COPY -ErrorAction SilentlyContinue

    $RedRounds = @($RoundFaults | Where-Object { $_ -gt 0 }).Count
    Write-Host "info: $RedRounds of $InstallRounds re-runs had a reader fault; $($Reader.Passes) reader passes in all"
    foreach ($line in $Reader.Report()) { Write-Host "  reader fault: $line" }
    $NoPass = @($RoundPasses | Where-Object { $_ -lt 1 }).Count
    Check "reader ran during every re-run ($NoPass of $InstallRounds re-runs had no reader pass, want 0)" ($NoPass -eq 0)
    Check "all $InstallRounds re-runs exit 0 ($RoundsExit0 of $InstallRounds)" ($RoundsExit0 -eq $InstallRounds)
    Check "every re-run lands its new text in both hook files ($RoundsLanded of $InstallRounds, non-vacuous)" ($RoundsLanded -eq $InstallRounds)
    Check "no shipped name is missing during the re-runs: the hook files, CLAUDE.md, settings.json, agents, lint, skills ($($Reader.Count('missing ')) faults)" ($Reader.Count('missing ') -eq 0)
    Check "no hook file is unreadable during the re-runs ($($Reader.Count('unreadable ')) faults)" ($Reader.Count('unreadable ') -eq 0)
    Check "no hook read is short or mixed: each read is one whole version ($($Reader.Count('short or mixed ')) faults)" ($Reader.Count('short or mixed ') -eq 0)
    Check "guard.py and guard_core.py never carry different INSTALL_IDs during the re-runs ($($Reader.Count('INSTALL_ID mismatch')) faults)" ($Reader.Count('INSTALL_ID mismatch') -eq 0)
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

    # ---- hooks-whole: no live hook file is ever seen truncated (temp, then rename) --------------
    # Owner ruling 2026-10-14 (install-atomic, arbiter 03:41). The installer writes each file to a
    # temp name and renames it into place, so a reader sees the old file or the new one, never a
    # half-written one. An in-place rewrite keeps the file's identity. A rename into place gives it a
    # new identity. So in a re-run that changes a hook file's text, each hook file that changes must
    # get a new identity, and the new text must land (non-vacuous). Two routes: install.ps1 run 2 in
    # copy mode, and the post-merge hook install.ps1 writes into .git\hooks, run by git's sh.
    if (-not ('FileIdentity' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

public static class FileIdentity
{
    [StructLayout(LayoutKind.Sequential)]
    public struct FileInfoById
    {
        public uint Attributes;
        public uint CreatedLo, CreatedHi, AccessedLo, AccessedHi, WrittenLo, WrittenHi;
        public uint Volume;
        public uint SizeHi, SizeLo;
        public uint Links;
        public uint IndexHi, IndexLo;
    }

    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    static extern SafeFileHandle CreateFileW(string name, uint access, uint share, IntPtr security, uint disposition, uint flags, IntPtr template);

    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool GetFileInformationByHandle(SafeFileHandle handle, out FileInfoById info);

    // Identity of the object at path, following links. A rewrite in place keeps it; a rename gives a new one.
    // Access 0 (query only), share read|write|delete, OPEN_EXISTING, BACKUP_SEMANTICS.
    public static string Of(string path)
    {
        using (SafeFileHandle h = CreateFileW(path, 0, 7, IntPtr.Zero, 3, 0x02000000, IntPtr.Zero))
        {
            if (h.IsInvalid) throw new IOException("cannot open " + path + ", Win32 error " + Marshal.GetLastWin32Error());
            FileInfoById info;
            if (!GetFileInformationByHandle(h, out info)) throw new IOException("no file information for " + path);
            return info.Volume.ToString("x") + ":" + info.IndexHi.ToString("x") + ":" + info.IndexLo.ToString("x");
        }
    }
}
'@
    }

    $HookFiles = @('guard.py', 'guard_core.py')
    $HookV1 = @('# guard v1', '# guard core v1')
    $HookV2 = @('# guard v2, new text of another length', '# guard core v2, new text of another length')

    # Writes the two hook files the case watches, in the clone.
    function Use-HookSource([string]$Dir, [string[]]$Texts) {
        Write-FixtureFile (Join-Path $Dir 'hooks\guard.py') $Texts[0]
        Write-FixtureFile (Join-Path $Dir 'hooks\guard_core.py') $Texts[1]
    }

    # True when both hook files in $Hooks hold exactly $Texts. A missing file reads as empty.
    function Test-HookLanded([string]$Hooks, [string[]]$Texts) {
        $g = ''; $c = ''
        if (Test-Path -LiteralPath (Join-Path $Hooks 'guard.py')) { $g = [IO.File]::ReadAllText((Join-Path $Hooks 'guard.py')) }
        if (Test-Path -LiteralPath (Join-Path $Hooks 'guard_core.py')) { $c = [IO.File]::ReadAllText((Join-Path $Hooks 'guard_core.py')) }
        return ($g -eq $Texts[0]) -and ($c -eq $Texts[1])
    }

    # The identity of each hook file in $Hooks, by name.
    function Get-HookIds([string]$Hooks) {
        $ids = @{}
        foreach ($n in $HookFiles) { $ids[$n] = [FileIdentity]::Of((Join-Path $Hooks $n)) }
        return $ids
    }

    # The hook files whose identity did not change: each one was rewritten in place.
    function Get-InPlaceHookFiles($Before, $After) {
        return @($HookFiles | Where-Object { $Before[$_] -eq $After[$_] })
    }

    # The git Bash sh: from PATH, else beside the git on PATH (Git\cmd\git.exe -> Git\bin\sh.exe).
    function Get-GitSh {
        $c = Get-Command sh -ErrorAction SilentlyContinue
        if ($c) { return $c.Source }
        $g = Get-Command git -ErrorAction SilentlyContinue
        if ($g) {
            $p = Join-Path (Split-Path (Split-Path $g.Source -Parent) -Parent) 'bin\sh.exe'
            if (Test-Path -LiteralPath $p) { return $p }
        }
        return $null
    }

    # Route 1: install.ps1 run 2 in copy mode.
    $H1 = New-Scratch 'hooks-whole-install' @('hooks')
    $H1Hooks = Join-Path $H1.Cfg 'hooks'
    Use-HookSource $H1.Clone $HookV1
    $env:CLAUDE_CONFIG_DIR = $H1.Cfg
    $env:CLAUDE_SETTINGS_FORCE_COPY = '1'
    try {
        $rcH1 = Invoke-Install $H1.Clone 'hooks-whole-install-run1.log'
        Check "hooks-whole: install run 1 (forced copy) exits 0 (exit $rcH1)" ($rcH1 -eq 0)
        Check "hooks-whole: install run 1 lands both hook files as copies, not links" ((Test-HookLanded $H1Hooks $HookV1) -and (-not (Test-ReparsePoint (Join-Path $H1Hooks 'guard.py'))))
        Use-HookSource $H1.Clone $HookV2
        $idsH1 = Get-HookIds $H1Hooks
        $rcH2 = Invoke-Install $H1.Clone 'hooks-whole-install-run2.log'
        Check "hooks-whole: install run 2 exits 0 (exit $rcH2)" ($rcH2 -eq 0)
        Check "hooks-whole: install run 2 lands the new text in both hook files (non-vacuous)" (Test-HookLanded $H1Hooks $HookV2)
        $inPlaceH1 = @(Get-InPlaceHookFiles $idsH1 (Get-HookIds $H1Hooks))
        foreach ($f in $inPlaceH1) { Write-Host "  rewritten in place by install run 2: $f" }
        Check "hooks-whole: install run 2 rewrites no hook file in place ($($inPlaceH1.Count) in place)" ($inPlaceH1.Count -eq 0)
    } finally {
        Remove-Item Env:\CLAUDE_CONFIG_DIR, Env:\CLAUDE_SETTINGS_FORCE_COPY -ErrorAction SilentlyContinue
    }

    # Route 2: the post-merge hook that install.ps1 writes into .git\hooks, run by git's sh.
    $H2 = New-Scratch 'hooks-whole-hook' @('hooks')
    $H2Hooks = Join-Path $H2.Cfg 'hooks'
    Use-HookSource $H2.Clone $HookV1
    $GitCmd = Get-Command git -ErrorAction SilentlyContinue
    $Sh = Get-GitSh
    if (-not $GitCmd -or -not $Sh) {
        Check "hooks-whole: git and a Git Bash sh are both found, so the post-merge hook can run" $false
    } else {
        $env:CLAUDE_CONFIG_DIR = $H2.Cfg
        $env:CLAUDE_SETTINGS_FORCE_COPY = '1'
        try {
            # A real repo on main, with one commit, so the hook's branch check passes.
            & git -C $H2.Clone init -q
            & git -C $H2.Clone symbolic-ref HEAD refs/heads/main
            & git -C $H2.Clone -c core.autocrlf=false add -A
            & git -C $H2.Clone -c core.autocrlf=false -c user.name=hooks-whole-test -c user.email=hooks-whole-test@example.invalid commit -q -m fixture
            Check "hooks-whole: the scratch clone is a git repo on main with one commit (exit $LASTEXITCODE)" ($LASTEXITCODE -eq 0)

            $rcH2a = Invoke-Install $H2.Clone 'hooks-whole-hook-run1.log'
            Check "hooks-whole: hook route: install run 1 (forced copy) exits 0 (exit $rcH2a)" ($rcH2a -eq 0)
            Check "hooks-whole: hook route: install run 1 writes the post-merge hook into .git\hooks" (Test-Path -LiteralPath (Join-Path $H2.Clone '.git\hooks\post-merge'))
            Use-HookSource $H2.Clone $HookV2
            $idsH2 = Get-HookIds $H2Hooks
            # The hook reads CLAUDE_CONFIG_DIR inside sh, so it gets forward slashes.
            $env:CLAUDE_CONFIG_DIR = $H2.Cfg.Replace('\', '/')
            $hookLog = Join-Path $Tmp 'hooks-whole-hook-run2.log'
            $pH = Start-Process -FilePath $Sh -ArgumentList '.git/hooks/post-merge' -WorkingDirectory $H2.Clone -Wait -PassThru -NoNewWindow -RedirectStandardOutput $hookLog -RedirectStandardError ($hookLog + '.err')
            Check "hooks-whole: hook route: the post-merge hook exits 0 (exit $($pH.ExitCode))" ($pH.ExitCode -eq 0)
            Check "hooks-whole: hook route: the hook lands the new text in both hook files (non-vacuous)" (Test-HookLanded $H2Hooks $HookV2)
            $inPlaceH2 = @(Get-InPlaceHookFiles $idsH2 (Get-HookIds $H2Hooks))
            foreach ($f in $inPlaceH2) { Write-Host "  rewritten in place by the hook: $f" }
            Check "hooks-whole: hook route: the hook rewrites no hook file in place ($($inPlaceH2.Count) in place)" ($inPlaceH2.Count -eq 0)
        } finally {
            Remove-Item Env:\CLAUDE_CONFIG_DIR, Env:\CLAUDE_SETTINGS_FORCE_COPY -ErrorAction SilentlyContinue
        }
    }
} finally {
    if ($Rec) { $Rec.Dispose() }
    Remove-Item Env:\CLAUDE_CONFIG_DIR, Env:\CLAUDE_SETTINGS_FORCE_COPY, Env:\CLAUDE_SETTINGS_USER_ENV_KEY -ErrorAction SilentlyContinue
    try { [Microsoft.Win32.Registry]::CurrentUser.DeleteSubKeyTree($EnvSub, $false) } catch { }
    Remove-Item -LiteralPath $Tmp -Recurse -Force -ErrorAction SilentlyContinue
}

if ($Failed) { Write-Host "$Failed case(s) failed"; exit 1 }
Write-Host "all cases passed"
exit 0
