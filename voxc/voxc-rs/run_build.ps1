$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -Path $scriptDir
Remove-Item -Path stdout.txt, stderr.txt -Force -ErrorAction SilentlyContinue
Write-Host "Starting cargo check in $scriptDir ..."
$p = Start-Process -FilePath "cargo" -ArgumentList "build","--release" -WorkingDirectory $scriptDir -NoNewWindow -Wait -PassThru -RedirectStandardOutput "stdout.txt" -RedirectStandardError "stderr.txt"
Write-Host "EXIT_CODE: $($p.ExitCode)"
Write-Host "Output written to stdout.txt and stderr.txt"
