import pandas as pd
import logging
import re
import re

# =====================
# SETUP LOGGING
# =====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('stats-products.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

logger.info("=" * 50)
logger.info("Starting stats-products script")
logger.info("=" * 50)

# =====================
# LOAD DATA
# =====================
logger.info("Loading products data...")
products_df = pd.read_csv("data/shopify_products.csv")
logger.info(f"Loaded {len(products_df)} rows")

size_mapping_dict = {
    '36': '36',
    '37': '37',
    '37 (6.5)': '37',
    '37 (7)': '37',
    '37.5': '37.5',
    '37.5 (7)': '37.5',
    '38': '38',
    '38 (8)': '38',
    '38 (7)': '38',
    '38 (7.5)': '38',
    '38.5': '38.5',
    '39': '39',
    '39 (8)': '39',
    '39 (9)': '39',
    '39 (8.5)': '39',
    '39 / Noir': '39',
    '39 / brun': '39',
    '40': '40',
    '40 (9)': '40',
    '40 / Noir': '40',
    '40 / brun': '40',
    '40.5': '40.5',
    '41': '41',
    '41 (10)': '41',
    '41 (11)': '41',
    '41 / Noir': '41',
    '41 / brun': '41',
    '42': '42',
    '42 (11)': '42',
    '42 / Noir': '42',
    '42 / brun': '42',
    '42.5': '42.5',
    '42.5 (11)': '42.5',
    '43': '43',
    '43 (12)': '43'
}

logger.info("Creating size_standard column...")
products_df['size_standard'] = products_df['variant_title'].map(size_mapping_dict)

logger.info("Cleaning product tags...")

def remove_arrivage_tags(tags_str):
    if pd.isna(tags_str):
        return tags_str
    tags = tags_str.split(',')
    filtered_tags = [tag.strip() for tag in tags if not re.match(r'arrivage_\d{4}[-_]\d{2}', tag.strip())]
    filtered_tags = [tag.strip() for tag in filtered_tags if not re.match(r'liquidation_\d{4}[-_]\d{2}', tag.strip())]
    filtered_tags = [tag.strip() for tag in filtered_tags if not 'commandes_personalisées' in tag.strip()]
    return ', '.join(filtered_tags)

products_df['product_tags_cleaned'] = products_df['product_tags'].apply(remove_arrivage_tags)
logger.info("✅ Tags cleaned")

cond1 = (products_df['size_standard'].str.isnumeric())
cond2 = (products_df['product_status'].isin(['ACTIVE']))

logger.info("Applying filters...")
filtered_df = products_df[cond1 & cond2]
logger.info(f"Filtered to {len(filtered_df)} rows")

logger.info("Grouping by size...")
stats_by_size = filtered_df.groupby('size_standard').agg({
    'variant_inventory_qty': 'sum',
    'variant_price': 'sum',
    'variant_cost' : 'sum',
    'product_title': lambda x: ', '.join(x.unique()),
}).reset_index()
logger.info(f"Grouped into {len(stats_by_size)} size categories")

logger.info("Exporting to CSV...")
stats_by_size.to_csv("data/shoes_stats_size.csv", index=False)
logger.info("Export complete: data/shoes_stats_size.csv")
logger.info("=" * 50)
logger.info("Script finished successfully")
logger.info("=" * 50)

logger.info("Extracting unique tags...")

active_products_df = products_df[cond2] 
tags_uniques = active_products_df['product_tags_cleaned'].unique()
logger.info(f"List of available tags : {tags_uniques}")

tags_mapping = {
    'Talons moyens' : 'talons_moyens',                
    'Talons hauts' : 'talons_hauts',
    'Talons plats' : 'talons_plats', 
    'BBWorks' : 'parfums_brumes',                     
    'parfums' : 'parfums_brumes',                     
    'bijoux' : 'bijoux',        
    'maquillage' : 'maquillage',
    'Baskets, Talons plats' : 'talons_plats',
    'BASE_ET_FIXATEUR, maquillage' : 'maquillage',      
    'BLUSH, maquillage' : 'maquillage',
    'CONCEALER, maquillage' : 'maquillage',      
    'EYELINER, maquillage' : 'maquillage',
    'FARDS_PAUPIERES, maquillage' : 'maquillage',      
    'FOUNDATION, maquillage' : 'maquillage',
    'GEL_SOURCIL, maquillage' : 'maquillage',      
    'GLOSS, maquillage' : 'maquillage',
    'maquillage, MASCARA' : 'maquillage',      
    'maquillage, RAL': 'maquillage',
    'noza_shop' : 'noza_shop',
    'LWILLI' : 'lwilli',
    'sacs-a-main' : 'sacs-a-main',
}

active_products_df['product_category'] = active_products_df['product_tags_cleaned'].map(tags_mapping)
logger.info("Grouping by tags...")
stats_by_tags = active_products_df.groupby('product_category').agg({
    'variant_inventory_qty': 'sum',
    'variant_price': 'sum',
    'variant_cost' : 'sum',
    'product_title': lambda x: ', '.join(x.unique()),
}).reset_index()
logger.info(f"Grouped into {len(stats_by_tags)} size categories")

logger.info("Exporting to CSV...")
stats_by_tags.to_csv("data/shoes_stats_tags.csv", index=False)
logger.info("Export complete: data/shoes_stats_tags.csv")
logger.info("=" * 50)
logger.info("Script finished successfully")
logger.info("=" * 50)