import ast
import copy
from pathlib import Path
import sys
from types import SimpleNamespace as NS, MethodType
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from acquisition_quality import parse_scan_metadata
from chemometrics import ChemometricsEngine


def packet(token='token',sequence=1,kind='LIGHT'):
    return (f'SCANMETA:{token}|V:1|FW:PLS_ACQ_1|SEQ:{sequence}|KIND:{kind}|GAIN_CODE:3|INT_T:50'
            '|LED_CODE:2|LED_WAIT_MS:150|TEMP_C:28|UPTIME_MS:2000|CONVERSION_MS:285|TOTAL_MS:445'
            f'|EXPOSURE_LED:{"OFF" if kind=="DARK" else "ON"}|READBACK:1|QUALITY:OK')


class MetadataParserTest(unittest.TestCase):
    def test_light_and_dark_and_unsigned_clock(self):
        self.assertEqual(parse_scan_metadata(packet(),'token')['GAIN_CODE'],3)
        self.assertEqual(parse_scan_metadata(packet(kind='DARK'),'token',dark=True)['KIND'],'DARK')
        self.assertEqual(parse_scan_metadata(packet().replace('UPTIME_MS:2000','UPTIME_MS:4294967295'),'token')['UPTIME_MS'],4294967295)
    def test_wrong_optics_version_or_readback_are_rejected(self):
        for old,new in [('GAIN_CODE:3','GAIN_CODE:2'),('INT_T:50','INT_T:25'),('LED_CODE:2','LED_CODE:3'),
                        ('LED_WAIT_MS:150','LED_WAIT_MS:300'),('READBACK:1','READBACK:0'),('V:1','V:2'),
                        ('QUALITY:OK','QUALITY:FAIL'),('EXPOSURE_LED:ON','EXPOSURE_LED:OFF')]:
            with self.subTest(field=old),self.assertRaises(ValueError):parse_scan_metadata(packet().replace(old,new),'token')
    def test_missing_duplicate_malformed_and_stale_id(self):
        for line in [packet()+'|SEQ:9',packet().replace('|READBACK:1',''),packet().replace('TEMP_C:28','TEMP_C:nan'),packet().replace('TOTAL_MS:445','TOTAL_MS:200'),packet().replace('SEQ:1','SEQ:0')]:
            with self.assertRaises(ValueError):parse_scan_metadata(line,'token')
        with self.assertRaises(ValueError):parse_scan_metadata(packet('old'),'token')
        with self.assertRaises(ValueError):parse_scan_metadata(packet(),'token',dark=True)


# Exercise actual window methods without constructing an app or any connection.
source=Path(__file__).resolve().parents[1]/'main.py'
window=next(n for n in ast.parse(source.read_text()).body if isinstance(n,ast.ClassDef) and n.name=='SpectrumLabMainWindow')
methods={'_on_scan_metadata_received','_complete_batch_read','_on_serial_scan_received'}
namespace={}
exec(compile(ast.fix_missing_locations(ast.Module(body=[n for n in window.body if isinstance(n,ast.FunctionDef) and n.name in methods],type_ignores=[])),str(source),'exec'),namespace)


class AcquisitionBindingTest(unittest.TestCase):
    def fixture(self,required=True,target=1):
        timer=NS(stop=lambda:None,start=lambda value:None)
        w=NS(_scan_metadata_protocol=required,_batch={'token':'token','cmd':'CMD:LER_ESPECTRO','data':None,'scans':[],'metadata':[],'target':target},
             _hardware_watchdog=timer,_acquisition_timer=timer,is_calibrating_white=False,chem_engine=ChemometricsEngine,
             errors=[],logs=[],statuses=[])
        w.log_message=w.logs.append
        def fail(message):w.errors.append(message);w._batch=None
        w._fail_operation=fail
        w._on_serial_status_received=lambda status,**kwargs:w.statuses.append(status)
        for name in methods:setattr(w,name,MethodType(namespace[name],w))
        return w
    def test_metadata_and_adc_are_bound_and_saved_in_order(self):
        w=self.fixture()
        w._on_scan_metadata_received(packet())
        w._on_serial_scan_received('token',[100]*6)
        w._complete_batch_read('token')
        self.assertFalse(w.errors)
        self.assertEqual(w._last_acquisition_metadata[0]['scan_id'],'token')
        self.assertEqual(w._last_raw_payload,[100]*6)
        self.assertEqual(w.statuses,['LEITURA_CONCLUIDA'])
    def test_new_firmware_missing_metadata_is_blocked_but_legacy_still_works(self):
        for required in (True,False):
            w=self.fixture(required)
            w._on_serial_scan_received('token',[100]*6);w._complete_batch_read('token')
            self.assertEqual(bool(w.errors),required)
    def test_stale_duplicate_mismatched_and_repeated_sequence(self):
        w=self.fixture();w._on_scan_metadata_received(packet('stale'))
        self.assertNotIn('scan_metadata',w._batch)
        w._on_scan_metadata_received(packet());w._on_scan_metadata_received(packet())
        self.assertTrue(w.errors)
        w=self.fixture();w._on_scan_metadata_received(packet().replace('INT_T:50','INT_T:25'))
        self.assertTrue(w.errors)
        w=self.fixture(target=2)
        w._on_scan_metadata_received(packet());w._on_serial_scan_received('token',[100]*6);w._complete_batch_read('token')
        w._batch.update(token='next',data=None,scan_metadata=None)
        w._on_scan_metadata_received(packet('next',sequence=1))
        self.assertTrue(w.errors)
    def test_completion_without_new_adc_remains_blocked(self):
        w=self.fixture();w._on_scan_metadata_received(packet());w._complete_batch_read('token')
        self.assertTrue(w.errors)
