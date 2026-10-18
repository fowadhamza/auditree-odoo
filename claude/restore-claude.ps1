# Restore Claude Code data packed by pack-claude.ps1 into this Windows profile.
#
# Prereqs: Git for Windows (for gpg), Claude Code installed and logged in once.
# Close VS Code first, then from the folder holding claude-data.tgz.gpg* + SHA256SUMS
# (e.g. the claude/ folder of the laptop-migration clone, copied to Windows):
#   powershell -ExecutionPolicy Bypass -File .\restore-claude.ps1
#
# Merges into %USERPROFILE%\.claude (existing files with the same name are
# overwritten; nothing is deleted). The old ~/.claude.json is saved next to the
# new one as .claude.json.from-old-laptop -- it is not swapped in automatically.
$ErrorActionPreference = 'Stop'

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$gpg = 'C:\Program Files\Git\usr\bin\gpg.exe'
if (-not (Test-Path $gpg)) { throw "gpg not found at $gpg -- install Git for Windows" }

Write-Host '== 1/4 verify checksums'
foreach ($line in Get-Content (Join-Path $here 'SHA256SUMS')) {
    if (-not $line.Trim()) { continue }
    $want, $name = $line -split '\s+', 2
    $got = (Get-FileHash (Join-Path $here $name) -Algorithm SHA256).Hash.ToLower()
    if ($got -ne $want) { throw "Checksum mismatch: $name -- download again" }
}

$tmp = Join-Path $env:TEMP "claude-restore-$(Get-Random)"
New-Item -ItemType Directory $tmp | Out-Null
try {
    Write-Host '== 2/4 join + decrypt'
    $enc = Join-Path $tmp 'claude-data.tgz.gpg'
    $parts = Get-ChildItem $here -Filter 'claude-data.tgz.gpg*' | Sort-Object Name
    $o = [IO.File]::Create($enc)
    try { foreach ($p in $parts) { $i = [IO.File]::OpenRead($p.FullName); try { $i.CopyTo($o) } finally { $i.Close() } } }
    finally { $o.Close() }

    $s = Read-Host 'Passphrase' -AsSecureString
    $b = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($s)
    $pf = Join-Path $tmp 'p'
    try { [IO.File]::WriteAllText($pf, [Runtime.InteropServices.Marshal]::PtrToStringBSTR($b), (New-Object Text.UTF8Encoding $false)) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b) }
    $tgz = Join-Path $tmp 'claude-data.tgz'
    & $gpg --batch --yes --pinentry-mode loopback --passphrase-file $pf -o $tgz -d $enc
    if ($LASTEXITCODE) { throw 'Decryption failed -- wrong passphrase?' }
    Remove-Item $pf

    Write-Host '== 3/4 extract'
    $x = Join-Path $tmp 'x'
    New-Item -ItemType Directory $x | Out-Null
    & tar.exe -xzf $tgz -C $x
    if ($LASTEXITCODE) { throw "tar failed ($LASTEXITCODE)" }

    Write-Host "== 4/4 merge into $env:USERPROFILE\.claude"
    & robocopy (Join-Path $x '.claude') (Join-Path $env:USERPROFILE '.claude') /E /NFL /NDL /NJH /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed ($LASTEXITCODE)" }
    $cj = Join-Path $env:USERPROFILE '.claude.json'
    if (Test-Path $cj) {
        Copy-Item (Join-Path $x '.claude.json') "$cj.from-old-laptop" -Force
        Write-Host '   kept your current .claude.json; old one saved as .claude.json.from-old-laptop'
    } else {
        Copy-Item (Join-Path $x '.claude.json') $cj
    }
} finally {
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}

Write-Host ''
Write-Host 'Restored projects:'
Get-ChildItem (Join-Path $env:USERPROFILE '.claude\projects') -Directory | ForEach-Object {
    '  {0}  ({1} sessions)' -f $_.Name, (Get-ChildItem $_.FullName -Filter *.jsonl).Count
}
Write-Host ''
Write-Host 'Sessions show up for a project only when it is opened from the SAME path as'
Write-Host 'before, e.g. \\wsl.localhost\Ubuntu-24.04\home\fowadhamza\Projects\Auditree.'
Write-Host 'If your distro or Linux username differs, rename the folder under'
Write-Host '.claude\projects to match the new path (see NEW-LAPTOP.md).'
