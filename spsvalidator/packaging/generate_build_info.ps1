Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Path $PSScriptRoot -Parent
$TargetPath = Join-Path $RootDir "src\spsvalidator\build_info.py"
Set-Location $RootDir

$AppVersion = python -c "import tomllib; print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])"

@"
APP_VERSION = "$AppVersion"
BUILD_MACOS_VERSION = "development"
BUILD_PLATFORM = "Windows"
"@ | Set-Content -Path $TargetPath -Encoding UTF8