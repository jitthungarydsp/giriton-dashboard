import ast
import re
import unittest
import unicodedata
from calendar import monthrange
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import Mock


class GoogleCourierRefreshTest(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[1] / 'scripts/import_google_bonus_malus_adjustments.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        self.ns = dict(re=re, requests=Mock(), unicodedata=unicodedata, date=date, datetime=datetime, timedelta=timedelta,
                       monthrange=monthrange, Any=Any, SOURCE_PREFIX='google_bonus_malus',
                       DEFAULT_SHEET_ID='sheet', DEFAULT_GID=1)
        # Isolate transformation/reconciliation from credentials and network.
        functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(path), 'exec'), self.ns)
        self.read_existing = self.ns['existing_adjustments']
        self.ns.update(closed_months=Mock(return_value=set()),
                       read_courier_master=Mock(return_value={}),
                       existing_adjustments=Mock(return_value={}),
                       insert_adjustment=Mock(), update_adjustment=Mock(),
                       deactivate_adjustment=Mock(), reactivate_sheet_adjustment=Mock())

    def sheet(self, rows):
        worksheet = Mock()
        worksheet.get_all_values.return_value = [list('ABCDEFGH'), *rows]
        self.ns['worksheet_by_gid'] = Mock(return_value=worksheet)

    def refresh(self):
        return self.ns['sync_courier_from_sheet']('100', 'Abonyi György', date(2026, 10, 1), date(2026, 10, 31))

    def row(self, amount=25000, when='2026-10-10 11:16:09.585000', name='Abonyi György', tx='S-1'):
        return [when, name, 'MALUSZ', 'Táska', amount, 0, 'admin', tx]

    def test_fractional_dates_and_negative_correction_are_both_imported(self):
        self.sheet([self.row(), self.row(-25000, '2026-10-31 18:56:00')])
        result = self.refresh()
        payloads = [call.args[0] for call in self.ns['insert_adjustment'].call_args_list]
        self.assertEqual(result['sheet_rows'], 2)
        self.assertEqual([(p['adjustment_type'], p['amount_huf']) for p in payloads],
                         [('malus', 25000), ('correction_income', 25000)])
        self.assertEqual({p['courier_id'] for p in payloads}, {'100'})

    def test_only_selected_courier_and_month_change(self):
        self.sheet([self.row(), self.row(name='Other'), self.row(when='2026-09-30 10:00:00')])
        prefix = 'google_bonus_malus:sheet:1:'
        self.ns['existing_adjustments'].return_value = {
            'selected': dict(id='selected', courier_id='100', source_key=prefix+'old', valid_from='2026-10-02'),
            'other': dict(id='other', courier_id='200', source_key=prefix+'other', valid_from='2026-10-02'),
            'september': dict(id='september', courier_id='100', source_key=prefix+'september', valid_from='2026-09-02'),
            'manual': dict(id='manual', courier_id='100', source_key='manual:1', valid_from='2026-10-02'),
        }
        self.assertEqual(self.refresh()['inserted'], 1)
        self.ns['existing_adjustments'].assert_called_once_with(courier_id='100')
        self.ns['read_courier_master'].assert_not_called()
        self.ns['deactivate_adjustment'].assert_called_once_with('selected')

    def test_existing_rows_are_paginated_and_filtered_by_selected_id(self):
        self.ns['supabase_url'] = Mock(return_value='https://example.invalid')
        self.ns['supabase_headers'] = Mock(return_value={})
        page1 = Mock(ok=True)
        page1.json.return_value = [dict(id=str(i), source_key=f'key-{i}') for i in range(1000)]
        page2 = Mock(ok=True)
        page2.json.return_value = [dict(id='1000', source_key='key-1000')]
        self.ns['requests'].get.side_effect = [page1, page2]
        self.assertEqual(len(self.read_existing(courier_id='100')), 1001)
        calls = self.ns['requests'].get.call_args_list
        self.assertEqual([call.kwargs['params']['offset'] for call in calls], ['0', '1000'])
        self.assertTrue(all(call.kwargs['params']['courier_id'] == 'eq.100' for call in calls))

    def test_invalid_selected_date_does_not_remove_existing_rows(self):
        self.sheet([self.row(when='not-a-date')])
        with self.assertRaisesRegex(ValueError, 'Hibás dátum'):
            self.refresh()
        self.ns['insert_adjustment'].assert_not_called()
        self.ns['deactivate_adjustment'].assert_not_called()

    def test_invalid_other_courier_date_does_not_block_selected_courier(self):
        self.sheet([self.row(), self.row(when='not-a-date', name='Other')])
        self.assertEqual(self.refresh()['inserted'], 1)

    def test_closed_month_is_explicit_and_never_writes(self):
        self.ns['closed_months'].return_value = {('100', '2026-10-01')}
        with self.assertRaisesRegex(ValueError, 'le van zárva'):
            self.refresh()
        self.ns['insert_adjustment'].assert_not_called()
        self.ns['deactivate_adjustment'].assert_not_called()

    def test_restore_only_rows_removed_by_importer(self):
        for deleted_by, expected in [('google-sheet-refresh', 1), ('human', 0)]:
            with self.subTest(deleted_by=deleted_by):
                self.sheet([self.row()])
                source = self.ns['rows_from_sheet']('sheet', 1)[0]
                key = self.ns['source_key']('sheet', 1, source)
                self.ns['existing_adjustments'].return_value = {
                    key: dict(id='existing', courier_id='100', is_active=False,
                              deleted_at='2026-10-11', deleted_by=deleted_by)}
                self.ns['reactivate_sheet_adjustment'].reset_mock()
                self.assertEqual(self.refresh()['updated'], expected)
                self.assertEqual(self.ns['reactivate_sheet_adjustment'].call_count, expected)

    def test_negative_bonus_is_a_deduction_and_dotted_fractional_date_parses(self):
        self.assertEqual(self.ns['adjustment_types_for_row']('BONUSZ', 0, -12000),
                         [('correction_deduction', 12000)])
        self.assertEqual(self.ns['parse_sheet_datetime']('2026.10.10. 11:16:09.585').month, 10)
        self.assertEqual(self.ns['adjustment_types_for_row']('', -25000, 10000),
                         [('correction_income', 25000), ('bonus', 10000)])

    def test_old_minute_only_sheet_date_does_not_block_october_refresh(self):
        self.sheet([self.row(when='2026.03.25. 20:48'), self.row()])
        result = self.refresh()
        self.assertEqual(result['inserted'], 1)
        self.ns['worksheet_by_gid'].return_value.get_all_values.assert_called_with(
            value_render_option='UNFORMATTED_VALUE', date_time_render_option='SERIAL_NUMBER')

    def test_sheet_serial_dates_keep_month_and_time_without_locale_guessing(self):
        values = [datetime(2026, 3, 25, 20, 48), datetime(2026, 10, 10, 11, 16, 9),
                  datetime(2026, 10, 31, 18, 56)]
        serials = [(d-datetime(1899, 12, 30)).total_seconds()/86400 for d in values]
        for value, serial in zip(values, serials):
            parsed = self.ns['parse_sheet_datetime'](serial)
            self.assertEqual(parsed.date(), value.date())
            self.assertLess(abs((parsed-value).total_seconds()), .001)
        self.sheet([self.row(when=serials[0]), self.row(when=serials[1])])
        self.assertEqual(self.refresh()['inserted'], 1)

    def test_embedded_courier_id_name_normalizes_to_master_name(self):
        self.assertEqual(
            self.ns['normalized_courier_sheet_name']('Piszker 9070 Klaudia'),
            self.ns['normalize_text']('Piszker Klaudia'),
        )

    def test_matching_payload_is_not_rewritten(self):
        row = {
            'effective_date': date(2026, 10, 10), 'adjustment_type': 'malus',
            'amount_huf': 25000, 'note': 'Táska', 'transaction_id': 'S-1',
            'raw_type': 'MALUSZ', 'recorded_by': 'admin',
        }
        payload = self.ns['adjustment_payload'](row, {'courier_id': '100'}, 'source')
        self.assertTrue(self.ns['adjustment_matches_payload'](dict(payload), payload))


if __name__ == '__main__':
    unittest.main()
