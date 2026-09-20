"""Publie la phrase de stock (generee par update-stock-status.py) dans le champ
description Shopify de chaque produit, SANS ecraser le reste de la description.

Comment ca marche : la description Shopify est decoupee en deux zones grace a
des marqueurs HTML invisibles sur la fiche produit :

    <!-- STOCK:START -->
    <p>Disponible en pointure 38 (1 unite)...</p>
    <!-- STOCK:END -->
    ... tout le reste de la description (texte marketing, etc.) ...

Ce script ne touche JAMAIS a ce qui est en dehors de ces marqueurs. A chaque
execution, il retrouve ce bloc (ou l'ajoute s'il n'existe pas encore) et le
remplace par la phrase de stock la plus recente.

Necessite le scope Shopify 'write_products' (Dev Dashboard de l'app).

Usage :
    python src/publish-stock-status.py --dry-run       # simulation, aucune ecriture
    python src/publish-stock-status.py --limit 3        # teste sur 3 produits seulement
    python src/publish-stock-status.py                  # publication reelle, tous les produits
"""

import argparse
import re

import pandas as pd
from utils import setup_logger, check_credentials, shopify_graphql

# =====================
# CONFIG
# =====================
# Fichier d'entree : genere par update-stock-status.py (une ligne par produit chaussure)
PREVIEW_CSV = "data/stock_status_preview.csv"
# Trace de chaque description remplacee (avant/apres), pour pouvoir revenir en
# arriere manuellement si un texte publie ne convient pas.
BACKUP_CSV = "data/stock_status_publish_log.csv"

# Marqueurs qui delimitent la section geree par CE script dans la description.
# Tout ce qui est en dehors de ces deux lignes n'est jamais lu ni modifie.
STOCK_START = "<!-- STOCK:START -->"
STOCK_END = "<!-- STOCK:END -->"

logger = setup_logger('publish-stock-status', 'publish-stock-status.log')


# =====================
# REQUETES GRAPHQL (lecture puis ecriture)
# =====================
# 1) Lire la description actuelle du produit, pour ne pas ecraser ce qu'il y a autour.
GET_DESCRIPTION_QUERY = """
query GetDescription($id: ID!) {
  product(id: $id) {
    descriptionHtml
  }
}
"""

# 2) Ecrire la nouvelle description (mutation = requete qui modifie des donnees sur Shopify).
UPDATE_DESCRIPTION_MUTATION = """
mutation UpdateDescription($id: ID!, $descriptionHtml: String!) {
  productUpdate(input: { id: $id, descriptionHtml: $descriptionHtml }) {
    product { id }
    userErrors { field message }
  }
}
"""


def fetch_current_description(product_gid):
    """Va chercher la description HTML actuelle du produit sur Shopify."""
    response = shopify_graphql(GET_DESCRIPTION_QUERY, variables={"id": product_gid})
    data = response.json()

    if "errors" in data or not data.get("data", {}).get("product"):
        raise RuntimeError(f"Lecture de la description impossible: {data.get('errors', data)}")

    # descriptionHtml peut etre None si le produit n'a jamais eu de description.
    return data["data"]["product"]["descriptionHtml"] or ""


def build_new_description(current_description, stock_sentence):
    """Insere ou remplace UNIQUEMENT le bloc de stock dans la description
    existante. Le reste de la description (ecrit a la main, ou par un futur
    script de description IA) est recopie tel quel."""
    new_block = f"{STOCK_START}\n<p>{stock_sentence}</p>\n{STOCK_END}"

    block_already_present = STOCK_START in current_description and STOCK_END in current_description

    if block_already_present:
        # Un bloc de stock existe deja (ecriture precedente) -> on remplace
        # juste ce morceau-la, rien d'autre.
        pattern = re.compile(re.escape(STOCK_START) + r".*?" + re.escape(STOCK_END), re.DOTALL)
        return pattern.sub(new_block, current_description)

    # Premiere fois pour ce produit -> on ajoute le bloc a la fin, sans
    # toucher a ce qui existait avant.
    separator = "\n" if current_description.strip() else ""
    return current_description + separator + new_block


def publish_description(product_gid, new_description):
    """Ecrit reellement la nouvelle description sur Shopify."""
    response = shopify_graphql(
        UPDATE_DESCRIPTION_MUTATION,
        variables={"id": product_gid, "descriptionHtml": new_description},
    )
    data = response.json()

    if "errors" in data:
        raise RuntimeError(f"Erreur GraphQL: {data['errors']}")

    # Shopify peut repondre 200 OK mais quand meme refuser la modification
    # (ex: scope manquant, produit verrouille) -> ca remonte ici, pas dans "errors".
    user_errors = data["data"]["productUpdate"]["userErrors"]
    if user_errors:
        raise RuntimeError(f"Shopify a refuse la mise a jour: {user_errors}")


def main():
    # =====================
    # OPTIONS EN LIGNE DE COMMANDE
    # =====================
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Montre ce qui changerait, n'ecrit rien sur Shopify")
    parser.add_argument("--limit", type=int, default=None, help="Ne traiter que les N premiers produits (pour tester)")
    args = parser.parse_args()

    check_credentials()

    # =====================
    # CHARGEMENT DE L'APERCU DE STOCK
    # =====================
    logger.info("Chargement de l'apercu de stock...")
    preview_df = pd.read_csv(PREVIEW_CSV)
    if args.limit:
        preview_df = preview_df.head(args.limit)
    logger.info(f"{len(preview_df)} produits a traiter" + (" (mode dry-run)" if args.dry_run else ""))

    # =====================
    # TRAITEMENT PRODUIT PAR PRODUIT
    # =====================
    # Un echec sur un produit est journalise puis on passe au suivant — un
    # seul produit en erreur ne doit pas bloquer tout le lot.
    backup_rows = []
    counts = {"updated": 0, "unchanged": 0, "failed": 0}

    for _, row in preview_df.iterrows():
        product_id = row["product_id"]
        product_gid = f"gid://shopify/Product/{product_id}"
        stock_sentence = row["stock_sentence"]

        try:
            current_description = fetch_current_description(product_gid)
            new_description = build_new_description(current_description, stock_sentence)

            if new_description == current_description:
                logger.info(f"= {row['product_title']}: deja a jour, rien a faire")
                counts["unchanged"] += 1
                continue

            # Garde une trace de l'ancienne ET de la nouvelle description
            # avant l'ecrasement, pour permettre un retour en arriere manuel.
            backup_rows.append({
                "product_id": product_id,
                "product_title": row["product_title"],
                "previous_description": current_description,
                "new_description": new_description,
            })

            if args.dry_run:
                logger.info(f"[DRY-RUN] {row['product_title']}: serait mis a jour")
            else:
                publish_description(product_gid, new_description)
                logger.info(f"✅ {row['product_title']}: description mise a jour")

            counts["updated"] += 1

        except Exception as e:
            logger.info(f"❌ {row['product_title']} ({product_id}): {e}")
            counts["failed"] += 1

    # =====================
    # TRACABILITE + RESUME FINAL
    # =====================
    if backup_rows:
        pd.DataFrame(backup_rows).to_csv(BACKUP_CSV, index=False, encoding="utf-8")
        logger.info(f"Trace des descriptions remplacees -> {BACKUP_CSV}")

    summary = (
        f"mises a jour: {counts['updated']}, "
        f"deja a jour: {counts['unchanged']}, "
        f"echecs: {counts['failed']}"
    )
    logger.info(f"Termine — {summary}")
    print(summary)


if __name__ == "__main__":
    main()
