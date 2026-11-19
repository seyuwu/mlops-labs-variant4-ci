from pathlib import Path
import json
import joblib
import pandas as pd
from sklearn.metrics import f1_score
from common import FEATURES, TARGET, QUALITY_THRESHOLD
from drift import psi

model = joblib.load('models/model.joblib')
reference = pd.read_csv('data/processed/train.csv')
test = pd.read_csv('data/processed/test.csv')
shift = pd.read_csv('data/shifted.csv')
baseline_f1 = f1_score(test[TARGET], model.predict(test[FEATURES]), zero_division=0)
shifted_f1 = f1_score(shift[TARGET], model.predict(shift[FEATURES]), zero_division=0)
metrics = {'f1': float(baseline_f1), 'threshold': QUALITY_THRESHOLD, 'samples': len(test)}
shifted_metrics = {'f1': float(shifted_f1), 'threshold': QUALITY_THRESHOLD, 'samples': len(shift)}
drift = {'feature': 'attendance', 'same_sample_psi': psi(reference['attendance'], reference['attendance']),
         'test_psi': psi(reference['attendance'], test['attendance']),
         'shifted_psi': psi(reference['attendance'], shift['attendance'])}
Path('reports').mkdir(exist_ok=True)
Path('metrics.json').write_text(json.dumps(metrics, indent=2), encoding='utf-8')
Path('metrics_shifted.json').write_text(json.dumps(shifted_metrics, indent=2), encoding='utf-8')
Path('reports/drift.json').write_text(json.dumps(drift, indent=2), encoding='utf-8')
print('normal:', metrics)
print('shifted:', shifted_metrics)
print('drift:', drift)
