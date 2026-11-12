import ast
import importlib.util
from datetime import datetime
from pathlib import Path
import sys
import unittest
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]


def api_functions():
    names = {
        'local_datetime', 'safe_int', 'safe_float_value', 'route_queue_started_value',
        'route_detail_minutes_between', 'route_detail_duration_text', 'route_detail_datetime_text',
        'route_detail_time_text', 'route_detail_route_type_label', 'route_detail_warehouse_address',
        'route_detail_narrative', 'build_route_detail_item_from_hub_stat',
        'hub_stat_shift_planned_start', 'hub_stat_late_start_minutes', 'hub_stat_daily_history_row',
    }
    tree = ast.parse((ROOT/'pwa_api.py').read_text(encoding='utf-8'))
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    ns = {'datetime': datetime, 'LOCAL_TIMEZONE': ZoneInfo('Europe/Budapest'),
          'normalize_time': lambda value: str(value or ''),
          'normalize_text': lambda value: str(value or '').lower(),
          'COURIER_HUB_WAREHOUSE_ADDRESSES': {1: 'Raktár'}}
    future = ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[future, *nodes], type_ignores=[])), 'pwa_api.py', 'exec'), ns)
    return ns


class RouteDurationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = api_functions()
        scripts = str(ROOT/'scripts')
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        spec = importlib.util.spec_from_file_location('hub_statistics', ROOT/'scripts/build_courier_hub_statistics.py')
        cls.builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.builder)

    def row(self):
        return {'courier_id': 42, 'route_id': 100, 'warehouse_id': 1, 'work_date': '2026-10-01',
                'shift_name': '08:00', 'route_assigned_at': '2026-10-01T08:00:00+02:00',
                'departed_at': '2026-10-01T08:30:00+02:00', 'returned_at': '2026-10-01T11:30:00+02:00',
                'actual_route_minutes': 210, 'total_minutes': 210, 'loading_minutes': 30,
                'story_text': 'Outdated saved story with identical durations'}

    def test_existing_bad_statistics_are_corrected_for_detail_and_excel(self):
        item = self.api['build_route_detail_item_from_hub_stat'](self.row())
        self.assertEqual((item['loadingMinutes'], item['routeMinutes'], item['totalMinutes']), (30, 180, 210))
        self.assertNotIn('Outdated', item['narrative'])
        self.assertIn('3 óra', item['narrative'])
        self.assertIn('3 óra 30 perc', item['narrative'])

    def test_daily_history_uses_same_corrected_durations(self):
        history = self.api['hub_stat_daily_history_row'](self.row(), {})
        story = history['routeStory']
        self.assertEqual((story['realLoadingMinutes'], story['realRouteMinutes'], story['totalRouteMinutes']), (30, 180, 210))

    def test_missing_departure_does_not_reuse_old_inclusive_route_time(self):
        row = self.row(); row['departed_at'] = None
        item = self.api['build_route_detail_item_from_hub_stat'](row)
        self.assertIsNone(item['routeMinutes'])
        self.assertIsNone(item['loadingMinutes'])
        self.assertEqual(item['totalMinutes'], 210)

    def test_no_loading_can_legitimately_have_equal_durations(self):
        row = self.row(); row['departed_at'] = row['route_assigned_at']
        item = self.api['build_route_detail_item_from_hub_stat'](row)
        self.assertEqual((item['loadingMinutes'], item['routeMinutes'], item['totalMinutes']), (0, 210, 210))

    def test_future_saved_statistics_exclude_loading_from_route_time(self):
        payload = {'shift': {'plannedStartAt': '2026-10-01T08:00:00+02:00'}, 'log': [
            {'type': 'ROUTE_ASSIGNED', 'occurredAt': '2026-10-01T08:00:00+02:00'},
            {'type': 'DEPARTED', 'occurredAt': '2026-10-01T08:30:00+02:00'},
            {'type': 'WAREHOUSE_ARRIVED', 'occurredAt': '2026-10-01T11:30:00+02:00'},
        ]}
        row = self.builder.build_route_stat({'courier_id':42, 'route_id':100, 'warehouse_id':1, 'response_json':payload},
                                           {}, calculate_google=False, courier_names={}, live_latest={}, financial_routes={})
        self.assertEqual((row['loading_minutes'], row['actual_route_minutes'], row['total_minutes']), (30, 180, 210))


if __name__ == '__main__':
    unittest.main()
