#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
export WINEPREFIX="$PWD/.wine-windows-build"
export WINEDEBUG=-all
export PYTHONUTF8=1
export PYINSTALLER_CONFIG_DIR='C:\pyinstaller-cache'
export QT_QPA_PLATFORM=offscreen
wine 'C:\Python312\python.exe' --version
wine 'C:\Python312\python.exe' -m pip install --no-index --find-links .windows-wheels -r requirements-linux.txt pefile pywin32-ctypes > instalacao-dependencias-windows.log 2>&1
wine 'C:\Python312\python.exe' -m unittest discover -s tests -v > testes-windows.log 2>&1
wine 'C:\Python312\python.exe' -m PyInstaller --noconfirm --onefile --windowed --name SpectrumLabPro_4_17_6_Windows --distpath dist-windows --workpath build-windows --icon assets/app_icon.ico --add-data 'banco_materiais.json;.' --add-data 'assets;assets' main.py > compilacao-windows.log 2>&1
wine 'C:\Python312\python.exe' -m pip freeze > dist-windows/dependencias-compilacao.txt
