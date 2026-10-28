# testing/SharedRead.ps1: read a file a child process wrote, even while that child or one it left
# behind still holds the file open for write. [IO.File]::ReadAllText refuses such a file on Windows
# ("being used by another process"). Dot-source it (5.1 and 7):
#   . (Join-Path $Here 'testing\SharedRead.ps1')
#   Read-Shared $Path     returns the file's text (UTF-8)
# The open allows read, write and delete sharing, so an installer rename is never refused by a reader.
# A missing or unreadable file throws. Callers that want '' for a missing file test the path first.

function Read-Shared([string]$Path) {
    $share = [IO.FileShare]([int][IO.FileShare]::ReadWrite -bor [int][IO.FileShare]::Delete)
    $fs = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, $share)
    try {
        $sr = New-Object IO.StreamReader($fs, (New-Object Text.UTF8Encoding($false)))
        return $sr.ReadToEnd()
    } finally { $fs.Close() }
}
