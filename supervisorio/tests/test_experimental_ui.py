"""Local Linux integration test, with simulated communication and temporary data."""
import json, os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PyQt5.QtCore import QObject,pyqtSignal
from PyQt5.QtWidgets import QApplication
import main

class FakeWorker(QObject):
    line_received=pyqtSignal(str)
    status_received=pyqtSignal(str)
    data_received=pyqtSignal(list)
    scan_received=pyqtSignal(str,list)
    connection_changed=pyqtSignal(bool,str)
    error_occurred=pyqtSignal(str)
    def __init__(self,parent=None):
        super().__init__(parent);self.sent=[];self.connected=True;self.mode='USB'
    def is_connected(self):return self.connected
    def send_command(self,cmd,priority=False):self.sent.append(cmd);return True
    def send_emergency(self):self.sent.append('CMD:EMERGENCIA')
    def disconnect_connection(self):self.connected=False
    @staticmethod
    def list_ports():return []

class ExperimentalIntegrationTest(unittest.TestCase):
    def test_optional_mode_preserves_legacy_calibration_and_commands(self):
        app=QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'SPECTRUM_LAB_DATA_DIR':tmp}),patch.object(main,'ConnectionWorker',FakeWorker):
            w=main.SpectrumLabMainWindow()
            try:
                w._calib_validity_timer.stop();w._heartbeat_timer.stop()
                self.assertTrue(w.chem_engine.save_calibration(white_scans=[[1000+i,1200+i,1400+i,1600+i,1800+i,2000+i] for i in range(10)],dark_scans=[[10]*6]*10,settings=w.chem_engine.DEFAULT_SETTINGS))
                sample=[700,800,950,1100,1200,1300]
                w._current_sample_id='SIMULATED';w._last_acquisition_scans=[sample]*5
                before=Path(w.chem_engine.calib_file_path).read_bytes()
                w.process_raw_spectral_data(sample,persist=False)
                self.assertFalse(hasattr(w,'pls_mode'))
                model_path=Path(__file__).resolve().parents[1]/'experiments/chemometrics/model_km_snv_4amostras.json'
                self.assertEqual(w._pls_model['method'],'km_snv')
                self.assertEqual(w._pls_model,json.loads(model_path.read_text()))
                sent=list(w.serial_worker.sent)
                self.assertIsNotNone(w._pls_result)
                self.assertEqual(w._pls_result['static_repeatability']['n_acquisitions'],5)
                self.assertAlmostEqual(w._pls_result['static_repeatability']['sample_sd'],0)
                self.assertFalse(w._pls_result['firmware_acquisition_verified'])
                self.assertAlmostEqual(w.current_kappa_value,round(max(0.0,w._pls_result['kappa_experimental']),2))
                self.assertEqual(w.serial_worker.sent,sent)
                self.assertEqual(Path(w.chem_engine.calib_file_path).read_bytes(),before)
                w._result_valid=False;w._refresh_pls()
                self.assertIsNone(w._pls_result)
                self.assertFalse(w.btn_export_pls.isEnabled())
                w.process_raw_spectral_data(sample,persist=False)
                self.assertIsNotNone(w._pls_result)
                w.chem_engine.active_mode='umido';w._refresh_pls()
                self.assertIsNone(w._pls_result)
            finally:
                w._hardware_watchdog.stop();w._acquisition_timer.stop();w._clear_cycle_timers()
                w.serial_worker.connected=False;w.close();w.deleteLater();app.processEvents()
