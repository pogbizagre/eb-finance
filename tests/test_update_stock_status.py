import importlib.util
import logging
import sys
import unittest
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
logging.basicConfig(handlers=[logging.NullHandler()])


def load_script(module_name, script_name):
    spec = importlib.util.spec_from_file_location(
        module_name, ROOT / "src" / script_name
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stock_status = load_script("stock_status", "update-stock-status.py")
stock_publisher = load_script("stock_publisher", "publish-stock-status.py")
GENERATED_AT = datetime(2026, 10, 12, 9, 30)


class ProductStockSentenceTests(unittest.TestCase):
    def test_named_variants_are_aggregated_and_zero_stock_is_omitted(self):
        variants = pd.DataFrame([
            {"size_standard": None, "variant_title": "Rouge", "variant_inventory_qty": 2},
            {"size_standard": None, "variant_title": "Rouge", "variant_inventory_qty": 1},
            {"size_standard": None, "variant_title": "Bleu", "variant_inventory_qty": 4},
            {"size_standard": None, "variant_title": "Vert", "variant_inventory_qty": 0},
        ])

        sentence = stock_status.format_product_stock_sentence(
            variants, False, GENERATED_AT
        )

        self.assertEqual(
            sentence,
            "Disponible en Bleu (4 unités) et Rouge (3 unités). "
            "(mis à jour le 12/10/2026 à 09:30)",
        )

    def test_default_or_empty_variant_titles_show_total_without_label(self):
        variants = pd.DataFrame([
            {"size_standard": None, "variant_title": "Default Title", "variant_inventory_qty": 2},
            {"size_standard": None, "variant_title": None, "variant_inventory_qty": 3},
        ])

        sentence = stock_status.format_product_stock_sentence(
            variants, False, GENERATED_AT
        )

        self.assertEqual(
            sentence,
            "Disponible en 5 unités. (mis à jour le 12/10/2026 à 09:30)",
        )

    def test_shoes_keep_sizes_and_include_unmapped_variants(self):
        variants = pd.DataFrame([
            {"size_standard": "40", "variant_title": "40 / Noir", "variant_inventory_qty": 1},
            {"size_standard": "38", "variant_title": "38 / Noir", "variant_inventory_qty": 2},
            {"size_standard": None, "variant_title": "Édition spéciale", "variant_inventory_qty": 1},
        ])

        sentence = stock_status.format_product_stock_sentence(
            variants, True, GENERATED_AT
        )

        self.assertEqual(
            sentence,
            "Disponible en pointure 38 (2 unités), pointure 40 (1 unité) et "
            "Édition spéciale (1 unité). (mis à jour le 12/10/2026 à 09:30)",
        )

    def test_no_available_variants_keeps_out_of_stock_message(self):
        variants = pd.DataFrame([
            {"size_standard": None, "variant_title": "Rouge", "variant_inventory_qty": 0},
            {"size_standard": None, "variant_title": "Bleu", "variant_inventory_qty": None},
        ])

        sentence = stock_status.format_product_stock_sentence(
            variants, False, GENERATED_AT
        )

        self.assertEqual(
            sentence,
            "Actuellement en rupture de stock. (mis à jour le 12/10/2026 à 09:30)",
        )

    def test_publisher_escapes_variant_text_inside_html(self):
        description = stock_publisher.build_new_description(
            "", "Disponible en Rouge & <Or>."
        )

        self.assertIn("<p>Disponible en Rouge &amp; &lt;Or&gt;.</p>", description)


if __name__ == "__main__":
    unittest.main()