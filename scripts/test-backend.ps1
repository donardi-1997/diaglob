<#
.SYNOPSIS
  Run the backend test suite in parallel with an isolated, offline test environment.

.DESCRIPTION
  Script options use a double dash so they never collide with pytest flags
  (PowerShell would otherwise bind abbreviations such as pytest's -s or -k):

    --workers N   number of parallel processes (default 8, measured sweet spot)
    --serial      single process (debugging, pdb, -s output)
    --lint        run ruff before the tests

  Every other argument is passed unchanged to pytest.

.EXAMPLE
  pwsh -File scripts/test-backend.ps1
  pwsh -File scripts/test-backend.ps1 tests/test_whatsapp.py -k template
  pwsh -File scripts/test-backend.ps1 --workers 4 -x
  pwsh -File scripts/test-backend.ps1 --serial tests/test_whatsapp.py -s
  pwsh -File scripts/test-backend.ps1 --lint
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$workers = "8"
$serial = $false
$lint = $false
$pytestArgs = [System.Collections.Generic.List[string]]::new()

for ($i = 0; $i -lt $args.Count; $i++) {
  $arg = [string]$args[$i]
  switch ($arg) {
    "--workers" {
      if ($i + 1 -ge $args.Count) { throw "--workers needs a value (number or 'auto')." }
      $i++
      $workers = [string]$args[$i]
    }
    "--serial" { $serial = $true }
    "--lint" { $lint = $true }
    default { $pytestArgs.Add($arg) }
  }
}

$backend = Join-Path (Split-Path -Parent $PSScriptRoot) "backend"
$python = Join-Path $backend ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
  $python = Join-Path $backend ".venv/bin/python"
}
if (-not (Test-Path $python)) {
  throw "Backend virtualenv not found. Create backend/.venv and run: pip install -r requirements.txt -r requirements-dev.txt"
}

# Never touch real infrastructure from unit tests.
$env:DATABASE_URL = "sqlite:///:memory:"
$env:AWS_EC2_METADATA_DISABLED = "true"
$env:AWS_ACCESS_KEY_ID = "testing"
$env:AWS_SECRET_ACCESS_KEY = "testing"
$env:KNOWLEDGE_RECONCILE_ON_STARTUP = "false"
$env:PRODUCT_ANALYTICS_ENABLED = "false"

Push-Location $backend
try {
  if ($lint) {
    & $python -m ruff check app/ tests/ tools/
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  }

  $arguments = [System.Collections.Generic.List[string]]::new()
  $arguments.AddRange([string[]]@("-m", "pytest", "-q", "-p", "no:warnings"))
  if (-not $serial) {
    & $python -c "import xdist" 2>$null
    if ($LASTEXITCODE -ne 0) {
      throw "pytest-xdist is not installed. Run: $python -m pip install -r requirements-dev.txt (or use --serial)."
    }
    # loadfile keeps each test module on one worker in file order, so modules
    # with module-scoped fixtures behave exactly as in a serial run.
    $arguments.AddRange([string[]]@("-n", $workers, "--dist", "loadfile"))
  }
  if ($pytestArgs.Count -gt 0) {
    $arguments.AddRange($pytestArgs)
  }
  else {
    $arguments.Add("tests")
  }

  $started = Get-Date
  & $python @arguments
  $code = $LASTEXITCODE
  Write-Host ("Backend tests finished in {0:n0}s" -f ((Get-Date) - $started).TotalSeconds)
  exit $code
}
finally {
  Pop-Location
}
