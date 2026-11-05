#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ "$(uname -s)" != Linux ]]; then
  echo "Execute este arquivo no Linux Mint." >&2
  exit 1
fi
if ! .venv-linux/bin/python -m pip --version >/dev/null 2>&1; then
  python3 -m venv .venv-linux
fi
.venv-linux/bin/python -m pip install --upgrade pip
.venv-linux/bin/python -m pip install -r requirements-linux.txt
.venv-linux/bin/python -m PyInstaller --noconfirm --clean --onedir --windowed \
  --name SpectrumLabPro_4_17_6 \
  --hidden-import acquisition_quality \
  --hidden-import experimental_chemometrics \
  --exclude-module sklearn \
  --add-data 'banco_materiais.json:.' \
  --add-data 'assets:assets' \
  --add-data 'experiments/chemometrics:experiments/chemometrics' supervisor_entry.py
.venv-linux/bin/python -m pip freeze > dist/SpectrumLabPro_4_17_6/dependencias-compilacao.txt
tar -czf dist/SpectrumLabPro_4_17_6_Linux_$(uname -m).tar.gz -C dist SpectrumLabPro_4_17_6
echo "Pronto. Abra dist/SpectrumLabPro_4_17_6/SpectrumLabPro_4_17_6"
echo "Para transportar o programa, leve toda a pasta ou o arquivo .tar.gz."
