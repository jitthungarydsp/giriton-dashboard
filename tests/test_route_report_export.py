import importlib.util
from io import BytesIO
from pathlib import Path
import re
import unittest
from openpyxl import Workbook, load_workbook

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('route_report_export',ROOT/'resources/route_report_export.py')
export=importlib.util.module_from_spec(spec);spec.loader.exec_module(export)


class RouteReportExportTests(unittest.TestCase):
    def test_download_contains_only_selected_columns_in_selected_order(self):
        wb=Workbook();sheet=wb.active
        export.populate_selected_sheet(sheet,[{'courierId':'42','courierName':'Teszt','tipHuf':1234,'orders':9,'warehouse':'BUD1'}],'tip,courierName,orders')
        output=BytesIO();wb.save(output);output.seek(0)
        rows=list(load_workbook(output,data_only=True).active.values)
        self.assertEqual(rows,[('Borravaló','Futár neve','Címek'),(1234,'Teszt',9)])

    def test_available_columns_and_labels_match_the_report_ui(self):
        source=(ROOT/'pwa/app.js').read_text(encoding='utf8')
        fields=source[source.index('const ROUTE_REPORT_FIELDS'):source.index('const DEFAULT_ROUTE_REPORT_FIELDS')]
        frontend=dict(re.findall(r'key: "([^"]+)".*?column: "([^"]+)"',fields))
        self.assertEqual(frontend,{k:v[0] for k,v in export.COLUMNS.items()})

    def test_invalid_duplicate_or_empty_selection_is_rejected(self):
        for selection in ['','courierName,secret','orders,orders']:
            with self.subTest(selection=selection),self.assertRaises(ValueError):export.selected_columns(selection)

    def test_derived_distance_duration_and_formula_safety(self):
        self.assertEqual(export.export_value({'routeDistance':{'distanceKm':42.5}},'distance'),42.5)
        self.assertEqual(export.export_value({'routeMinutes':251},'routeTime'),'4:11')
        self.assertEqual(export.export_value({'totalMinutes':301},'over5h'),'Igen')
        self.assertEqual(export.export_value({'courierName':'=1+1'},'courierName'),"'=1+1")


if __name__=='__main__':unittest.main()
