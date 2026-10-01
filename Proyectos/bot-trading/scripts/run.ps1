# Atajo en Windows: .\scripts\run.ps1 [comando] [opciones]  (por defecto: run)
Set-Location (Join-Path $PSScriptRoot "..")
if (-not (Test-Path .\.venv\Scripts\python.exe)) { Write-Error "Primero ejecuta scripts\install.ps1"; exit 1 }
if ($args.Count -eq 0) { $args = @("run") }
& .\.venv\Scripts\python.exe -m bot @args
exit $LASTEXITCODE
