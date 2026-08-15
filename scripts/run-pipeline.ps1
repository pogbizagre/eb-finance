# Lance le pipeline complet (extraction Shopify -> stats -> images -> stock).
# Pense pour etre appele par le Planificateur de taches Windows.
#
# Prerequis : copier env.ps1.example en env.ps1 et y renseigner vos identifiants
# (voir ce fichier pour le detail).

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$envFile = Join-Path $PSScriptRoot "env.ps1"
if (-not (Test-Path $envFile)) {
    Write-Error "env.ps1 introuvable - copiez env.ps1.example en env.ps1 et renseignez vos identifiants."
    exit 1
}
. $envFile

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
& $python (Join-Path $PSScriptRoot "src\run_pipeline.py")
exit $LASTEXITCODE
