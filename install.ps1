# ============================================================================
# Miho AI Windows installer entrypoint
# ============================================================================
# Short URL entrypoint for PowerShell users:
#   irm https://raw.githubusercontent.com/etlab8320/miho-ai/main/install.ps1 | iex
#
# The full installer lives in scripts/install.ps1.  Keep this file tiny so the
# public one-liner stays stable even if the internal installer layout changes.
# ============================================================================

param(
    [switch]$NoVenv,
    [switch]$SkipSetup,
    [string]$Branch = "main",
    [string]$Commit = "",
    [string]$Tag = "",
    [string]$MihoHome = "$env:LOCALAPPDATA\miho",
    [string]$InstallDir = "$env:LOCALAPPDATA\miho\miho-agent",
    [switch]$Manifest,
    [string]$Stage,
    [switch]$ProtocolVersion,
    [switch]$NonInteractive,
    [switch]$Json,
    [string]$Ensure = "",
    [switch]$PostInstall
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$ref = $Branch
if ($Tag) { $ref = $Tag }
if ($Commit) { $ref = $Commit }

$installerUrl = "https://raw.githubusercontent.com/etlab8320/miho-ai/$ref/scripts/install.ps1"
$installerSource = Invoke-RestMethod -Uri $installerUrl
if (-not $installerSource) {
    throw "Downloaded empty installer from $installerUrl"
}

$forward = @{}
foreach ($key in $PSBoundParameters.Keys) {
    $forward[$key] = $PSBoundParameters[$key]
}

& ([scriptblock]::Create($installerSource)) @forward
