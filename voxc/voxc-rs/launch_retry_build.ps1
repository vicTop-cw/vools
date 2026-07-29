# Build with retry logic - if cargo is killed, restart it (reusing compiled deps)
$targetDir = Join-Path $PSScriptRoot "target_retry_v1"
$env:CARGO_TARGET_DIR = $targetDir

$outFile = Join-Path $PSScriptRoot "build_retry_out.txt"
$doneMarker = Join-Path $PSScriptRoot "build_retry_done.txt"
Remove-Item -Force $outFile, $doneMarker -ErrorAction SilentlyContinue
Remove-Item -Force (Join-Path $targetDir "release\.cargo-*") -ErrorAction SilentlyContinue

# Inner retry script
$innerScript = @"
`$env:CARGO_TARGET_DIR = '$targetDir'
Set-Location '$PSScriptRoot'
`$ErrorActionPreference = 'Continue'

`$maxRetries = 20
`$retry = 0
`$success = `$false

while (-not `$success -and `$retry -lt `$maxRetries) {
    `$retry++
    "Attempt #`$retry at `(Get-Date -Format 'HH:mm:ss'`)"

    # Clean lock files from previous attempt
    Remove-Item -Force (Join-Path '$targetDir' 'release\.cargo-*') -ErrorAction SilentlyContinue

    # Run cargo build
    & cargo build --release *>&1 | Out-File -FilePath '$outFile' -Encoding utf8 -Append
    `$code = `$LASTEXITCODE

    "Attempt #`$retry exit code: `$code"

    if (`$code -eq 0) {
        `$success = `$true
        "BUILD SUCCEEDED on attempt #`$retry"
    } elseif (`$code -eq -1 -or `$code -eq 1) {
        # Process was killed or had error, retry
        "Retrying (process was killed or error)..."
        Start-Sleep -Seconds 5
    } else {
        "Unknown exit code: `$code, retrying..."
        Start-Sleep -Seconds 5
    }
}

if (`$success) {
    "SUCCESS" | Out-File -FilePath '$doneMarker' -Encoding utf8
} else {
    "FAILED after `$maxRetries attempts" | Out-File -FilePath '$doneMarker' -Encoding utf8
}

# Check executable
`$exePath = Join-Path '$targetDir' 'release\voxc.exe'
if (Test-Path `$exePath) {
    "EXE_PRODUCED: YES, size: `(Get-Item `$exePath`).Length bytes" | Out-File -FilePath '$doneMarker' -Encoding utf8 -Append
} else {
    "EXE_PRODUCED: NO" | Out-File -FilePath '$doneMarker' -Encoding utf8 -Append
}

"FINISHED_AT: `(Get-Date -Format 'yyyy-MM-dd HH:mm:ss'`)" | Out-File -FilePath '$doneMarker' -Encoding utf8 -Append
"FINAL_EXIT_CODE: `$code" | Out-File -FilePath '$doneMarker' -Encoding utf8 -Append
"@

$innerScriptFile = Join-Path $PSScriptRoot "inner_retry.ps1"
$innerScript | Out-File -FilePath $innerScriptFile -Encoding utf8

Write-Host "Launching retry build script..."
Write-Host "Target dir: $targetDir"
Write-Host "Done marker: $doneMarker"

# Launch independent process
Start-Process powershell -ArgumentList "-ExecutionPolicy Bypass -File `"$innerScriptFile`"" -WindowStyle Hidden

Write-Host "Independent retry process launched."
