<#
.SYNOPSIS
  CJK-safe pipeline runner.

.DESCRIPTION
  GNU make.exe (the ezwinports MinGW build) on a Big5 / cp950 Windows mangles
  non-ASCII characters in both its argv and the environment block it hands to
  child processes. Microsoft Teams names its transcript exports in Chinese
  (e.g. "...會議錄製.vtt"), so those paths cannot survive `make run`.

  This wrapper bypasses make.exe entirely: PowerShell passes UTF-16 argv
  straight to python, which decodes it correctly. It is the equivalent of
  `make run` for any transcript whose path contains non-ASCII characters.

  For ASCII-only paths either tool works; `make run SRC=... NAME=...` is fine.

.PARAMETER Src
  Path to the transcript (.txt Android recorder, or .vtt Teams export).

.PARAMETER Name
  Output folder name under out\. Optional; defaults to the SRC basename.

.PARAMETER Model
  Override the LLM for this run only (e.g. claude-opus-4-7, gpt-latest).
  Defaults to the .env value (medium, on-prem). Use a cloud model for
  non-confidential meetings where quality matters more than privacy.

.EXAMPLE
  .\run.ps1 "src\20260526_..._驗證狀況了解\I2S FPGA ...會議錄製.vtt" I2S_FPGA_20260526

.EXAMPLE
  .\run.ps1 "src\meeting.vtt" debug_mtg claude-opus-4-7
#>
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Src,

    [Parameter(Position = 1)]
    [string]$Name = "",

    [Parameter(Position = 2)]
    [string]$Model = ""
)

$ErrorActionPreference = "Stop"

$py     = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$helper = Join-Path $PSScriptRoot "scripts\_make_run.py"

if (-not (Test-Path $py)) {
    Write-Error "python venv not found at $py — run 'make install' first."
    exit 1
}

# _make_run.py takes positional FILE [NAME] [MODEL]; pass only what's set so
# empty trailing args don't shadow a later positional.
$callArgs = @($helper, $Src)
if ($Name)  { $callArgs += $Name }
if ($Model) { $callArgs += "MODEL=$Model" }   # KEY= form: unambiguous if NAME omitted
& $py @callArgs
exit $LASTEXITCODE
