"""
load-shopify-to-snowflake.py

À lancer après extract-orders.py et extract-products.py. Lit
data/shopify_orders.csv et data/shopify_products.csv (qui ne contiennent
maintenant que les lignes créées/modifiées depuis le dernier run, grâce au
watermark utilisé côté extraction) et fait un MERGE (upsert) dans les tables
Snowflake — plus d'overwrite complet, puisqu'on n'a plus l'état complet à
chaque run.

Approche : chaque CSV est d'abord chargé dans une table de staging
temporaire (write_pandas, auto_create_table=True — elle disparaît en fin de
session Snowflake), puis un MERGE INTO fusionne le staging dans la table
finale sur la clé (ITEM_ID / VARIANT_ID). Si le CSV ne contient aucune ligne
(rien de changé depuis le dernier run), l'étape est simplement sautée.

Dépendances : pip install "snowflake-connector-python[pandas]"

Variables d'environnement attendues (probablement déjà définies pour ton
pipeline paiements, sauf les deux dernières) :
    SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PASSWORD (ou SNOWFLAKE_TOKEN),
    SNOWFLAKE_WAREHOUSE
    SNOWFLAKE_SHOPIFY_DATABASE   -> "SHOPIFY"
    SNOWFLAKE_SHOPIFY_SCHEMA     -> "PUBLIC"
"""

import pandas as pd
from snowflake.connector.pandas_tools import write_pandas
from utils import (
    setup_logger,
    check_credentials,
    get_snowflake_connection,
    add_size_standard,
    categorize_products,
)

logger = setup_logger('load-shopify-to-snowflake', 'load-shopify-to-snowflake.log')

check_credentials()


def add_product_categorization(df):
    """Calcule SIZE_STANDARD et PRODUCT_CATEGORY avant le chargement, pour que
    les vues SQL Snowflake (V_PRODUCT_STATS_BY_SIZE / V_PRODUCT_STATS_BY_TAG,
    voir snowflake_shopify_views.sql) n'aient plus qu'à agréger, sans dupliquer
    la logique de mapping pointure/tags en SQL."""
    df = add_size_standard(df)
    df = categorize_products(df)
    return df.drop(columns=["product_tags_cleaned"])  # colonne intermédiaire, pas dans le schéma


def merge_csv_into_table(conn, csv_path, target_table, key_column,
                          tz_columns=None, date_only_columns=None, transform=None):
    df = pd.read_csv(csv_path)

    if df.empty:
        logger.info(f"ℹ️ {csv_path} est vide (rien de nouveau depuis le dernier run), rien à charger.")
        return

    if transform is not None:
        df = transform(df)

    # Conversion explicite plutôt que parse_dates de read_csv : ce dernier ne
    # garantit pas un dtype datetime64[ns, UTC] propre pour des colonnes avec
    # fuseau horaire (peut rester en dtype "object", que write_pandas ne sait
    # alors plus mapper correctement vers TIMESTAMP_TZ côté Snowflake).
    for col in (tz_columns or []):
        df[col] = pd.to_datetime(df[col], utc=True)

    for col in (date_only_columns or []):
        df[col] = pd.to_datetime(df[col]).dt.date

    # write_pandas veut des noms de colonnes en MAJUSCULES pour matcher les
    # colonnes Snowflake créées par le DDL fourni (snowflake_shopify_schema.sql)
    df.columns = [c.upper() for c in df.columns]

    stage_table = f"STAGE_{target_table}"

    # auto_create_table=True + overwrite=True : la table de staging est
    # entièrement jetable, recréée à chaque run avec juste les lignes de ce
    # CSV (donc les lignes changées depuis le dernier run, pas tout l'historique).
    #
    # use_logical_type=True : sans ça, write_pandas écrit les colonnes
    # datetime comme des entiers bruts (epoch en nanosecondes -> NUMBER)
    # plutôt que comme de vrais TIMESTAMP_TZ/TIMESTAMP_NTZ, ce qui fait
    # échouer le MERGE contre la table finale (colonnes incompatibles).
    success, _, nrows, _ = write_pandas(
        conn,
        df,
        stage_table,
        auto_create_table=True,
        overwrite=True,
        table_type="temporary",
        use_logical_type=True,
    )
    if not success:
        raise RuntimeError(f"Échec du chargement de {csv_path} dans la table de staging {stage_table}")

    columns = list(df.columns)
    update_columns = [c for c in columns if c != key_column]

    set_clause = ", ".join(f"target.{c} = source.{c}" for c in update_columns)
    insert_columns = ", ".join(columns)
    insert_values = ", ".join(f"source.{c}" for c in columns)

    merge_sql = f"""
        MERGE INTO {target_table} AS target
        USING {stage_table} AS source
        ON target.{key_column} = source.{key_column}
        WHEN MATCHED THEN UPDATE SET {set_clause}
        WHEN NOT MATCHED THEN INSERT ({insert_columns}) VALUES ({insert_values})
    """

    cur = conn.cursor()
    cur.execute(merge_sql)
    result = cur.fetchone()
    logger.info(f"✅ MERGE {target_table} depuis {csv_path} : {nrows} ligne(s) traitée(s) — {result}")


if __name__ == "__main__":
    conn = get_snowflake_connection()

    try:
        merge_csv_into_table(
            conn,
            "data/shopify_orders.csv",
            "SHOPIFY_ORDER_LINE_ITEMS",
            key_column="ITEM_ID",
            tz_columns=["extraction_date", "order_updated_at"],  # TIMESTAMP_TZ
            date_only_columns=["order_dt"],                      # DATE
        )
        merge_csv_into_table(
            conn,
            "data/shopify_products.csv",
            "SHOPIFY_PRODUCT_VARIANTS",
            key_column="VARIANT_ID",
            tz_columns=["extraction_date", "product_updated_at"],  # TIMESTAMP_TZ
            date_only_columns=["product_created_at"],               # DATE
            transform=add_product_categorization,
        )
    finally:
        conn.close()
