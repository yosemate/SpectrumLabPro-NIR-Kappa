"""Build the PLS supervisor with bundled models and an isolated executable check."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    windows=os.name=='nt'
    if not windows and not sys.platform.startswith('linux'):
        raise RuntimeError('Execute com Python Windows ou Linux.')
    root=Path(__file__).resolve().parent
    platform='windows' if windows else 'linux'
    name='SpectrumLabPro_PLS_ACQ1_'+('Windows' if windows else 'Linux')
    build=root/('build-pls-'+platform);dist=root/('dist-pls-'+platform)
    env=dict(os.environ,PYINSTALLER_CONFIG_DIR=str(build/'pyinstaller-cache'),PYTHONDONTWRITEBYTECODE='1')
    args=[sys.executable,'-m','PyInstaller','--noconfirm','--onefile' if windows else '--onedir',
          '--windowed','--name',name,'--distpath',str(dist),'--workpath',str(build),
          '--specpath',str(build),'--hidden-import','acquisition_quality',
          '--hidden-import','experimental_chemometrics','--exclude-module','sklearn']
    for source,target in [('banco_materiais.json','.'),('assets','assets'),('experiments/chemometrics','experiments/chemometrics')]:
        args += ['--add-data',str(root/source)+os.pathsep+target]
    if windows:args += ['--icon',str(root/'assets/app_icon.ico')]
    args += [str(root/'supervisor_entry.py')]
    subprocess.run(args,cwd=root,env=env,check=True)
    executable=dist/(name+'.exe') if windows else dist/name/name
    report=dist/'verificacao-executavel.json'
    subprocess.run([str(executable),'--build-self-test',str(report)],cwd=root,env=env,check=True,timeout=180)
    assert json.loads(report.read_text())['ok'],'Falha ao verificar o executável.'
    if not windows:
        shutil.make_archive(str(dist/name),'gztar',root_dir=dist,base_dir=name)
    print('Executável verificado:',executable)


if __name__=='__main__':
    main()
