"""Optional PLS1 experiment. Input: calibrated fractions, never raw ADC or percent.
No optical calibration, hardware writes, automatic model selection or industrial claims.
"""
import csv
import hashlib
import json
from pathlib import Path
import numpy as np

CHANNELS = [610, 680, 730, 760, 810, 860]
LIMITATION = 'EXPERIMENTAL — sem validação industrial; não substitui Kappa laboratorial.'


def spectra(values):
    x = np.asarray(values, dtype=float)
    if x.ndim != 2 or x.shape[1] != 6 or not len(x) or not np.isfinite(x).all():
        raise ValueError('São necessários espectros finitos com seis canais.')
    return x


def snv(values):
    x = spectra(values)
    sd = x.std(axis=1, ddof=1, keepdims=True)
    if np.any(sd <= 1e-12):
        raise ValueError('SNV indefinido para espectro constante.')
    return (x - x.mean(axis=1, keepdims=True)) / sd


def km_snv(values, eps=0.011):
    """Kubelka-Munk K/S = (1-R)^2/(2R) with damped SNV floor eps for flat/bright spectra."""
    x = spectra(values)
    if np.any(x <= 0):
        raise ValueError('Reflectâncias devem ser positivas para Kubelka-Munk.')
    r_clamped = np.minimum(x, 1.0)
    ks = (1.0 - r_clamped) ** 2 / (2.0 * x)
    eps_val = float(eps) if eps is not None else 0.011
    if not np.isfinite(eps_val) or eps_val <= 0:
        raise ValueError('Parâmetro eps inválido para KM-SNV.')
    sd = np.sqrt(ks.var(axis=1, ddof=1, keepdims=True) + eps_val ** 2)
    return (ks - ks.mean(axis=1, keepdims=True)) / sd


def preprocess(values, method, reference=None):
    x = spectra(values)
    if method == 'raw':
        return x.copy()
    if method == 'snv':
        return snv(x)
    if method == 'km_snv':
        return km_snv(x, reference if isinstance(reference, (int, float)) else 0.011)
    if method != 'msc' or reference is None:
        raise ValueError('MSC exige referência de treinamento; método desconhecido.')
    ref = spectra([reference])[0]
    centered = ref - ref.mean()
    denom = centered @ centered
    if denom <= 1e-12:
        raise ValueError('Referência MSC constante.')
    slopes = (x - x.mean(axis=1, keepdims=True)) @ centered / denom
    if np.any(slopes <= 1e-10):
        raise ValueError('Inclinação MSC nula ou negativa.')
    offsets = x.mean(axis=1) - slopes * ref.mean()
    return (x - offsets[:, None]) / slopes[:, None]


def load_csv(path):
    """Explicit long table: physical sample identity and reference provenance required."""
    with open(path, encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    required = {'sample_id', 'position_id', 'reference_status', 'kappa', 'mode', 'source',
                *(f'r{w}' for w in CHANNELS)}
    if not rows or not required.issubset(rows[0]):
        raise ValueError('CSV deve conter: ' + ', '.join(sorted(required)))
    for row in rows:
        row['x'] = [float(row[f'r{w}']) for w in CHANNELS]
        row['kappa'] = float(row['kappa'])
    validate_rows(rows)
    return rows


def validate_rows(rows):
    if not rows:
        raise ValueError('Nenhuma amostra.')
    x = spectra([r['x'] for r in rows])
    if np.any(x <= 0):
        raise ValueError('Usar reflectâncias relativas positivas em fração.')
    by_sample = {}
    for r in rows:
        if not r['sample_id'].strip() or not r['position_id'].strip() or not r['source'].strip():
            raise ValueError('Identidade física, posição e fonte obrigatórias.')
        if r['reference_status'] not in ('laboratory', 'assumed'):
            raise ValueError('Referência deve ser laboratory ou assumed.')
        if r['mode'] not in ('seco', 'umido') or not np.isfinite(r['kappa']) or r['kappa'] < 0:
            raise ValueError('Modo ou Kappa inválido.')
        if 'eldorado' in r['sample_id'].casefold() and r['reference_status'] != 'assumed':
            raise ValueError('Eldorado Kappa 0.58 deve permanecer presumido (assumed).')
        meta = (r['kappa'], r['mode'], r['reference_status'])
        if r['sample_id'] in by_sample and by_sample[r['sample_id']] != meta:
            raise ValueError('Referências conflitantes para a mesma amostra física.')
        by_sample[r['sample_id']] = meta
    if len({r['mode'] for r in rows}) != 1:
        raise ValueError('Não misturar modos ópticos no mesmo modelo.')


def representatives(rows, method, reference):
    """Equal sample weight; average scans within position, then positions per sample."""
    ids = sorted({r['sample_id'] for r in rows})
    means, targets = [], []
    for sid in ids:
        group = [r for r in rows if r['sample_id'] == sid]
        positions = sorted({r['position_id'] for r in group})
        means.append(np.mean([preprocess([r['x'] for r in group if r['position_id'] == p],
                                         method, reference).mean(axis=0) for p in positions], axis=0))
        targets.append(group[0]['kappa'])
    return np.array(means), np.array(targets), ids


def _pls1_fit_numpy(x, y):
    xc = x - x.mean(axis=0)
    yc = y - y.mean()
    w = xc.T @ yc
    w = w / np.linalg.norm(w)
    t = xc @ w
    coef = w * ((yc @ t) / (t @ t))
    offset = float(y.mean() - x.mean(axis=0) @ coef)
    return coef, offset


def fit_model(rows, method='raw'):
    validate_rows(rows)
    if any(r['reference_status'] != 'laboratory' for r in rows):
        raise ValueError('Valores presumidos são excluídos do treinamento.')
    raw, y, ids = representatives(rows, 'raw', None)
    if len(ids) < 3 or np.ptp(y) <= 1e-12:
        raise ValueError('PLS exige ao menos três amostras físicas com Kappa variável.')
    reference = raw.mean(axis=0).tolist() if method == 'msc' else None
    x, y, _ = representatives(rows, method, reference)
    if np.linalg.matrix_rank(x - x.mean(axis=0)) < 1:
        raise ValueError('Espectros sem variação para PLS.')
    # Fixed a priori: one latent component. No tuning on outer holdout results.
    try:
        from sklearn.cross_decomposition import PLSRegression
        model = PLSRegression(n_components=1, scale=False, max_iter=1000, tol=1e-10).fit(x, y)
        coef = np.asarray(model.coef_).reshape(-1)
        offset = float(model.predict(np.zeros((1, 6))).ravel()[0])
    except ImportError:
        coef, offset = _pls1_fit_numpy(x, y)
    return {'schema': 1, 'method': method, 'components': 1, 'channels': CHANNELS,
            'units': 'relative_fraction', 'mode': rows[0]['mode'], 'reference': reference,
            'coef': coef.tolist(), 'offset': offset, 'sample_ids': ids,
            'kappa_range': [float(y.min()), float(y.max())], 'limitation': LIMITATION}


def predict(model, values, mode):
    if (model.get('schema') != 1 or model.get('channels') != CHANNELS
            or model.get('units') != 'relative_fraction' or model.get('mode') != mode
            or model.get('components') != 1):
        raise ValueError('Modelo incompatível com modo, unidade ou canais.')
    coef = np.asarray(model['coef'], dtype=float)
    if coef.shape != (6,) or not np.isfinite(coef).all() or not np.isfinite(model['offset']):
        raise ValueError('Coeficientes inválidos.')
    raw = spectra(values)
    if np.any(raw <= 0):
        raise ValueError('Reflectâncias devem ser positivas.')
    y = preprocess(raw, model['method'], model['reference']) @ coef + model['offset']
    if not np.isfinite(y).all():
        raise ValueError('Previsão não finita.')
    return y  # Do not clip negative or extrapolated predictions to hide model failures.


def prediction_repeatability(model, calibrated_scans, mode):
    """Static replicate dispersion, never an analytical uncertainty estimate."""
    values=predict(model, calibrated_scans, mode)
    if len(values)<2:
        return None
    return {"n_acquisitions":len(values), "predictions":values.tolist(),
            "mean":float(values.mean()), "sample_sd":float(values.std(ddof=1)),
            "range":float(np.ptp(values)), "analytical_uncertainty":False}


def metrics(y, predicted):
    y, p = np.asarray(y), np.asarray(predicted)
    error = p - y
    total = np.sum((y-y.mean())**2)
    return {'n_samples': len(y), 'rmse': float(np.sqrt(np.mean(error**2))),
            'mae': float(np.mean(np.abs(error))), 'bias': float(error.mean()),
            'r2': float(1-np.sum(error**2)/total) if total > 0 else None}


def evaluate(rows):
    validate_rows(rows)
    lab = [r for r in rows if r['reference_status'] == 'laboratory']
    ids = sorted({r['sample_id'] for r in lab})
    if len(ids) < 4:
        raise ValueError('Validação agrupada exige ao menos quatro amostras laboratoriais físicas.')
    result = {'validation': 'leave-one-physical-sample-out; 1 component fixed a priori',
              'limitation': LIMITATION, 'excluded_assumed_samples': sorted({r['sample_id'] for r in rows if r['reference_status']=='assumed'}),
              'methods': {}}
    for method in ('raw', 'snv', 'msc'):
        folds, truth, predictions, baseline = [], [], [], []
        try:
            for sid in ids:
                train = [r for r in lab if r['sample_id'] != sid]
                test = [r for r in lab if r['sample_id'] == sid]
                model = fit_model(train, method)
                per_position = [float(predict(model, [r['x'] for r in test if r['position_id']==pos], test[0]['mode']).mean())
                                for pos in sorted({r['position_id'] for r in test})]
                prediction = float(np.mean(per_position))
                _, train_y, _ = representatives(train, 'raw', None)
                truth.append(test[0]['kappa']); predictions.append(prediction); baseline.append(float(train_y.mean()))
                folds.append({'test_sample': sid, 'train_samples': model['sample_ids'],
                              'actual': truth[-1], 'predicted': prediction,
                              'position_predictions': per_position,
                              'position_range': float(np.ptp(per_position))})
            result['methods'][method] = {'metrics': metrics(truth, predictions), 'folds': folds,
                                         'mean_baseline_metrics': metrics(truth, baseline)}
        except ValueError as err:
            result['methods'][method] = {'unavailable': str(err)}
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description=LIMITATION)
    parser.add_argument('csv'); parser.add_argument('--output', required=True)
    parser.add_argument('--method', choices=['raw', 'snv', 'msc'], default='raw')
    args = parser.parse_args()
    rows = load_csv(args.csv)
    report = evaluate(rows)
    chosen = report['methods'][args.method]
    if 'unavailable' in chosen:
        raise ValueError(chosen['unavailable'])
    model = fit_model([r for r in rows if r['reference_status']=='laboratory'], args.method)
    model['validation'] = report
    model['source_sha256'] = hashlib.sha256(Path(args.csv).read_bytes()).hexdigest()
    Path(args.output).write_text(json.dumps(model, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    print(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
