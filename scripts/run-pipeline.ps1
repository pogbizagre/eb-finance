# Lance le pipeline complet (extraction Shopify -> stats -> images -> stock).
# Pense pour etre appele par le Planificateur de taches Windows.
#
# Prerequis : copier env.ps1.example en env.ps1 et y renseigner vos identifiants
# (voir ce fichier pour le detail).
#
# Tout est journalise dans logs\run-pipeline-wrapper.log, y compris les echecs
# qui se produisent AVANT que python ne demarre (env.ps1 manquant, chemin
# invalide...) — le Planificateur de taches ne capture rien de tout ca par
# defaut, d'ou ce fichier dedie.

Set-Location $PSScriptRoot

$logDir = Join-Path $PSScriptRoot "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir "run-pipeline-wrapper.log"

function Write-Log($message) {
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') - $message" | Out-File -FilePath $logFile -Append -Encoding utf8
}

Write-Log "Demarrage du wrapper"

try {
    $envFile = Join-Path $PSScriptRoot "env.ps1"
    if (-not (Test-Path $envFile)) {
        Write-Log "ERREUR: env.ps1 introuvable - copiez env.ps1.example en env.ps1"
        exit 1
    }
    . $envFile

    $python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $python)) {
        Write-Log "ERREUR: python introuvable a $python"
        exit 1
    }

    & $python (Join-Path $PSScriptRoot "src\run_pipeline.py") *>> $logFile
    $exitCode = $LASTEXITCODE

    Write-Log "Fin du wrapper, code de sortie $exitCode"
    exit $exitCode
} catch {
    Write-Log "EXCEPTION: $($_.Exception.Message)"
    exit 1
}
