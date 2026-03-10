param(
  [string]$App = "apps/spend-analytics/app.py",
  [int]$Port = 8501,
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$StreamlitArgs
)

$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
$appPath = Join-Path $repoRoot $App

if (-not (Test-Path $pythonExe)) {
  Write-Error "Project venv not found: $pythonExe`nRun 'uv sync' in $repoRoot (or create .venv) first."
  exit 1
}

if (-not (Test-Path $appPath)) {
  Write-Error "App file not found: $appPath"
  exit 1
}

& $pythonExe -c "import sys; print('Using python:', sys.executable)"

$cmd = @(
  "-m", "streamlit", "run", $appPath,
  "--server.port", "$Port"
)

if ($StreamlitArgs) {
  $cmd += $StreamlitArgs
}

& $pythonExe @cmd
