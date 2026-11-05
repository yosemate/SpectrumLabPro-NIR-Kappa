"""Run with Windows Python: windows_executable_smoke.py path/to/application.exe."""
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def main():
    exe = Path(sys.argv[1]).resolve()
    folder = Path(tempfile.mkdtemp(prefix='SpectrumSmoke_'))
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen',
               SPECTRUM_LAB_DATA_DIR=str(folder / 'data'), MPLCONFIGDIR=str(folder / 'mpl'))
    started = time.time()
    proc = subprocess.Popen([str(exe)], env=env)
    try:
        deadline = time.monotonic() + 60
        ready = False
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise RuntimeError(f'Executable exited early: {proc.returncode}')
            crashes = [p for p in Path(tempfile.gettempdir()).glob('_MEI*/crash.log')
                       if p.stat().st_mtime >= started]
            if crashes:
                raise RuntimeError(crashes[0].read_text(encoding='utf-8'))
            database = folder / 'data' / 'alarmes.db'
            if database.exists():
                try:
                    with sqlite3.connect(database) as db:
                        db.execute('select count(*) from alarm_occurrences').fetchone()
                    ready = True
                    break
                except sqlite3.Error:
                    pass
            time.sleep(.25)
        if not ready:
            raise RuntimeError('Interface did not initialize within 60 seconds.')
        time.sleep(3)
        assert proc.poll() is None, 'Application exited after initializing.'
        crashes = [p for p in Path(tempfile.gettempdir()).glob('_MEI*/crash.log')
                   if p.stat().st_mtime >= started]
        assert not crashes, 'Interface error recorded in crash.log.'
        print('PASS: Windows EXE loaded resources, initialized interface and alarm database without crash.log.')
    finally:
        subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == '__main__':
    main()
