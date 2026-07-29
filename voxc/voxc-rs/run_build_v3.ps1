# Simple build verification script
$ErrorActionPreference = "Continue"

# Use isolated target directory
$targetDir = Join-Path $PSScriptRoot "target_verify2"
$env:CARGO_TARGET_DIR = $targetDir

# Remove lock files
Remove-Item -Force (Join-Path $targetDir "release\.cargo-*") -ErrorAction SilentlyContinue

# Output file
$outFile = Join-Path $PSScriptRoot "build_v3_out.txt"
Remove-Item -Force $outFile -ErrorAction SilentlyContinue

Write-Host "Starting cargo build --release at $(Get-Date -Format 'HH:mm:ss')"
Write-Host "Target dir: $targetDir"

# Use ProcessStartInfo with RedirectStandardOutput/Error to capture native output directly
# (avoiding PowerShell's CLIXML wrapping of native stderr)
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = "cargo"
$psi.Arguments = "build --release"
$psi.WorkingDirectory = $PSScriptRoot
$psi.UseShellExecute = $false
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.EnvironmentVariables["CARGO_TARGET_DIR"] = $targetDir

$proc = New-Object System.Diagnostics.Process
$proc.StartInfo = $psi

# Build output via event handlers (so we capture native stderr lines directly)
$outBuilder = New-Object System.Text.StringBuilder
$errBuilder = New-Object System.Text.StringBuilder

$null = Register-ObjectEvent -InputObject $proc -EventName "OutputDataReceived" -Action {
    if ($EventArgs.Data) {
        $outBuilder.AppendLine($EventArgs.Data) | Out-Null
    }
}
$null = Register-ObjectEvent -InputObject $proc -EventName "ErrorDataReceived" -Action {
    if ($EventArgs.Data) {
        $errBuilder.AppendLine($EventArgs.Data) | Out-Null
    }
}

$null = $proc.Start()
$proc.BeginOutputReadLine()
$proc.BeginErrorReadLine()
$proc.WaitForExit()
$exitCode = $proc.ExitCode

# Write outputs to file
"=== STDOUT ===" | Out-File -FilePath $outFile -Encoding utf8
$outBuilder.ToString() | Out-File -FilePath $outFile -Encoding utf8 -Append
"=== STDERR ===" | Out-File -FilePath $outFile -Encoding utf8 -Append
$errBuilder.ToString() | Out-File -FilePath $outFile -Encoding utf8 -Append
"=== EXIT_CODE: $exitCode ===" | Out-File -FilePath $outFile -Encoding utf8 -Append
"=== FINISHED_AT: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" | Out-File -FilePath $outFile -Encoding utf8 -Append

# Check if executable was produced
$exePath = Join-Path $targetDir "release\voxc.exe"
if (Test-Path $exePath) {
    $size = (Get-Item $exePath).Length
    "=== EXE_PRODUCED: YES (size: $size bytes) ===" | Out-File -FilePath $outFile -Encoding utf8 -Append
} else {
    "=== EXE_PRODUCED: NO ===" | Out-File -FilePath $outFile -Encoding utf8 -Append
}

Write-Host "Build finished. Exit code: $exitCode"
Write-Host "Output written to: $outFile"
