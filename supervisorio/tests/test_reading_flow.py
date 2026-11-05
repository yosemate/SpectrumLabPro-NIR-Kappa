import ast
import unittest
import uuid
import time
from pathlib import Path
from types import SimpleNamespace as S

source = Path(__file__).resolve().parents[1] / 'main.py'
root = ast.parse(source.read_text())
window = next(n for n in root.body if isinstance(n, ast.ClassDef) and n.name == 'SpectrumLabMainWindow')
methods = {'_handle_auto_cycle_fsm', 'start_simple_auto_cycle', '_ready_for_reread', 'start_retained_sample_cycle'}
namespace = {'uuid': uuid, 'time': time}
module = ast.Module(body=[n for n in window.body if isinstance(n, ast.FunctionDef) and n.name in methods], type_ignores=[])
exec(compile(ast.fix_missing_locations(module), str(source), 'exec'), namespace)

class ReadingFlowTest(unittest.TestCase):
    def fixture(self, valid=True):
        events = []
        widget = S(setValue=lambda value: None, setText=lambda text: None)
        w = S(fsm_state='AUTO_LENDO_ESPECTRO', _last_raw_payload=[10]*6, _result_valid=False,
              cycle_progress=widget, lbl_cycle_status=widget, auto_cycle_active=True,
              modo_repetibilidade=False, is_calibrating_white=False, _pending_routine='AUTO')
        w._current_sample_id = 'AM-ORIGINAL'
        w._retained_sample_id = None
        w.equipment = S(drawer_closed=True, closed=True, open=False, housing_closed=True,
                        carriage_retracted=True, carriage_advanced=False, received_at=time.monotonic())
        def process(values):
            events.append('result')
            w._result_valid = valid
            if not valid:
                w.fsm_state = 'FALHA'
        w.process_raw_spectral_data = process
        w._hide_radiation_alert = lambda: events.append('hide_alert')
        w.responsive_shell = S(select_page=lambda page: events.append('show_results'))
        w.log_message = lambda text: None
        w.send_serial_command = lambda command: events.append(command)
        w._show_drawer_alert = lambda *args: None
        w._show_radiation_alert = lambda *args: None
        w._enable_controls = lambda: events.append('enable_controls')
        w._disable_controls = lambda: None
        w._clear_cycle_timers = lambda: None
        w.check_hardware_connected = lambda: True
        w._ready_for_scan = lambda: w.fsm_state == 'IDLE'
        w._ready_for_reread = lambda: namespace['_ready_for_reread'](w)
        return w, events

    def retained_fixture(self):
        w, events = self.fixture()
        handler = namespace['_handle_auto_cycle_fsm']
        handler(w, 'LEITURA_CONCLUIDA')
        handler(w, 'SENSOR_RECUADO')
        events.clear()
        return w, events

    def test_reread_keeps_identity_and_never_opens_chamber(self):
        w, events = self.retained_fixture()
        w.input_sample_id = S(text=lambda: 'OUTRA-AMOSTRA')
        namespace['start_retained_sample_cycle'](w)
        self.assertEqual(w._current_sample_id, 'AM-ORIGINAL')
        self.assertEqual(w.fsm_state, 'AUTO_AVANCANDO_SENSOR')
        self.assertFalse(w._result_valid)
        handler = namespace['_handle_auto_cycle_fsm']
        handler(w, 'SENSOR_AVANCADO')
        w._last_raw_payload = [20]*6
        handler(w, 'LEITURA_CONCLUIDA')
        handler(w, 'SENSOR_RECUADO')
        self.assertEqual([e for e in events if e.startswith('CMD:')],
                         ['CMD:AVANCAR_SENSOR', 'CMD:LER_ESPECTRO', 'CMD:RECUAR_SENSOR'])
        self.assertEqual(events.count('result'), 1)
        self.assertEqual(w.fsm_state, 'IDLE')
        self.assertEqual(w._retained_sample_id, 'AM-ORIGINAL')
        self.assertTrue(w._ready_for_reread())

    def test_reread_rejects_invalid_positions_or_stale_telemetry(self):
        for field, value in [('drawer_closed', False), ('closed', False), ('open', True),
                             ('housing_closed', False), ('carriage_retracted', False),
                             ('carriage_advanced', True), ('received_at', time.monotonic()-10)]:
            with self.subTest(field=field):
                w, events = self.retained_fixture()
                setattr(w.equipment, field, value)
                namespace['start_retained_sample_cycle'](w)
                self.assertEqual(events, [])

    def test_reread_rejects_missing_sample_or_invalid_calibration(self):
        w, events = self.retained_fixture()
        w._retained_sample_id = None
        namespace['start_retained_sample_cycle'](w)
        self.assertEqual(events, [])
        w, events = self.retained_fixture()
        w._ready_for_scan = lambda: False
        namespace['start_retained_sample_cycle'](w)
        self.assertEqual(events, [])

    def test_result_before_retraction_and_no_ejection(self):
        w, events = self.fixture()
        handler = namespace['_handle_auto_cycle_fsm']
        handler(w, 'LEITURA_CONCLUIDA')
        self.assertLess(events.index('result'), events.index('CMD:RECUAR_SENSOR'))
        self.assertIn('show_results', events)
        self.assertEqual(w.fsm_state, 'AUTO_RECUANDO_SENSOR')
        handler(w, 'SENSOR_RECUADO')
        self.assertEqual(w.fsm_state, 'IDLE')
        self.assertFalse(w.auto_cycle_active)
        self.assertIsNone(w._pending_routine)
        self.assertTrue(w._result_valid)
        self.assertEqual([e for e in events if e.startswith('CMD:')], ['CMD:RECUAR_SENSOR'])
        handler(w, 'LEITURA_CONCLUIDA')
        self.assertEqual(events.count('result'), 1)
        namespace['start_simple_auto_cycle'](w)
        self.assertEqual(events[-1], 'CMD:ABRIR_GAVETA')
        self.assertEqual(w.fsm_state, 'PREP_ABRINDO_GAVETA')
        self.assertFalse(w._result_valid)

    def test_rejected_result_does_not_continue_cycle(self):
        w, events = self.fixture(valid=False)
        namespace['_handle_auto_cycle_fsm'](w, 'LEITURA_CONCLUIDA')
        self.assertEqual(w.fsm_state, 'FALHA')
        self.assertEqual(events, ['result'])

    def test_next_cycle_waits_for_sensor_to_retract(self):
        w, events = self.fixture()
        namespace['_handle_auto_cycle_fsm'](w, 'LEITURA_CONCLUIDA')
        namespace['start_simple_auto_cycle'](w)
        self.assertNotIn('CMD:ABRIR_GAVETA', events)

if __name__ == '__main__':
    unittest.main()
