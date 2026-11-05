import os
import time
import unittest
from collections import deque
from types import SimpleNamespace
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtWidgets import QApplication
from responsive_ui import ResponsiveShell, table, populate

class AlarmUpdatesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_event_burst_is_coalesced_and_bounded(self):
        shell = SimpleNamespace(events=deque(maxlen=500), _events_dirty=False, event_table=object())
        with patch('responsive_ui.populate') as fill:
            start = time.perf_counter()
            for i in range(10000):
                ResponsiveShell.record_event(shell, str(i))
            elapsed = time.perf_counter() - start
            fill.assert_not_called()
            self.assertEqual(len(shell.events), 500)
            ResponsiveShell._refresh_event_table(shell)
            ResponsiveShell._refresh_event_table(shell)
            fill.assert_called_once()
            self.assertEqual(fill.call_args.args[1][0][1], '9999')
            print(f'\n10.000 eventos agrupados em {elapsed:.3f}s; uma atualização da tabela.')

    def test_table_preserves_update_signal_and_sorting_settings(self):
        widget = table(['Horário', 'Evento'])
        widget.setSortingEnabled(True)
        widget.blockSignals(True)
        populate(widget, [('10:00', 'Evento A'), ('11:00', 'Evento B')])
        self.assertTrue(widget.updatesEnabled())
        self.assertTrue(widget.isSortingEnabled())
        self.assertTrue(widget.signalsBlocked())
        self.assertEqual(widget.rowCount(), 2)
        widget.close()

if __name__ == '__main__':
    unittest.main()
