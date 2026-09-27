"""Utilitaires partagés : logging, config, auth OAuth (client credentials) et
helper GraphQL Shopify.

Utilisé par tous les scripts sous src/ pour éviter de dupliquer la config du
logging, et par extract-products.py / extract-orders.py pour l'authentification
et le cache du token Shopify.
"""

import requests
import os
import re
import time
import logging
import pandas as pd
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger('shopify-client')

REQUEST_TIMEOUT = 30  # secondes


def setup_logger(name, logfile):
    """Configure le logging pour un script (fichier dans logs/, format uniforme)
    et retourne son logger. Doit être appelé avant check_credentials()/
    get_access_token() pour que leurs logs atterrissent au bon endroit."""
    os.makedirs("logs", exist_ok=True)
    logging.basicConfig(
        filename=f"logs/{logfile}",
        format='%(asctime)s %(message)s',
        filemode='w',
        level=logging.INFO,
    )
    return logging.getLogger(name)


# =====================
# CONFIG
# =====================
SHOP_NAME = os.getenv("SHOPIFY_SHOP", "epiphanieboutique")  # sans .myshopify.com
CLIENT_ID = os.getenv("SHOPIFY_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("SHOPIFY_CLIENT_SECRET", "")
API_VERSION = "2026-07"

SHOP_DOMAIN = f"{SHOP_NAME}.myshopify.com"
GRAPHQL_URL = f"https://{SHOP_DOMAIN}/admin/api/{API_VERSION}/graphql.json"
TOKEN_URL = f"https://{SHOP_DOMAIN}/admin/oauth/access_token"


def check_credentials():
    """À appeler après setup_logger(), pour que ce message atterrisse dans le
    fichier de log du script appelant plutôt que dans celui du dernier script
    qui a appelé logging.basicConfig()."""
    logger.info('Vérification des identifiants')
    if not CLIENT_ID or not CLIENT_SECRET:
        raise ValueError("SHOPIFY_CLIENT_ID / SHOPIFY_CLIENT_SECRET non définis")


# =====================
# SESSION HTTP : connexions réutilisées + retry automatique
# =====================
# Réutilise les connexions TCP/TLS entre tous les appels paginés, et relance
# automatiquement les erreurs transitoires (429/500/502/503/504) avec un
# backoff exponentiel.
_session = requests.Session()
_retry = Retry(
    total=5,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["POST"],
)
_adapter = HTTPAdapter(max_retries=_retry)
_session.mount("https://", _adapter)
_session.mount("http://", _adapter)

# =====================
# AUTH : client credentials grant (Dev Dashboard)
# =====================
_token = None
_token_expires_at = 0


def get_access_token():
    """Récupère (et met en cache) un access token via client credentials grant.
    Les tokens expirent après 24h (86399s)."""
    global _token, _token_expires_at

    if _token and time.time() < _token_expires_at - 60:
        return _token

    logger.info('Récupération du token via OAuth (client credentials)')
    response = _session.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        },
        timeout=REQUEST_TIMEOUT,
    )

    if not response.ok:
        logger.info(f"❌ Échec récupération du token: {response.status_code} {response.text}")
        raise RuntimeError(f"Token request failed: {response.status_code} {response.text}")

    payload = response.json()
    _token = payload["access_token"]
    _token_expires_at = time.time() + payload.get("expires_in", 86399)
    logger.info("✅ Token OAuth récupéré")
    return _token


def shopify_graphql(query, variables=None, max_retries=5):
    """Exécute une requête (ou mutation) GraphQL Shopify. `variables` est le
    dict standard GraphQL — à utiliser dès que la requête transporte du texte
    libre (HTML, accents, guillemets...) pour éviter tout souci d'échappement
    dans la chaîne de la requête elle-même.

    Relance automatiquement si Shopify répond avec un throttling au niveau du
    coût de la requête (HTTP 200 avec une erreur GraphQL de code THROTTLED —
    non couvert par le retry HTTP de la Session, qui ne regarde que le status
    code)."""
    headers = {
        "X-Shopify-Access-Token": get_access_token(),
        "Content-Type": "application/json",
    }

    payload = {"query": query}
    if variables is not None:
        payload["variables"] = variables

    response = None
    for attempt in range(max_retries):
        response = _session.post(
            GRAPHQL_URL, json=payload, headers=headers, timeout=REQUEST_TIMEOUT
        )

        try:
            data = response.json()
        except ValueError:
            return response  # laisse l'appelant gérer une réponse non-JSON

        errors = data.get("errors") or []
        throttled = any(
            isinstance(e, dict) and e.get("extensions", {}).get("code") == "THROTTLED"
            for e in errors
        )
        if not throttled or attempt == max_retries - 1:
            return response

        wait = 2 ** attempt
        logger.info(f"⏳ Requête limitée par Shopify (THROTTLED), nouvelle tentative dans {wait}s...")
        time.sleep(wait)

    return response


# =====================
# SNOWFLAKE : connexion + watermark (pour les extractions incrémentales)
# =====================
# Utilisé par extract-orders.py, extract-products.py et
# load-shopify-to-snowflake.py. Nécessite les variables d'environnement
# SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PASSWORD (ou SNOWFLAKE_TOKEN),
# SNOWFLAKE_WAREHOUSE, et optionnellement SNOWFLAKE_SHOPIFY_DATABASE /
# SNOWFLAKE_SHOPIFY_SCHEMA (défaut SHOPIFY.PUBLIC).

def get_snowflake_connection():
    """Ouvre une connexion à la base SHOPIFY, avec le rôle ROLE_SHOPIFY.
    Le compte de service (SVC_DATA_ENG) est partagé avec le pipeline
    paiements et a ROLE_PAIEMENTS comme rôle par défaut — on demande donc
    ROLE_SHOPIFY explicitement à la connexion, sinon on resterait sur
    ROLE_PAIEMENTS sans accès à SHOPIFY. À fermer par l'appelant
    (conn.close()) une fois le travail terminé.

    Authentification par clé privée RSA, comme le pipeline paiements
    (SNOWFLAKE_PRIVATE_KEY : le contenu de la clé privée PEM, non chiffrée,
    en variable d'environnement — pas un chemin de fichier, pour rester
    compatible avec GitHub Actions Secrets)."""
    import snowflake.connector
    from cryptography.hazmat.primitives import serialization

    private_key_pem = os.environ["SNOWFLAKE_PRIVATE_KEY"].encode()
    private_key = serialization.load_pem_private_key(private_key_pem, password=None)
    private_key_der = private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],  # SVC_DATA_ENG
        private_key=private_key_der,
        role=os.environ.get("SNOWFLAKE_ROLE", "ROLE_SHOPIFY"),
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],  # WH_DATA_ENG (partagé)
        database=os.environ.get("SNOWFLAKE_SHOPIFY_DATABASE", "SHOPIFY"),
        schema=os.environ.get("SNOWFLAKE_SHOPIFY_SCHEMA", "PUBLIC"),
    )


def get_snowflake_watermark(conn, table, column, default="1970-01-01T00:00:00Z"):
    """Retourne MAX(column) déjà chargé dans `table`, en ISO 8601 UTC, pour
    servir de point de départ à une extraction incrémentale. `conn` est une
    connexion déjà ouverte (voir get_snowflake_connection) — cette fonction
    ne l'ouvre ni ne la ferme. Retourne `default` si la table est vide,
    inexistante (premier run avant la création du schéma) ou si la requête
    échoue — dans ce dernier cas on préfère une extraction complète plutôt
    que de planter tout le run."""
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT MAX({column}) FROM {table}")
        row = cur.fetchone()
        if row and row[0] is not None:
            return row[0].isoformat()
        return default
    except Exception as e:
        logger.info(
            f"⚠️ Impossible de récupérer le watermark ({table}.{column}), "
            f"on repart de {default} (extraction complète) : {e}"
        )
        return default


def fetch_snowflake_table(conn, table):
    """Lit `table` en entier depuis Snowflake et retourne un DataFrame avec
    des noms de colonnes en minuscules (les tables sont en MAJUSCULES côté
    Snowflake — voir snowflake_shopify_schema.sql — mais tous les scripts
    d'analyse, écrits à l'origine pour les CSV d'extraction, attendent des
    colonnes en minuscules).

    Comme les tables sont maintenues par MERGE (une ligne par ITEM_ID /
    VARIANT_ID, mise à jour en place), une lecture complète donne bien l'état
    courant de toutes les commandes/tous les produits, pas seulement le delta
    du dernier run incrémental — contrairement aux CSV locaux produits par
    extract-orders.py / extract-products.py sans --full.

    `conn` est une connexion déjà ouverte (voir get_snowflake_connection) —
    cette fonction ne l'ouvre ni ne la ferme."""
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM {table}")
    df = cur.fetch_pandas_all()
    df.columns = [c.lower() for c in df.columns]
    return df


# =====================
# CATÉGORISATION PRODUITS (pointure + catégorie via tags)
# =====================
# Source unique pour stats-products.py et product-descriptions/*.py — évite que
# les deux définitions de "c'est une chaussure" divergent avec le temps.

SIZE_MAPPING = {
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
    '41.5': '41.5',
    '42': '42',
    '42 (11)': '42',
    '42 / Noir': '42',
    '42 / brun': '42',
    '42.5': '42.5',
    '42.5 (11)': '42.5',
    '43': '43',
    '43 (12)': '43',
}

TAGS_MAPPING = {
    'Talons moyens': 'talons_moyens',
    'Talons hauts': 'talons_hauts',
    'Talons plats': 'talons_plats',
    'BBWorks': 'parfums_brumes',
    'parfums': 'parfums_brumes',
    'bijoux': 'bijoux',
    'maquillage': 'maquillage',
    'Baskets, Talons plats': 'talons_plats',
    'BASE_ET_FIXATEUR, maquillage': 'maquillage',
    'BLUSH, maquillage': 'maquillage',
    'CONCEALER, maquillage': 'maquillage',
    'EYELINER, maquillage': 'maquillage',
    'FARDS_PAUPIERES, maquillage': 'maquillage',
    'FOUNDATION, maquillage': 'maquillage',
    'GEL_SOURCIL, maquillage': 'maquillage',
    'GLOSS, maquillage': 'maquillage',
    'maquillage, MASCARA': 'maquillage',
    'maquillage, RAL': 'maquillage',
    'maquillage, Rouge à lèvres': 'maquillage',
    'highlighter, maquillage': 'maquillage',
    'noza_shop': 'noza_shop',
    'LWILLI': 'lwilli',
    'sacs-a-main': 'sacs-a-main',
}

# Catégories considérées comme "chaussures" pour le résumé de stock par pointure.
SHOE_CATEGORIES = {'talons_hauts', 'talons_moyens', 'talons_plats'}

_EXCLUDED_TAG_PATTERNS = [
    re.compile(r'arrivage_\d{4}[-_]\d{2}'),
    re.compile(r'liquidation_\d{4}[-_]\d{2}'),
    re.compile(r'size-\d{2}'),
    re.compile(r'liquidation'),
    re.compile(r'nouvelle_collection'),
]


def clean_product_tags(tags_str):
    """Retire les tags techniques (arrivage_YYYY-MM, liquidation_YYYY-MM,
    size-NN, commandes_personalisées) d'une chaîne de tags Shopify séparés
    par des virgules."""
    if pd.isna(tags_str):
        return tags_str
    tags = [tag.strip() for tag in tags_str.split(',')]
    filtered_tags = [
        tag for tag in tags
        if 'commandes_personalisées' not in tag
        and not any(pattern.match(tag) for pattern in _EXCLUDED_TAG_PATTERNS)
    ]
    return ', '.join(filtered_tags)


def add_size_standard(df):
    """Retourne une copie de df avec une colonne 'size_standard' dérivée de
    'variant_title' (NaN si variant_title ne correspond à aucune pointure connue)."""
    df = df.copy()
    df['size_standard'] = df['variant_title'].map(SIZE_MAPPING)
    return df


def categorize_products(df):
    """Retourne une copie de df avec 'product_tags_cleaned' et 'product_category'
    dérivées de 'product_tags' (product_category est NaN si aucun tag connu ne
    correspond — voir TAGS_MAPPING)."""
    df = df.copy()
    df['product_tags_cleaned'] = df['product_tags'].apply(clean_product_tags)
    df['product_category'] = df['product_tags_cleaned'].map(TAGS_MAPPING)
    return df
