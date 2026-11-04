import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import sync_courier_financial_overview as sync


class HubDelayCleaningTest(unittest.TestCase):
    def build(self, financial_route=None):
        ref = {"route_id": 1590606, "delivery_date": "2026-10-31", "order_count": 14}
        if financial_route is not None:
            ref["financial_route"] = financial_route
        return sync.build_delay_row(courier_id=7644, warehouse_id=2, route_ref=ref,
            response_json={"stops": [{"deltaMinutes": n} for n in (2, 1, 5, 12)]},
            status_code=200, year=2026, month=10)

    def test_dataport_cleaning_overrides_raw_stop_delays(self):
        route = {"routeId": 1590606, "dataportDelayedOrderCount": 4,
                 "delayOrders": [{"delayMinutes": n, "cleaned": True, "cleanedReason": "KARMA"} for n in (2, 1, 5, 12)]}
        result = self.build(route)
        self.assertEqual(result["cleaned_delay_count"], 4)
        self.assertEqual(result["cleaned_delay_minutes"], 20)
        self.assertEqual(result["uncleaned_delay_count"], 0)
        self.assertEqual(result["uncleaned_delay_minutes"], 0)
        self.assertEqual(result["cleaned_reasons"], ["KARMA"])

    def test_incomplete_breakdown_does_not_erase_observed_delays(self):
        result = self.build({"routeId": 1590606, "dataportDelayedOrderCount": 4, "delayOrders": []})
        self.assertEqual(result["delayed_stops_count"], 4)
        self.assertEqual(result["uncleaned_delay_count"], 4)

    def test_missing_or_wrong_route_breakdown_is_ignored(self):
        for route in (None, {"routeId": 9999, "delayOrders": []}):
            with self.subTest(route=route):
                result = self.build(route)
                self.assertEqual(result["uncleaned_delay_minutes"], 20)
                self.assertEqual(result["cleaned_delay_count"], 0)

    def test_mixed_delays_and_explicit_empty_breakdown(self):
        result = self.build({"routeId": 1590606, "delayOrders": [
            {"delayMinutes": 2, "cleaned": True}, {"delayMinutes": 12, "cleaned": False}]})
        self.assertEqual(result["cleaned_delay_count"], 1)
        self.assertEqual(result["uncleaned_delay_count"], 1)
        self.assertEqual(result["total_delay_minutes"], 14)
        cleared = self.build({"routeId": 1590606, "delayOrders": [], "dataportDelayedOrderCount": 0})
        self.assertEqual(cleared["delayed_stops_count"], 0)

    def test_financial_route_is_kept_when_building_detail_references(self):
        route = {"routeId": 1590606, "deliveryDate": "2026-10-31", "delayOrders": []}
        refs = sync.extract_route_refs({"routes": [route]})
        self.assertIs(refs[0]["financial_route"], route)


if __name__ == "__main__":
    unittest.main()
