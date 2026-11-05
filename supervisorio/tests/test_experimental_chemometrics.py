"""Numerical, leakage, identity, and persistence contracts for optional PLS."""
import copy
import json
import pathlib
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import numpy as np
import experimental_chemometrics as ec
try:
    from sklearn.cross_decomposition import PLSRegression
except ImportError:
    PLSRegression = None
from chemometrics import ChemometricsEngine


def dataset():
    rows=[]
    for i in range(5):
        for position in ('1','2'):
            x=np.array([.2,.3,.4,.5,.6,.7])+i*np.array([.03,.02,.01,.04,.01,.02])
            rows.append(dict(sample_id=str(i),position_id=position,reference_status='laboratory',
                             kappa=3.+i*4,mode='seco',source='synthetic test',x=x.tolist()))
    return rows


class NumericalTests(unittest.TestCase):
    def test_true_snv_sample_std_and_affine_invariance(self):
        x=np.array([[.2,.4,.3,.7,.8,.6]])
        z=ec.snv(x)
        np.testing.assert_allclose(z.mean(axis=1),0,atol=1e-14)
        np.testing.assert_allclose(z.std(axis=1,ddof=1),1)
        np.testing.assert_allclose(z,ec.snv(3*x+2),atol=1e-14)
        np.testing.assert_allclose(ChemometricsEngine.normalize_snv(x[0]),z[0])
        self.assertAlmostEqual(sum(ChemometricsEngine.normalize_sum(x[0])),1)
    def test_msc_known_affine_scatter(self):
        ref=np.array([.2,.4,.3,.7,.8,.6])
        x=np.array([ref,3*ref+.2,.7*ref+.3])
        np.testing.assert_allclose(ec.preprocess(x,'msc',ref),np.tile(ref,(3,1)),atol=1e-14)
    def test_invalid_and_degenerate_spectra(self):
        for x in ([[1]*5],[[np.nan]*6],[[np.inf]*6]):
            with self.assertRaises(ValueError):ec.snv(x)
        with self.assertRaises(ValueError):ec.snv([[1]*6])
        with self.assertRaises(ValueError):ec.preprocess([[1,2,3,4,5,6]],'msc',[1]*6)
        with self.assertRaises(ValueError):ec.preprocess([[6,5,4,3,2,1]],'msc',[1,2,3,4,5,6])
    def test_json_predictions_equal_sklearn(self):
        rows=dataset()
        for method in ('raw','snv','msc'):
            model=ec.fit_model(rows,method)
            x,y,_=ec.representatives(rows,method,model['reference'])
            actual=ec.predict(json.loads(json.dumps(model)),[r['x'] for r in rows],'seco')
            if PLSRegression is not None:
                expected=PLSRegression(n_components=1,scale=False,max_iter=1000,tol=1e-10).fit(x,y)
                expected_pred=expected.predict(ec.preprocess([r['x'] for r in rows],method,model['reference'])).ravel()
            else:
                c,o=ec._pls1_fit_numpy(x,y)
                expected_pred=ec.preprocess([r['x'] for r in rows],method,model['reference'])@c+o
            np.testing.assert_allclose(actual,expected_pred,atol=1e-9)
    def test_groups_never_overlap_and_metrics_use_samples(self):
        report=ec.evaluate(dataset())
        for method in report['methods'].values():
            self.assertEqual(method['metrics']['n_samples'],5)
            for fold in method['folds']:
                self.assertNotIn(fold['test_sample'],fold['train_samples'])
                self.assertEqual(len(fold['position_predictions']),2)
    def test_msc_reference_is_training_only(self):
        captured=[]
        real=ec.fit_model
        def spy(rows,method):
            model=real(rows,method)
            if method=='msc':
                raw,_,_=ec.representatives(rows,'raw',None)
                np.testing.assert_allclose(model['reference'],raw.mean(axis=0))
                captured.append(model)
            return model
        with patch.object(ec,'fit_model',side_effect=spy):ec.evaluate(dataset())
        self.assertEqual(len(captured),5)
    def test_assumed_branqueada_cannot_enter_training_or_metrics(self):
        rows=dataset()
        eld=copy.deepcopy(rows[0]);eld.update(sample_id='Celulose Branqueada',kappa=.58,reference_status='assumed')
        with self.assertRaises(ValueError):ec.fit_model(rows+[eld])
        report=ec.evaluate(rows+[eld])
        self.assertEqual(report['excluded_assumed_samples'],['Celulose Branqueada'])
        self.assertEqual(report['methods']['raw']['metrics']['n_samples'],5)
        eld['reference_status']='laboratory'
        with self.assertRaises(ValueError):ec.evaluate(rows+[eld])
    def test_conflicts_and_too_few_samples(self):
        rows=dataset();bad=copy.deepcopy(rows[0]);bad['kappa']=999
        with self.assertRaises(ValueError):ec.evaluate(rows+[bad])
        with self.assertRaises(ValueError):ec.evaluate(rows[:6])
    def test_mode_and_channel_mismatch_block_prediction(self):
        model=ec.fit_model(dataset())
        with self.assertRaises(ValueError):ec.predict(model,[dataset()[0]['x']],'umido')
        model['channels']=list(reversed(ec.CHANNELS))
        with self.assertRaises(ValueError):ec.predict(model,[dataset()[0]['x']],'seco')
    def test_replicates_do_not_overweight_sample(self):
        rows=dataset()
        a=ec.fit_model(rows,'msc')
        b=ec.fit_model(rows+[copy.deepcopy(rows[0])]*30,'msc')
        np.testing.assert_allclose(a['coef'],b['coef'],atol=1e-8)
        np.testing.assert_allclose(a['reference'],b['reference'])
    def test_static_prediction_dispersion_is_not_analytical_uncertainty(self):
        rows=dataset();model=ec.fit_model(rows,'raw')
        x=[rows[0]['x'],rows[2]['x'],rows[4]['x']]
        result=ec.prediction_repeatability(model,x,'seco')
        expected=ec.predict(model,x,'seco')
        self.assertAlmostEqual(result['sample_sd'],float(np.std(expected,ddof=1)))
        self.assertFalse(result['analytical_uncertainty'])
        self.assertEqual(result['n_acquisitions'],3)
        self.assertIsNone(ec.prediction_repeatability(model,x[:1],'seco'))

    def test_actual_data_four_groups_and_three_positions(self):
        path=pathlib.Path(__file__).resolve().parents[1]/'experiments/chemometrics/samples.csv'
        if not path.exists():self.skipTest('Real experiment data not copied')
        rows=ec.load_csv(path)
        self.assertEqual(len(rows),7)
        self.assertEqual(len([r for r in rows if r['sample_id']=='K19.28']),3)
        report=ec.evaluate(rows)
        self.assertEqual(report['methods']['snv']['metrics']['n_samples'],4)
        self.assertIn('unavailable',report['methods']['msc'])
        self.assertAlmostEqual(report['methods']['snv']['metrics']['rmse'],2.1540063128,places=7)


if __name__=='__main__':unittest.main()
