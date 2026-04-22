# TalosOS Windows installer — experimental.
#
# Native Windows support in TalosOS is experimental. For the smoothest ride
# we recommend WSL2 with Ubuntu 22.04/24.04 and the Linux installer. This
# script builds the C++ side against MSVC/MinGW; the Python CLI and runtime
# bindings still assume a POSIX-ish shell to source setup scripts, so you
# will probably want WSL for day-to-day use.
#
# Usage (elevated or per-user prefix):
#   pwsh .\scripts\install.ps1
#   pwsh .\scripts\install.ps1 -Prefix C:\talosos
#   pwsh .\scripts\install.ps1 -Prefix $env:USERPROFILE\talosos -Jobs 8

[CmdletBinding()]
param(
  [string]$Prefix = "C:\talosos",
  [int]$Jobs = [Environment]::ProcessorCount,
  [string]$BuildType = "Release",
  [string]$BuildDir = "build-win"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

Write-Host "TalosOS install (Windows, experimental)"
Write-Host "  repo:       $repoRoot"
Write-Host "  prefix:     $Prefix"
Write-Host "  jobs:       $Jobs"
Write-Host "  build type: $BuildType"
Write-Host ""

# --- Dependency check ---
foreach ($cmd in @("cmake", "cargo", "python")) {
  if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
    Write-Error "$cmd not on PATH. Install Visual Studio C++ build tools, CMake 3.16+, Rust toolchain, and Python 3.7+."
    exit 1
  }
}

Write-Host "[1/3] configuring…"
cmake -S $repoRoot -B $BuildDir `
      -DCMAKE_BUILD_TYPE="$BuildType" `
      -DCMAKE_INSTALL_PREFIX="$Prefix"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[2/3] building (jobs=$Jobs)…"
cmake --build $BuildDir --config $BuildType -j $Jobs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[3/3] installing to $Prefix…"
cmake --install $BuildDir --config $BuildType
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

@"

Done. To use TalosOS from a new PowerShell window:

  `$env:Path = "$Prefix\bin;`$env:Path"
  `$env:CMAKE_PREFIX_PATH = "$Prefix;`$env:CMAKE_PREFIX_PATH"
  `$env:PYTHONPATH = "$Prefix\lib\site-packages;`$env:PYTHONPATH"

Or run:
  . $Prefix\setup.ps1   # if present

NOTE: Windows native Path is experimental — some CLI features (launch /
plot / viz / rqt) are tested primarily on Linux/macOS. For production use,
WSL2 + Ubuntu is strongly recommended.
"@ | Write-Host
