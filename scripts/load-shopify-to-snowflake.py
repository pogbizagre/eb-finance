"""
load-shopify-to-snowflake.py

À lancer après extract-orders.py et extract-products.py (ou à la suite dans
le même job planifié). Lit data/shopify_orders.csv et data/shopify_products.csv
et remplace le contenu des tables dans la base Snowflake SHOPIFY (dédiée,
séparée de la base paiements).

Comme les deux scripts d'extraction font une extraction COMPLÈTE à chaque
run, on fait un refresh complet ici aussi (overwrite=True) plutôt qu'un
MERGE incrémental. Le jour où les webhooks Shopify sont branchés, ils
pourront continuer d'alimenter ces mêmes tables via des MERGE ciblés
(ITEM_ID / VARIANT_ID sont les clés dans les deux cas), sans rien changer
au schéma.

Dépendances : pip install snowflake-connector-python[pandas]

Variables d'environnement attendues — celles-ci pointent vers la base
SHOPIFY, distincte de celles de ton pipeline paiements :
    SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PASSWORD (ou SNOWFLAKE_TOKEN
    si tu utilises un Personal Access Token / SSO), SNOWFLAKE_WAREHOUSE
    SNOWFLAKE_SHOPIFY_DATABASE   -> "SHOPIFY"
    SNOWFLAKE_SHOPIFY_SCHEMA     -> "PUBLIC"
"""

import os
import pandas as pd
import snowflake.connector
from snowflake.connector.pandas_tools import write_pandas
from utils import setup_logger, check_credentials

logger = setup_logger('load-shopify-to-snowflake', 'load-shopify-to-snowflake.log')

check_credentials()


def get_snowflake_connection():
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ.get("SNOWFLAKE_PASSWORD"),
        token=os.environ.get("SNOWFLAKE_TOKEN"),
        authenticator="oauth" if os.environ.get("SNOWFLAKE_TOKEN") else "snowflake",
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ.get("SNOWFLAKE_SHOPIFY_DATABASE", "SHOPIFY"),
        schema=os.environ.get("SNOWFLAKE_SHOPIFY_SCHEMA", "RAW"),
    )


def load_csv_to_table(conn, csv_path, table_name, date_columns=None):
    df = pd.read_csv(csv_path, parse_dates=date_columns or [])

    # write_pandas veut des noms de colonnes en MAJUSCULES pour matcher
    # les colonnes Snowflake créées par le DDL fourni (snowflake_shopify_schema.sql)
    df.columns = [c.upper() for c in df.columns]

    success, nchunks, nrows, _ = write_pandas(
        conn,
        df,
        table_name,
        auto_create_table=False,  # les tables sont déjà créées via le DDL fourni
        overwrite=True,           # refresh complet, cohérent avec l'extraction source
    )

    if not success:
        raise RuntimeError(f"Échec du chargement de {csv_path} dans {table_name}")

    logger.info(f"✅ {nrows} lignes chargées dans {table_name} depuis {csv_path}")


if __name__ == "__main__":
    conn = get_snowflake_connection()

    try:
        load_csv_to_table(
            conn,
            "data/shopify_orders.csv",
            "SHOPIFY_ORDER_LINE_ITEMS",
            date_columns=["extraction_date", "order_dt"],
        )
        load_csv_to_table(
            conn,
            "data/shopify_products.csv",
            "SHOPIFY_PRODUCT_VARIANTS",
            date_columns=["extraction_date", "product_created_at", "product_updated_at"],
        )
    finally:
        conn.close()
