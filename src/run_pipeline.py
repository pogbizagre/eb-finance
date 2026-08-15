"""Orchestrateur : exécute les scripts du pipeline dans l'ordre, s'arrête au
premier échec. Pensé pour être appelé sans surveillance (Planificateur de
tâches Windows) — voir run-pipeline.ps1 à la racine du dépôt.

Ordre : extraction Shopify -> stats/calcul -> images & statut de stock.
Aucun de ces scripts n'écrit encore sur Shopify (voir architecture) ; ce
pipeline reste donc en lecture/génération seule pour l'instant.
"""

import os
import subprocess
import sys
from utils import setup_logger

logger = setup_logger('run-pipeline', 'run-pipeline.log')

PYTHON = sys.executable  # le python du venv qui exécute ce script
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

STEPS = [
    "extract-products.py",
    "extract-orders.py",
    "stats-products.py",
    "order-calculate-benefit-cost.py",
    "download-images.py",
    "update-stock-status.py",
]


def main():
    logger.info("=" * 50)
    logger.info("Démarrage du pipeline")
    logger.info("=" * 50)

    for step in STEPS:
        script_path = os.path.join(REPO_ROOT, "src", step)
        logger.info(f"▶ {step}")

        result = subprocess.run(
            [PYTHON, script_path],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            logger.info(f"❌ {step} a échoué (code {result.returncode})")
            if result.stderr:
                logger.info(result.stderr[-4000:])  # dernières lignes seulement
            logger.info("=" * 50)
            logger.info("Pipeline arrêté (échec)")
            logger.info("=" * 50)
            sys.exit(1)

        logger.info(f"✅ {step} terminé")

    logger.info("=" * 50)
    logger.info("Pipeline terminé avec succès")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
