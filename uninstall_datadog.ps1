# Stop and remove the Datadog service if it exists
if (Get-Service -Name "datadogagent" -ErrorAction SilentlyContinue) {
    Stop-Service -Name "datadogagent" -Force -ErrorAction SilentlyContinue
    sc.exe delete "datadogagent" | Out-Null
    Write-Host "Stopped and deleted service datadogagent"
}

# Uninstall via MSI product codes
Get-WmiObject -Class Win32_Product |
  Where-Object { $_.Name -like "Datadog*" } |
  ForEach-Object {
    $code = $_.IdentifyingNumber
    Write-Host "Uninstalling $($_.Name) ($code)…"
    Start-Process msiexec.exe -ArgumentList "/x $code /qn /norestart" -Wait
  }

# Remove leftover directories
$paths = @(
  "C:\Program Files\Datadog",
  "C:\ProgramData\Datadog",
  "C:\ProgramData\Amazon\SSM\InstanceData\*\document\orchestration\*\awsrunPowerShellScript"
)
foreach ($p in $paths) {
  if (Test-Path $p) {
    Remove-Item -Path $p -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "Removed $p"
  }
}

# (Optional) Remove any leftover logs or temp folders
Remove-Item -Path "C:\Temp\datadog" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "C:\Windows\Temp\datadog_*" -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "Datadog uninstallation complete. You can now rerun the automation."
