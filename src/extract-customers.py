import argparse
import pandas as pd
import os
import json
from datetime import datetime, timezone
from utils import (
    setup_logger,
    check_credentials,
    shopify_graphql,
    get_snowflake_connection,
    get_snowflake_watermark,
)

# =====================
# OPTIONS EN LIGNE DE COMMANDE
# =====================
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "--full",
    action="store_true",
    help=(
        "Ignore le watermark Snowflake et force une extraction complète des "
        "clients, sans se connecter à Snowflake du tout."
    ),
)
args = parser.parse_args()

# =====================
# SETUP DOSSIERS / LOGGING
# =====================
os.makedirs("data", exist_ok=True)
logger = setup_logger('extract-customers', 'extract-customers.log')

check_credentials()

# Horodatage unique de l'extraction, appliqué à toutes les lignes
EXTRACTION_DATE = datetime.now(timezone.utc).isoformat()

# =====================
# --full : bypass total, ni watermark ni connexion Snowflake.
# =====================
if args.full:
    WATERMARK = "1970-01-01T00:00:00Z"
    logger.info("Mode --full : extraction complète, watermark ignoré (aucune connexion Snowflake)")
else:
    _conn = get_snowflake_connection()
    try:
        WATERMARK = get_snowflake_watermark(_conn, "SHOPIFY_CUSTOMERS", "CUSTOMER_UPDATED_AT")
    finally:
        _conn.close()
    logger.info(f"Watermark de départ : {WATERMARK}")

CUSTOMERS_FILTER = f"updated_at:>='{WATERMARK}'"

# =====================
# FETCH CLIENTS (créées ou modifiées depuis le watermark), AVEC PAGINATION
# =====================
all_customers = []
has_next_page = True
after_cursor = None

while has_next_page:
    query = f"""{{
      customers(first: 250, after: {f'"{after_cursor}"' if after_cursor else 'null'}, query: "{CUSTOMERS_FILTER}") {{
        edges {{
          node {{
            id firstName lastName email phone createdAt updatedAt numberOfOrders
            defaultAddress {{ city country }}
            }}
          }}
      pageInfo {{ hasNextPage endCursor }}
      }}
    }}
    """

    response = shopify_graphql(query)

    data = response.json()

    if "errors" in data:
        logger.info(f"❌ Erreur GraphQL: {data['errors']}")
        break

    customers_data = data["data"]["customers"]
    all_customers.extend(customers_data["edges"])

    has_next_page = customers_data["pageInfo"]["hasNextPage"]
    after_cursor = customers_data["pageInfo"]["endCursor"]

    logger.info(f"Récupéré {len(all_customers)} clients...")

# Save raw JSON data (uniquement les clients touchées par ce run incrémental)
with open("data/shopify_customers_raw.json", "w", encoding="utf-8") as f:
    json.dump({"customers": all_customers}, f, indent=2, ensure_ascii=False)

# =====================
# TRANSFORMATION
# =====================
customers = []

for edge in all_customers:
    customer = edge["node"]
    
    customer_id = customer["id"].split('/')[-1] if customer else None
    address = customer.get("defaultAddress") or {}
    customer_city = address.get("city")
    customer_country = address.get("country")

    customers.append({
        "extraction_date": EXTRACTION_DATE,
        "customer_id": customer_id,
        "first_name": customer["firstName"],
        "last_name": customer["lastName"],
        "email": customer["email"],
        "phone": customer["phone"],
        "customer_created_dt" : customer['createdAt'],
        "customer_updated_at": customer["updatedAt"], 
        "customer_nb_orders" : int(customer["numberOfOrders"]),
        "customer_city" : customer_city,
        "customer_country" : customer_country,
    })

df = pd.DataFrame(customers)

# =====================
# EXPORT
# =====================
df.to_csv("data/shopify_customers.csv", index=False, encoding="utf-8")

logger.info(f"✅ Export terminé : shopify_customers.csv ({len(df)} lignes, depuis {WATERMARK})")