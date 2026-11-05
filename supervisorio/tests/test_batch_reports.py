import datetime
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtCore import QDate
from PyQt5.QtWidgets import QApplication, QDialogButtonBox
from batch_reports import (BatchExportDialog, filter_readings, historical_report_arguments,
                           export_history_reports)

RECORDS = [
    dict(id=1, timestamp='26/10/2026 10:00:00', codigo_amostra='A-1', operador='Ana', metodo_analitico='Amostra Seca', kappa_estimado=10),
    dict(id=2, timestamp='2026-10-29 23:59:59', codigo_amostra='B-2', operador='Bruno', metodo_analitico='Suspensão Aquosa', kappa_estimado=20),
    dict(id=3, timestamp='01/11/2026 00:00:00', codigo_amostra='A-3', operador='Ana', metodo_analitico='Amostra Seca', kappa_estimado=30),
    dict(id=4, timestamp='02/11/2026 00:00:00', codigo_amostra='A-4', operador='Ana', metodo_analitico='Amostra Seca', kappa_estimado=40),
    dict(id=5, timestamp='sem data', codigo_amostra='X', operador='Ana', metodo_analitico='Amostra Seca', kappa_estimado=float('nan')),
]

class BatchReportsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_date_kappa_and_metadata_filters(self):
        day = datetime.date(2026, 10, 29)
        self.assertEqual([r['id'] for r in filter_readings(RECORDS, start=day, end=day)], [2])
        self.assertEqual([r['id'] for r in filter_readings(RECORDS, kappa_min=10, kappa_max=30, operator='ana', method='seco', sample='a-')], [1, 3])
        self.assertEqual(len(filter_readings(RECORDS)), 5)

    def test_week_and_selected_scope(self):
        dialog = BatchExportDialog(RECORDS, [2, 4])
        self.assertEqual([r['id'] for r in dialog.filtered_records], [2, 4])
        dialog.scope.setCurrentIndex(0)
        dialog.start.setDate(QDate(2026, 10, 29))
        dialog.period.setCurrentIndex(dialog.period.findData('week'))
        self.assertEqual([r['id'] for r in dialog.filtered_records], [1, 2, 3])
        dialog.kappa_enabled.setChecked(True)
        dialog.kappa_min.setValue(40)
        dialog.kappa_max.setValue(10)
        self.assertFalse(dialog.buttons.button(QDialogButtonBox.Save).isEnabled())
        dialog.close()

    def test_historical_calibration_is_preserved(self):
        import json
        record = dict(RECORDS[0], calibration_snapshot=json.dumps({'calibration_id': 'OLD-CAL'}), raw_scans_json='[[1,2,3,4,5,6]]', acquisition_count=1)
        args = historical_report_arguments(record)
        self.assertEqual(args['calibration_snapshot']['calibration_id'], 'OLD-CAL')
        self.assertEqual(args['raw_scans'], [[1, 2, 3, 4, 5, 6]])

    def test_safe_names_isolated_failure_and_no_overwrite(self):
        def fake_pdf(path, **kwargs):
            Path(path).write_bytes(b'%PDF-test')
        records = [dict(RECORDS[0], codigo_amostra='../../same'), dict(RECORDS[1], codigo_amostra='../../same'), dict(RECORDS[2], calibration_snapshot='invalid json')]
        with tempfile.TemporaryDirectory() as directory, patch('batch_reports.generate_pdf_report', fake_pdf):
            first = export_history_reports(records, directory)
            second = export_history_reports(records[:1], directory)
            self.assertNotEqual(first['folder'], second['folder'])
            self.assertEqual(len(first['files']), 2)
            self.assertEqual(len(first['errors']), 1)
            self.assertEqual(len(list(Path(first['folder']).iterdir())), 2)
            for path in first['files']:
                self.assertEqual(Path(path).parent, Path(first['folder']))
                self.assertEqual(Path(path).read_bytes(), b'%PDF-test')

    def test_cancel_preserves_completed_reports(self):
        calls = []
        def fake_pdf(path, **kwargs):
            Path(path).write_bytes(b'%PDF-test')
        with tempfile.TemporaryDirectory() as directory, patch('batch_reports.generate_pdf_report', fake_pdf):
            result = export_history_reports(RECORDS, directory, progress=calls.append, cancelled=lambda: bool(calls))
            self.assertTrue(result['cancelled'])
            self.assertEqual(len(result['files']), 1)
            self.assertEqual(calls, [1])

if __name__ == '__main__':
    unittest.main()
