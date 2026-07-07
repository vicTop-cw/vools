# frp 客户端 (frpc) Windows 一键部署脚本
# 用法：powershell -ExecutionPolicy Bypass -File setup_frpc.ps1 [-Version "0.67.0"] [-Dest "C:\frp"]
param(
    [string]$Version = "0.67.0",
    [string]$Dest = (Get-Location).Path
)

$ErrorActionPreference = "Stop"

# 1. 添加 Windows Defender 排除（需要管理员权限）
Write-Host "[1/4] 正在为 $Dest 添加 Windows Defender 排除 ..."
try {
    Import-Module Defender -ErrorAction Stop
    Add-MpExclusion -Path $Dest -ErrorAction Stop
    Write-Host "  OK - 排除已添加。"
} catch {
    Write-Host "  警告 - 无法添加 Defender 排除：$_"
    Write-Host "  如果 frpc.exe 被删除，请手动将 '$Dest' 添加到杀毒软件白名单。"
}

# 2. 下载
$url = "https://github.com/fatedier/frp/releases/download/v$Version/frp_${Version}_windows_amd64.zip"
$zip = Join-Path $Dest "frp.zip"
Write-Host "[2/4] 正在下载 frp v$Version ..."
Invoke-WebRequest -Uri $url -OutFile $zip
Write-Host "  OK - 下载完成。"

# 3. 解压 frpc.exe
Write-Host "[3/4] 正在解压 frpc.exe ..."
Add-Type -AssemblyName System.IO.Compression.FileSystem
$tmp = Join-Path $Dest "frp_tmp"
if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
[System.IO.Compression.ZipFile]::ExtractToDirectory($zip, $tmp)
Copy-Item (Join-Path $tmp "frp_${Version}_windows_amd64\frpc.exe") $Dest -Force
Remove-Item $zip -Force
Remove-Item $tmp -Recurse -Force
Write-Host "  OK - frpc.exe 解压完成。"

# 4. 验证
$frpc = Join-Path $Dest "frpc.exe"
if (Test-Path $frpc) {
    $size = [math]::Round((Get-Item $frpc).Length / 1MB, 1)
    Write-Host "[4/4] 成功：frpc.exe (${size}MB) 已就绪，路径 $frpc"
} else {
    Write-Host "[4/4] 失败：frpc.exe 未找到，可能被杀毒软件删除。"
    exit 1
}
