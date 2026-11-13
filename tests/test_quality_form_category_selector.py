import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class GoogleFormCategorySelectorTest(unittest.TestCase):
    def test_category_fallback_uses_exact_visible_radio_text(self):
        source=(ROOT/'scripts'/'run_quality_form_worker.py').read_text(encoding='utf-8')
        self.assertIn('//*[@role="radio" and ', source)
        self.assertIn('normalize-space(.)="{label}"', source)
        self.assertIn('.//*[normalize-space(.)="{label}"]', source)
        self.assertIn('if el.is_displayed()', source)
        ast.parse(source)

    def test_every_category_uses_verified_public_prefill_before_ui_verification(self):
        source=(ROOT/'scripts'/'run_quality_form_worker.py').read_text(encoding='utf-8')
        self.assertIn("'Elszámolás': (1609979400,275666129,949548968)", source)
        self.assertIn("'entry.608543996':category", source)
        self.assertIn("self.open(form.FORM_URL+'?'+urlencode(prefill))", source)
        self.assertIn('Reklamáció típusa nem jelölődött ki:', source)


if __name__ == '__main__':
    unittest.main()
