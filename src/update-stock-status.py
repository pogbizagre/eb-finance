"""Génère le statut de stock des produits actifs.

Les chaussures sont résumées par pointure; les autres produits par quantité.

Étape 1 seulement : produit un fichier d'aperçu à relire manuellement.
Aucune écriture sur Shopify ici — ça viendra dans une étape suivante, une fois
le texte généré validé (voir architecture convenue : bloc <!-- STOCK:START/END -->
inséré dans la description existante, sans toucher au reste).

Suppose que data/shopify_products.csv est à jour (lancer extract-products.py
avant, si besoin). À exécuter depuis la racine du dépôt.
"""

from datetime import datetime

import pandas as pd
from utils import setup_logger, add_size_standard, categorize_products, SHOE_CATEGORIES

PRODUCTS_CSV = "data/shopify_products.csv"
OUTPUT_CSV = "data/stock_status_preview.csv"

logger = setup_logger('update-stock-status', 'update-stock-status.log')


def format_stock_sentence(sizes_qty, generated_at=None):
    """sizes_qty : liste de (size_standard, qty) triée par pointure, qty > 0 uniquement.
    generated_at : datetime à utiliser comme horodatage (par défaut : maintenant)."""
    timestamp = (generated_at or datetime.now()).strftime("%d/%m/%Y à %H:%M")

    if not sizes_qty:
        return f"Actuellement en rupture de stock. (mis à jour le {timestamp})"

    parts = [
        f"pointure {size} ({int(qty)} unité{'s' if qty > 1 else ''})"
        for size, qty in sizes_qty
    ]

    if len(parts) == 1:
        sentence = f"Disponible en {parts[0]}."
    else:
        sentence = "Disponible en " + ", ".join(parts[:-1]) + f" et {parts[-1]}."

    return f"{sentence} (mis à jour le {timestamp})"


def format_quantity_sentence(quantity, generated_at=None):
    """Formate le stock total d'un produit qui n'est pas une chaussure."""
    timestamp = (generated_at or datetime.now()).strftime("%d/%m/%Y à %H:%M")
    quantity = int(quantity)

    if quantity <= 0:
        return f"Actuellement en rupture de stock. (mis à jour le {timestamp})"

    unit = "unité" if quantity == 1 else "unités"
    return f"Disponible en {quantity} {unit}. (mis à jour le {timestamp})"


def main():
    logger.info("Loading products data...")
    products_df = pd.read_csv(PRODUCTS_CSV)
    logger.info(f"Loaded {len(products_df)} rows")

    products_df = add_size_standard(products_df)
    products_df = categorize_products(products_df)
    
    products_df.to_csv("data/inspect_product.csv", index=False, encoding="utf-8")

    is_active = products_df['product_status'].isin(['ACTIVE'])
    is_shoe = products_df['product_category'].isin(SHOE_CATEGORIES)
    has_size = products_df['size_standard'].notna()
    active_products_df = products_df[is_active].copy()
    shoes_df = active_products_df[is_shoe & has_size].copy()
    other_products_df = active_products_df[~is_shoe].copy()
    logger.info(f"{len(shoes_df)} lignes de variantes chaussures actives")
    logger.info(f"{len(other_products_df)} lignes de variantes d'autres produits actifs")

    shoes_df['variant_inventory_qty'] = shoes_df['variant_inventory_qty'].fillna(0)
    other_products_df['variant_inventory_qty'] = other_products_df['variant_inventory_qty'].fillna(0)

    results = []
    for product_id, group in shoes_df.groupby('product_id'):
        stock_by_size = (
            group.groupby('size_standard')['variant_inventory_qty']
            .sum()
            .reset_index()
        )
        # stock_by_size.head()
        stock_by_size = stock_by_size[stock_by_size['variant_inventory_qty'] > 0]
        stock_by_size = stock_by_size.sort_values(
            by='size_standard', key=lambda col: col.astype(float)
        )

        sizes_qty = list(stock_by_size.itertuples(index=False, name=None))
        sentence = format_stock_sentence(sizes_qty)

        results.append({
            "product_id": product_id,
            "product_handle": group['product_handle'].iloc[0],
            "product_title": group['product_title'].iloc[0],
            "product_category": group['product_category'].iloc[0],
            "stock_sentence": sentence,
        })

    for product_id, group in other_products_df.groupby('product_id'):
        quantity = group['variant_inventory_qty'].sum()
        sentence = format_quantity_sentence(quantity)

        results.append({
            "product_id": product_id,
            "product_handle": group['product_handle'].iloc[0],
            "product_title": group['product_title'].iloc[0],
            "product_category": group['product_category'].iloc[0],
            "stock_sentence": sentence,
        })

    result_df = pd.DataFrame(results)
    result_df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")
    logger.info(f"✅ {len(result_df)} phrases de stock générées → {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
