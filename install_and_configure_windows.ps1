<#
.SYNOPSIS
  Install, update or uninstall the Datadog Agent on Windows.
.PARAMETER ConfigTask
  “install”, “update” or “uninstall”
.PARAMETER AgentConfigParam
  The name of the SSM Parameter containing your agent-config.yaml
.PARAMETER S3Path
  The S3 URI (s3://…) where your artifacts live
#>
param(
  [Parameter(Mandatory=$true)]
  [ValidateSet('install','update','uninstall')]
  [string]$ConfigTask,

  [Parameter(Mandatory=$true)]
  [string]$AgentConfigParam,

  [Parameter(Mandatory=$true)]
  [string]$S3Path
)

Write-Host "→ ConfigTask       = $ConfigTask"
Write-Host "→ AgentConfigParam = $AgentConfigParam"
Write-Host "→ S3Path           = $S3Path"

New-Item -ItemType Directory -Path C:\Temp\datadog -Force | Out-Null
Set-Location C:\Temp\datadog
$ProgressPreference = 'SilentlyContinue'

# Fetch artifacts from S3
aws s3 cp "$S3Path/datadog-agent-7-latest.amd64.msi" .
aws s3 cp "$S3Path/datadog-secret-backend-windows.zip" .
aws s3 cp "$S3Path/configure_host.py" .

if ($ConfigTask -in @('install','update')) {
  Write-Host "Installing/updating Datadog Agent..."
  Start-Process msiexec.exe -ArgumentList '/i datadog-agent-7-latest.amd64.msi /qn' -Wait -NoNewWindow

  $python = 'C:\Program Files\Datadog\Datadog Agent\embedded3\python.exe'
  if (-Not (Test-Path $python)) {
    Write-Error "❌ Python not found at $python"
    exit 1
  }

  & $python configure_host.py `
    --config $AgentConfigParam `
    --secrets_backend datadog-secret-backend-windows.zip `
    --action $ConfigTask

} elseif ($ConfigTask -eq 'uninstall') {
  Write-Host "Uninstalling Datadog Agent..."
  $pkg = Get-WmiObject -Class Win32_Product | Where-Object { $_.Name -like 'Datadog Agent*' }
  if ($pkg) {
    Start-Process msiexec.exe -ArgumentList "/x $($pkg.IdentifyingNumber) /qn" -Wait -NoNewWindow
  } else {
    Write-Host "Datadog Agent not installed."
  }
} else {
  Write-Error "❌ Unknown action: $ConfigTask"
  exit 1
}

Write-Host "✅ Done."
