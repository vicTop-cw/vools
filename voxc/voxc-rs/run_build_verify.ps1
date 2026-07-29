# Build Vox compiler with isolated target directory to avoid file lock conflicts
# with any concurrent IDE/background builds.

$ErrorActionPreference = "Continue"

# Use a unique target directory for this verification build
$env:CARGO_TARGET_DIR = "$PSScriptRoot\target_introspect_verify"

# Clean any previous lock file from incomplete builds
$lockFile = Join-Path $env:CARGO_TARGET_DIR ".cargo-lock"
if (Test-Path $lockFile) {
    Remove-Item -Force $lockFile -ErrorAction SilentlyContinue
}

Write-Host "=== Starting cargo build --release ==="
Write-Host "Target dir: $env:CARGO_TARGET_DIR"
Write-Host "Start time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"

# Run cargo build and capture all output (stdout + stderr) to a file
$outFile = "$PSScriptRoot\build_verify_out.txt"
$errFile = "$PSScriptRoot\build_verify_err.txt"
$resultFile = "$PSScriptRoot\build_verify_result.txt"

# Clear previous outputs
Remove-Item -Force $outFile, $errFile, $resultFile -ErrorAction SilentlyContinue

# Use Start-Process to avoid PowerShell CLIXML wrapping of native stderr
$proc = Start-Process -FilePath "cargo" `
    -ArgumentList "build", "--release" `
    -WorkingDirectory $PSScriptRoot `
    -NoNewWindow `
    -PassThru `
    -RedirectStandardOutput $outFile `
    -RedirectStandardError $errFile

Write-Host "Build process started (PID: $($proc.Id)). Waiting for completion..."

# Wait for the build to finish (could take a while for fresh target dir)
$proc.WaitForExit()
$exitCode = $proc.ExitCode

Write-Host "Build finished at: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "Exit code: $exitCode"

# Write the result summary
"EXIT_CODE: $exitCode" | Out-File -FilePath $resultFile -Encoding utf8
"FINISHED_AT: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File -FilePath $resultFile -Encoding utf8 -Append
"TARGET_DIR: $env:CARGO_TARGET_DIR" | Out-File -FilePath $resultFile -Encoding utf8 -Append

# Check if the executable was produced
$exePath = Join-Path $env:CARGO_TARGET_DIR "release\voxc.exe"
if (Test-Path $exePath) {
    "EXE_PRODUCED: YES" | Out-File -FilePath $resultFile -Encoding utf8 -Append
    "EXE_PATH: $exePath" | Out-File -FilePath $resultFile -Encoding utf8 -Append
    $size = (Get-Item $exePath).Length
    "EXE_SIZE_BYTES: $size" | Out-File -FilePath $resultFile -Encoding utf8 -Append
} else {
    "EXE_PRODUCED: NO" | Out-File -FilePath $resultFile -Encoding utf8 -Append
}

Write-Host "=== Build verification complete ==="
Write-Host "Result file: $resultFile"
