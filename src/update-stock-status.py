"""Génère le statut de stock des produits actifs.

Les pointures connues sont résumées par pointure; les autres variantes sont
résumées par titre de variante.

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


def format_variant_stock_sentence(variants_qty, generated_at=None):
    """Formate les stocks disponibles sous forme de (libellé, quantité).

    Un libellé à None représente une variante générique sans titre exploitable.
    """
    timestamp = (generated_at or datetime.now()).strftime("%d/%m/%Y à %H:%M")
    available = [
        (label, int(quantity))
        for label, quantity in variants_qty
        if int(quantity) > 0
    ]

    if not available:
        return f"Actuellement en rupture de stock. (mis à jour le {timestamp})"

    parts = []
    for label, quantity in available:
        unit = "unité" if quantity == 1 else "unités"
        if label is None:
            parts.append(f"{quantity} {unit}")
        else:
            parts.append(f"{label} ({quantity} {unit})")

    if len(parts) == 1:
        sentence = f"Disponible en {parts[0]}."
    else:
        sentence = "Disponible en " + ", ".join(parts[:-1]) + f" et {parts[-1]}."

    return f"{sentence} (mis à jour le {timestamp})"


def format_product_stock_sentence(group, is_shoe, generated_at=None):
    """Résume le stock par pointure connue ou par titre de variante."""
    variants = group[['size_standard', 'variant_title', 'variant_inventory_qty']].copy()
    variants['variant_inventory_qty'] = variants['variant_inventory_qty'].fillna(0)
    stock_items = []

    if is_shoe:
        sized_variants = variants[variants['size_standard'].notna()]
        stock_by_size = sized_variants.groupby('size_standard')['variant_inventory_qty'].sum()
        for size, quantity in stock_by_size.items():
            stock_items.append(((0, float(size)), f"pointure {size}", quantity))
        variants = variants[variants['size_standard'].isna()]

    def variant_label(title):
        if (
            pd.isna(title)
            or not str(title).strip()
            or str(title).strip().casefold() == 'default title'
        ):
            return None
        return str(title).strip()

    variants['stock_label'] = variants['variant_title'].map(variant_label)
    stock_by_variant = variants.groupby('stock_label', dropna=False)['variant_inventory_qty'].sum()
    for label, quantity in stock_by_variant.items():
        label = None if pd.isna(label) else label
        sort_label = label.casefold() if label is not None else ''
        stock_items.append(((1, sort_label), label, quantity))

    stock_items.sort(key=lambda item: item[0])
    return format_variant_stock_sentence(
        [(label, quantity) for _, label, quantity in stock_items], generated_at
    )


def main():
    logger.info("Loading products data...")
    products_df = pd.read_csv(PRODUCTS_CSV)
    logger.info(f"Loaded {len(products_df)} rows")

    products_df = add_size_standard(products_df)
    products_df = categorize_products(products_df)
    
    products_df.to_csv("data/inspect_product.csv", index=False, encoding="utf-8")

    is_active = products_df['product_status'].isin(['ACTIVE'])
    active_products_df = products_df[is_active].copy()
    logger.info(f"{len(active_products_df)} lignes de variantes actives")

    results = []
    for product_id, group in active_products_df.groupby('product_id'):
        is_shoe = group['product_category'].isin(SHOE_CATEGORIES).any()
        sentence = format_product_stock_sentence(group, is_shoe)

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
