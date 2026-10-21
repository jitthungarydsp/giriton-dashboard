from copy import deepcopy
from datetime import date
from unittest.mock import Mock, patch
import unittest

from resources import giriton_attendance_db as db
from scripts import giriton_attendance_uidl_sync as sync


def row(day="2026-09-21", name="Teszt Futar", **fields):
    return {"work_date": day, "courier_name": name, **fields}


class AttendanceSyncTest(unittest.TestCase):
    def test_duplicate_database_keys_merge_without_losing_entries(self):
        first = row(checkin_start="6:00", checkin_end="12:00", raw_details="Elso muszak", shift_text="Normal",
                    response_json={"activity_entries": [{"start": "06:00", "end": "12:00"}]})
        second = row(checkin_start="14:00", checkin_end="18:00", raw_details="Masodik muszak", shift_text="Normal",
                     response_json={"activity_entries": [{"start": "14:00", "end": "18:00"}]})
        original = deepcopy([first, second, first])
        result = db._build_db_rows([first, second, first])
        self.assertEqual([first, second, first], original)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["checkin_start"], "06:00:00")
        self.assertEqual(result[0]["checkin_end"], "18:00:00")
        self.assertEqual(result[0]["raw_details"], "Elso muszak | Masodik muszak")
        self.assertEqual(result[0]["shift_text"], "Normal")
        self.assertEqual(len(result[0]["response_json"]["activity_entries"]), 2)
        self.assertEqual(len(result[0]["response_json"]["merged_responses"]), 2)

    def test_daily_identity_keeps_other_days_and_people_separate(self):
        result = db._build_db_rows([row(), row(), row(name="Masik Futar"), row(day="2026-09-22")])
        self.assertEqual(len(result), 3)
        self.assertEqual(db._build_db_rows([row(name=""), row(day="")]), [])

    def test_upsert_sends_unique_keys_and_preserves_stored_details(self):
        key = (db.SOURCE_NAME, "2026-09-21", "Teszt Futar")
        response = Mock()
        response.text = "[{}]"
        response.json.return_value = [{}]
        with patch.object(db, "get_supabase_config", return_value=("https://test.invalid", "test")), \
             patch.object(db, "_read_existing_rows_for_dates", return_value={key: {"checkin_end": "18:00:00"}}), \
             patch.object(db, "_count_stored_rows", return_value=1), \
             patch.object(db.requests, "post", return_value=response) as post:
            result = db.upsert_giriton_attendance_rows([row(checkin_start="06:00"), row(checkin_start="07:00")])
        sent = post.call_args.kwargs["json"]
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]["checkin_start"], "06:00:00")
        self.assertEqual(sent[0]["checkin_end"], "18:00:00")
        self.assertEqual(result["rows"], 1)
        self.assertEqual(result["stored_rows"], 1)

    def test_exact_stored_count_is_not_limited_to_response_page(self):
        response = Mock(headers={"Content-Range": "0-999/1500"})
        response.json.return_value = [{}] * 1000
        with patch.object(db.requests, "get", return_value=response):
            self.assertEqual(db._count_stored_rows("https://test.invalid", "test", ["2026-09-21"]), 1500)

    def test_parser_excludes_responses_from_previous_displayed_day(self):
        with patch.object(sync, "parse_attendance_uidl_rows", return_value=[row(), row(day="2026-10-21")]):
            result = sync.parse_payload_rows([{}], date(2026, 9, 21))
        self.assertEqual([r["work_date"] for r in result], ["2026-09-21"])

    def test_capture_discards_old_date_and_reads_through_grid_end(self):
        driver = Mock()
        driver.execute_script.side_effect = ["20/10/2026", {}, {"bottom": False}, {"bottom": True}]
        with patch.object(sync, "install_vaadin_response_capture"), \
             patch.object(sync, "set_giriton_date") as set_date, \
             patch.object(sync.time, "sleep"), \
             patch.object(sync, "captured_vaadin_responses", side_effect=[["old"], ["new"], [], ["page2"], ["page3"], []]):
            result = sync.capture_attendance_day(driver, date(2026, 10, 21))
        self.assertEqual(result, ["new", "page2", "page3"])
        set_date.assert_called_once_with(driver, date(2026, 10, 21))
        self.assertIn(".v-grid-scroller-vertical", driver.execute_script.call_args.args[0])

    def test_range_records_each_day_and_reports_failures_without_claiming_success(self):
        driver = Mock()
        def capture(_driver, day):
            if day.day == 22:
                raise RuntimeError("Missing day")
            return [row(day=day.isoformat())]
        with patch.multiple(sync, giriton_login_credentials=Mock(return_value=("test", "test")),
                            create_driver=Mock(return_value=driver), login=Mock(),
                            install_vaadin_response_capture=Mock(), open_attendance=Mock(),
                            select_all_departments=Mock(), capture_attendance_day=Mock(side_effect=capture),
                            write_debug_payloads=Mock(), parse_payload_rows=Mock(side_effect=lambda data, day: data),
                            upsert_giriton_attendance_rows=Mock(return_value={"status": "ok", "rows": 1, "stored_rows": 1})):
            result = sync.sync_attendance_range(date(2026, 9, 21), date(2026, 9, 23))
        self.assertEqual(result["status"], "partial")
        self.assertEqual([d["status"] for d in result["days"]], ["ok", "error", "ok"])
        self.assertEqual(result["rows"], 2)
        driver.quit.assert_called_once()

    def test_invalid_range_never_opens_browser(self):
        with patch.object(sync, "create_driver") as create:
            for start, end in [(date(2026, 10, 21), date(2026, 9, 21)), (date(2025, 1, 1), date(2026, 10, 21))]:
                with self.assertRaises(ValueError):
                    sync.sync_attendance_range(start, end)
        create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
