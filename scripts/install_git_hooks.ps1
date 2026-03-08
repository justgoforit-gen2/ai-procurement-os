param(
  [string]$RepoRoot = (Resolve-Path "$PSScriptRoot\.." | Select-Object -ExpandProperty Path)
)

$ErrorActionPreference = 'Stop'

$gitDir = Join-Path $RepoRoot '.git'
if (-not (Test-Path $gitDir)) {
  throw "Not a git repository: $RepoRoot"
}

$src = Join-Path $RepoRoot 'githooks\pre-push'
if (-not (Test-Path $src)) {
  throw "Hook source not found: $src"
}

$dstDir = Join-Path $RepoRoot '.git\hooks'
$dst = Join-Path $dstDir 'pre-push'

New-Item -ItemType Directory -Force -Path $dstDir | Out-Null
Copy-Item -Force -Path $src -Destination $dst

Write-Host "Installed pre-push hook to: $dst"
Write-Host "Note: Git hooks are local-only and are not pushed to GitHub."
