param([string]$ArchiveName = 'candidate-source.zip')
$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$archivePath = Join-Path $taskRoot ".planning/2026-11-02-harness-optimization/$ArchiveName"
$sourceFiles = git -C $taskRoot -c core.quotepath=false ls-files -c -o --exclude-standard -- python-agent RainN0Coding-frontend src deploy infrastructure docs/optimization pom.xml mvnw mvnw.cmd .mvn pyproject.toml uv.lock .gitignore Harness优化.md
if ($LASTEXITCODE -ne 0) { throw 'Could not enumerate source files' }
$sourceFiles = $sourceFiles | Where-Object {
    $_ -and $_ -notmatch '(^|/)(node_modules|\.venv|data|__pycache__|\.pytest_cache|\.test-tmp[^/]*)(/|$)' -and
    $_ -notmatch '^src/main/resources/static/' -and $_ -notmatch '\.(db|db-wal|db-shm|pyc|log|env)$' -and
    (Test-Path -LiteralPath (Join-Path $taskRoot $_) -PathType Leaf)
} | Sort-Object -Unique
Add-Type -AssemblyName System.IO.Compression
$stream = [IO.File]::Create($archivePath)
$archive = [IO.Compression.ZipArchive]::new($stream, [IO.Compression.ZipArchiveMode]::Create)
try {
    foreach ($relativePath in $sourceFiles) {
        $entry = $archive.CreateEntry($relativePath, [IO.Compression.CompressionLevel]::Fastest)
        $outputStream = $entry.Open()
        $inputStream = [IO.File]::OpenRead((Join-Path $taskRoot $relativePath))
        try { $inputStream.CopyTo($outputStream) }
        finally { $inputStream.Dispose(); $outputStream.Dispose() }
    }
} finally { $archive.Dispose(); $stream.Dispose() }
scp -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=15 -o ConnectionAttempts=2 $archivePath "ubuntu@124.223.164.223:/home/ubuntu/harness-20261102/$ArchiveName"
if ($LASTEXITCODE -ne 0) { throw 'Source upload failed; no remote extraction attempted' }
$remoteScript = @"
set -eu
sudo -n python3 -m zipfile -e /home/ubuntu/harness-20261102/$ArchiveName /opt/rainn0coding/harness-20261102/candidate
sudo -n chown -R rainn0coding:rainn0coding /opt/rainn0coding/harness-20261102/candidate
"@
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=15 -o ConnectionAttempts=2 ubuntu@124.223.164.223 $remoteScript
if ($LASTEXITCODE -ne 0) { throw 'Remote extraction failed' }
Write-Output "Synchronized $($sourceFiles.Count) source files"
