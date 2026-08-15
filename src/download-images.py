"""Télécharge la première image de chaque chaussure active dans data/product_images/,
nommée par product_id (ex: 7657701244970.png) — utilisé plus tard par
generate-ai-description.py pour faire correspondre une image à un produit Shopify.

Suppose que data/shopify_products.csv est à jour et contient product_image_url
(voir extract-products.py). À exécuter depuis la racine du dépôt.

Idempotent : une image déjà téléchargée est ignorée, sauf avec --force.
"""

import argparse
import os
from urllib.parse import urlparse

import pandas as pd
import requests
from utils import setup_logger, categorize_products, SHOE_CATEGORIES

PRODUCTS_CSV = "data/shopify_products.csv"
IMAGES_DIR = "data/product_images"
REQUEST_TIMEOUT = 30

logger = setup_logger('download-images', 'download-images.log')


def guess_extension(url):
    path = urlparse(url).path
    ext = os.path.splitext(path)[1].lower()
    return ext if ext else ".jpg"


def download_one(session, product_id, url, force=False):
    filename = f"{product_id}{guess_extension(url)}"
    dest = os.path.join(IMAGES_DIR, filename)

    if os.path.exists(dest) and not force:
        return "skipped_exists"

    response = session.get(url, timeout=REQUEST_TIMEOUT)
    if not response.ok:
        logger.info(f"❌ {product_id}: échec téléchargement ({response.status_code}) — {url}")
        return "failed"

    with open(dest, "wb") as f:
        f.write(response.content)
    return "downloaded"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Re-télécharge même si le fichier existe déjà")
    parser.add_argument("--all-statuses", action="store_true", help="Inclure aussi les produits non ACTIVE")
    args = parser.parse_args()

    os.makedirs(IMAGES_DIR, exist_ok=True)

    logger.info("Loading products data...")
    products_df = pd.read_csv(PRODUCTS_CSV)

    products_df = products_df.drop_duplicates(subset="product_id")
    if not args.all_statuses:
        products_df = products_df[products_df["product_status"].isin(["ACTIVE", "DRAFT"])]

    products_df = categorize_products(products_df)
    is_shoe = products_df['product_category'].isin(SHOE_CATEGORIES)
    products_df = products_df[is_shoe]

    total = len(products_df)
    missing_image = products_df["product_image_url"].isna().sum()
    logger.info(f"{total} produits à traiter ({missing_image} sans image)")

    session = requests.Session()
    counts = {"downloaded": 0, "skipped_exists": 0, "skipped_no_image": 0, "failed": 0}

    for _, row in products_df.iterrows():
        product_id = row["product_id"]
        url = row["product_image_url"]

        if pd.isna(url):
            counts["skipped_no_image"] += 1
            continue

        result = download_one(session, product_id, url, force=args.force)
        counts[result] += 1

    logger.info(
        f"✅ Terminé — téléchargées: {counts['downloaded']}, "
        f"déjà présentes: {counts['skipped_exists']}, "
        f"sans image: {counts['skipped_no_image']}, "
        f"échecs: {counts['failed']}"
    )
    logger.info(
        f"Téléchargées: {counts['downloaded']} | "
        f"Déjà présentes: {counts['skipped_exists']} | "
        f"Sans image: {counts['skipped_no_image']} | "
        f"Échecs: {counts['failed']}"
    )


if __name__ == "__main__":
    main()
