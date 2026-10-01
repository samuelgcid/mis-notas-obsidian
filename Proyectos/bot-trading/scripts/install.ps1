# Instalación local en Windows (PowerShell):
#   powershell -ExecutionPolicy Bypass -File scripts\install.ps1
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$py = Get-Command py -ErrorAction SilentlyContinue
if ($py) { $python = "py"; $pyArgs = @("-3") } else { $python = "python"; $pyArgs = @() }
& $python @pyArgs -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if ($LASTEXITCODE -ne 0) { Write-Error "Hace falta Python 3.10 o superior (https://www.python.org/downloads/)"; exit 1 }

Write-Host "-> Creando entorno virtual en .venv"
& $python @pyArgs -m venv .venv
$venvPy = ".\.venv\Scripts\python.exe"
& $venvPy -m pip install -q --upgrade pip
Write-Host "-> Instalando dependencias"
& $venvPy -m pip install -q -r requirements-dev.txt
Write-Host "-> Ejecutando tests"
& $venvPy -m pytest -q
if ($LASTEXITCODE -ne 0) { Write-Error "Los tests fallan"; exit 1 }

New-Item -ItemType Directory -Force -Path data | Out-Null
if (-not (Test-Path config.yaml)) {
  Write-Host "-> No hay config.yaml: lanzo el asistente"
  & $venvPy -m bot setup
}
Write-Host "-> Comprobación previa"
& $venvPy -m bot check

Write-Host ""
Write-Host "Instalación terminada. Comandos útiles:"
Write-Host "  .\scripts\run.ps1            # arrancar el bot"
Write-Host "  .\scripts\run.ps1 status     # ver estado"
