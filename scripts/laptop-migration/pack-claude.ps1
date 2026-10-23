# Pack Claude Code data from this Windows profile into an encrypted file for a
# new laptop: every session transcript (all projects), memory, settings, skills,
# plugins, plans, file history, plus ~/.claude.json.
#
# Left out: .credentials.json (log in again on the new laptop) and runtime junk
# (cache, telemetry, session-env, shell-snapshots, ide, sessions).
#
# Close VS Code / Claude Code first so the current session is fully written, then
# in a normal PowerShell window:
#   powershell -ExecutionPolicy Bypass -File "\\wsl.localhost\Ubuntu-24.04\home\fowadhamza\Projects\Auditree\scripts\laptop-migration\pack-claude.ps1"
#
# Output: %USERPROFILE%\claude-migration\claude-data.tgz.gpg[.part-NNN] + SHA256SUMS
$ErrorActionPreference = 'Stop'

$gpg = 'C:\Program Files\Git\usr\bin\gpg.exe'
if (-not (Test-Path $gpg)) { throw "gpg not found at $gpg -- install Git for Windows" }
$out = Join-Path $env:USERPROFILE 'claude-migration'
if (Test-Path $out) { throw "$out already exists -- move it away first" }
$partSize = 90MB

function Get-Plain([Security.SecureString]$s) {
    $b = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($s)
    try { [Runtime.InteropServices.Marshal]::PtrToStringBSTR($b) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b) }
}
$p1 = Get-Plain (Read-Host 'Passphrase (min 16 chars)' -AsSecureString)
$p2 = Get-Plain (Read-Host 'Repeat passphrase' -AsSecureString)
if ($p1.Length -lt 16) { throw 'Too short' }
if ($p1 -ne $p2) { throw 'Passphrases differ' }

$tmp = Join-Path $env:TEMP "claude-pack-$(Get-Random)"
New-Item -ItemType Directory $tmp | Out-Null
New-Item -ItemType Directory $out | Out-Null
try {
    Write-Host '== 1/3 tar'
    $tgz = Join-Path $tmp 'claude-data.tgz'
    Push-Location $env:USERPROFILE
    try {
        & tar.exe -czf $tgz `
            --exclude=.claude/.credentials.json --exclude=.claude/cache `
            --exclude=.claude/telemetry --exclude=.claude/session-env `
            --exclude=.claude/shell-snapshots --exclude=.claude/ide `
            --exclude=.claude/sessions `
            .claude .claude.json
        if ($LASTEXITCODE -gt 1) { throw "tar failed ($LASTEXITCODE)" }
        if ($LASTEXITCODE -eq 1) { Write-Warning 'tar reported warnings (a file changed while reading) -- usually harmless' }
    } finally { Pop-Location }
    Write-Host ('   {0:N1} MB compressed' -f ((Get-Item $tgz).Length / 1MB))

    Write-Host '== 2/3 gpg AES256'
    $pf = Join-Path $tmp 'p'
    [IO.File]::WriteAllText($pf, $p1, (New-Object Text.UTF8Encoding $false))
    $enc = Join-Path $out 'claude-data.tgz.gpg'
    & $gpg --batch --yes --pinentry-mode loopback --passphrase-file $pf `
        --symmetric --cipher-algo AES256 --s2k-digest-algo SHA512 `
        --s2k-mode 3 --s2k-count 65011712 -o $enc $tgz
    if ($LASTEXITCODE) { throw "gpg failed ($LASTEXITCODE)" }

    Write-Host '== 3/3 split + checksums'
    if ((Get-Item $enc).Length -gt $partSize) {
        $in = [IO.File]::OpenRead($enc)
        try {
            $buf = New-Object byte[] (4MB); $i = 0
            while ($in.Position -lt $in.Length) {
                $o = [IO.File]::Create(('{0}.part-{1:D3}' -f $enc, $i))
                try {
                    $left = $partSize
                    while ($left -gt 0 -and ($n = $in.Read($buf, 0, [Math]::Min($buf.Length, $left))) -gt 0) {
                        $o.Write($buf, 0, $n); $left -= $n
                    }
                } finally { $o.Close() }
                $i++
            }
        } finally { $in.Close() }
        Remove-Item $enc
    }
    $sums = Get-ChildItem $out -Filter 'claude-data.tgz.gpg*' | Sort-Object Name |
        ForEach-Object { '{0}  {1}' -f (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower(), $_.Name }
    [IO.File]::WriteAllText((Join-Path $out 'SHA256SUMS'), (($sums -join "`n") + "`n"), (New-Object Text.UTF8Encoding $false))
} finally {
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
    $p1 = $null; $p2 = $null
}

Get-ChildItem $out | Format-Table Name, @{n='MB'; e={'{0:N1}' -f ($_.Length / 1MB)}} -AutoSize
Write-Host "Done: $out"
