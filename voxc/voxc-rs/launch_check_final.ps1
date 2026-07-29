# Final verification using cargo check --offline (reuse compiled deps)
$targetDir = Join-Path $PSScriptRoot "target_retry_v1"
$env:CARGO_TARGET_DIR = $targetDir

$outFile = Join-Path $PSScriptRoot "check_final_out.txt"
$doneMarker = Join-Path $PSScriptRoot "check_final_done.txt"
Remove-Item -Force $outFile, $doneMarker -ErrorAction SilentlyContinue
Remove-Item -Force (Join-Path $targetDir "release\.cargo-*") -ErrorAction SilentlyContinue

# Inner script
$innerScript = @"
`$env:CARGO_TARGET_DIR = '$targetDir'
Set-Location '$PSScriptRoot'
`$ErrorActionPreference = 'Continue'

# Run cargo check --offline (faster than build, reuses compiled deps)
"Starting cargo check --offline at (Get-Date -Format 'HH:mm:ss')"
& cargo check --release --offline *>&1 | Out-File -FilePath '$outFile' -Encoding utf8
`$code = `$LASTEXITCODE
"EXIT_CODE: `$code" | Out-File -FilePath '$outFile' -Encoding utf8 -Append
"FINISHED_AT: (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File -FilePath '$outFile' -Encoding utf8 -Append

"DONE_CODE_`$code" | Out-File -FilePath '$doneMarker' -Encoding utf8
"@

$innerScriptFile = Join-Path $PSScriptRoot "inner_check_final.ps1"
$innerScript | Out-File -FilePath $innerScriptFile -Encoding utf8

Write-Host "Launching cargo check --offline..."
Start-Process powershell -ArgumentList "-ExecutionPolicy Bypass -File `"$innerScriptFile`"" -WindowStyle Hidden
Write-Host "Process launched. Check $doneMarker for completion."
