$env:CARGO_TARGET_DIR = 'E:\IDEProjects\AI\vools\voxc\voxc-rs\target_final_v1'
Set-Location 'E:\IDEProjects\AI\vools\voxc\voxc-rs'
$ErrorActionPreference = 'Continue'

# Run cargo build, redirect all output to file
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = 'cargo'
$psi.Arguments = 'build --release'
$psi.WorkingDirectory = 'E:\IDEProjects\AI\vools\voxc\voxc-rs'
$psi.UseShellExecute = $false
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.EnvironmentVariables['CARGO_TARGET_DIR'] = 'E:\IDEProjects\AI\vools\voxc\voxc-rs\target_final_v1'

$proc = New-Object System.Diagnostics.Process
$proc.StartInfo = $psi

$sbOut = New-Object System.Text.StringBuilder
$sbErr = New-Object System.Text.StringBuilder

$outAction = {
    if ($EventArgs.Data) {
        $sbOut.AppendLine($EventArgs.Data) | Out-Null
    }
}
$errAction = {
    if ($EventArgs.Data) {
        $sbErr.AppendLine($EventArgs.Data) | Out-Null
    }
}

Register-ObjectEvent -InputObject $proc -EventName 'OutputDataReceived' -Action $outAction | Out-Null
Register-ObjectEvent -InputObject $proc -EventName 'ErrorDataReceived' -Action $errAction | Out-Null

$proc.Start() | Out-Null
$proc.BeginOutputReadLine()
$proc.BeginErrorReadLine()
$proc.WaitForExit()
$exitCode = $proc.ExitCode

# Write outputs
'=== STDOUT ===' | Out-File -FilePath 'E:\IDEProjects\AI\vools\voxc\voxc-rs\build_final_out.txt' -Encoding utf8
$sbOut.ToString() | Out-File -FilePath 'E:\IDEProjects\AI\vools\voxc\voxc-rs\build_final_out.txt' -Encoding utf8 -Append
'=== STDERR ===' | Out-File -FilePath 'E:\IDEProjects\AI\vools\voxc\voxc-rs\build_final_out.txt' -Encoding utf8 -Append
$sbErr.ToString() | Out-File -FilePath 'E:\IDEProjects\AI\vools\voxc\voxc-rs\build_final_out.txt' -Encoding utf8 -Append
'=== EXIT_CODE: ' + $exitCode + ' ===' | Out-File -FilePath 'E:\IDEProjects\AI\vools\voxc\voxc-rs\build_final_out.txt' -Encoding utf8 -Append
'=== FINISHED_AT: ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + ' ===' | Out-File -FilePath 'E:\IDEProjects\AI\vools\voxc\voxc-rs\build_final_out.txt' -Encoding utf8 -Append

# Check executable
$exePath = Join-Path 'E:\IDEProjects\AI\vools\voxc\voxc-rs\target_final_v1' 'release\voxc.exe'
if (Test-Path $exePath) {
    '=== EXE_PRODUCED: YES ===' | Out-File -FilePath 'E:\IDEProjects\AI\vools\voxc\voxc-rs\build_final_out.txt' -Encoding utf8 -Append
    '=== EXE_SIZE: ' + (Get-Item $exePath).Length + ' bytes ===' | Out-File -FilePath 'E:\IDEProjects\AI\vools\voxc\voxc-rs\build_final_out.txt' -Encoding utf8 -Append
} else {
    '=== EXE_PRODUCED: NO ===' | Out-File -FilePath 'E:\IDEProjects\AI\vools\voxc\voxc-rs\build_final_out.txt' -Encoding utf8 -Append
}

# Write done marker
'BUILD_DONE' | Out-File -FilePath 'E:\IDEProjects\AI\vools\voxc\voxc-rs\build_final_done.txt' -Encoding utf8
