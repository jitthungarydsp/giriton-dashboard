import unittest
from datetime import date
from unittest.mock import patch

from resources.pwa_invoice_validation import _extract_invoice_dates, validate_invoice


class InvoiceDateOrderTest(unittest.TestCase):
    def test_nav_values_before_labels_do_not_pick_invoice_period(self):
        text = """Fizetési mód: Átutalás
2026.10.19. Teljesítés: 2026.10.19. Keltezés: 2026.10.26. Fizetési határidő:
HUF Pénznem: 2026.09.01.-2026.09.30. Teljesítési időszak:"""
        fields = _extract_invoice_dates(text)
        self.assertEqual(fields, {
            "issue_date": date(2026, 10, 19), "performance_date": date(2026, 10, 19),
            "due_date": date(2026, 10, 26),
        })
        self.assertEqual((fields["due_date"] - fields["issue_date"]).days, 7)

    def test_reversed_columns_keep_distinct_performance_and_issue_dates(self):
        fields = _extract_invoice_dates(
            "2026.10.18.\nTeljesítés:\n2026.10.19.\nKeltezés:\n2026.10.27.\nFizetési határidő:"
        )
        self.assertEqual(fields["performance_date"], date(2026, 10, 18))
        self.assertEqual(fields["issue_date"], date(2026, 10, 19))
        self.assertEqual(fields["due_date"], date(2026, 10, 27))

    def test_normal_label_before_value_order_is_unchanged(self):
        fields = _extract_invoice_dates(
            "Teljesítés: 2026.10.19. Keltezés: 2026.10.19. Fizetési határidő: 2026.10.26."
        )
        self.assertEqual(fields["issue_date"], date(2026, 10, 19))
        self.assertEqual(fields["due_date"], date(2026, 10, 26))


class InvoicePdfSpacingTest(unittest.TestCase):
    # Text-based PDFs can have visible spaces which pypdf does not return.
    text = """BODONYIGELLÉRTFERENC,61776784
1083Budapest
Práterutca65.1em.19.ajtó
Adószám:91720470-1-42
Bankszámlaszám:
11773085-00552875
Sorszám:BG-2026-16
VEVŐ:
JustinTimeTransportHungaryKft.
1201Budapest
Atlétautca44.
Adószám:32649460-2-43
Teljesítésdátuma:2026.10.27.
Kiállításdátuma:2026.10.19.
Fizetésihatáridő:2026.10.27.
Összesen:179532Ft
"""

    def validate(self, text=None, **overrides):
        args = dict(
            file_name="test.pdf", content=b"%PDF-test", invoice_month=date(2026, 10, 1),
            courier_name="Bodonyi Gellért Ferenc", courier_id="7267",
            expected_seller_name="BODONYI GELLÉRT FERENC, 61776784",
            expected_seller_address="1083 Budapest Práter utca 65. 1em. 19.ajtó",
            expected_seller_tax_number="91720470-1-42", expected_gross_amount=179532,
            invoice_number="BG-2026-16", gross_amount=179532, require_submission_fields=True,
        )
        args.update(overrides)
        with patch("resources.pwa_invoice_validation.extract_pdf_text", return_value=self.text if text is None else text):
            return validate_invoice(**args)

    def check(self, result, title):
        return next(check for check in result["checks"] if check["title"] == title)

    def test_joined_names_and_addresses_are_accepted(self):
        result = self.validate()
        self.assertTrue(result["ok"], result["checks"])
        for title in ("Eladó neve", "Vevő neve", "Vevő címe", "Eladó címe", "Számlaszám egyezése"):
            with self.subTest(title=title):
                check = self.check(result, title)
                self.assertEqual(check["status"], "ok")
                self.assertNotIn("Javítandó", check["detail"])
        self.assertEqual(result["parsed"]["invoiceNumber"], "BG-2026-16")

    def test_normal_spaced_text_still_works(self):
        text = self.text.replace("BODONYIGELLÉRTFERENC", "BODONYI GELLÉRT FERENC")
        text = text.replace("JustinTimeTransportHungaryKft", "Just in Time Transport Hungary Kft")
        text = text.replace("1201Budapest", "1201 Budapest").replace("Atlétautca44", "Atléta utca 44")
        self.assertTrue(self.validate(text)["ok"])

    def test_different_or_longer_seller_name_is_rejected(self):
        for replacement in ("MÁSIKGELLÉRTFERENC", "XBODONYIGELLÉRTFERENC", "BODONYIGELLÉRTFERENCZ"):
            with self.subTest(replacement=replacement):
                result = self.validate(self.text.replace("BODONYIGELLÉRTFERENC", replacement))
                self.assertEqual(self.check(result, "Eladó neve")["status"], "error")

    def test_different_profile_identifier_is_rejected(self):
        result = self.validate(self.text.replace("61776784", "61776785"))
        self.assertEqual(self.check(result, "Eladó neve")["status"], "error")

    def test_different_buyer_name_is_rejected(self):
        result = self.validate(self.text.replace("TransportHungary", "TransportAustria"))
        self.assertEqual(self.check(result, "Vevő neve")["status"], "error")

    def test_address_cannot_match_prefix_of_house_or_postal_number(self):
        for text in (self.text.replace("utca44", "utca440"), self.text.replace("1201Budapest", "11201Budapest")):
            with self.subTest(text=text):
                self.assertEqual(self.check(self.validate(text), "Vevő címe")["status"], "error")

    def test_bank_account_is_not_accepted_as_invoice_serial(self):
        result = self.validate(invoice_number="11773085-00552875")
        self.assertFalse(result["ok"])
        check = self.check(result, "Számlaszám egyezése")
        self.assertEqual(check["status"], "error")
        self.assertIn("BG-2026-16", check["detail"])
        self.assertIn("bankszámlaszámot", check["detail"])


if __name__ == "__main__":
    unittest.main()
