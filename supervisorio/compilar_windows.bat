@echo off
setlocal
cd /d "%~dp0"
py -3.12 -m venv .venv-windows
if errorlevel 1 exit /b 1
.venv-windows\Scripts\python.exe -m pip install -r requirements-linux.txt
if errorlevel 1 exit /b 1
.venv-windows\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --name SpectrumLabPro_4_17_6_Windows --distpath dist-windows --workpath build-windows --icon assets\app_icon.ico --add-data "banco_materiais.json;." --add-data "assets;assets" main.py
if errorlevel 1 exit /b 1
.venv-windows\Scripts\python.exe -m pip freeze > dist-windows\dependencias-compilacao.txt
echo Pronto: dist-windows\SpectrumLabPro_4_17_6_Windows.exe
endlocal
