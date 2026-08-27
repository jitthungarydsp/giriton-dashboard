import unittest

from resources.settlement_pdf import build_tig_breakdown


class SettlementTigBreakdownTest(unittest.TestCase):
    def test_negative_service_remainder_reduces_tip(self):
        result = build_tig_breakdown(
            {"tig_type": "AAM"},
            {"payable": 51646, "tip": 98300, "cash": 109803},
        )

        self.assertEqual(result["transferServiceHuf"], 0)
        self.assertEqual(result["tipHuf"], 51646)
        self.assertEqual(result["originalTipHuf"], 98300)
        self.assertEqual(result["finalTotalHuf"], 51646)

        tip_row = next(row for row in result["rows"] if row["key"] == "tip")
        self.assertEqual(tip_row["grossHuf"], 51646)

    def test_positive_service_keeps_full_tip(self):
        result = build_tig_breakdown(
            {"tig_type": "AAM"},
            {"payable": 120000, "tip": 20000, "cash": 0},
        )

        self.assertEqual(result["transferServiceHuf"], 100000)
        self.assertEqual(result["tipHuf"], 20000)
        self.assertEqual(result["finalTotalHuf"], 120000)

    def test_vat_service_is_grossed_and_tip_keeps_full_tam_amount(self):
        result = build_tig_breakdown(
            {"tig_type": "VAT"},
            {"payable": 501199, "tip": 131216, "cash": 0},
        )

        self.assertEqual(result["tipHuf"], 131216)
        self.assertEqual(result["finalTotalHuf"], 601094)

        transfer_row = next(row for row in result["rows"] if row["key"] == "transfer_service")
        tip_row = next(row for row in result["rows"] if row["key"] == "tip")
        self.assertEqual(transfer_row["grossHuf"], 469878)
        self.assertEqual(transfer_row["netHuf"], 369983)
        self.assertEqual(transfer_row["vatHuf"], 99895)
        self.assertEqual(tip_row["grossHuf"], 131216)


if __name__ == "__main__":
    unittest.main()
