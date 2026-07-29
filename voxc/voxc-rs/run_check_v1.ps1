# Quick syntax verification using cargo check (faster than build)
$ErrorActionPreference = "Continue"

# Use a fresh target directory to avoid stale lock files
$targetDir = Join-Path $PSScriptRoot "target_check_v1"
$env:CARGO_TARGET_DIR = $targetDir

# Output file
$outFile = Join-Path $PSScriptRoot "check_v1_out.txt"
Remove-Item -Force $outFile -ErrorAction SilentlyContinue

Write-Host "Starting cargo check --release at $(Get-Date -Format 'HH:mm:ss')"
Write-Host "Target dir: $targetDir"

# Use ProcessStartInfo to capture native stderr directly (avoiding PowerShell CLIXML)
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = "cargo"
$psi.Arguments = "check --release --message-format=short"
$psi.WorkingDirectory = $PSScriptRoot
$psi.UseShellExecute = $false
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.EnvironmentVariables["CARGO_TARGET_DIR"] = $targetDir

$proc = New-Object System.Diagnostics.Process
$proc.StartInfo = $psi

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

Write-Host "Check finished. Exit code: $exitCode"
Write-Host "Output written to: $outFile"
