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


def shopify_graphql(query, max_retries=5):
    """Exécute une requête GraphQL Shopify. Relance automatiquement si Shopify
    répond avec un throttling au niveau du coût de la requête (HTTP 200 avec
    une erreur GraphQL de code THROTTLED — non couvert par le retry HTTP de la
    Session, qui ne regarde que le status code)."""
    headers = {
        "X-Shopify-Access-Token": get_access_token(),
        "Content-Type": "application/json",
    }

    response = None
    for attempt in range(max_retries):
        response = _session.post(
            GRAPHQL_URL, json={"query": query}, headers=headers, timeout=REQUEST_TIMEOUT
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
