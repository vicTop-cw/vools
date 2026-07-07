param(
    [Parameter(Mandatory=$true)]
    [string]$Name
)
$value = [System.Environment]::GetEnvironmentVariable($Name, 'Process')
if ($null -eq $value) {
    $value = ""
}
Write-Output $value