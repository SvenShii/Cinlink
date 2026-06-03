param(
  [string]$Source = "git+https://github.com/SvenShii/Cinlink.git",
  [string]$ApiKey = "",
  [string]$RuntimeBase = "",
  [string]$BillingBase = "",
  [switch]$Editable,
  [switch]$NoPathUpdate
)

$ErrorActionPreference = "Stop"

function Write-Step {
  param([string]$Message)
  Write-Host "[CinLinkCLI] $Message"
}

function Get-PythonCommand {
  $py = Get-Command py -ErrorAction SilentlyContinue
  if ($py) {
    return @("py", "-3")
  }
  $python = Get-Command python -ErrorAction SilentlyContinue
  if ($python) {
    return @("python")
  }
  throw "Python was not found. Install Python 3.11+ first."
}

function Invoke-Python {
  param([string[]]$PythonCommand, [string[]]$Arguments)
  $prefixArgs = @()
  if ($PythonCommand.Length -gt 1) {
    $prefixArgs = $PythonCommand[1..($PythonCommand.Length - 1)]
  }
  & $PythonCommand[0] @prefixArgs @Arguments
}

function Add-UserPath {
  param([string]$Directory)
  if (-not (Test-Path -LiteralPath $Directory)) {
    return
  }
  $resolved = (Resolve-Path -LiteralPath $Directory).Path.TrimEnd("\")
  $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
  $parts = @()
  if ($userPath) {
    $parts = $userPath -split ";" | Where-Object { $_ -and $_.Trim() }
  }
  $alreadyPresent = $false
  foreach ($part in $parts) {
    if ($part.TrimEnd("\").Equals($resolved, [StringComparison]::OrdinalIgnoreCase)) {
      $alreadyPresent = $true
      break
    }
  }
  if (-not $alreadyPresent) {
    $newPath = if ($userPath) { "$userPath;$resolved" } else { $resolved }
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    Write-Step "Added to user PATH: $resolved"
  } else {
    Write-Step "User PATH already contains: $resolved"
  }
  $env:Path = "$env:Path;$resolved"
}

$python = Get-PythonCommand
Write-Step "Using Python: $($python -join ' ')"

Invoke-Python $python @("-m", "pip", "install", "--upgrade", "pip")

Write-Step "Removing legacy popularvideo-cli package if present"
Invoke-Python $python @("-m", "pip", "uninstall", "-y", "popularvideo-cli")

if ($Editable) {
  Write-Step "Installing editable package from current directory"
  Invoke-Python $python @("-m", "pip", "install", "-e", ".")
} else {
  Write-Step "Installing package from $Source"
  Invoke-Python $python @("-m", "pip", "install", "--upgrade", $Source)
}

$scriptsDir = (Invoke-Python $python @("-c", "import sysconfig; print(sysconfig.get_path('scripts'))")) | Select-Object -Last 1
if (-not $NoPathUpdate) {
  Add-UserPath $scriptsDir
} else {
  Write-Step "Skipping PATH update. Scripts directory: $scriptsDir"
}

if ($ApiKey) {
  $onboardingArgs = @("--json", "onboarding", "--api-key", $ApiKey)
  if ($RuntimeBase) {
    $onboardingArgs += @("--runtime-base", $RuntimeBase)
  }
  if ($BillingBase) {
    $onboardingArgs += @("--billing-base", $BillingBase)
  }
  Write-Step "Writing CinLink API configuration"
  & (Join-Path $scriptsDir "cinlink.exe") @onboardingArgs
}

Write-Step "Running doctor"
& (Join-Path $scriptsDir "cinlink.exe") --json doctor

Write-Step "Done. Restart terminals that were already open before this install if they cannot find cinlink."
