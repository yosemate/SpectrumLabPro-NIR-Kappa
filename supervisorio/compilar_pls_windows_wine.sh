#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
export WINEPREFIX="$PWD/.wine-windows-build"
export WINEDEBUG=-all
export PYTHONUTF8=1
exec wine 'C:\Python312\python.exe' compilar_pls.py
