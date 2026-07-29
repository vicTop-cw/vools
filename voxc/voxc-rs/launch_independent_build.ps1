# Launch a completely independent PowerShell process to run cargo build
# This process is not managed by RunCommand, so it won't be terminated

$targetDir = Join-Path $PSScriptRoot "target_final_v1"
$outFile = Join-Path $PSScriptRoot "build_final_out.txt"
$doneMarker = Join-Path $PSScriptRoot "build_final_done.txt"

# Clean previous artifacts
Remove-Item -Force $outFile, $doneMarker -ErrorAction SilentlyContinue
Remove-Item -Force (Join-Path $targetDir "release\.cargo-*") -ErrorAction SilentlyContinue

# Inner script that will run in the independent process
$innerScript = @"
`$env:CARGO_TARGET_DIR = '$targetDir'
Set-Location '$PSScriptRoot'
`$ErrorActionPreference = 'Continue'

# Run cargo build, redirect all output to file
`$psi = New-Object System.Diagnostics.ProcessStartInfo
`$psi.FileName = 'cargo'
`$psi.Arguments = 'build --release'
`$psi.WorkingDirectory = '$PSScriptRoot'
`$psi.UseShellExecute = `$false
`$psi.RedirectStandardOutput = `$true
`$psi.RedirectStandardError = `$true
`$psi.EnvironmentVariables['CARGO_TARGET_DIR'] = '$targetDir'

`$proc = New-Object System.Diagnostics.Process
`$proc.StartInfo = `$psi

`$sbOut = New-Object System.Text.StringBuilder
`$sbErr = New-Object System.Text.StringBuilder

`$outAction = {
    if (`$EventArgs.Data) {
        `$sbOut.AppendLine(`$EventArgs.Data) | Out-Null
    }
}
`$errAction = {
    if (`$EventArgs.Data) {
        `$sbErr.AppendLine(`$EventArgs.Data) | Out-Null
    }
}

Register-ObjectEvent -InputObject `$proc -EventName 'OutputDataReceived' -Action `$outAction | Out-Null
Register-ObjectEvent -InputObject `$proc -EventName 'ErrorDataReceived' -Action `$errAction | Out-Null

`$proc.Start() | Out-Null
`$proc.BeginOutputReadLine()
`$proc.BeginErrorReadLine()
`$proc.WaitForExit()
`$exitCode = `$proc.ExitCode

# Write outputs
'=== STDOUT ===' | Out-File -FilePath '$outFile' -Encoding utf8
`$sbOut.ToString() | Out-File -FilePath '$outFile' -Encoding utf8 -Append
'=== STDERR ===' | Out-File -FilePath '$outFile' -Encoding utf8 -Append
`$sbErr.ToString() | Out-File -FilePath '$outFile' -Encoding utf8 -Append
'=== EXIT_CODE: ' + `$exitCode + ' ===' | Out-File -FilePath '$outFile' -Encoding utf8 -Append
'=== FINISHED_AT: ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + ' ===' | Out-File -FilePath '$outFile' -Encoding utf8 -Append

# Check executable
`$exePath = Join-Path '$targetDir' 'release\voxc.exe'
if (Test-Path `$exePath) {
    '=== EXE_PRODUCED: YES ===' | Out-File -FilePath '$outFile' -Encoding utf8 -Append
    '=== EXE_SIZE: ' + (Get-Item `$exePath).Length + ' bytes ===' | Out-File -FilePath '$outFile' -Encoding utf8 -Append
} else {
    '=== EXE_PRODUCED: NO ===' | Out-File -FilePath '$outFile' -Encoding utf8 -Append
}

# Write done marker
'BUILD_DONE' | Out-File -FilePath '$doneMarker' -Encoding utf8
"@

$innerScriptFile = Join-Path $PSScriptRoot "inner_build.ps1"
$innerScript | Out-File -FilePath $innerScriptFile -Encoding utf8

Write-Host "Launching independent PowerShell process to run cargo build..."
Write-Host "Target dir: $targetDir"
Write-Host "Output file: $outFile"
Write-Host "Done marker: $doneMarker"

# Launch independent process (detached, hidden window)
Start-Process powershell -ArgumentList "-ExecutionPolicy Bypass -File `"$innerScriptFile`"" -WindowStyle Hidden

Write-Host "Independent process launched. Check $doneMarker for completion."
Write-Host "You can poll the file with: Test-Path $doneMarker"
