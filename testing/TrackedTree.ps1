# testing/TrackedTree.ps1: copy what git lists under named repo folders into a fixture tree, so no
# PowerShell fixture lists files. The rules and the reason are in testing/tracked_tree.py; this is the
# same helper for PowerShell suites (5.1 and 7). Dot-source it:
#   . (Join-Path $Repo 'testing\TrackedTree.ps1')
#   Copy-Tracked -Root $Repo -DestRoot $Clone -Folders 'hooks'            lands $Clone\hooks\<path>
#   Copy-TrackedFolder -Root $Repo -Folder 'hooks' -Dest $Dir -Skip @('x.py')   lands $Dir\<path>
# Each throws when git cannot list a folder or lists nothing in it. Returns the copied paths, relative to the folder.

function Get-TrackedList([string]$Root, [string]$Folder) {
    $Folder = $Folder.TrimEnd('/', '\')
    $raw = & git -C $Root -c core.quotePath=false ls-files -z --cached --others --exclude-standard -- ($Folder + '/')
    if ($LASTEXITCODE -ne 0) { throw "TrackedTree: git ls-files failed for $Folder/ in $Root" }
    $names = @()
    foreach ($p in @(($raw -join "`n") -split "`0" | Sort-Object -Unique)) {
        if (-not $p) { continue }
        $leaf = ($p -split '/')[-1]
        if ($leaf -clike 'test_*' -or $leaf -clike '*_test.py' -or $leaf -clike '*.test.*') { continue }
        if (-not (Test-Path -LiteralPath (Join-Path $Root $p) -PathType Leaf)) { continue }
        $names += $p.Substring($Folder.Length + 1)
    }
    if ($names.Count -eq 0) { throw "TrackedTree: git lists no file under $Folder/ in $Root" }
    return $names
}

function Copy-TrackedFolder([string]$Root, [string]$Folder, [string]$Dest, [string[]]$Skip = @()) {
    $copied = @()
    foreach ($rel in @(Get-TrackedList $Root $Folder)) {
        if ($Skip -ccontains $rel) { continue }
        $target = Join-Path $Dest ($rel -replace '/', '\')
        $parent = Split-Path -Parent $target
        if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
        Copy-Item -LiteralPath (Join-Path (Join-Path $Root $Folder) ($rel -replace '/', '\')) -Destination $target
        $copied += $rel
    }
    return $copied
}

function Copy-Tracked([string]$Root, [string]$DestRoot, [string[]]$Folders) {
    $copied = @()
    foreach ($f in $Folders) {
        $f = $f.TrimEnd('/', '\')
        $copied += @(Copy-TrackedFolder $Root $f (Join-Path $DestRoot $f) | ForEach-Object { $f + '/' + $_ })
    }
    return $copied
}
