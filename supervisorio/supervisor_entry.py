"""Desktop entry and isolated packaged-resource diagnostic for release verification."""
import json
import os
from pathlib import Path
import sys
import tempfile
import traceback


def packaged_self_test(destination):
    os.environ['QT_QPA_PLATFORM']='offscreen'
    report={'ok':False,'platform':sys.platform,'frozen':bool(getattr(sys,'frozen',False))}
    try:
        with tempfile.TemporaryDirectory(prefix='SpectrumPLSSmoke_') as temp:
            os.environ['SPECTRUM_LAB_DATA_DIR']=str(Path(temp)/'data')
            os.environ['MPLCONFIGDIR']=str(Path(temp)/'mpl')
            from PyQt5.QtCore import QObject,pyqtSignal
            from PyQt5.QtWidgets import QApplication
            import main as application
            from experimental_chemometrics import predict
            from acquisition_quality import parse_scan_metadata
            class OfflineWorker(QObject):
                line_received=pyqtSignal(str)
                status_received=pyqtSignal(str)
                data_received=pyqtSignal(list)
                scan_received=pyqtSignal(str,list)
                connection_changed=pyqtSignal(bool,str)
                error_occurred=pyqtSignal(str)
                def __init__(self,parent=None):
                    super().__init__(parent);self.connected=False;self.sent=[];self.mode='USB'
                def is_connected(self):return False
                def send_command(self,cmd,priority=False):self.sent.append(cmd);return False
                def send_emergency(self):self.sent.append('CMD:EMERGENCIA')
                def disconnect_connection(self):pass
                @staticmethod
                def list_ports():return []
            application.ConnectionWorker=OfflineWorker
            app=QApplication.instance() or QApplication([])
            window=application.SpectrumLabMainWindow()
            try:
                window._heartbeat_timer.stop();window._calib_validity_timer.stop()
                assert not hasattr(window,'pls_mode'),'PLS toggle should be removed (active by default)'
                assert window._pls_model is not None,'Bundled PLS model missing'
                assert window._pls_model['method']=='km_snv'
                raw_path=Path(application.__file__).resolve().parent/'experiments/chemometrics/model_raw.json'
                assert json.loads(raw_path.read_text())['method']=='raw'
                reference=[.39730445708980605,.4741276740402593,.48778678535473957,.4876216164146036,.43931681936432526,.45728643216080406]
                predicted=float(predict(window._pls_model,[reference],'seco')[0])
                assert 18.0<predicted<21.5,(predicted,'PLS numeric regression')
                assert window.chem_engine.save_calibration(
                    white_scans=[[1000+i,1200+i,1400+i,1600+i,1800+i,2000+i] for i in range(10)],
                    dark_scans=[[10]*6]*10,settings=window.chem_engine.DEFAULT_SETTINGS)
                sample=[700,800,950,1100,1200,1300]
                window._current_sample_id='PACKAGED-SELF-TEST'
                window._last_acquisition_scans=[sample]*5
                window.process_raw_spectral_data(sample,persist=False)
                assert window._pls_result is not None,window.lbl_pls.text()
                assert window._pls_result['static_repeatability']['n_acquisitions']==5
                assert abs(window.current_kappa_value-round(max(0.0,window._pls_result['kappa_experimental']),2))<1e-6
                assert not window.serial_worker.sent,'Diagnostic sent a hardware command'
                packet='SCANMETA:test|V:1|FW:PLS_ACQ_1|SEQ:1|KIND:LIGHT|GAIN_CODE:3|INT_T:50|LED_CODE:2|LED_WAIT_MS:150|TEMP_C:28|UPTIME_MS:2000|CONVERSION_MS:285|TOTAL_MS:445|EXPOSURE_LED:ON|READBACK:1|QUALITY:OK'
                assert parse_scan_metadata(packet,'test')['INT_T']==50
                window._result_valid=False;window._refresh_pls()
                assert window._pls_result is None
                report.update(ok=True,model='KM_SNV PLS1',reference_prediction=predicted,
                              interface=True,raw_model_bundled=True,firmware_metadata_parser=True,
                              static_replicates=5,hardware_commands=0)
            finally:
                window._hardware_watchdog.stop();window._acquisition_timer.stop();window._clear_cycle_timers()
                window.close();window.deleteLater();app.processEvents()
    except BaseException:
        report['error']=traceback.format_exc()
    Path(destination).write_text(json.dumps(report,indent=2),encoding='utf-8')
    return 0 if report['ok'] else 1


def run():
    if '--build-self-test' in sys.argv:
        index=sys.argv.index('--build-self-test')
        return packaged_self_test(sys.argv[index+1])
    if sys.platform.startswith('linux'):
        base=Path(os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local/share')))/'SpectrumLabPro'
        os.environ.setdefault('SPECTRUM_LAB_DATA_DIR',str(base))
    from main import main
    main()


if __name__=='__main__':
    sys.exit(run())
