$env:CARGO_TARGET_DIR = 'E:\IDEProjects\AI\vools\voxc\voxc-rs\target_retry_v1'
Set-Location 'E:\IDEProjects\AI\vools\voxc\voxc-rs'
$ErrorActionPreference = 'Continue'

# Run cargo check --offline (faster than build, reuses compiled deps)
"Starting cargo check --offline at (Get-Date -Format 'HH:mm:ss')"
& cargo check --release --offline *>&1 | Out-File -FilePath 'E:\IDEProjects\AI\vools\voxc\voxc-rs\check_final_out.txt' -Encoding utf8
$code = $LASTEXITCODE
"EXIT_CODE: $code" | Out-File -FilePath 'E:\IDEProjects\AI\vools\voxc\voxc-rs\check_final_out.txt' -Encoding utf8 -Append
"FINISHED_AT: (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File -FilePath 'E:\IDEProjects\AI\vools\voxc\voxc-rs\check_final_out.txt' -Encoding utf8 -Append

"DONE_CODE_$code" | Out-File -FilePath 'E:\IDEProjects\AI\vools\voxc\voxc-rs\check_final_done.txt' -Encoding utf8
