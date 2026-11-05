"""Reproducible import of the explicitly mapped local 2026-11-04 experiment.
Lab targets come from user-labelled filenames, not the demonstrative Kappa column.
"""
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

MAPPING = [
 ('AmostraCelulose Branqueada.pdf', 'AM-59970EEA', 'Celulose Branqueada', 0.58, 'assumed', '1'),
 ('AmostraKappa4.27.pdf', 'AM-E135CCEB', 'K4.27', 4.27, 'laboratory', '1'),
 ('AmostraKappa4.50.pdf', 'AM-C46E7D0C', 'K4.50', 4.50, 'laboratory', '1'),
 ('AmostraKappa19.95.pdf', 'AM-02C19AFC', 'K19.95', 19.95, 'laboratory', '1'),
 ('AmostraKappa19.28.pdf', 'AM-88B14C31', 'K19.28', 19.28, 'laboratory', '1'),
 ('AmostraKappa19.28Leitura2.pdf', 'AM-CECEA30A', 'K19.28', 19.28, 'laboratory', '2'),
 ('AmostraKappa19.28Leitura3.pdf', 'AM-1658F269', 'K19.28', 19.28, 'laboratory', '3')]


def main(folder, output):
    folder, output = Path(folder), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    csv_path = folder/'Historico_Ensaios_20261104_134937.csv'
    with csv_path.open(encoding='utf-8-sig', newline='') as f:
        historical = {r['Amostra']: r for r in csv.DictReader(f, delimiter=';')}
    rows, provenance = [], {'files': {}, 'excluded_history_ids': [],
        'reference_warning': 'Kappa targets supplied by user-labelled filenames; independent laboratory certificates not supplied. Celulose Branqueada 0.58 assumed.',
        'positions': 'K19.28 positions 1/2/3 are the same physical sample per user conversation; never independent references.'}
    used = []
    for filename, reading_id, sample_id, kappa, status, position in MAPPING:
        path = folder/filename
        text = subprocess.check_output(['pdftotext', '-layout', str(path), '-'], text=True)
        if reading_id not in text or 'Amostra seca' not in text:
            raise ValueError('Report identity/mode mismatch: '+filename)
        parsed = []
        for nm in (610, 680, 730, 760, 810, 860):
            match = re.search(r'^\s*'+str(nm)+r' nm\s+([\d.,]+)\s+([\d.,]+)\s*$', text, re.M)
            if not match:
                raise ValueError('Missing channel in '+filename)
            parsed.append(float(match[2].replace('.', '').replace(',', '.'))/100)
        hist = historical.get(reading_id)
        if hist:
            exact = [float(hist[f'Ref_{nm}'])/100 for nm in (610,680,730,760,810,860)]
            if any(abs(a-b)>0.000051 for a,b in zip(parsed,exact)):
                raise ValueError('CSV/PDF mismatch: '+reading_id)
            x, source = exact, csv_path.name+'#'+reading_id
            used.append(reading_id)
        else:
            x, source = parsed, filename+'#'+reading_id+' (PDF percent rounded to 0.01)'
        rows.append(dict(sample_id=sample_id,position_id=position,reference_status=status,
                         kappa=kappa,mode='seco',source=source,**{f'r{nm}':v for nm,v in zip((610,680,730,760,810,860),x)}))
        provenance['files'][filename] = hashlib.sha256(path.read_bytes()).hexdigest()
    provenance['files'][csv_path.name] = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    provenance['excluded_history_ids'] = sorted(set(historical)-set(used))
    with (output/'samples.csv').open('w',newline='',encoding='utf-8') as f:
        writer = csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    (output/'provenance.json').write_text(json.dumps(provenance,indent=2,ensure_ascii=False),encoding='utf-8')


if __name__=='__main__':
    main(*sys.argv[1:])
