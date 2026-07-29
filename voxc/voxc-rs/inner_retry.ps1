$env:CARGO_TARGET_DIR = 'E:\IDEProjects\AI\vools\voxc\voxc-rs\target_retry_v1'
Set-Location 'E:\IDEProjects\AI\vools\voxc\voxc-rs'
$ErrorActionPreference = 'Continue'

$maxRetries = 20
$retry = 0
$success = $false

while (-not $success -and $retry -lt $maxRetries) {
    $retry++
    "Attempt #$retry at (Get-Date -Format 'HH:mm:ss')"

    # Clean lock files from previous attempt
    Remove-Item -Force (Join-Path 'E:\IDEProjects\AI\vools\voxc\voxc-rs\target_retry_v1' 'release\.cargo-*') -ErrorAction SilentlyContinue

    # Run cargo build
    & cargo build --release *>&1 | Out-File -FilePath 'E:\IDEProjects\AI\vools\voxc\voxc-rs\build_retry_out.txt' -Encoding utf8 -Append
    $code = $LASTEXITCODE

    "Attempt #$retry exit code: $code"

    if ($code -eq 0) {
        $success = $true
        "BUILD SUCCEEDED on attempt #$retry"
    } elseif ($code -eq -1 -or $code -eq 1) {
        # Process was killed or had error, retry
        "Retrying (process was killed or error)..."
        Start-Sleep -Seconds 5
    } else {
        "Unknown exit code: $code, retrying..."
        Start-Sleep -Seconds 5
    }
}

if ($success) {
    "SUCCESS" | Out-File -FilePath 'E:\IDEProjects\AI\vools\voxc\voxc-rs\build_retry_done.txt' -Encoding utf8
} else {
    "FAILED after $maxRetries attempts" | Out-File -FilePath 'E:\IDEProjects\AI\vools\voxc\voxc-rs\build_retry_done.txt' -Encoding utf8
}

# Check executable
$exePath = Join-Path 'E:\IDEProjects\AI\vools\voxc\voxc-rs\target_retry_v1' 'release\voxc.exe'
if (Test-Path $exePath) {
    "EXE_PRODUCED: YES, size: (Get-Item $exePath).Length bytes" | Out-File -FilePath 'E:\IDEProjects\AI\vools\voxc\voxc-rs\build_retry_done.txt' -Encoding utf8 -Append
} else {
    "EXE_PRODUCED: NO" | Out-File -FilePath 'E:\IDEProjects\AI\vools\voxc\voxc-rs\build_retry_done.txt' -Encoding utf8 -Append
}

"FINISHED_AT: (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File -FilePath 'E:\IDEProjects\AI\vools\voxc\voxc-rs\build_retry_done.txt' -Encoding utf8 -Append
"FINAL_EXIT_CODE: $code" | Out-File -FilePath 'E:\IDEProjects\AI\vools\voxc\voxc-rs\build_retry_done.txt' -Encoding utf8 -Append
